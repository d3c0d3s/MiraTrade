"""``miratrade flow`` — the once-a-day option chain capture and its state."""
from __future__ import annotations

import sys
from pathlib import Path

from miratrade import store
from miratrade.flow import WINDOW, SOURCE, daily_capture, missed_sessions, session_window

TASK = "MiraTradeFlowDaily"


def cmd_daily(a) -> None:
    """Capture once, if this is the window and the session is not already done."""
    out = daily_capture(a.tickers or None, from_events=a.from_events, limit=a.limit,
                        source=a.source, force=a.force)
    print(f"{out['why'].capitalize()}"
          + (f" — {out['rows']} contracts stored." if out["ran"] else "."))
    if out["missed"] and not out["ran"]:
        raise SystemExit(1)              # a scheduled task should show as failed when days are lost


def cmd_status(a) -> None:
    """What has been captured, what is missing, and whether now is the moment."""
    from datetime import date

    from miratrade.data.options import session_date

    inside, where = session_window()
    print(where)
    session = session_date()
    db = store.connect(read_only=True) if Path(store.db.DB_PATH).exists() else None
    if db is None:
        print("No market database yet.")
        return
    try:
        done = sorted(store.covered(db, SOURCE))
        missed = missed_sessions(db, session)
        print(f"Session a capture now would belong to: {session}")
        print(f"Sessions captured: {len(done)}"
              + (f" ({done[0]} → {done[-1]})" if done else ""))
        print(f"Already done for {session}: {'yes' if session.isoformat() in done else 'no'}")
        rows = db.execute("SELECT source, count(*) AS n, count(DISTINCT ticker) AS t, "
                          "min(date) AS a, max(date) AS b FROM option_flow GROUP BY source").fetchall()
        for r in rows:
            print(f"  {r['source']:<10} {r['n']:>8,} contracts, {r['t']:>4} tickers, "
                  f"{r['a']} → {r['b']}")
        if missed:
            print("\nMISSED, and not recoverable — the volume of a session is only readable while "
                  "that session is the last one:")
            for d in missed:
                print(f"  {d} ({d.strftime('%A')})")
        elif done:
            print("\nNo missed session.")
    finally:
        db.close()


def cmd_install(a) -> None:
    """Print the command that registers the nightly run with the Windows Task Scheduler.

    It is printed rather than run: registering a scheduled task changes the machine's configuration,
    which is the user's to make, not this program's.
    """
    python = Path(sys.executable)
    start, end = WINDOW
    when = a.at
    print("The capture has to happen between the New York close and the next open, and the app "
          "cannot be relied on to be open then. Register it with Windows:\n")
    print(f'schtasks /Create /TN {TASK} /TR "\\"{python}\\" -m miratrade.cli flow daily" '
          f'/SC DAILY /ST {when} /F\n')
    print(f"That runs it every day at {when} on this computer's clock. The command is idempotent: "
          f"it does nothing outside the {start}–{end} New York window, and nothing for a session it "
          "has already captured, so running it more often than needed is harmless.")
    print("\nCheck it afterwards with:")
    print(f"  schtasks /Query /TN {TASK}")
    print(f"  miratrade flow status")
    print(f"\nRemove it with:\n  schtasks /Delete /TN {TASK} /F")


def add_parser(sub) -> None:
    fl = sub.add_parser("flow", help="the once-a-day option chain capture (volume and open interest)")
    inner = fl.add_subparsers(dest="flow_cmd", required=True)

    da = inner.add_parser("daily", help="capture once, if this is the window and it is not done yet")
    da.add_argument("tickers", nargs="*", help="override the universe")
    da.add_argument("--from-events", type=int, default=30, metavar="DAYS")
    da.add_argument("--limit", type=int, default=60)
    da.add_argument("--source", choices=["schwab", "etrade"], default=None)
    da.add_argument("--force", action="store_true",
                    help="capture even outside the window or for a session already done "
                         "(the figures may then be a part of a session)")
    da.set_defaults(func=cmd_daily)

    st = inner.add_parser("status", help="what was captured, what was missed, and whether now is "
                                        "the moment")
    st.set_defaults(func=cmd_status)

    ins = inner.add_parser("install", help="how to register the nightly run with Windows")
    ins.add_argument("--at", default="18:30", help="time on this computer's clock (default 18:30)")
    ins.set_defaults(func=cmd_install)
