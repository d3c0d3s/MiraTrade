"""The earnings calendar: parse it, store it, and answer the one question a call has to ask —
does this contract have to sit through a report?"""
from datetime import date

import pandas as pd

import pytest

from miratrade import store
from miratrade.data.earnings import (covered_tickers, crosses_earnings, days_until, next_report,
                                     parse_calendar, parse_history, store_earnings, update_calendar)

# The CSV Alpha Vantage really returns for EARNINGS_CALENDAR, trimmed.
CALENDAR = ("symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay\r\n"
            "ADXN,ADDEX THERAPEUTICS LIMITED,2026-09-28,2026-06-30,,USD,pre-market\r\n"
            "PFE,PFIZER INC,2026-11-03,2026-09-30,0.61,USD,pre-market\r\n"
            "AAPL,APPLE INC,2026-10-29,2026-09-30,2.35,USD,post-market\r\n"
            ",BROKEN ROW WITH NO SYMBOL,2026-10-01,2026-09-30,,USD,\r\n"
            "NODATE,NO REPORT DATE CORP,,2026-09-30,,USD,\r\n")

# The JSON EARNINGS returns, trimmed to two quarters.
HISTORY = {"symbol": "IBM", "quarterlyEarnings": [
    {"fiscalDateEnding": "2026-06-30", "reportedDate": "2026-07-22", "reportedEPS": "2.93",
     "estimatedEPS": "2.93", "surprise": "0", "surprisePercentage": "0", "reportTime": "post-market"},
    {"fiscalDateEnding": "2026-03-31", "reportedDate": "2026-04-23", "reportedEPS": "1.60",
     "estimatedEPS": "1.42", "surprise": "0.18", "surprisePercentage": "12.6761",
     "reportTime": "post-market"},
    {"fiscalDateEnding": "2025-12-31", "reportedDate": "", "reportedEPS": "3.5"}]}


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / "market.db")
    yield conn
    conn.close()


def test_the_calendar_parses_and_skips_rows_that_say_nothing():
    rows = parse_calendar(CALENDAR)
    assert sorted(rows["ticker"]) == ["AAPL", "ADXN", "PFE"]     # no symbol and no date are dropped
    pfe = rows[rows["ticker"] == "PFE"].iloc[0]
    assert pfe["report_date"] == "2026-11-03" and pfe["when_of_day"] == "pre-market"
    assert pfe["estimate"] == 0.61 and pd.isna(pfe["reported"])
    assert pd.isna(rows[rows["ticker"] == "ADXN"].iloc[0]["estimate"])  # blank is not zero
    assert set(rows["source"]) == {"alphavantage"}


def test_the_reported_history_parses_with_its_surprises():
    rows = parse_history(HISTORY)
    assert len(rows) == 2                                        # the quarter with no date is dropped
    latest = rows.iloc[0]
    assert latest["ticker"] == "IBM" and latest["report_date"] == "2026-07-22"
    assert latest["reported"] == 2.93 and latest["surprise_pct"] == 0.0
    assert rows.iloc[1]["surprise_pct"] == pytest.approx(12.6761)
    assert parse_history({"symbol": "X"}).empty


def test_a_round_trip_keeps_the_dates_as_dates(db):
    assert store_earnings(parse_calendar(CALENDAR), db) == 3
    back = store.read(db, "earnings")
    assert back["report_date"].dtype.kind == "M"
    assert covered_tickers(db) == 3


def test_refreshing_the_calendar_replaces_rather_than_duplicates(db):
    update_calendar(db, key="test", opener=lambda *a, **k: _Response(CALENDAR), log=lambda _m: None)
    update_calendar(db, key="test", opener=lambda *a, **k: _Response(CALENDAR), log=lambda _m: None)
    assert len(store.read(db, "earnings")) == 3
    assert store.notes(db)["earnings_calendar_updated"]


def test_a_refusal_is_raised_instead_of_stored_as_nothing(db):
    """Alpha Vantage answers a rejected request with 200 and a JSON note, so a body that is not the
    CSV has to be read rather than quietly becoming an empty calendar."""
    note = '{"Information": "the demo API key is for demo purposes only"}'
    with pytest.raises(RuntimeError, match="refused the request"):
        update_calendar(db, key="test", opener=lambda *a, **k: _Response(note), log=lambda _m: None)
    assert len(store.read(db, "earnings")) == 0


# --------------------------------------------------------------------------- the question

def test_it_says_whether_a_contract_would_sit_through_a_report(db):
    store_earnings(parse_calendar(CALENDAR), db)
    today = date(2026, 9, 27)

    assert next_report(db, "PFE", today) == date(2026, 11, 3)
    assert days_until(db, "PFE", today) == 37
    assert next_report(db, "pfe", today) == date(2026, 11, 3)        # case does not matter

    # a 45-day contract expires 11 November, after Pfizer reports on 3 November
    assert crosses_earnings(db, "PFE", today, date(2026, 11, 11)) == date(2026, 11, 3)
    # a 30-day one expires before it, and is a different trade
    assert crosses_earnings(db, "PFE", today, date(2026, 10, 27)) is None


def test_not_knowing_is_reported_as_not_knowing_not_as_safety(db):
    """A missing calendar and a company that never reports look the same from here. The absence of a
    warning must not read as a promise, which is why the callers say so in words."""
    store_earnings(parse_calendar(CALENDAR), db)
    assert next_report(db, "LEN", date(2026, 9, 27)) is None
    assert days_until(db, "LEN", date(2026, 9, 27)) is None
    assert crosses_earnings(db, "LEN", date(2026, 9, 27), date(2026, 12, 31)) is None


