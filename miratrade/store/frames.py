"""DataFrames in and out of the market database, without either side having to know the other.

The rules are in one place so a round trip is lossless: dates become ISO text on the way in and
timestamps again on the way out, booleans become 0/1, and a table whose rows belong to a document
has that document's rows replaced rather than appended, so re-parsing a filing cannot leave two
slightly different copies of it behind.
"""
from __future__ import annotations

import sqlite3
from typing import Iterable

import pandas as pd

from miratrade.store.db import now
from miratrade.store.schema import BY_DOCUMENT, TABLES

# Columns that hold a date, per table, so a read gives back the dtypes the rest of the code expects.
DATE_COLUMNS: dict[str, tuple[str, ...]] = {
    "insiders": ("filing_date", "trade_date"),
    "ownership": ("filing_date",),
    "shares_outstanding": ("filed",),
    "prices": ("date",),
    "short_volume": ("date",),
    "option_flow": ("date", "expiry"),
    "congress_trades": ("filing_date", "trade_date"),
    "events": ("signal_date",),
    "earnings": ("report_date", "fiscal_end"),
    "coverage": ("day",),
}


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def _iso(value):
    """A date as ``YYYY-MM-DD``; anything unparseable becomes NULL rather than a wrong date."""
    if value is None or value != value:                      # None or NaN/NaT
        return None
    stamp = pd.Timestamp(value)
    return None if pd.isna(stamp) else stamp.strftime("%Y-%m-%d")


def to_rows(df: pd.DataFrame, table: str, conn: sqlite3.Connection) -> tuple[list[str], list[tuple]]:
    """``df`` as plain tuples for ``table``, keeping only columns the table actually has."""
    known = columns(conn, table)
    dates = DATE_COLUMNS.get(table, ())
    used = [c for c in known if c in df.columns]
    out = df[used].copy()
    # Price bars keep the day in the index rather than in a column. The index may be named "date" or
    # not named at all, depending on who built the frame, so a date-like index is used either way —
    # dropping it silently is how a whole download turns into rows with no day.
    index_name = df.index.name if df.index.name in known else None
    if index_name is None and isinstance(df.index, pd.DatetimeIndex):
        index_name = next((c for c in dates if c in known and c not in used), None)
    if index_name and index_name not in used:
        out = df.copy()
        out.index.name = index_name
        out = out.reset_index()
        used = [c for c in known if c in out.columns]
        out = out[used]
    for col in used:
        if col in dates:
            out[col] = out[col].map(_iso)
        elif out[col].dtype == bool:
            out[col] = out[col].astype(int)
    return used, [tuple(None if v != v else v for v in row)       # NaN → NULL
                  for row in out.itertuples(index=False, name=None)]


def write(conn: sqlite3.Connection, table: str, df: pd.DataFrame | None) -> int:
    """Put ``df`` into ``table`` and return how many rows were written.

    A table keyed on a primary key has its matching rows replaced. A table whose rows belong to a
    document (``insiders``, ``ownership``, ``congress_trades``) first has the rows of the documents
    appearing in ``df`` deleted, because those rows have no key of their own.
    """
    if table not in TABLES:
        raise KeyError(f"no table called {table!r} in the market database")
    if df is None or not len(df):
        return 0
    if table in BY_DOCUMENT:
        # These tables have no key of their own, so an identical row twice would simply stay twice.
        # Two lines of a filing that agree on owner, date, code, size and price are the same
        # transaction reported twice, never two real ones.
        df = df.drop_duplicates()
    used, rows = to_rows(df, table, conn)
    if not used:
        raise ValueError(f"none of {list(df.columns)} match the columns of {table}")
    with conn:
        for key in BY_DOCUMENT.get(table, ()):
            if key in used:
                ids = sorted({r[used.index(key)] for r in rows})
                for chunk in _chunks(ids, 500):                   # SQLite caps parameters per query
                    marks = ",".join("?" * len(chunk))
                    conn.execute(f"DELETE FROM {table} WHERE {key} IN ({marks})", chunk)
        marks = ",".join("?" * len(used))
        conn.executemany(f"INSERT OR REPLACE INTO {table} ({', '.join(used)}) VALUES ({marks})", rows)
    return len(rows)


def read(conn: sqlite3.Connection, table: str, where: str = "", params: Iterable = (),
         order: str = "") -> pd.DataFrame:
    """``table`` as a DataFrame, with its date columns parsed and its flags left as text.

    ``where`` is plain SQL without the keyword, so a caller filters in the database instead of
    loading everything: ``read(conn, "insiders", "ticker = ? AND filing_date >= ?", ("PFE", "2026-01-01"))``.
    """
    sql = f"SELECT * FROM {table}"                              # table names come from our own schema
    if where:
        sql += f" WHERE {where}"
    if order:
        sql += f" ORDER BY {order}"
    df = pd.read_sql_query(sql, conn, params=list(params))
    for col in DATE_COLUMNS.get(table, ()):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def prices(conn: sqlite3.Connection, tickers: Iterable[str] | None = None, start=None,
           end=None) -> dict[str, pd.DataFrame]:
    """Daily bars per ticker, shaped the way the rest of the code passes prices around: a dict of
    ``DataFrame`` indexed by date with open/high/low/close/volume."""
    where, params = [], []
    if tickers is not None:
        names = sorted({t.upper() for t in tickers})
        if not names:
            return {}
        where.append(f"ticker IN ({','.join('?' * len(names))})")
        params += names
    for column, value, op in (("date", start, ">="), ("date", end, "<=")):
        if value is not None:
            where.append(f"{column} {op} ?")
            params.append(_iso(value))
    df = read(conn, "prices", " AND ".join(where), params, order="ticker, date")
    out = {}
    for ticker, rows in df.groupby("ticker", sort=True):
        bars = rows.set_index("date")[["open", "high", "low", "close", "volume"]]
        bars.index.name = "date"
        out[str(ticker)] = bars
    return out


# --------------------------------------------------------------------------- coverage

def covered(conn: sqlite3.Connection, source: str, scope: str = "") -> set[str]:
    """The ISO days already downloaded for a source, so a run can skip them."""
    rows = conn.execute("SELECT day FROM coverage WHERE source=? AND scope=?", (source, scope))
    return {r["day"] for r in rows}


def mark_covered(conn: sqlite3.Connection, source: str, days, rows: int = 0, scope: str = "") -> None:
    """Record that a source was asked about these days. Nothing found is still an answer worth
    remembering: without it every quiet day would be downloaded again on the next run."""
    stamp = now()
    values = [(source, scope, _iso(d), int(rows), stamp) for d in days if _iso(d)]
    if not values:
        return
    with conn:
        conn.executemany(
            "INSERT INTO coverage (source, scope, day, rows, fetched_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(source, scope, day) DO UPDATE SET rows=excluded.rows, "
            "fetched_at=excluded.fetched_at", values)


def gaps(conn: sqlite3.Connection, source: str, days: Iterable, scope: str = "") -> list:
    """The days of ``days`` this source has never been asked about, in order."""
    have = covered(conn, source, scope)
    return [d for d in days if _iso(d) not in have]


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]
