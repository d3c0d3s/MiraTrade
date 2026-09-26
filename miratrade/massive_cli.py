"""``miratrade massive setup | test | backfill``."""
from __future__ import annotations

import getpass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


def cmd_setup(a) -> None:
    from miratrade.brokers.credentials import CredentialStore
    from miratrade.data.massive import KEY_NAME

    key = getpass.getpass("Massive API key (hidden): ").strip()
    if not key:
        raise SystemExit("Nothing saved.")
    CredentialStore().set(KEY_NAME, key)
    print("Saved in the Windows Credential Manager (service 'MiraTrade'). Check it: miratrade massive test")


def cmd_test(a) -> None:
    from miratrade.data.massive import MassiveClient

    c = MassiveClient()
    listed = c.contracts("SPY", _third_friday_ahead(), "call")
    print(f"OK: the key works ({len(listed)} SPY calls listed for the next monthly expiry).")


def _third_friday_ahead() -> date:
    from miratrade.options_trades import monthly_expiry

    return monthly_expiry(date.today(), 30, 7)


def cmd_backfill(a) -> None:
    """Real daily bars of the call each event would have bought (free plan: ~5 requests/min)."""
    from miratrade.config import Config
    from miratrade.data.massive import MassiveClient, real_contract_bars
    from miratrade.options_trades import option_contract
    from dataclasses import replace

    events = pd.read_csv(Path(a.report) / "events.csv", parse_dates=["signal_date", "entry_date"])
    if "rv20" not in events:
        raise SystemExit("This report predates the backfill; run `miratrade analyze` again (it is cached).")
    oldest = pd.Timestamp(date.today() - timedelta(days=int(a.history_years * 365)))
    events = events[(events["entry_date"] >= oldest) & events["rv20"].notna()]
    events = events.sort_values("entry_date", ascending=False).head(a.max or None)
    p = replace(Config().options, target_dte=a.dte, min_dte=max(21, a.dte - 15))
    client = MassiveClient()
    found = 0
    print(f"{len(events)} events since {oldest.date()} · ~{len(events) * 1.3 / 5 / 60:.1f} h at 5 requests/min "
          "(cached: stop any time and run again to resume)")
    for n, e in enumerate(events.itertuples(), 1):
        c = option_contract(e.entry, e.entry_date.date(), e.rv20, p)
        end = min(e.entry_date.date() + timedelta(days=45), c["expiry"])
        ticker, bars = real_contract_bars(client, e.ticker, e.entry_date.date(), c["expiry"], c["strike"], end)
        found += bool(len(bars))
        if n % 25 == 0 or n == len(events):
            print(f"  {n}/{len(events)} events · {found} with real prices · {client.requests} requests", flush=True)


def add_parser(sub) -> None:
    sp = sub.add_parser("massive", help="Massive (ex-Polygon) options data")
    s = sp.add_subparsers(dest="massive_cmd", required=True)
    s.add_parser("setup", help="save the API key in the Credential Manager").set_defaults(func=cmd_setup)
    s.add_parser("test", help="check the key with one request").set_defaults(func=cmd_test)
    b = s.add_parser("backfill", help="real prices of the calls each event would have bought")
    b.add_argument("--report", default="reports/5y", help="report folder holding events.csv")
    b.add_argument("--dte", type=int, default=45)
    b.add_argument("--history-years", type=float, default=2.0, help="the free plan keeps 2 years")
    b.add_argument("--max", type=int, help="at most this many events (newest first)")
    b.set_defaults(func=cmd_backfill)
