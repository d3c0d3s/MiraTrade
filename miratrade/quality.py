"""Does a condition earn its place? Measured in time, in two halves, against a base rate.

The first lever in this project's own list is **event quality** — which events are worth calling
events at all — and until now it had no numbers. Adding intervals and a base rate produced three
uncomfortable readings on the five-year report, all of them in-sample:

* insider buys beat the base rate, and barely (1.11×);
* the $250k filter and the cluster filter sit **inside** the base's reach, so neither is earning
  its place;
* 13D/13G events are **worse** than an event of any kind — and they are nearly half of what the
  product shows.

This module turns those into out-of-sample answers, which is the only form in which they are worth
acting on. The method is the one the 8-K study arrived at the hard way:

1. **Split in time, never at random.** The earlier part discovers, the later part confirms.
   Splitting these rows randomly puts the same week on both sides of the fence and calls the second
   half a confirmation of the first.
2. **Compare against a base rate**, not against nothing. A rate with nothing to measure against can
   only agree with itself.
3. **Every condition tested is a test.** Checking eight and reporting the best is not checking one,
   and :mod:`miratrade.attempts` holds the correction.
4. **Report the interval.** On a few hundred events a three-point difference and no difference look
   identical, and saying so is the difference between evidence and a press release.

What it cannot do is tell you whether a condition makes money. It measures how often a target was
reached first. The same events in the five-year report stopped out 66 % of the time for an average
of −3 %, which is option decay eating a 32 % hit rate — a condition can improve the hit rate and
still lose.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from miratrade.stats import Rate, wilson

# The conditions worth asking about, as (name, how to select them). Deliberately few: each one is
# another test, and mining a hundred flags for the two that look good is the thing the attempt
# counter exists to make visible.
CONDITIONS: dict[str, str] = {
    "insider buy": "event:insider_buy",
    "…by an executive": "ins:exec_buy",
    "…of $250k or more": "ins:big_250k+",
    "…in a cluster of 2+": "ins:cluster2+",
    "13D / 13G": "event:13dg",
    "unusual option flow": "event:flow",
}


@dataclass
class Verdict:
    """One condition, judged in both halves of the window."""
    name: str
    n_all: int = 0
    rate_all: float = float("nan")
    n_early: int = 0
    rate_early: float = float("nan")
    n_late: int = 0
    rate_late: float = float("nan")
    base_all: float = float("nan")
    base_early: float = float("nan")
    base_late: float = float("nan")
    alpha: float = 0.05

    def _clears(self, hits: int, n: int, base: float) -> bool | None:
        if not n or base != base:
            return None
        low, _high = wilson(hits, n)
        return low > base

    @property
    def clears_early(self) -> bool | None:
        return self._clears(round(self.rate_early * self.n_early), self.n_early, self.base_early)

    @property
    def clears_late(self) -> bool | None:
        return self._clears(round(self.rate_late * self.n_late), self.n_late, self.base_late)

    @property
    def survives(self) -> bool:
        """Clears the base in **both** halves. Anything less is a result about a period."""
        return bool(self.clears_early) and bool(self.clears_late)

    @property
    def harmful(self) -> bool | None:
        """Whole interval below the base, in both halves. A condition to exclude, not to add."""
        if not self.n_early or not self.n_late:
            return None
        return (wilson(round(self.rate_early * self.n_early), self.n_early)[1] < self.base_early
                and wilson(round(self.rate_late * self.n_late), self.n_late)[1] < self.base_late)

    @property
    def direction(self) -> int:
        """+1 if above the base in both halves, −1 if below in both, 0 if it flips.

        A deliberately weaker statement than :attr:`survives`, and kept separate from it so the two
        can never be confused. Clearing the base means the interval is above it; pointing the same
        way twice means only that the sign did not change — which is worth knowing, because a
        condition that flips sign between halves is noise and one that does not is at least a
        consistent *something*.

        It is weak on its own: two coin flips agree half the time. It earns its keep next to the
        magnitudes, not instead of them.
        """
        if not self.n_early or not self.n_late:
            return 0
        if self.base_early != self.base_early or self.base_late != self.base_late:
            return 0
        early = self.rate_early - self.base_early
        late = self.rate_late - self.base_late
        if early > 0 and late > 0:
            return 1
        if early < 0 and late < 0:
            return -1
        return 0

    def say(self, translate=None) -> str:
        from miratrade.messages import sayer

        say = sayer(translate)
        if not self.n_all:
            return say("{name}: no events to judge.", name=self.name)
        if self.harmful:
            return say("{name}: WORSE than an event of any kind, in both halves. A candidate to "
                       "exclude.", name=self.name)
        if self.survives:
            return say("{name}: clears the base rate in both halves.", name=self.name)
        if self.clears_early or self.clears_late:
            return say("{name}: clears in one half only, which is a result about a period rather "
                       "than a finding.", name=self.name)
        if self.direction == -1:
            return say("{name}: below the base rate in both halves, without the interval settling "
                       "it. Consistent, and consistently the wrong way.", name=self.name)
        if self.direction == 1:
            return say("{name}: above the base rate in both halves, too small for the interval to "
                       "settle it.", name=self.name)
        return say("{name}: changes sign between the halves, which is what noise looks like.",
                   name=self.name)


def judge(history: pd.DataFrame, variant: str, conditions=None, train_fraction: float = 0.6,
          min_n: int = 30, date_column: str = "signal_date") -> list[Verdict]:
    """Every condition, in the whole window and in each half of it.

    ``history`` is a report's ``events.csv``: one row per event with ``res_<variant>`` holding 1
    for target-first, −1 for stop-first and 0 for neither.
    """
    res = f"res_{variant}"
    if history is None or history.empty or res not in history:
        return []
    table = history.dropna(subset=[res]).copy()
    if date_column in table:
        table[date_column] = pd.to_datetime(table[date_column], errors="coerce")
        table = table.dropna(subset=[date_column]).sort_values(date_column)
        days = table[date_column]
        cut = days.min() + (days.max() - days.min()) * train_fraction
        early, late = table[days <= cut], table[days > cut]
    else:
        # No dates: split by position, which is the same thing when the file is written in order.
        edge = int(len(table) * train_fraction)
        early, late = table.iloc[:edge], table.iloc[edge:]

    def rate(frame) -> tuple[int, float]:
        if not len(frame):
            return 0, float("nan")
        return len(frame), float((frame[res] == 1).mean())

    out = []
    for name, flag in (conditions or CONDITIONS).items():
        if flag not in table:
            continue
        picks = [f[f[flag].astype(bool)] for f in (table, early, late)]
        if len(picks[0]) < min_n:
            continue
        verdict = Verdict(name=name)
        (verdict.n_all, verdict.rate_all) = rate(picks[0])
        (verdict.n_early, verdict.rate_early) = rate(picks[1])
        (verdict.n_late, verdict.rate_late) = rate(picks[2])
        _n, verdict.base_all = rate(table)
        _n, verdict.base_early = rate(early)
        _n, verdict.base_late = rate(late)
        out.append(verdict)

    if out:
        from miratrade import attempts

        corrected = attempts.sidak(len(out))
        for verdict in out:
            verdict.alpha = corrected
    return out


def table(verdicts: list[Verdict]) -> pd.DataFrame:
    """The verdicts as rows, for printing or for a report."""
    rows = []
    for v in verdicts:
        low, high = wilson(round(v.rate_all * v.n_all), v.n_all)
        rows.append({"condition": v.name, "n": v.n_all,
                     "rate": v.rate_all, "low": low, "high": high, "base": v.base_all,
                     "lift": (v.rate_all / v.base_all) if v.base_all else float("nan"),
                     "early": v.clears_early, "late": v.clears_late,
                     "lift_early": (v.rate_early / v.base_early) if v.base_early else float("nan"),
                     "lift_late": (v.rate_late / v.base_late) if v.base_late else float("nan"),
                     "direction": v.direction,
                     "survives": v.survives, "harmful": v.harmful})
    return pd.DataFrame(rows)


def verdict_line(verdicts: list[Verdict], translate=None) -> str:
    """What may honestly be said about the set, including when the answer is nothing."""
    from miratrade.messages import sayer

    say = sayer(translate)
    if not verdicts:
        return say("No condition had enough events to judge.")
    kept = [v.name for v in verdicts if v.survives]
    drop = [v.name for v in verdicts if v.harmful]
    parts = []
    if kept:
        parts.append(say("Earns its place in both halves: {names}.", names=", ".join(kept)))
    else:
        parts.append(say("No condition clears the base rate in both halves of the window."))
    if drop:
        parts.append(say("Worse than an event of any kind: {names}.", names=", ".join(drop)))
    down = [v.name for v in verdicts if v.direction == -1 and not v.harmful]
    flips = [v.name for v in verdicts if v.direction == 0]
    if down:
        parts.append(say("Below the base in both halves without the interval settling it: "
                         "{names}. Weaker than a finding, and consistently the wrong way.",
                         names=", ".join(down)))
    if flips:
        parts.append(say("Changes sign between the halves, which is what noise looks like: "
                         "{names}.", names=", ".join(flips)))
    parts.append(say("Reaching the target more often is not the same as making money: the same "
                     "events can stop out and still lose on decay."))
    return " ".join(parts)
