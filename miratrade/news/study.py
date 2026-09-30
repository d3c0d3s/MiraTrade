"""Does corporate news around an event change anything? The measurement, written down.

The first version of this was a script in a terminal, and it found something real. That is exactly
when a study has to stop being a script: the answer is going to be quoted, and a number nobody can
re-run is a number nobody can check.

What it does, and why each part is there:

* **Placebos from the same companies.** The comparison is not "events against the market" but
  "events against other days at these same companies, far enough from any event". Companies that
  attract insider buying file differently from the average company, and without that control the
  study measures which companies are in the sample.
* **Nothing from after the day.** Only filings strictly before the signal count. An 8-K cannot be
  back-dated, which is the whole reason this data was chosen, and it would be a waste to throw that
  away by looking forward.
* **Every item is a test, and they are counted.** Fifteen comparisons against α = 0.05 finds
  something roughly half the time on noise alone. The Šidák correction from
  :mod:`miratrade.attempts` is applied and reported beside the raw p.
* **Split in time.** The earlier part of the window discovers and the later part confirms. A result
  that only appears in one of them is a result about that period.

Fisher's exact test is computed here rather than pulled from scipy: it is one hypergeometric sum,
and the alternative is a large dependency for a single number.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from miratrade.news import filings

PLACEBOS_PER_TICKER = 10
FAR_FROM_EVENT_DAYS = 45      # a placebo this close to a real event is not a control
WINDOW_DAYS = 30              # how far back from a signal an item counts
MIN_OBSERVED = 20             # fewer than this between both groups and the arithmetic is theatre


def fisher_greater(a: int, b: int, c: int, d: int) -> float:
    """One-sided Fisher exact: P(a table this lopsided, or more, towards the events).

    One-sided on purpose. The hypothesis is directional — that this kind of news shows up *more*
    around these events — and testing it two-sided would answer a question nobody asked.
    """
    n = a + b + c + d
    if n == 0:
        return 1.0
    row1, col1 = a + b, a + c
    denom = math.comb(n, col1)
    if denom == 0:
        return 1.0
    hi = min(row1, col1)
    return min(1.0, sum(math.comb(row1, k) * math.comb(n - row1, col1 - k) / denom
                        for k in range(a, hi + 1)))


@dataclass
class Sample:
    """The days being compared, and the ones that had to be left out."""
    events: pd.DataFrame
    placebos: pd.DataFrame
    measurable: int = 0
    total: int = 0
    skipped: list[str] = field(default_factory=list)


def build_sample(db, seed: int = 7, per_ticker: int = PLACEBOS_PER_TICKER,
                 far: int = FAR_FROM_EVENT_DAYS) -> Sample:
    """The stored events, and matched placebo days at the same companies."""
    from miratrade import store

    events = store.read(db, "events")[["ticker", "signal_date"]]
    events["signal_date"] = pd.to_datetime(events["signal_date"])
    have = {row["ticker"] for row in db.execute("SELECT DISTINCT ticker FROM filings")}
    measurable = events[events["ticker"].isin(have)].reset_index(drop=True)

    rng = np.random.default_rng(seed)
    prices = store.prices(db, sorted(measurable["ticker"].unique()))
    real = measurable.groupby("ticker")["signal_date"].apply(list).to_dict()
    rows, skipped = [], []
    for ticker, days in real.items():
        bars = prices.get(ticker)
        if bars is None or not len(bars):
            skipped.append(ticker)
            continue
        pool = [d for d in bars.index if all(abs((d - r).days) > far for r in days)]
        if len(pool) < 5:
            skipped.append(ticker)
            continue
        for k in rng.choice(len(pool), size=min(per_ticker, len(pool)), replace=False):
            rows.append({"ticker": ticker, "signal_date": pool[k]})
    return Sample(events=measurable, placebos=pd.DataFrame(rows),
                  measurable=len(measurable), total=len(events), skipped=sorted(skipped))


def _seen(db, days: pd.DataFrame, before: int) -> tuple[dict, int]:
    """For each day, which items were filed in the window strictly before it."""
    from miratrade import store

    table = store.read(db, "filings")
    table["filing_date"] = pd.to_datetime(table["filing_date"])
    table = table[~table["item"].isin(filings.ROUTINE)]
    by_ticker = {t: g for t, g in table.groupby("ticker")}
    counts: dict[str, int] = {}
    for _, row in days.iterrows():
        group = by_ticker.get(row["ticker"])
        if group is None:
            continue
        low = row["signal_date"] - pd.Timedelta(days=before)
        window = group[(group["filing_date"] > low) & (group["filing_date"] <= row["signal_date"])]
        for item in set(window["item"]):
            counts[item] = counts.get(item, 0) + 1
    return counts, len(days)


def compare(db, sample: Sample, before: int = WINDOW_DAYS,
            min_observed: int = MIN_OBSERVED, alpha: float = 0.05) -> pd.DataFrame:
    """Item by item: how often it appears before an event against before a placebo day."""
    from miratrade import attempts

    seen_events, n_events = _seen(db, sample.events, before)
    seen_placebo, n_placebo = _seen(db, sample.placebos, before)
    if not n_events or not n_placebo:
        return pd.DataFrame()

    rows = []
    for item in sorted(set(seen_events) | set(seen_placebo)):
        a, b = seen_events.get(item, 0), seen_placebo.get(item, 0)
        if a + b < min_observed:
            continue
        rows.append({"item": item, "means": filings.ITEMS.get(item, ""),
                     "events_pct": 100 * a / n_events, "placebo_pct": 100 * b / n_placebo,
                     "n_events": a, "n_placebo": b,
                     "ratio": (a / n_events) / (b / n_placebo) if b else float("inf"),
                     "p": fisher_greater(a, n_events - a, b, n_placebo - b)})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Every item compared is another test. Fifteen against 0.05 finds something roughly half the
    # time on noise alone, and the number that changes behaviour is that one, not the alpha.
    corrected = attempts.sidak(len(out), alpha)
    out["alpha"] = corrected
    out["survives"] = out["p"] < corrected
    return out.sort_values("p").reset_index(drop=True)


def split(sample: Sample, train_fraction: float = 0.6) -> tuple[Sample, Sample]:
    """The window cut in time: the earlier part discovers, the later part confirms.

    In time, never at random. Splitting these rows randomly would put the same week on both sides
    of the fence and call the second half a confirmation of the first.
    """
    if sample.events.empty:
        return sample, sample
    days = sample.events["signal_date"]
    cut = days.min() + (days.max() - days.min()) * train_fraction

    def carve(frame, keep_early):
        mask = frame["signal_date"] <= cut if keep_early else frame["signal_date"] > cut
        return frame[mask].reset_index(drop=True)

    early = Sample(carve(sample.events, True), carve(sample.placebos, True))
    late = Sample(carve(sample.events, False), carve(sample.placebos, False))
    early.measurable = len(early.events)
    late.measurable = len(late.events)
    return early, late


def report(db, before: int = WINDOW_DAYS, alpha: float = 0.05,
           train_fraction: float = 0.6) -> dict:
    """The whole study: the full window, then the same test in each half of it."""
    sample = build_sample(db)
    early, late = split(sample, train_fraction)
    return {"sample": sample,
            "all": compare(db, sample, before, alpha=alpha),
            "discovery": compare(db, early, before, alpha=alpha),
            "confirmation": compare(db, late, before, alpha=alpha)}


def survivors(table: pd.DataFrame) -> set[str]:
    return set(table.loc[table["survives"], "item"]) if len(table) else set()


def verdict(study: dict) -> str:
    """What may honestly be said, in one sentence, including when the answer is nothing."""
    found = survivors(study["discovery"]) & survivors(study["confirmation"])
    if not len(study["all"]):
        return "Not enough stored 8-K items near events to compare anything yet."
    if not found:
        kept = survivors(study["all"])
        return ("Nothing survives in both halves of the window"
                + (f" ({', '.join(sorted(kept))} survives over the whole window, which is the "
                   f"weaker claim)." if kept else "."))
    return (f"{', '.join(sorted(found))} survives the correction in both halves. That is a "
            f"difference in how often the item appears, not a measured effect on a result.")
