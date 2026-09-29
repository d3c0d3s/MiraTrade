"""``miratrade congress`` — congressional disclosures into the shared market database.

PERSONAL USE ONLY. The Ethics in Government Act, 5 U.S.C. app. § 105(c), makes it unlawful to obtain
or use these reports for any commercial purpose other than by news and communications media, for
determining a credit rating, or in soliciting money; the Attorney General may sue for up to $10,000
per violation. The notice is printed on every run so the restriction never becomes invisible.
"""
from __future__ import annotations

from datetime import date, timedelta

from miratrade import store

NOTICE = (
    "Congressional disclosures are covered by the Ethics in Government Act, 5 U.S.C. app. § 105(c):\n"
    "  personal use only — not for any commercial purpose, credit rating or soliciting money.\n"
    "  This is the one part of MiraTrade that must be removed before the app is sold.\n")


def cmd_members(args) -> None:
    from miratrade.data.congress import update_members

    db = store.connect(args.db)
    try:
        print(f"{update_members(db)} members stored.")
    finally:
        db.close()


def cmd_trades(args) -> None:
    from miratrade.data.congress import update_members
    from miratrade.data.congress_house import fetch_trades

    print(NOTICE)
    end = date.today()
    start = end - timedelta(days=args.days)
    db = store.connect(args.db)
    try:
        if not len(store.read(db, "congress_members")):
            update_members(db)                      # the roster is what names on a filing match
        print(f"House PTRs filed {start} → {end}:")
        fetch_trades(start, end, db=db, limit=args.limit)
        rows = store.read(db, "congress_trades", "ticker IS NOT NULL", order="filing_date DESC")
        print(f"\n{len(rows)} stored transactions have a ticker.")
        if len(rows):
            recent = rows.head(args.show)[["filing_date", "trade_date", "member", "ticker", "type",
                                           "amount_low", "amount_high"]]
            print(recent.to_string(index=False))
    finally:
        db.close()


def add_parser(sub) -> None:
    cg = sub.add_parser("congress", help="congressional disclosures (personal use only, § 105(c))")
    inner = cg.add_subparsers(dest="congress_cmd", required=True)

    me = inner.add_parser("members", help="refresh the roster and its committee sectors")
    me.set_defaults(func=cmd_members)

    tr = inner.add_parser("trades", help="download House Periodic Transaction Reports")
    tr.add_argument("--days", type=int, default=90, help="how far back to look (default 90)")
    tr.add_argument("--limit", type=int, default=None, help="stop after this many filings")
    tr.add_argument("--show", type=int, default=15, help="rows to print at the end")
    tr.set_defaults(func=cmd_trades)

    for p in (me, tr):
        p.add_argument("--db", default=None, help="a database file other than the default")
