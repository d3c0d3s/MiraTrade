"""When companies report, and why an option trade has to know.

Two things happen around a known earnings date, and both work against a bought call:

* **Implied volatility rises into it and collapses after it.** The market prices the expected move in
  beforehand, so the contract is dear; once the news is out the uncertainty is gone and the premium
  falls, even when the stock moved the right way. A trade can be right about the direction and still
  lose — that is what "IV crush" means.
* **The gap jumps through the stop.** A stop is a price, and a price that opens 12 % lower was never
  offered in between.

So a contract whose expiry sits on the far side of a report is a different trade from one that does
not, and the app should say so rather than leave it to be noticed.

Source: Alpha Vantage. ``EARNINGS_CALENDAR`` returns the **whole market's** upcoming dates in one
request — the free key's 25 requests a day is plenty for a once-a-day refresh. ``EARNINGS`` returns
one symbol's reported dates going back decades, which is what a backtest needs; that one is per
symbol, so it is fetched for the tickers being studied rather than for everything.

Their terms grant personal, non-commercial use (see docs/DATA.md).
"""
from __future__ import annotations

import csv
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import date
from typing import Callable

import pandas as pd

BASE_URL = "https://www.alphavantage.co/query"
KEY_NAME = "alphavantage.api_key"
SOURCE = "alphavantage"
EARNINGS_COLUMNS = ["ticker", "report_date", "fiscal_end", "when_of_day", "estimate", "reported",
                    "surprise_pct", "source"]


def api_key(store=None) -> str:
    """The key, from the Windows Credential Manager or ``MIRATRADE_AV_KEY``.

    Never from a file in the checkout and never passed in a URL that gets logged.
    """
    key = os.environ.get("MIRATRADE_AV_KEY")
    if key:
        return key
    from miratrade.brokers.credentials import CredentialStore

    key = (store or CredentialStore()).get(KEY_NAME)
    if not key:
        raise RuntimeError("No Alpha Vantage key: run `miratrade earnings setup`. A free key covers "
                           "the calendar — one request returns the whole market.")
    return key


def _get(params: dict, key: str, opener: Callable | None = None) -> bytes:
    url = f"{BASE_URL}?{urllib.parse.urlencode({**params, 'apikey': key})}"
    request = urllib.request.Request(url, headers={"User-Agent": "MiraTrade research"})
    with (opener or urllib.request.urlopen)(request, timeout=90) as response:
        return response.read()


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_calendar(text: str) -> pd.DataFrame:
    """The upcoming-earnings CSV as rows of the ``earnings`` table."""
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        ticker, report = (row.get("symbol") or "").strip().upper(), (row.get("reportDate") or "").strip()
        if not ticker or not report:
            continue
        rows.append({"ticker": ticker, "report_date": report,
                     "fiscal_end": (row.get("fiscalDateEnding") or "").strip() or None,
                     "when_of_day": (row.get("timeOfTheDay") or "").strip() or None,
                     "estimate": _num(row.get("estimate")), "reported": None,
                     "surprise_pct": None, "source": SOURCE})
    return pd.DataFrame(rows, columns=EARNINGS_COLUMNS)


def parse_history(payload: dict | bytes | str, ticker: str = "") -> pd.DataFrame:
    """One symbol's reported quarters, from the ``EARNINGS`` response."""
    if isinstance(payload, (bytes, str)):
        payload = json.loads(payload)
    ticker = (payload.get("symbol") or ticker or "").strip().upper()
    rows = []
    for q in payload.get("quarterlyEarnings") or []:
        report = (q.get("reportedDate") or "").strip()
        if not ticker or not report:
            continue
        rows.append({"ticker": ticker, "report_date": report,
                     "fiscal_end": (q.get("fiscalDateEnding") or "").strip() or None,
                     "when_of_day": (q.get("reportTime") or "").strip() or None,
                     "estimate": _num(q.get("estimatedEPS")), "reported": _num(q.get("reportedEPS")),
                     "surprise_pct": _num(q.get("surprisePercentage")), "source": SOURCE})
    return pd.DataFrame(rows, columns=EARNINGS_COLUMNS)


