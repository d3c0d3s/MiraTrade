"""``miratrade schedule`` — the unattended download, and how to have Windows run it."""
from __future__ import annotations

import sys
from datetime import datetime

from miratrade import schedule, store
from miratrade.config import load_user_config


def add_parser(sub) -> None:
    sc = sub.add_parser("schedule", help="the unattended download: what is missing, and how to "
                                         "have Windows fetch it while the market is open and at 23:00")
    inner = sc.add_subparsers(dest="schedule_cmd", required=True)

    st = inner.add_parser("status", help="what is missing right now, downloading nothing")
    st.set_defaults(func=cmd_status)

    rn = inner.add_parser("run", help="fetch the missing sessions, then re-derive the events")
    rn.add_argument("--force", action="store_true",
                    help="run even outside the window (the gap check still applies)")
    rn.add_argument("--max-days", type=int, default=schedule.MAX_CATCH_UP_DAYS,
                    help="furthest back a catch-up will reach on its own")
    rn.set_defaults(func=cmd_run)

    ins = inner.add_parser("install", help="print the Windows commands that register the task")
    ins.add_argument("--every", type=int, default=60,
                     help="minutes between runs while the market is open")
    ins.set_defaults(func=cmd_install)


def cmd_status(a) -> None:
    db = store.connect()
    try:
        what = schedule.plan(db, reason="manual")
        print(what.say())
        if what.capped:
            print(f"  more than {schedule.MAX_CATCH_UP_DAYS} sessions are missing; a background run "
                  f"fetches the most recent ones. `miratrade scan --days N` fetches further back.")
        reason = schedule.due(datetime.now().astimezone(), load_user_config())
        print(f"A run now would be: {reason or 'outside both windows — nothing would start'}")
    finally:
        db.close()


def cmd_run(a) -> None:
    """One turn of the unattended download. Safe to call as often as a scheduler likes."""
    cfg = load_user_config()
    now = datetime.now().astimezone()
    reason = schedule.due(now, cfg)
    if reason is None and not a.force:
        print("Outside the download window; nothing to do. `--force` runs anyway.")
        return
    db = store.connect()
    try:
        # The backup goes first, before anything is written. A copy that only happens when a
        # download succeeds is not a daily backup.
        try:
            from miratrade.backup import make_backup

            make_backup(log=lambda m: print(m))
        except Exception as e:
            print(f"  backup failed: {e}")
        what = schedule.plan(db, now=now, reason=reason or "forced", max_days=a.max_days)
        out = schedule.run(db, what, cfg=cfg)
        if out["skipped"]:
            return
        print(f"{out['events']} events after re-deriving.")
    finally:
        db.close()


def cmd_install(a) -> None:
    print("Run these once, in a terminal, to have Windows fetch on its own.\n"
          "They are printed rather than run: registering a scheduled task changes your machine,\n"
          "and a program that quietly installs itself into a system scheduler is doing something\n"
          "you did not watch it do.\n")
    for command in schedule.schtasks_commands(sys.executable, a.every):
        print(f"  {command}\n")
    print(f"To remove them:\n\n"
          f'  schtasks /Delete /TN "{schedule.TASK_NAME} (market)" /F\n'
          f'  schtasks /Delete /TN "{schedule.TASK_NAME} (evening)" /F\n')
    print("Each run checks what has already been downloaded and asks only for the gap, so running\n"
          "it often costs almost nothing.")
