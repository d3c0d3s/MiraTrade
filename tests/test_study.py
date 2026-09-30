"""The 8-K study.

It started as a script that found something. That is exactly when a study has to stop being a
script: the answer gets quoted, and a number nobody can re-run is a number nobody can check. These
tests are about the four things that make the answer mean anything — the control group, the
direction of time, the correction, and the split.
"""
from datetime import date, timedelta

import pandas as pd
import pytest

from miratrade import store
from miratrade.news import study


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / "market.db")
    index = pd.bdate_range(end="2026-09-25", periods=400)
    close = pd.Series([20.0] * len(index), index=index)
    for ticker in ("AAA", "BBB"):
        store.write(conn, "prices", pd.DataFrame(
            {"open": close, "high": close, "low": close, "close": close, "volume": 1e6},
            index=index).assign(ticker=ticker, source="test"))
    yield conn
    conn.close()


def _event(db, ticker, day):
    store.write(db, "events", pd.DataFrame([{
        "ticker": ticker, "signal_date": day, "insider_buy": 1, "flow": 0, "ownership": 0,
        "congress": 0, "mkt_cap": 1e9, "close": 20.0, "what": "", "what_parts": "[]",
        "flags": "{}"}]))


def _filing(db, ticker, day, item, accession=None):
    store.write(db, "filings", pd.DataFrame([{
        "accession": accession or f"{ticker}-{day}-{item}", "ticker": ticker, "item": item,
        "form": "8-K", "filing_date": day, "accepted_at": f"{day}T20:00:00Z",
        "report_date": day}]))


# --------------------------------------------------------------------------- the arithmetic

def test_fisher_matches_a_hand_computed_table():
    """One hypergeometric sum, rather than a large dependency for a single number."""
    assert study.fisher_greater(0, 0, 0, 0) == 1.0
    assert study.fisher_greater(5, 0, 0, 5) == pytest.approx(1 / 252, abs=1e-6)
    assert study.fisher_greater(1, 1, 1, 1) == pytest.approx(5 / 6, abs=1e-6)
    # lopsided towards the events is small; the other way round is not
    assert study.fisher_greater(20, 80, 5, 95) < 0.01
    assert study.fisher_greater(5, 95, 20, 80) > 0.99


def test_it_is_one_sided_and_says_so():
    """The hypothesis is directional — this kind of news shows up MORE around these events — and a
    two-sided test would answer a question nobody asked."""
    assert study.fisher_greater(2, 8, 8, 2) > study.fisher_greater(8, 2, 2, 8)


# --------------------------------------------------------------------------- the control group

def test_placebos_come_from_the_same_companies(db):
    """Not "events against the market" but "events against other days at these same companies".
    Companies that attract insider buying file differently from the average company, and without
    that control the study measures which companies are in the sample."""
    _event(db, "AAA", "2026-09-10")
    _filing(db, "AAA", "2026-09-05", "5.02")
    sample = study.build_sample(db)
    assert set(sample.placebos["ticker"]) == {"AAA"}
    assert len(sample.placebos) == study.PLACEBOS_PER_TICKER


def test_a_placebo_is_never_near_a_real_event(db):
    _event(db, "AAA", "2026-09-10")
    _filing(db, "AAA", "2026-09-05", "5.02")
    sample = study.build_sample(db)
    real = pd.Timestamp("2026-09-10")
    assert all(abs((d - real).days) > study.FAR_FROM_EVENT_DAYS
               for d in sample.placebos["signal_date"])


def test_events_whose_company_has_no_filings_are_left_out_and_counted(db):
    _event(db, "AAA", "2026-09-10")
    _event(db, "BBB", "2026-09-10")
    _filing(db, "AAA", "2026-09-05", "5.02")
    sample = study.build_sample(db)
    assert sample.total == 2 and sample.measurable == 1


# --------------------------------------------------------------------------- the direction of time

def test_nothing_filed_after_a_signal_can_count_towards_it(db):
    """An 8-K cannot be back-dated, which is the whole reason this data was chosen. It would be a
    waste to throw that away by looking forward."""
    _event(db, "AAA", "2026-09-10")
    _filing(db, "AAA", "2026-09-20", "5.02")          # after the signal
    seen, n = study._seen(db, study.build_sample(db).events, study.WINDOW_DAYS)
    assert seen == {} and n == 1


def test_only_the_window_before_counts(db):
    _event(db, "AAA", "2026-09-10")
    _filing(db, "AAA", "2026-09-05", "5.02")          # inside 30 days
    _filing(db, "AAA", "2026-06-01", "3.01")          # long before
    seen, _n = study._seen(db, study.build_sample(db).events, study.WINDOW_DAYS)
    assert set(seen) == {"5.02"}


