"""How sure a number is, and what it is measured against.

These are the two things the evidence reported without, and each is the difference between evidence
and a claim: a proportion without its interval reads as a measurement, and a rate without a base
can only ever agree with itself.
"""
import math

import pytest

from miratrade.stats import Rate, Z, enough_for, say_rate, wilson


# --------------------------------------------------------------------------- the interval

def test_the_interval_is_wide_when_the_sample_is_small():
    """The width is the honest part. It is what says "this is what we have, and it is not much"."""
    low, high = wilson(14, 63)                  # 22 % over 63 events
    assert 0.13 < low < 0.15 and 0.33 < high < 0.35
    wide_low, wide_high = wilson(4, 8)          # the same 50 %, on eight
    assert (wide_high - wide_low) > (high - low)


def test_more_data_narrows_it():
    before = wilson(22, 100)
    after = wilson(220, 1000)
    assert (after[1] - after[0]) < (before[1] - before[0]) / 2


def test_it_never_leaves_the_possible():
    """Why Wilson and not the textbook normal interval: at these sample sizes and rates the normal
    one reaches below zero, and a screen showing −4 % of anything is a screen nobody trusts again."""
    for hits, n in ((0, 10), (10, 10), (1, 200), (199, 200), (0, 1), (1, 1)):
        low, high = wilson(hits, n)
        assert 0.0 <= low <= high <= 1.0


def test_no_observations_is_unknown_not_zero():
    """A screen drawing 0 % for "we have never seen one" is the confident-looking emptiness this
    project exists to avoid."""
    low, high = wilson(0, 0)
    assert math.isnan(low) and math.isnan(high)


def test_it_is_centred_near_the_proportion_but_pulled_from_the_edges():
    low, high = wilson(50, 100)
    assert low < 0.5 < high and abs((low + high) / 2 - 0.5) < 0.01
    low, high = wilson(1, 100)                  # near an edge it is asymmetric, and should be
    assert (high - 0.01) > (0.01 - low)


# --------------------------------------------------------------------------- the comparison

def test_a_rate_knows_what_it_is_measured_against():
    r = Rate(hits=14, n=63, base=0.19)
    assert r.value == pytest.approx(0.2222, abs=1e-3)
    assert r.lift == pytest.approx(1.17, abs=0.01)


def test_no_base_and_a_base_of_no_advantage_are_different_answers():
    """`None` and 1.0 must not be drawn the same: one is "no better than nothing", the other is
    "nobody checked"."""
    assert Rate(hits=14, n=63).lift is None
    assert Rate(hits=14, n=63).beats_base is None
    assert Rate(hits=19, n=100, base=0.19).lift == pytest.approx(1.0)
    assert Rate(hits=19, n=100, base=0.19).beats_base is False


def test_beating_the_base_means_the_whole_interval_clears_it():
    """Deliberately the weakest possible claim: an interval sitting above the base is not a
    validated edge, it is an absence of evidence against one."""
    # 22 % over 63 against 19 %: the interval starts at 14 %, so it does not clear it
    assert Rate(hits=14, n=63, base=0.19).beats_base is False
    # the same rate over a thousand does
    assert Rate(hits=220, n=1000, base=0.19).beats_base is True


def test_the_sentence_leads_with_the_range_and_names_the_comparison():
    said = say_rate(Rate(hits=14, n=63, base=0.19))
    assert "22 %" in said and "14 %" in said and "34 %" in said and "19 %" in said
    bare = say_rate(Rate(hits=14, n=63))
    assert "19 %" not in bare and "between" in bare
    assert say_rate(Rate(hits=0, n=0)) == "no cases"


# --------------------------------------------------------------------------- how much would settle it

def test_it_says_how_much_more_data_would_settle_the_question():
    """Far more useful than another decimal on a number that cannot settle it."""
    assert enough_for(0.03, 0.19) > 500          # three points over a 19 % base: hundreds of events
    assert enough_for(0.10, 0.19) < 150          # ten points: a manageable number
    assert enough_for(0.10, 0.19) < enough_for(0.03, 0.19)


def test_an_impossible_question_asks_for_nothing():
    assert enough_for(0.0, 0.19) == 0 and enough_for(-0.1, 0.19) == 0
    assert enough_for(0.05, 0.0) == 0 and enough_for(0.05, 1.0) == 0


# --------------------------------------------------------------------------- through the evidence

def test_the_evidence_carries_the_base_rate_and_the_interval():
    import pandas as pd

    from miratrade.scan import evidence

    # 40 events, ten of them "big", and the big ones do better than the rest
    rows = []
    for i in range(40):
        big = i < 10
        rows.append({"event:insider_buy": True, "ins:big_250k+": big,
                     "res_call45_40": 1 if (big and i < 6) or (not big and i % 5 == 0) else -1,
                     "ret_call45_40": 0.2 if big else -0.1})
    history = pd.DataFrame(rows)

    found = evidence({"event:insider_buy": True, "ins:big_250k+": True}, history,
                     "call45_40", min_n=5)
    assert found.n == 10 and found.base_n == 40
    assert found.target == pytest.approx(0.6)
    assert found.base_target == pytest.approx((6 + 6) / 40)   # the similar ones are in the base too

    said = found.say()
    assert "between" in said and "of any kind" in said
    assert found.rate.base is not None and found.rate.lift > 1


def test_no_history_means_no_base_rather_than_a_base_of_zero():
    import pandas as pd

    from miratrade.scan import evidence

    found = evidence({"event:insider_buy": True}, pd.DataFrame(), "call45_40")
    assert found.n == 0 and found.base_n == 0
    assert found.rate.base is None
    assert "No similar event" in found.say()