def _complain(raw: bytes) -> None:
    """Alpha Vantage answers a rejected request with 200 and a JSON note, so a body that is not what
    was asked for has to be read rather than stored as an empty result."""
    head = raw[:400].decode("utf-8", "replace")
    for marker in ('"Error Message"', '"Note"', '"Information"'):
        if marker in head:
            raise RuntimeError(f"Alpha Vantage refused the request: {head.strip()}")


def fetch_calendar(horizon: str = "3month", key: str | None = None,
                   opener: Callable | None = None) -> pd.DataFrame:
    """Every upcoming report in the next 3, 6 or 12 months — the whole market, one request."""
    raw = _get({"function": "EARNINGS_CALENDAR", "horizon": horizon}, key or api_key(), opener)
    _complain(raw)
    return parse_calendar(raw.decode("utf-8", "replace"))


def fetch_history(ticker: str, key: str | None = None, opener: Callable | None = None) -> pd.DataFrame:
    """One symbol's reported dates, decades of them, for conditioning a backtest."""
    raw = _get({"function": "EARNINGS", "symbol": ticker.upper()}, key or api_key(), opener)
    _complain(raw)
    return parse_history(raw, ticker)


def store_earnings(df: pd.DataFrame, db=None) -> int:
    from miratrade import store

    owned, db = db is None, db if db is not None else store.connect()
    try:
        return store.write(db, "earnings", df)
    finally:
        if owned:
            db.close()


def update_calendar(db=None, horizon: str = "3month", key: str | None = None,
                    opener: Callable | None = None, log: Callable[[str], None] = print) -> int:
    from miratrade import store

    owned, db = db is None, db if db is not None else store.connect()
    try:
        rows = fetch_calendar(horizon, key, opener)
        written = store.write(db, "earnings", rows)
        store.note(db, "earnings_calendar_updated", store.now())
        log(f"  earnings calendar: {written} upcoming reports over "
            f"{rows['ticker'].nunique() if len(rows) else 0} tickers")
        return written
    finally:
        if owned:
            db.close()


# --------------------------------------------------------------------------- the free, official source

SEC_SOURCE = "sec_8k_2.02"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
# "Results of Operations and Financial Condition": the item a company files its earnings release under.
EARNINGS_ITEM = "2.02"


def parse_submissions(payload: dict | bytes | str, ticker: str = "") -> pd.DataFrame:
    """Earnings announcement dates from a company's EDGAR submissions.

    Every 8-K carrying **Item 2.02** is a results announcement, and its filing date is the day the
    company made the numbers public — which is exactly the date a backtest may condition on. This is
    the primary source: free, official, and the announcement itself rather than somebody's calendar
    of it.
    """
    if isinstance(payload, (bytes, str)):
        payload = json.loads(payload)
    ticker = (ticker or (payload.get("tickers") or [""])[0] or "").strip().upper()
    recent = (payload.get("filings") or {}).get("recent") or {}
    forms, dates = recent.get("form") or [], recent.get("filingDate") or []
    items, reports = recent.get("items") or [], recent.get("reportDate") or []
    rows = []
    for i, form in enumerate(forms):
        filed_items = (items[i] or "") if i < len(items) else ""
        if form != "8-K" or EARNINGS_ITEM not in filed_items:
            continue
        filed = dates[i] if i < len(dates) else ""
        if not ticker or not filed:
            continue
        rows.append({"ticker": ticker, "report_date": filed,
                     "fiscal_end": (reports[i] if i < len(reports) else "") or None,
                     "when_of_day": None, "estimate": None, "reported": None,
                     "surprise_pct": None, "source": SEC_SOURCE})
    return pd.DataFrame(rows, columns=EARNINGS_COLUMNS)