def test_routine_items_never_enter_the_comparison(db):
    """9.01 marks that documents are attached and rides along with almost everything. Counting it
    as news would drown the codes that mean something."""
    _event(db, "AAA", "2026-09-10")
    _filing(db, "AAA", "2026-09-05", "9.01")
    _filing(db, "AAA", "2026-09-05", "5.07")
    seen, _n = study._seen(db, study.build_sample(db).events, study.WINDOW_DAYS)
    assert seen == {}


# --------------------------------------------------------------------------- the correction

def test_every_item_compared_is_counted_as_a_test(db):
    """Fifteen comparisons against 0.05 finds something roughly half the time on noise alone."""
    from miratrade import attempts

    for i in range(30):
        day = date(2026, 6, 1) + timedelta(days=i * 3)
        _event(db, "AAA", day.isoformat())
        for item in ("5.02", "1.01", "3.02"):
            _filing(db, "AAA", (day - timedelta(days=5)).isoformat(), item,
                    accession=f"a{i}{item}")
    table = study.compare(db, study.build_sample(db), min_observed=1)
    assert len(table)
    assert table["alpha"].iloc[0] == pytest.approx(attempts.sidak(len(table)))
    assert table["alpha"].iloc[0] < 0.05          # always stricter than the uncorrected level


def test_an_item_too_rare_to_judge_is_dropped_rather_than_reported(db):
    _event(db, "AAA", "2026-09-10")
    _filing(db, "AAA", "2026-09-05", "4.02")
    assert study.compare(db, study.build_sample(db)).empty   # one observation is not a finding


# --------------------------------------------------------------------------- the split

def test_the_window_is_split_in_time_never_at_random(db):
    """Splitting these rows randomly would put the same week on both sides of the fence and call
    the second half a confirmation of the first."""
    for i in range(10):
        _event(db, "AAA", (date(2026, 1, 1) + timedelta(days=i * 20)).isoformat())
    _filing(db, "AAA", "2026-01-01", "5.02")
    sample = study.build_sample(db)
    early, late = study.split(sample, train_fraction=0.6)

    assert early.events["signal_date"].max() < late.events["signal_date"].min()
    assert len(early.events) + len(late.events) == len(sample.events)


def test_the_verdict_says_nothing_when_there_is_nothing(db):
    said = study.verdict({"sample": study.build_sample(db), "all": pd.DataFrame(),
                          "discovery": pd.DataFrame(), "confirmation": pd.DataFrame()})
    assert "Not enough" in said


def test_surviving_only_the_whole_window_is_reported_as_the_weaker_claim(db):
    """A result that appears over the whole window but not in both halves is a result about a
    period. Saying so is the difference between a study and a press release."""
    whole = pd.DataFrame([{"item": "3.02", "survives": True}])
    empty = pd.DataFrame([{"item": "3.02", "survives": False}])
    said = study.verdict({"sample": None, "all": whole, "discovery": empty, "confirmation": empty})
    assert "Nothing survives in both halves" in said and "weaker claim" in said


def test_placebos_are_matched_to_the_same_point_in_the_quarter(db):
    """The control that decided the whole study. Insiders may only buy in the window that opens
    after results, so events pile up a few weeks after a 2.02 by construction — and everything else
    filed in those weeks comes along for free. Matching on it took results announcements from 52 %
    against 29 % to 63.7 % against 63.8 %: no difference at all."""
    # Quarterly results going back well before the first event, so that a placebo day also has a
    # last announcement to be measured from. Without that history its phase is unknown, and an
    # unknown is dropped rather than guessed — which the next test is about.
    for q in range(10):
        _filing(db, "AAA", (date(2025, 1, 15) + timedelta(days=q * 91)).isoformat(), "2.02",
                accession=f"q{q}")
    for i in range(6):
        _event(db, "AAA", (date(2026, 3, 1) + timedelta(days=i * 30)).isoformat())

    matched = study.match_on_cycle(db, study.build_sample(db))
    assert len(matched.events) and len(matched.placebos)
    for _, event in matched.events.iterrows():
        near = matched.placebos[matched.placebos["ticker"] == event["ticker"]]
        assert ((near["since"] - event["since"]).abs() <= study.SAME_PHASE_DAYS).any()


def test_a_day_with_no_known_results_announcement_is_dropped_not_guessed(db):
    """No 2.02 on file means the quarter's clock is unknown, and an unknown is not a zero."""
    _event(db, "AAA", "2026-09-10")
    _filing(db, "AAA", "2026-09-05", "5.02")          # no 2.02 anywhere
    assert study.days_since_earnings(db, study.build_sample(db).events).isna().all()
    assert study.match_on_cycle(db, study.build_sample(db)).events.empty


def test_the_report_keeps_the_uncontrolled_numbers_too(db):
    """Both are shown on purpose: the difference between them IS the finding."""
    _event(db, "AAA", "2026-09-10")
    _filing(db, "AAA", "2026-09-05", "2.02")
    out = study.report(db)
    assert {"all", "without_control", "unmatched", "discovery", "confirmation"} <= set(out)
