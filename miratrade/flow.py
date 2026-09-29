"""The once-a-day option chain capture, and knowing when it did not happen.

A chain shows the session that has just finished, so the capture has a window: after the New York
close and before the next open. Inside that window the figures are final and they belong to one
session. Outside it they are either mid-session and incomplete, or already replaced by the next
session's.

That window is also why a missed day matters and cannot be repaired. Open interest is cumulative and
comes back tomorrow; **the volume of a session is only visible while that session is the last one**,
and no free source sells it back afterwards. So this module does two things: run at most once per
session, and say plainly which sessions were lost.

Safe to call as often as you like — a session already captured is not captured again.
"""
from __future__ import annotations

from datetime import date
from typing import Callable

import pandas as pd

# New York time. Fifteen minutes after the close, so the figures have settled, until fifteen before
# the next open, so a late run cannot catch a session that has already started.
WINDOW = ("16:15", "09:15")
SOURCE = "flow_daily"          # coverage rows saying "the daily run finished for this session"
LOOK_BACK = 10                 # business days to check for a session that was missed


def flow_universe(tickers: list[str] | None, from_events: int = 30, limit: int = 60,
                  db=None) -> list[str]:
    """Which tickers to snapshot today.

    A broker chain is one request per ticker, so the universe has to be a decision, not everything.
    ``--from-events`` takes the tickers that already have an event stored in the last N days: that is
    where flow would add evidence to a signal we already have, and it is a rule that only looks at
    what was knowable on the day, so it introduces no lookahead into a later backtest.
    """
    from miratrade import store
    from miratrade.scan import load_events

    if tickers:
        return [t.upper() for t in tickers][:limit]
    owned, db = db is None, db if db is not None else store.connect(read_only=True)
    try:
        events = load_events(db, days=from_events)
    finally:
        if owned:
            db.close()
    if not len(events):
        return []
    # the busiest names first: if the limit bites, it keeps the ones with most to explain
    counts = events["ticker"].value_counts()
    return [str(t) for t in counts.index[:limit]]


def session_window(now=None) -> tuple[bool, str]:
    """Whether the figures on the wire right now are a **complete** session, and a sentence saying so.

    What makes a capture valid is not a clock range but that no session is in progress: the chain then
    shows the last session, closed and final. So the window is everything except a weekday between
    the open and the close — which means the whole of a weekend, and the whole of a market holiday.
    Writing it as a plain 16:15–09:15 range called a Sunday afternoon "outside the window", when it
    is the safest moment of the week to read Friday's session.
    """
    from datetime import time as _time

    from miratrade.scan import new_york_time

    start, end = WINDOW
    here = new_york_time(pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC"))
    trading_hours = (here.weekday() < 5
                     and _time.fromisoformat(end) <= here.time() <= _time.fromisoformat(start))
    when = f"New York {here:%H:%M} {here:%A}"
    if trading_hours:
        return False, (f"{when}: a session is in progress, and a chain read now would be part of one "
                       f"rather than a finished session. The window is after {start} and before "
                       f"{end}, and all weekend.")
    return True, f"{when}: no session in progress, so the chain shows one that is complete"


def captured_sessions(db, source: str = SOURCE) -> set[str]:
    from miratrade import store

    return store.covered(db, source)


def missed_sessions(db, session: date | None = None, back: int = LOOK_BACK,
                    source: str = SOURCE) -> list[date]:
    """Business days before ``session`` that were never captured, once capturing had begun.

    Days before the very first capture are not misses — nothing was running then. Only a gap after
    that first day counts, and only a gap is worth reporting, because it cannot be filled in.
    """
    done = captured_sessions(db, source)
    if not done:
        return []
    session = session or date.today()
    first = min(done)
    days = [d for d in pd.bdate_range(end=pd.Timestamp(session) - pd.Timedelta(days=1),
                                      periods=back).date
            if d.isoformat() >= first]
    return [d for d in days if d.isoformat() not in done]


def resolve_broker(source: str | None = None):
    """The broker to read chains from, and the name to store them under."""
    from miratrade.config import load_user_config

    source = source or load_user_config().data.quote_broker
    if source == "etrade":
        from miratrade.brokers.etrade import EtradeBroker

        return EtradeBroker()
    from miratrade.brokers.schwab import SchwabBroker

    return SchwabBroker()


def daily_capture(tickers: list[str] | None = None, broker=None, db=None, now=None,
                  log: Callable[[str], None] = print, force: bool = False,
                  from_events: int = 30, limit: int = 60, source: str | None = None) -> dict:
    """Capture today's chains once, if this is the moment and it has not been done.

    Returns what happened, so a caller — a scheduled task, the app's timer — can report it without
    having to work it out again: ``{"ran": bool, "why": str, "session": date, "rows": int,
    "missed": [date, …]}``.
    """
    from miratrade import store
    from miratrade.data.options import session_date, snapshot_broker

    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    session = session_date(now)
    inside, where = session_window(now)
    owned, db = db is None, db if db is not None else store.connect()
    try:
        # the daily copy first, before anything is written: this is the job that already runs every
        # day, and a backup that only happens when a capture succeeds is not a daily backup
        try:
            from miratrade.backup import make_backup

            make_backup(log=log)
        except Exception as e:                    # a failed copy must never stop the capture
            log(f"  backup failed: {e}")

        missed = missed_sessions(db, session, source=SOURCE)
        if missed:
            log(f"  WARNING: no capture for {', '.join(str(d) for d in missed)}. Open interest will "
                "catch up on its own, but the volume of those sessions is gone — it is only readable "
                "while the session is the last one.")
        if session.isoformat() in captured_sessions(db) and not force:
            return {"ran": False, "why": f"session {session} already captured", "session": session,
                    "rows": 0, "missed": missed}
        if not inside and not force:
            return {"ran": False, "why": where, "session": session, "rows": 0, "missed": missed}

        names = tickers if tickers is not None else flow_universe(None, from_events, limit, db)
        if not names:
            return {"ran": False, "why": "no tickers to capture; run `miratrade scan` first",
                    "session": session, "rows": 0, "missed": missed}
        broker = broker or resolve_broker(source)
        log(f"  {where}. Session {session}, {len(names)} tickers from {broker.name}.")
        rows = snapshot_broker(names, broker, asof=session, db=db, log=log)
        store.mark_covered(db, SOURCE, [session], rows=len(rows))
        return {"ran": True, "why": f"captured session {session}", "session": session,
                "rows": len(rows), "missed": missed}
    finally:
        if owned:
            db.close()