def fetch_sec_earnings(tickers, ciks: dict, client=None, log: Callable[[str], None] = print,
                       db=None) -> int:
    """Announcement dates for these tickers from EDGAR, stored as they arrive.

    One request per company, inside the SEC's rate budget, so a few hundred companies take about a
    minute. A ticker with no CIK is reported rather than silently skipped.
    """
    from miratrade import store
    from miratrade.data.sec import SecClient

    client = client or SecClient()
    owned, db = db is None, db if db is not None else store.connect()
    written, missing, empty = 0, [], []
    try:
        for ticker in sorted({str(t).upper() for t in tickers}):
            cik = ciks.get(ticker)
            if not cik:
                missing.append(ticker)
                continue
            raw = client.get(SUBMISSIONS_URL.format(cik=str(cik).lstrip("0")), max_age_days=7)
            if raw is None:
                missing.append(ticker)
                continue
            rows = parse_submissions(raw, ticker)
            if not len(rows):
                empty.append(ticker)
                continue
            written += store.write(db, "earnings", rows)
        log(f"  EDGAR 8-K item {EARNINGS_ITEM}: {written} announcement dates"
            + (f"; {len(missing)} tickers with no CIK" if missing else "")
            + (f"; {len(empty)} with no results 8-K on file" if empty else ""))
        return written
    finally:
        if owned:
            db.close()


# --------------------------------------------------------------------------- asking the question

def next_report(db, ticker: str, on: date | None = None) -> date | None:
    """The first report date on or after ``on``, or ``None`` when none is known.

    ``None`` means *not known*, never *there is none* — a missing calendar and a company that does
    not report look the same from here, so a caller must not read silence as safety.
    """
    on = on or date.today()
    row = db.execute("SELECT min(report_date) AS d FROM earnings WHERE upper(ticker) = ? "
                     "AND report_date >= ?", (ticker.upper(), on.isoformat())).fetchone()
    value = row["d"] if row is not None else None
    return date.fromisoformat(value) if value else None


def crosses_earnings(db, ticker: str, start: date, expiry: date) -> date | None:
    """The report date a trade from ``start`` to ``expiry`` would have to sit through, if any."""
    row = db.execute("SELECT min(report_date) AS d FROM earnings WHERE upper(ticker) = ? "
                     "AND report_date >= ? AND report_date <= ?",
                     (ticker.upper(), start.isoformat(), expiry.isoformat())).fetchone()
    value = row["d"] if row is not None else None
    return date.fromisoformat(value) if value else None


def days_until(db, ticker: str, on: date | None = None) -> int | None:
    nxt = next_report(db, ticker, on)
    return None if nxt is None else (nxt - (on or date.today())).days


def days_to_earnings(db, ticker: str, dates) -> "pd.Series":
    """For each day in ``dates``, how many days until that ticker's next announcement.

    Only announcements **at or after** each day count, so the series carries nothing that was not
    knowable on the day — a backtest may condition on it. Days with no known next announcement are
    NaN, and the conditions leave them alone rather than guessing.
    """
    import numpy as np

    index = pd.DatetimeIndex(dates)
    rows = db.execute("SELECT report_date FROM earnings WHERE upper(ticker) = ? ORDER BY report_date",
                      (ticker.upper(),)).fetchall()
    known = pd.DatetimeIndex([r["report_date"] for r in rows]) if rows else pd.DatetimeIndex([])
    if not len(known):
        return pd.Series(np.nan, index=index, name="days_to_earnings")
    position = known.searchsorted(index, side="left")
    ahead = np.where(position < len(known), position, -1)
    out = np.where(ahead >= 0, (known[ahead].values - index.values) / np.timedelta64(1, "D"), np.nan)
    return pd.Series(out, index=index, name="days_to_earnings")


def covered_tickers(db) -> int:
    row = db.execute("SELECT count(DISTINCT ticker) AS n FROM earnings").fetchone()
    return int(row["n"]) if row else 0
