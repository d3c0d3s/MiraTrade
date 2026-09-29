"""The once-a-day capture: run in the right window, once per session, and say what was lost.

A missed session cannot be repaired — open interest catches up on its own but the volume of a
session is only readable while that session is the last one — so noticing the gap is the feature.
"""
from datetime import date

import pandas as pd
import pytest

from miratrade import store
from miratrade.flow import SOURCE, daily_capture, missed_sessions, session_window

CHAIN = pd.DataFrame({"symbol": ["A  261016C00010000"], "underlying": ["A"], "type": ["C"],
                      "expiry": [pd.Timestamp("2026-10-16")], "dte": [20], "strike": [10.0],
                      "bid": [1.0], "ask": [1.2], "mark": [1.1], "delta": [0.6], "iv": [0.4],
                      "open_interest": [100], "volume": [300]})


class FakeBroker:
    name = "etrade"
    calls = 0

    def quotes(self, symbols):
        return {"A": type("Q", (), {"last": 11.0})()}

    def option_chain(self, symbol, a, b):
        FakeBroker.calls += 1
        return CHAIN


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / "market.db")
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def _reset():
    FakeBroker.calls = 0


# --------------------------------------------------------------------------- the window

@pytest.mark.parametrize("now, inside", [
    ("2026-09-28 22:30Z", True),    # Monday 18:30 New York: closed, the session is complete
    ("2026-09-29 07:00Z", True),    # Tuesday 03:00: still Monday's session on the wire
    ("2026-09-28 12:00Z", True),    # Monday 08:00: before the open, so Friday's is complete
    ("2026-09-28 15:00Z", False),   # Monday 11:00: a session is in progress
    ("2026-09-28 19:00Z", False),   # Monday 15:00: still in progress
    ("2026-09-26 15:00Z", True),    # Saturday: no session all day
    ("2026-09-27 18:53Z", True),    # Sunday afternoon: the safest moment of the week
])
def test_the_window_is_whenever_no_session_is_in_progress(now, inside):
    """Written as a plain 16:15-09:15 clock range this called a Sunday afternoon "outside the
    window", when it is exactly when Friday's session is final and safe to read."""
    assert session_window(now)[0] is inside


def test_the_window_explains_itself_either_way():
    assert "in progress" in session_window("2026-09-28 15:00Z")[1]
    assert "complete" in session_window("2026-09-28 22:30Z")[1]
    assert "Monday" in session_window("2026-09-28 22:30Z")[1]


# --------------------------------------------------------------------------- running once

def test_it_captures_once_and_then_leaves_the_session_alone(db):
    monday_evening = "2026-09-28 22:30Z"
    first = daily_capture(["A"], FakeBroker(), db=db, now=monday_evening, log=lambda _m: None)
    assert first["ran"] and first["session"] == date(2026, 9, 28) and first["rows"] == 1
    assert FakeBroker.calls == 1

    again = daily_capture(["A"], FakeBroker(), db=db, now=monday_evening, log=lambda _m: None)
    assert not again["ran"] and "already captured" in again["why"]
    assert FakeBroker.calls == 1                    # the broker was not asked a second time

    later = daily_capture(["A"], FakeBroker(), db=db, now="2026-09-29 07:00Z", log=lambda _m: None)
    assert not later["ran"]                         # 03:00 Tuesday is still Monday's session
    assert FakeBroker.calls == 1


def test_it_does_nothing_while_a_session_is_in_progress(db):
    out = daily_capture(["A"], FakeBroker(), db=db, now="2026-09-28 15:00Z", log=lambda _m: None)
    assert not out["ran"] and "in progress" in out["why"]
    assert FakeBroker.calls == 0 and len(store.read(db, "option_flow")) == 0


def test_force_captures_anyway_for_someone_who_means_it(db):
    out = daily_capture(["A"], FakeBroker(), db=db, now="2026-09-28 15:00Z", force=True,
                        log=lambda _m: None)
    assert out["ran"] and FakeBroker.calls == 1


def test_a_new_session_is_captured_the_next_evening(db):
    daily_capture(["A"], FakeBroker(), db=db, now="2026-09-28 22:30Z", log=lambda _m: None)
    out = daily_capture(["A"], FakeBroker(), db=db, now="2026-09-29 22:30Z", log=lambda _m: None)
    assert out["ran"] and out["session"] == date(2026, 9, 29)
    assert sorted(store.covered(db, SOURCE)) == ["2026-09-28", "2026-09-29"]


def test_with_no_tickers_it_says_so_instead_of_asking_the_broker(db):
    out = daily_capture([], FakeBroker(), db=db, now="2026-09-28 22:30Z", log=lambda _m: None)
    assert not out["ran"] and "no tickers" in out["why"]
    assert FakeBroker.calls == 0


# --------------------------------------------------------------------------- the missed days

def test_a_skipped_business_day_is_reported(db):
    store.mark_covered(db, SOURCE, [date(2026, 9, 21)], rows=1)      # Monday captured
    store.mark_covered(db, SOURCE, [date(2026, 9, 24)], rows=1)      # Thursday captured
    missed = missed_sessions(db, session=date(2026, 9, 25))
    assert missed == [date(2026, 9, 22), date(2026, 9, 23)]          # Tuesday and Wednesday lost


def test_the_weekend_is_not_a_missed_session(db):
    store.mark_covered(db, SOURCE, [date(2026, 9, 25)], rows=1)      # Friday
    assert missed_sessions(db, session=date(2026, 9, 28)) == []      # Monday: nothing in between


def test_days_before_the_first_capture_are_not_misses(db):
    """Nothing was running then, so it is not a gap. Only a gap after the first day counts."""
    store.mark_covered(db, SOURCE, [date(2026, 9, 24)], rows=1)
    assert missed_sessions(db, session=date(2026, 9, 25)) == []
    assert missed_sessions(db, session=date(2026, 9, 25), back=200) == []


def test_nothing_captured_yet_is_not_a_pile_of_misses(db):
    assert missed_sessions(db, session=date(2026, 9, 25)) == []


def test_the_capture_warns_about_what_was_lost_and_still_runs(db):
    store.mark_covered(db, SOURCE, [date(2026, 9, 24)], rows=1)      # Thursday only
    said = []
    out = daily_capture(["A"], FakeBroker(), db=db, now="2026-09-28 22:30Z", log=said.append)

    assert out["missed"] == [date(2026, 9, 25)]                      # Friday was lost
    assert out["ran"] is True                                       # and today is still captured
    warning = " ".join(said)
    assert "WARNING" in warning and "2026-09-25" in warning
    assert "gone" in warning                                        # it says it cannot be recovered
