"""What the Scanner screen shows: every row of financial data collected, narrowed by filters.

The Scanner is the plain view of the data. It applies no strategy, suggests no contract and judges
nothing — Signals does that with the events and their evidence, and Reports does it with five years
of history. Here a row is a row as it was filed, and the only thing that happens to it is filtering.

Filtering happens in SQL, not in pandas. With three quarters of a million price bars in the database
that is the difference between a screen that answers while you type and one that reloads a file every
time you change a dropdown. Every source below therefore declares which filters it understands, and
:func:`query` turns a :class:`Filters` into one statement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, NamedTuple

import pandas as pd

EDGAR_FILING = "https://www.sec.gov/Archives/edgar/data/{cik}/{plain}/{accession}-index.htm"


class Column(NamedTuple):
    """A column as the table shows it: the SQL that produces it and its English heading."""
    sql: str
    label: str
    kind: str = "text"          # text, date, number, money or link — how the screen formats it


@dataclass(frozen=True)
class Source:
    """One kind of collected data the Scanner can list."""
    key: str
    label: str
    table: str
    date_column: str
    columns: tuple[Column, ...]
    ticker_column: str | None = "ticker"
    amount_column: str | None = None
    filters: tuple[str, ...] = ()
    searchable: tuple[str, ...] = ()      # columns a free-text search looks in
    join: str = ""
    note: str = ""
    order: str = ""

    @property
    def default_order(self) -> str:
        return self.order or f"{self.date_column} DESC"


# Insider purchases and sales as filed on Form 4. `code` P is an open-market purchase and S a sale;
# the others are awards and exercises, which is why the screen can filter on it.
INSIDERS = Source(
    key="insiders", label="Insiders (Form 4)", table="insiders", date_column="filing_date",
    amount_column="value", searchable=("ticker", "owner", "issuer", "title"),
    filters=("dates", "ticker", "text", "code", "amount", "role", "plan", "new_position"),
    note="As filed, including the filers' own errors. Code P is an open-market purchase; A, M, F and "
         "G are awards, exercises, tax withholding and gifts.",
    columns=(
        Column("filing_date", "Filed", "date"),
        Column("trade_date", "Traded", "date"),
        Column("ticker", "Ticker"),
        Column("owner", "Insider"),
        Column("title", "Role"),
        Column("code", "Code"),
        Column("shares", "Shares", "number"),
        Column("price", "Price", "money"),
        Column("value", "Value", "money"),
        Column("plan_10b5_1", "10b5-1", "text"),
        Column("issuer_cik || '|' || accession", "Filing", "link"),
    ))

# Congressional Periodic Transaction Reports. PERSONAL USE ONLY — Ethics in Government Act,
# 5 U.S.C. app. § 105(c). See docs/DATA.md.
CONGRESS = Source(
    key="congress", label="Congress", table="congress_trades", date_column="t.filing_date",
    ticker_column="t.ticker", amount_column="t.amount_high",
    join="LEFT JOIN congress_members m ON m.bioguide_id = t.bioguide_id",
    searchable=("t.ticker", "t.member", "t.asset"),
    filters=("dates", "ticker", "text", "trade_type", "amount", "chamber", "member"),
    note="Filed up to 45 days after the transaction, and disclosed as a range rather than an exact "
         "amount. Personal use only (5 U.S.C. app. § 105(c)).",
    columns=(
        Column("t.filing_date", "Filed", "date"),
        Column("t.trade_date", "Traded", "date"),
        Column("CAST(julianday(t.filing_date) - julianday(t.trade_date) AS INTEGER)", "Days late",
               "number"),
        Column("t.member", "Member"),
        Column("t.chamber", "Chamber"),
        Column("t.ticker", "Ticker"),
        Column("t.asset", "Asset"),
        Column("t.type", "Type"),
        Column("t.owner", "Held by"),
        Column("t.amount_low", "From", "money"),
        Column("t.amount_high", "To", "money"),
        Column("m.sectors", "Committee sectors"),
        Column("t.filing_url", "Filing", "link"),
    ))

OWNERSHIP = Source(
    key="ownership", label="13D / 13G stakes", table="ownership", date_column="filing_date",
    searchable=("ticker", "filer"),
    filters=("dates", "ticker", "text", "stake_kind", "passive", "amendments"),
    note="Someone crossed 5 % of a company. A 13D declares active intent; a 13G is passive, and from "
         "an index fund it is a consequence of fund flows rather than a view.",
    columns=(
        Column("filing_date", "Filed", "date"),
        Column("ticker", "Ticker"),
        Column("filer", "Filer"),
        Column("kind", "Kind"),
        Column("amendment", "Amended"),
        Column("passive", "Passive"),
        Column("subject_cik || '|' || accession", "Filing", "link"),
    ))

FLOW = Source(
    key="flow", label="Option flow", table="option_flow", date_column="date",
    amount_column="premium", searchable=("ticker",),
    filters=("dates", "ticker", "text", "option_type", "amount", "contract_volume"),
    note="One row per contract per day. Premium is volume × mid × 100. Volume above open interest "
         "means positions were opened, not closed.",
    columns=(
        Column("date", "Day", "date"),
        Column("ticker", "Ticker"),
        Column("expiry", "Expiry", "date"),
        Column("type", "Type"),
        Column("strike", "Strike", "money"),
        Column("volume", "Volume", "number"),
        Column("open_interest", "Open interest", "number"),
        Column("premium", "Premium", "money"),
        Column("side", "Side"),
    ))

DARK = Source(
    key="dark", label="Off-exchange volume", table="short_volume", date_column="date",
    searchable=("ticker",), filters=("dates", "ticker", "text"),
    note="FINRA's daily off-exchange volume: dark pools, ATSs and wholesalers. It is NOT short "
         "interest, and a third to a half of all volume trades this way normally.",
    columns=(
        Column("date", "Day", "date"),
        Column("ticker", "Ticker"),
        Column("short_volume", "Off-exchange", "number"),
        Column("total_volume", "Total", "number"),
        Column("CASE WHEN total_volume > 0 THEN 100.0 * short_volume / total_volume END", "Share %",
               "number"),
    ))

PRICES = Source(
    key="prices", label="Daily prices", table="prices", date_column="date",
    searchable=("ticker",), filters=("dates", "ticker", "text"), order="ticker, date DESC",
    note="Where a bar came from matters: 'schwab' is your own broker account, 'research' is "
         "Yahoo/Stooq and is for personal research only.",
    columns=(
        Column("date", "Day", "date"),
        Column("ticker", "Ticker"),
        Column("open", "Open", "money"),
        Column("high", "High", "money"),
        Column("low", "Low", "money"),
        Column("close", "Close", "money"),
        Column("volume", "Volume", "number"),
        Column("source", "Source"),
    ))

SOURCES: tuple[Source, ...] = (INSIDERS, CONGRESS, OWNERSHIP, FLOW, DARK, PRICES)
BY_KEY = {s.key: s for s in SOURCES}

# The choices each filter offers, as (value, English label). An empty value means "no filter".
CODES = (("", "Any transaction"), ("P", "Purchases (P)"), ("S", "Sales (S)"),
         ("A", "Awards (A)"), ("M", "Option exercises (M)"))
ROLES = (("", "Anyone"), ("officer", "Officers"), ("director", "Directors"),
         ("ten_pct", "10 % holders"))
TRADE_TYPES = (("", "Any transaction"), ("purchase", "Purchases"), ("sale", "Sales"),
               ("partial sale", "Partial sales"), ("exchange", "Exchanges"))
CHAMBERS = (("", "Both chambers"), ("house", "House"), ("senate", "Senate"))
STAKE_KINDS = (("", "13D and 13G"), ("13D", "13D only (active)"), ("13G", "13G only (passive)"))
OPTION_TYPES = (("", "Calls and puts"), ("call", "Calls"), ("put", "Puts"))


@dataclass
class Filters:
    """What the Scanner is currently narrowed to. Every field is optional."""
    days: int = 30
    ticker: str = ""
    code: str = ""
    role: str = ""
    exclude_plan: bool = False
    trade_type: str = ""
    chamber: str = ""
    member: str = ""
    stake_kind: str = ""
    exclude_passive: bool = False
    option_type: str = ""
    min_amount: float = 0.0
    text: str = ""                  # free text, looked for in the columns the source declares
    new_position: bool = False      # an insider buying into a holding they did not have
    exclude_amendments: bool = False
    min_volume: float = 0.0
    min_open_interest: float = 0.0
    start: date | None = None       # an explicit window, instead of "the last N days"
    end: date | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def since(self) -> date:
        """Where "the last N days" begins, counted back from the end of the window."""
        return (self.end or date.today()) - timedelta(days=max(0, self.days))


def _where(source: Source, f: Filters) -> tuple[list[str], list]:
    clauses, params = [], []
    understands = set(source.filters)

    if "dates" in understands:
        # an explicit start wins over "the last N days", so a window can be asked for exactly
        first = f.start if f.start is not None else (f.since() if f.days else None)
        if first is not None:
            clauses.append(f"{source.date_column} >= ?")
            params.append(first.isoformat())
        if f.end is not None or f.days or f.start is not None:
            clauses.append(f"{source.date_column} <= ?")
            params.append((f.end or date.today()).isoformat())
    if "ticker" in understands and f.ticker.strip() and source.ticker_column:
        # several tickers at once, the way a watchlist is written: "PFE, AAPL"
        wanted = [t.strip().upper() for t in f.ticker.replace(";", ",").split(",") if t.strip()]
        if wanted:
            clauses.append(f"upper({source.ticker_column}) IN ({','.join('?' * len(wanted))})")
            params += wanted
    if "amount" in understands and f.min_amount and source.amount_column:
        clauses.append(f"{source.amount_column} >= ?")
        params.append(float(f.min_amount))
    if "code" in understands and f.code:
        clauses.append("code = ?")
        params.append(f.code)
    if "role" in understands and f.role:
        clauses.append({"officer": "is_officer = 1", "director": "is_director = 1",
                        "ten_pct": "is_ten_pct = 1"}[f.role])
    if "plan" in understands and f.exclude_plan:
        clauses.append("coalesce(plan_10b5_1, 0) = 0")
    if "trade_type" in understands and f.trade_type:
        clauses.append("t.type = ?")
        params.append(f.trade_type)
    if "chamber" in understands and f.chamber:
        clauses.append("t.chamber = ?")
        params.append(f.chamber)
    if "member" in understands and f.member.strip():
        clauses.append("t.member LIKE ?")
        params.append(f"%{f.member.strip()}%")
    if "stake_kind" in understands and f.stake_kind:
        clauses.append("kind = ?")
        params.append(f.stake_kind)
    if "passive" in understands and f.exclude_passive:
        clauses.append("coalesce(passive, 0) = 0")
    if "option_type" in understands and f.option_type:
        clauses.append("type = ?")
        params.append(f.option_type)
    if "text" in understands and f.text.strip() and source.searchable:
        # one box that looks wherever the source says a name lives: a ticker, a person, an asset
        needle = f"%{f.text.strip()}%"
        clauses.append("(" + " OR ".join(f"{c} LIKE ?" for c in source.searchable) + ")")
        params += [needle] * len(source.searchable)
    if "new_position" in understands and f.new_position:
        clauses.append("delta_own_pct >= 0.999")     # bought into a holding they did not have
    if "amendments" in understands and f.exclude_amendments:
        clauses.append("coalesce(amendment, 0) = 0")
    if "contract_volume" in understands:
        if f.min_volume:
            clauses.append("volume >= ?")
            params.append(float(f.min_volume))
        if f.min_open_interest:
            clauses.append("open_interest >= ?")
            params.append(float(f.min_open_interest))
    return clauses, params


def query(source: Source | str, f: Filters | None = None, limit: int = 2000) -> tuple[str, list]:
    """The statement that lists this source under these filters, and its parameters."""
    source = source if isinstance(source, Source) else BY_KEY[source]
    f = f or Filters()
    clauses, params = _where(source, f)
    select = ", ".join(f"{c.sql} AS {_alias(i)}" for i, c in enumerate(source.columns))
    table = f"{source.table} t {source.join}" if source.join else source.table
    sql = f"SELECT {select} FROM {table}"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return sql + f" ORDER BY {source.default_order} LIMIT {int(limit)}", params


def count(source: Source | str, f: Filters | None = None) -> tuple[str, list]:
    """The same filters, counting instead of listing, so the screen can say how many were left out."""
    source = source if isinstance(source, Source) else BY_KEY[source]
    clauses, params = _where(source, f or Filters())
    table = f"{source.table} t {source.join}" if source.join else source.table
    sql = f"SELECT count(*) AS n FROM {table}"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return sql, params


def _alias(i: int) -> str:
    return f"c{i}"


def run(db, source: Source | str, f: Filters | None = None, limit: int = 2000) -> pd.DataFrame:
    """The rows, with the columns named by their English headings and dates parsed."""
    source = source if isinstance(source, Source) else BY_KEY[source]
    sql, params = query(source, f, limit)
    df = pd.read_sql_query(sql, db, params=params)
    df.columns = [c.label for c in source.columns]
    for column in source.columns:
        if column.kind == "date" and column.label in df.columns:
            df[column.label] = pd.to_datetime(df[column.label], errors="coerce")
    return df


def total(db, source: Source | str, f: Filters | None = None) -> int:
    sql, params = count(source, f)
    return int(pd.read_sql_query(sql, db, params=params).iloc[0, 0])


def filing_link(source: Source | str, value: str) -> str:
    """The web page of the original document, so any row can be checked against the source.

    SEC rows carry ``cik|accession`` and are turned into their EDGAR filing index; congressional rows
    already hold the document's own URL.
    """
    source = source if isinstance(source, Source) else BY_KEY[source]
    text = str(value or "")
    if source.key == "congress":
        return text if text.startswith("http") else ""
    cik, _, accession = text.partition("|")
    if not accession or not cik:
        return ""
    return EDGAR_FILING.format(cik=cik.lstrip("0"), plain=accession.replace("-", ""),
                               accession=accession)


def summary(db) -> list[tuple[str, int, str, str]]:
    """Per source: its label, how many rows are stored and the first and last day covered.

    This is the Scanner's opening view — what has been collected at all, before any filter.
    """
    out = []
    for source in SOURCES:
        table = f"{source.table} t {source.join}" if source.join else source.table
        try:
            row = pd.read_sql_query(
                f"SELECT count(*) AS n, min({source.date_column}) AS a, "
                f"max({source.date_column}) AS b FROM {table}", db).iloc[0]
        except Exception:                      # a database from before this source existed
            continue
        out.append((source.label, int(row["n"]), str(row["a"] or ""), str(row["b"] or "")))
    return out
