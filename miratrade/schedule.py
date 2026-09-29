"""The unattended download: what is actually missing, and when to go and get it.

Two triggers, because they answer two different questions.

* **While the market is open**, every so often. New Form 4s arrive through the afternoon and the
  evening in New York, and an event you see on the day is worth more than the same event tomorrow.
* **At 23:00**, once. This one is the safety net: it asks for whatever the daytime runs missed,
  whether because the machine was asleep, the network was down, or nobody turned the computer on.

Both run the same thing, and the important part is what it does **first**: it looks at ``coverage``
and works out which business days have never been asked about. Then it asks for those and no
others. Without that, a task running every 30 minutes downloads the same fortnight of filings
forty-eight times a day — which is wasteful for us and abusive of a public service that has already
answered the question.

A day with nothing in it is a covered day. That is the whole reason ``coverage`` records the days
asked about rather than the rows returned: otherwise a quiet Tuesday is re-downloaded for ever.

This module decides *what* and *when*. It does not install anything: ``miratrade schedule install``
prints the command, and registering a task with Windows is the user's own action, on their own
machine, in their own words.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable

import pandas as pd

from miratrade.config import Config
from miratrade.data.sec import SOURCE as FORM4
from miratrade.freshness import last_session

# How far back the catch-up will ever reach on its own. A machine off for a month should fetch the
# month, not five years: five years is a deliberate act with a progress bar, not something a
# background task decides to do at 23:00 on its own.
MAX_CATCH_UP_DAYS = 45
EVENING = time(23, 0)
TASK_NAME = "MiraTrade daily"


@dataclass(frozen=True)
class Plan:
    """What a run would do, before it does it."""
    days: list[date]                   # business days never asked about, oldest first
    last: date | None                  # the newest day already covered
    reason: str                        # "market open" | "evening catch-up" | "manual"
    capped: bool = False               # more was missing than MAX_CATCH_UP_DAYS allows

    @property
    def needed(self) -> bool:
        return bool(self.days)

    @property
    def span(self) -> tuple[date, date] | None:
        return (self.days[0], self.days[-1]) if self.days else None

    def say(self, translate=None) -> str:
        from miratrade.messages import sayer

        say = sayer(translate)
        if not self.needed:
            return say("Nothing to download: everything up to {day} is already stored.",
                       day=self.last.isoformat() if self.last else "—")
        first, last = self.span
        if first == last:
            return say("One session to download: {day}.", day=first.isoformat())
        return say("{count} sessions to download, {first} to {last}.",
                   count=len(self.days), first=first.isoformat(), last=last.isoformat())


def business_days(first: date, last: date) -> list[date]:
    return [d.date() for d in pd.bdate_range(first, last)]


def plan(db, now: datetime | None = None, reason: str = "manual",
         max_days: int = MAX_CATCH_UP_DAYS, source: str = FORM4) -> Plan:
    """Which business days have never been asked about, up to the last session.

    Deliberately **not** "everything since the last download": a gap in the middle — a day the
    machine was off while later days were fetched — would never be filled by counting forward from
    the newest row.
    """
    from miratrade import store

    today = (now or datetime.now()).date()
    end = last_session(today)
    try:
        covered = store.covered(db, source)
    except Exception:
        covered = set()
    first = end - timedelta(days=max_days * 2)          # calendar days: bdate_range thins them out
    wanted = [d for d in business_days(first, end) if d.isoformat() not in covered]
    capped = len(wanted) > max_days
    newest = max((date.fromisoformat(d) for d in covered), default=None) if covered else None
    return Plan(days=wanted[-max_days:] if capped else wanted, last=newest, reason=reason,
                capped=capped)


def due(now: datetime, cfg: Config = Config(), last_evening: date | None = None) -> str | None:
    """Why a run should start now, or ``None``.

    The daytime window is the one already in the settings — the hours New York actually files in —
    so the two ways of refreshing do not disagree about when there is something to find. The
    evening run is separate and fires once, however many times the task wakes up after 23:00.
    """
    from miratrade.scan import within_window

    stamp = pd.Timestamp(now)
    if stamp.tz is None:
        stamp = stamp.tz_localize("UTC")
    ny = stamp.tz_convert("America/New_York")
    if ny.time() >= EVENING and ny.weekday() < 5 and last_evening != ny.date():
        return "evening catch-up"
    d = cfg.data
    if within_window(stamp, d.auto_refresh_from, d.auto_refresh_to, d.auto_refresh_weekdays_only):
        return "market open"
    return None


def run(db, what: Plan, cfg: Config = Config(), log: Callable[[str], None] = print,
        fetch=None) -> dict:
    """Fetch the missing days, then re-derive the events. Returns what happened.

    Downloading and reasoning are kept apart here as everywhere else: the scan brings the filings
    in, and :mod:`miratrade.reprocess` turns them into events under whatever settings are current.
    A background task that silently re-derived events under settings nobody chose would be a
    surprise; this one uses the stored settings, which are the ones the screens show.
    """
    from miratrade.reprocess import reprocess
    from miratrade.scan import run_scan, store_scan

    if not what.needed:
        log("  " + what.say())
        return {"downloaded": 0, "events": 0, "days": 0, "skipped": True}
    first, last = what.span
    days = (last - first).days + 1
    log(f"  {what.reason}: {what.say()}")
    result = run_scan(days=days, end=last, cfg=cfg, log=log,
                      **({"fetch": fetch} if fetch is not None else {}))
    written = store_scan(result, db=db)
    log(f"  stored {written['events']} events, {written['prices']} price bars")
    # The events are rebuilt over the whole stored window, not only the new days: a purchase filed
    # today can complete a cluster that started last week, and only re-deriving today would miss it.
    out = reprocess(db, cfg=cfg, log=log)
    return {"downloaded": written.get("events", 0), "events": len(out["events"]), "days": days,
            "skipped": False}


# --------------------------------------------------------------------------- registering it

def schtasks_commands(python: str, every_minutes: int = 60) -> list[str]:
    """The two Windows commands that would register the task, printed for the user to run.

    Printed rather than executed. Registering a scheduled task changes the machine, and a program
    that quietly installs itself into a system scheduler is doing something its user did not watch
    it do. The commands are plain, and removing them is one line.
    """
    # cmd.exe wants the whole /TR in double quotes with the inner ones escaped as \". Python's !r
    # gives single quotes and escaped backslashes, which schtasks takes literally and the task then
    # fails at 23:00 with nobody watching — the worst place for a quoting mistake.
    run_cmd = f'\\"{python}\\" -X utf8 -m miratrade.cli schedule run'
    return [
        f'schtasks /Create /TN "{TASK_NAME} (market)" /TR "{run_cmd}" /SC MINUTE '
        f'/MO {int(every_minutes)} /ST 09:00 /ET 22:30 /K /F',
        f'schtasks /Create /TN "{TASK_NAME} (evening)" /TR "{run_cmd}" /SC DAILY /ST 23:00 /F',
    ]
