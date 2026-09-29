"""How far behind the stored data is, and whether that matters for what you are about to do.

Once the screens stopped downloading — Signals searches what is stored, Reports analyses what is
stored — something has to say when what is stored is old. Otherwise the app looks instant and
quietly answers last week's question.

The measure is deliberately about **downloads, not events**: "no new events" and "nothing was
downloaded" look identical in a list, and they mean opposite things. So the answer comes from the
``coverage`` table, which records the days each source was *asked* about, including the days the
answer was nothing.

The last session, not today, is the reference. Asking why Sunday has no filings is not a question
anyone needs the app to raise.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

# Form 4 is the source that drives events, and the only one of them that records coverage per day.
# 13D/G is fetched inside a scan's window rather than day by day, so it has nothing to report here,
# and prices record a requested *span* per ticker, where "the last day" means nothing. Measuring
# the one source that can answer honestly beats averaging three that cannot.
EVENT_SOURCES = ("sec_form4",)
STALE_AFTER = 1                       # business days behind before it is worth saying anything


@dataclass(frozen=True)
class Freshness:
    """What is known about how current the store is."""
    last: date | None                 # newest day any event source was asked about
    session: date                     # the last session that could hold filings
    behind: int                       # business days between the two
    rows: int                         # events stored right now

    @property
    def stale(self) -> bool:
        return self.last is None or self.behind > STALE_AFTER

    @property
    def never(self) -> bool:
        return self.last is None

    def say(self, translate=None) -> str:
        """One sentence for a screen, in the interface's language."""
        from miratrade.messages import sayer

        say = sayer(translate)
        if self.never:
            return say("Nothing has been downloaded yet. Go to Scanner and press «Update data».")
        if not self.stale:
            return say("Data up to {day}.", day=self.last.isoformat())
        if self.behind == 1:
            return say("Data up to {day}: one session behind. Update it from Scanner.",
                       day=self.last.isoformat())
        return say("Data up to {day}: {days} sessions behind. Update it from Scanner.",
                   day=self.last.isoformat(), days=self.behind)


def last_session(now: date | None = None) -> date:
    """The last weekday on or before ``now``.

    A weekday is not the same as a trading day — the market holidays are not in here — so being one
    day behind on a holiday week is normal, which is why :data:`STALE_AFTER` allows one.
    """
    day = now or date.today()
    while day.weekday() >= 5:                 # Saturday, Sunday
        day -= timedelta(days=1)
    return day


def last_download(db, sources=EVENT_SOURCES) -> date | None:
    """The newest day any of those sources was asked about."""
    marks = ",".join("?" * len(sources))
    row = db.execute(f"SELECT max(day) AS d FROM coverage WHERE source IN ({marks})",
                     list(sources)).fetchone()
    return date.fromisoformat(row["d"][:10]) if row and row["d"] else None


def sessions_between(first: date, last: date) -> int:
    """Business days strictly after ``first``, up to and including ``last``."""
    if last <= first:
        return 0
    return max(0, len(pd.bdate_range(first + timedelta(days=1), last)))


def check(db, now: date | None = None, sources=EVENT_SOURCES) -> Freshness:
    """How current the store is. Never raises: a screen asking this must still draw."""
    session = last_session(now)
    try:
        last = last_download(db, sources)
    except Exception:
        last = None
    try:
        rows = int(db.execute("SELECT count(*) AS n FROM events").fetchone()["n"])
    except Exception:
        rows = 0
    return Freshness(last=last, session=session,
                     behind=sessions_between(last, session) if last else 0, rows=rows)
