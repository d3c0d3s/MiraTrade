"""``miratrade earnings`` — the report calendar that an option trade has to know about."""
from __future__ import annotations

from datetime import date, timedelta

from miratrade import store
from miratrade.data.earnings import (KEY_NAME, covered_tickers, crosses_earnings, fetch_history,
                                     next_report, store_earnings, update_calendar)


def cmd_setup(a) -> None:
    """Save the Alpha Vantage key in the Windows Credential Manager, never in a file."""
    from miratrade.brokers.credentials import CredentialStore

    key = (a.key or "").strip()
    if not key:
        raise SystemExit("Pass the key: `miratrade earnings setup --key YOURKEY`. A free one from "
                         "alphavantage.co/support covers the calendar — one request per day returns "
                         "the whole market. Register it as yourself, not as a company: their terms "
                         "count use 'on behalf of a corporation' as commercial.")
    CredentialStore().set(KEY_NAME, key)
    print("Saved in the Windows Credential Manager.")


def cmd_update(a) -> None:
    db = store.connect(a.db)
    try:
        if a.from_report:
            _from_edgar(a.from_report, db)
            return
        update_calendar(db, horizon=a.horizon)
        if a.tickers:
            for ticker in a.tickers:                 # per symbol, decades back, for the backtest
                rows = fetch_history(ticker)
                print(f"  {ticker.upper()}: {store_earnings(rows, db)} reported quarters")
        print(f"\n{covered_tickers(db)} tickers with a known report date.")
    finally:
        db.close()


def cmd_check(a) -> None:
    """Whether a trade on this ticker would have to sit through a report."""
    db = store.connect(read_only=True)
    try:
        today = date.today()
        for ticker in a.tickers:
            nxt = next_report(db, ticker, today)
            if nxt is None:
                print(f"{ticker.upper():<6} no report date known — not the same as none")
                continue
            expiry = today + timedelta(days=a.dte)
            crossing = crosses_earnings(db, ticker, today, expiry)
            days = (nxt - today).days
            print(f"{ticker.upper():<6} next report {nxt} ({days} days)"
                  + (f"  ← a {a.dte}-day contract would sit through it" if crossing else ""))
    finally:
        db.close()


def add_parser(sub) -> None:
    ea = sub.add_parser("earnings", help="the report calendar: IV collapses after a report and the "
                                        "gap gees through a stop, so a trade crossing one differs")
    inner = ea.add_subparsers(dest="earnings_cmd", required=True)

    se = inner.add_parser("setup", help="save your Alpha Vantage key")
    se.add_argument("--key", default=None)
    se.set_defaults(func=cmd_setup)

    up = inner.add_parser("update", help="refresh the upcoming calendar (one request, whole market)")
    up.add_argument("tickers", nargs="*", help="also fetch these symbols' reported history")
    up.add_argument("--from-report", default=None, metavar="DIR",
                    help="take the tickers from a report's events.csv and fetch their announcement "
                         "dates from EDGAR (free, no key: the 8-K filed under item 2.02)")
    up.add_argument("--horizon", choices=["3month", "6month", "12month"], default="3month")
    up.add_argument("--db", default=None)
    up.set_defaults(func=cmd_update)

    ch = inner.add_parser("check", help="would a contract on this ticker cross a report?")
    ch.add_argument("tickers", nargs="+")
    ch.add_argument("--dte", type=int, default=45, help="days to expiry to test (default 45)")
    ch.set_defaults(func=cmd_check)


def _from_edgar(report_dir: str, db) -> None:
    """Announcement dates for a report's whole universe, from EDGAR rather than a paid calendar.

    One request per company inside the SEC's budget, so a few hundred take about a minute, and it
    needs no key at all — the 8-K filed under item 2.02 is the announcement itself.
    """
    import json
    from pathlib import Path

    import pandas as pd

    from miratrade.data.earnings import fetch_sec_earnings
    from miratrade.data.fundamentals import ticker_ciks
    from miratrade.data.sec import SecClient

    events = Path(report_dir) / "events.csv"
    if not events.exists():
        raise SystemExit(f"No events.csv in {report_dir}: run `miratrade analyze` there first.")
    tickers = sorted(set(pd.read_csv(events, usecols=["ticker"])["ticker"]))
    client = SecClient()
    listing = json.loads(client.get("https://www.sec.gov/files/company_tickers.json", max_age_days=7))
    ciks = ticker_ciks(store.read(db, "insiders"), listing)
    print(f"{len(tickers)} tickers in {report_dir}; asking EDGAR for their results 8-Ks")
    fetch_sec_earnings(tickers, ciks, client, db=db)