def test_a_report_already_past_is_not_the_next_one(db):
    store_earnings(parse_calendar(CALENDAR), db)
    after = date(2026, 11, 4)
    assert next_report(db, "PFE", after) is None                   # 3 November is behind us
    assert crosses_earnings(db, "PFE", after, date(2026, 12, 31)) is None


def test_the_earliest_report_in_the_window_is_the_one_that_matters(db):
    store_earnings(pd.DataFrame([
        {"ticker": "ACME", "report_date": "2026-11-20", "source": "x"},
        {"ticker": "ACME", "report_date": "2026-10-15", "source": "x"}]), db)
    assert crosses_earnings(db, "ACME", date(2026, 9, 27), date(2026, 12, 1)) == date(2026, 10, 15)


class _Response:
    """The context-manager shape urlopen returns."""

    def __init__(self, text):
        self._text = text.encode("utf-8")

    def read(self):
        return self._text

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


# --------------------------------------------------------------------------- the free, official source

SUBMISSIONS = {"tickers": ["PFE"], "filings": {"recent": {
    "form": ["8-K", "10-Q", "8-K", "8-K", "8-K", "4"],
    "filingDate": ["2026-08-04", "2026-08-05", "2026-06-18", "2026-05-05", "2026-02-03", "2026-01-09"],
    "items": ["2.02,9.01", None, "7.01", "2.02,9.01", "2.02", None],
    "reportDate": ["2026-06-30", "2026-06-30", "2026-06-18", "2026-03-31", "2025-12-31", ""]}}}


def test_an_earnings_announcement_is_an_8k_carrying_item_202():
    """The 8-K filed under Item 2.02 IS the results announcement, and its filing date is the day the
    numbers became public — the only date a backtest may condition on. Free, and the primary source."""
    from miratrade.data.earnings import parse_submissions

    rows = parse_submissions(SUBMISSIONS)
    assert rows["report_date"].tolist() == ["2026-08-04", "2026-05-05", "2026-02-03"]
    assert set(rows["ticker"]) == {"PFE"} and set(rows["source"]) == {"sec_8k_2.02"}
    # the 10-Q, the 8-K about something else (item 7.01) and the Form 4 are all left out
    assert len(rows) == 3


def test_a_company_with_no_results_8k_gives_nothing_rather_than_failing():
    from miratrade.data.earnings import parse_submissions

    assert parse_submissions({"tickers": ["X"], "filings": {"recent": {"form": ["4"],
                                                                      "filingDate": ["2026-01-01"],
                                                                      "items": [None]}}}).empty
    assert parse_submissions({"tickers": ["X"], "filings": {}}).empty
    assert parse_submissions({}).empty


def test_days_to_earnings_only_ever_looks_forward(db):
    """It must carry nothing that was not knowable on the day, or a backtest conditioning on it would
    be reading the future."""
    from miratrade.data.earnings import days_to_earnings

    store_earnings(pd.DataFrame([
        {"ticker": "ACME", "report_date": "2026-02-03", "source": "sec_8k_2.02"},
        {"ticker": "ACME", "report_date": "2026-05-05", "source": "sec_8k_2.02"}]), db)

    days = days_to_earnings(db, "ACME", pd.DatetimeIndex(
        ["2026-01-01", "2026-02-03", "2026-02-04", "2026-05-05", "2026-05-06"]))
    assert days.iloc[0] == 33          # 1 January to 3 February
    assert days.iloc[1] == 0           # the day itself still counts as ahead
    assert days.iloc[2] == 90          # the next one, not the one just gone
    assert days.iloc[3] == 0
    assert pd.isna(days.iloc[4])       # nothing known after the last announcement: not zero

    assert days_to_earnings(db, "NOPE", pd.DatetimeIndex(["2026-01-01"])).isna().all()


def test_the_conditions_leave_an_unknown_alone_instead_of_reading_it_as_false(db):
    """A condition that quietly becomes False when its data is missing would let the miner build a
    rule out of absent data."""
    import numpy as np

    from miratrade.backtest import build_panel, conditions
    from miratrade.data.earnings import days_to_earnings
    from miratrade.synthetic import make_market

    store_earnings(pd.DataFrame([{"ticker": "T01", "report_date": "2026-01-15",
                                  "source": "sec_8k_2.02"}]), db)
    prices, insiders, flow = make_market()
    known = {"T01": days_to_earnings(db, "T01", prices["T01"].index)}

    with_dates = build_panel(prices, insiders, flow, earnings=known)
    without = build_panel(prices, insiders, flow)
    assert "days_to_earnings" in with_dates["T01"].columns
    assert "days_to_earnings" not in without["T01"].columns

    # where the number is known the four conditions appear and agree with each other
    row = with_dates["T01"].iloc[0].copy()
    for days, expected in ((3, {"earn:within_7d", "earn:within_21d", "earn:before_expiry"}),
                           (14, {"earn:within_21d", "earn:before_expiry"}),
                           (40, {"earn:before_expiry"}),
                           (200, {"earn:clear"})):
        row["days_to_earnings"] = days
        fired = {k for k, v in conditions(row).items() if k.startswith("earn:") and v}
        assert fired == expected, days

    row["days_to_earnings"] = np.nan
    assert not any(k.startswith("earn:") for k in conditions(row))   # absent, not False
