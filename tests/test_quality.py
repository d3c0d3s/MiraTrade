"""Does a condition earn its place?

The first lever in this project's list is event quality, and until now it had no numbers. These
tests are about the four things that make the answer worth acting on: the split is in time, the
comparison is against a base rate, every condition tested counts as a test, and "clears the base"
is kept apart from the much weaker "points the same way twice".
"""
from datetime import date, timedelta

import pandas as pd
import pytest

from miratrade import quality
from miratrade.quality import Verdict, judge, table, verdict_line

VARIANT = "call45_40"


def history(rows) -> pd.DataFrame:
    """One row per event. ``res_`` is 1 for target-first, −1 for stop-first."""
    out = []
    for i, (flag, hit, early) in enumerate(rows):
        day = date(2025, 1, 1) + timedelta(days=i if early else 900 + i)
        out.append({"signal_date": day.isoformat(), "event:insider_buy": True,
                    "ins:exec_buy": flag, f"res_{VARIANT}": 1 if hit else -1})
    return pd.DataFrame(out)


def built(early, late, base_early=0.3, base_late=0.3, n=200):
    """A verdict with the rates set directly, for the arithmetic rather than the plumbing."""
    return Verdict(name="x", n_all=2 * n, rate_all=(early + late) / 2,
                   n_early=n, rate_early=early, n_late=n, rate_late=late,
                   base_all=(base_early + base_late) / 2,
                   base_early=base_early, base_late=base_late)


# --------------------------------------------------------------------------- the split

def test_the_split_is_in_time_not_at_random():
    """Splitting these rows randomly puts the same week on both sides of the fence and calls the
    second half a confirmation of the first."""
    rows = [(True, True, True)] * 60 + [(True, False, False)] * 40
    judged = judge(history(rows), VARIANT, {"exec": "ins:exec_buy"}, min_n=10)
    one = judged[0]
    # every early event hit and every late event missed: a random split could not produce that
    assert one.rate_early == pytest.approx(1.0) and one.rate_late == pytest.approx(0.0)


def test_a_condition_with_too_few_events_is_not_judged():
    rows = [(True, True, True)] * 5 + [(False, False, True)] * 95
    assert judge(history(rows), VARIANT, {"exec": "ins:exec_buy"}, min_n=30) == []


def test_no_results_means_nothing_to_judge():
    assert judge(pd.DataFrame(), VARIANT) == []
    assert judge(pd.DataFrame([{"a": 1}]), VARIANT) == []


# --------------------------------------------------------------------------- clearing the base

def test_clearing_means_the_whole_interval_is_above_the_base():
    """Deliberately the weakest possible claim about an edge: an interval merely sitting above the
    base is an absence of evidence against one, not a validated advantage."""
    assert built(0.60, 0.60).survives is True          # far above on 200 each
    assert built(0.32, 0.32).survives is False         # the real-world case: two points, too wide


def test_clearing_one_half_only_is_a_result_about_a_period():
    one = built(0.60, 0.30)
    assert one.clears_early and not one.clears_late
    assert one.survives is False
    assert "one half only" in one.say()


def test_a_condition_worse_in_both_halves_is_named_as_one_to_exclude():
    bad = built(0.10, 0.10)
    assert bad.harmful is True and "WORSE" in bad.say()


# --------------------------------------------------------------------------- direction

def test_direction_is_weaker_than_clearing_and_kept_apart_from_it():
    """Two coin flips agree half the time, so this earns its keep next to the magnitudes, never
    instead of them."""
    small = built(0.32, 0.33)
    assert small.direction == 1 and small.survives is False
    assert "too small for the interval to settle it" in small.say()


def test_a_condition_that_flips_sign_is_called_noise():
    # Neither half clears — a half that does is reported as such instead, which is the more
    # informative statement and should win.
    flips = built(0.27, 0.33)
    assert flips.direction == 0
    assert not flips.clears_early and not flips.clears_late
    assert "what noise looks like" in flips.say()


def test_consistently_below_is_reported_without_being_called_a_finding():
    below = built(0.27, 0.26)
    assert below.direction == -1 and below.harmful is False
    said = below.say()
    assert "both halves" in said and "wrong way" in said


def test_direction_is_zero_when_there_is_nothing_to_compare():
    assert Verdict(name="x").direction == 0


# --------------------------------------------------------------------------- the set

def test_every_condition_tested_counts_as_a_test():
    """Checking eight and reporting the best is not checking one."""
    from miratrade import attempts

    rows = [(i % 2 == 0, i % 3 == 0, i < 60) for i in range(200)]
    judged = judge(history(rows), VARIANT,
                   {"a": "ins:exec_buy", "b": "event:insider_buy"}, min_n=10)
    assert len(judged) == 2
    assert all(v.alpha == pytest.approx(attempts.sidak(2)) for v in judged)
    assert judged[0].alpha < 0.05


def test_the_verdict_says_when_nothing_survives():
    """Which is the answer the five-year report actually gives, and saying it plainly is the
    difference between a study and a press release."""
    said = verdict_line([built(0.32, 0.33), built(0.26, 0.37)])
    assert "No condition clears the base rate in both halves" in said
    assert "not the same as making money" in said


def test_the_verdict_handles_having_nothing_to_say():
    assert "No condition had enough events" in verdict_line([])


def test_the_table_carries_both_halves_and_the_interval():
    rows = table([built(0.32, 0.33)])
    assert {"n", "rate", "low", "high", "base", "lift", "lift_early", "lift_late",
            "direction", "survives", "harmful"} <= set(rows.columns)
    assert rows["low"].iloc[0] < rows["rate"].iloc[0] < rows["high"].iloc[0]


def test_the_conditions_asked_about_are_few_and_named():
    """Each one is another test, and mining a hundred flags for the two that look good is the thing
    the attempt counter exists to make visible."""
    assert len(quality.CONDITIONS) <= 8
    assert "13D / 13G" in quality.CONDITIONS
