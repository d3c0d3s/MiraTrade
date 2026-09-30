"""How sure a number is, and what it should be compared against.

Two things the project reported without, and both are the difference between evidence and a claim.

**A proportion is an estimate, not a measurement.** "22 % reached the target" over 63 events has a
95 % interval of roughly 13 % to 34 %. Showing the 22 alone is the overconfidence that makes a
backtest read like a forecast, and the width is the honest part: it is what says "this is what we
have, and it is not much".

**A rate means nothing on its own.** 22 % is good or terrible depending on what happens on a day
nobody selected. The 8-K study could kill a finding precisely because it had placebos to compare
against; the event evidence had nothing, so it could only ever agree with itself.

Wilson rather than the textbook normal interval. At the sample sizes here — tens of events, rates
near 20 % — the normal interval is simply wrong: it can reach below zero, and it is badly off
whenever a proportion is near an edge. Wilson stays inside [0, 1] and behaves at small n, which is
the only place this is ever used.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# 95 %, two-sided. Not a knob: a second confidence level in the interface would be one more thing
# to misread, and nobody has ever asked a screen for an 89 % interval.
Z = 1.959963984540054


@dataclass(frozen=True)
class Rate:
    """A proportion with its interval and, when there is one, what it is measured against."""
    hits: int
    n: int
    base: float | None = None            # the same rate on days nobody selected

    @property
    def value(self) -> float:
        return self.hits / self.n if self.n else float("nan")

    @property
    def interval(self) -> tuple[float, float]:
        return wilson(self.hits, self.n)

    @property
    def lift(self) -> float | None:
        """How many times the base rate. ``None`` when there is nothing to compare against.

        ``None`` and 1.0 are different answers and must not be drawn the same: one is "no better
        than nothing", the other is "nobody checked".
        """
        if self.base is None or not self.base:
            return None
        return self.value / self.base

    @property
    def beats_base(self) -> bool | None:
        """Whether the interval clears the base rate at all. ``None`` when there is no base.

        Deliberately the weakest possible claim: an interval that merely sits above the base is
        not a validated edge, it is an absence of evidence against one.
        """
        if self.base is None:
            return None
        return self.interval[0] > self.base


def wilson(hits: int, n: int, z: float = Z) -> tuple[float, float]:
    """The Wilson score interval for a proportion.

    Reduces to (nan, nan) with no observations — an unknown, not a zero. A screen drawing 0 % for
    "we have never seen one" is the kind of confident-looking emptiness this project exists to
    avoid.
    """
    if n <= 0:
        return (float("nan"), float("nan"))
    hits = max(0, min(int(hits), int(n)))
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def say_rate(rate: Rate, translate=None, number=None) -> str:
    """One proportion, as a person should read it: the estimate, its range, and the comparison."""
    from miratrade.messages import sayer

    say = sayer(translate)
    if not rate.n:
        return say("no cases")
    num = number or (lambda v, decimals=0: f"{v:,.{decimals}f}".replace("-", "−"))
    pct = lambda x: f"{num(x * 100, 0)} %"           # noqa: E731
    low, high = rate.interval
    if rate.base is None:
        return say("{value} (between {low} and {high})",
                   value=pct(rate.value), low=pct(low), high=pct(high))
    return say("{value} (between {low} and {high}), against {base} for events of any kind",
               value=pct(rate.value), low=pct(low), high=pct(high), base=pct(rate.base))


def enough_for(difference: float, base: float, z: float = Z) -> int:
    """Roughly how many events it would take to see ``difference`` above ``base`` at all.

    Not a promise, an order of magnitude — the answer to "how much more data would settle this",
    which is a far more useful thing to know than another decimal on a number that cannot settle it.
    """
    if not 0 < base < 1 or difference <= 0:
        return 0
    p = min(0.999, base + difference)
    return max(1, math.ceil(z * z * p * (1 - p) / (difference * difference)))
