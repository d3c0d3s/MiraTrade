"""Running the rules again over data already downloaded.

The point of the engine is that a threshold becomes something you can try: change it, see what it
would have found over the whole history, in seconds and without asking the SEC for the same two
months of filings again. So the tests are about the two things that make that true — the same
settings give the same events, a stricter setting gives fewer — and about the one thing that would
quietly break it: reaching for the network.
"""
from datetime import date, timedelta

import pandas as pd
import pytest

from miratrade import store
from miratrade.config import Config
from miratrade.reprocess import (candidates, flow_between, reprocess, replace_events, sources,
                                 window)

TODAY = date(2026, 9, 25)


def _bars(last: date = TODAY, days: int = 600, start: float = 40.0) -> pd.DataFrame:
    """A gently rising series ending on ``last``: enough history for the 200-day averages.

    Built backwards from the last day on purpose. Counting forwards from a start date means doing
    business-day arithmetic in one's head, and getting it wrong gives bars that stop before the
    filings — a panel with nothing to fire on, which looks exactly like a broken rule.
    """
    index = pd.bdate_range(end=pd.Timestamp(last), periods=days)
    close = pd.Series([start + i * 0.05 for i in range(days)], index=index)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": 3_000_000.0}, index=index)


@pytest.fixture
def loaded(tmp_path):
    """A store holding two months of filings and two years of bars for two companies."""
    db = store.connect(tmp_path / "market.db")
    for ticker in ("PFE", "ACME", "SPY"):
        store.write(db, "prices", _bars().assign(ticker=ticker, source="test"))
    store.write(db, "insiders", pd.DataFrame([
        # a big purchase by two people at PFE: an event under any sane setting
        {"accession": "a1", "filing_date": "2026-09-21", "trade_date": "2026-09-18",
         "ticker": "PFE", "owner_cik": "1", "owner": "A Director", "code": "P",
         "shares": 20_000.0, "price": 60.0, "value": 1_200_000.0, "is_officer": 1},
        {"accession": "a2", "filing_date": "2026-09-22", "trade_date": "2026-09-18",
         "ticker": "PFE", "owner_cik": "2", "owner": "The CFO", "code": "P",
         "shares": 10_000.0, "price": 60.0, "value": 600_000.0, "is_officer": 1},
        # and a small one at ACME, which a higher minimum should drop
        {"accession": "a3", "filing_date": "2026-09-22", "trade_date": "2026-09-19",
         "ticker": "ACME", "owner_cik": "3", "owner": "A Director", "code": "P",
         "shares": 900.0, "price": 60.0, "value": 54_000.0, "is_officer": 0},
    ]))
    yield db
    db.close()


def _run(db, **kw):
    return reprocess(db, end=TODAY, log=lambda _m: None, **kw)


# --------------------------------------------------------------------------- it does the work

def test_the_events_are_rebuilt_from_the_store_alone(loaded):
    out = _run(loaded, days=30)
    assert "PFE" in set(out["events"]["ticker"])
    assert out["written"] == len(out["events"])

    stored = store.read(loaded, "events")
    assert set(stored["ticker"]) == set(out["events"]["ticker"])
    assert stored["insider_buy"].astype(bool).all()


def test_nothing_is_downloaded(loaded, monkeypatch):
    """Not an implementation detail: it is the whole reason the engine exists. Every way out to the
    network is made to explode, and the run has to finish anyway."""
    import socket
    import urllib.request

    import requests

    def refuse(*a, **k):
        raise AssertionError("reprocess tried to reach the network")

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", refuse)
    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)

    assert len(_run(loaded, days=30)["events"])


def test_the_same_settings_give_the_same_events(loaded):
    first = _run(loaded, days=30)["events"]
    again = _run(loaded, days=30)["events"]
    assert list(first["ticker"]) == list(again["ticker"])
    assert list(first["signal_date"]) == list(again["signal_date"])


def test_a_stricter_minimum_finds_fewer_without_fetching_anything_again(loaded):
    """What the engine is for. The filings do not change; the rule does."""
    loose = Config()
    loose.insider.min_value_usd = 25_000
    strict = Config()
    strict.insider.min_value_usd = 500_000

    wide = set(_run(loaded, days=30, cfg=loose)["events"]["ticker"])
    narrow = set(_run(loaded, days=30, cfg=strict)["events"]["ticker"])
    assert "ACME" in wide and "ACME" not in narrow        # $54,000 no longer counts
    assert "PFE" in narrow                                # $1.2M still does


def test_trying_a_setting_can_leave_the_table_alone(loaded):
    _run(loaded, days=30)
    before = store.read(loaded, "events")
    assert len(before)

    strict = Config()
    strict.insider.min_value_usd = 50_000_000              # nothing survives this
    out = _run(loaded, days=30, cfg=strict, write=False)
    assert not len(out["events"]) and out["written"] == 0
    assert len(store.read(loaded, "events")) == len(before)


def test_events_a_stricter_rule_no_longer_finds_are_removed(loaded):
    """A row the settings say is not a signal must not stay in the table looking current."""
    _run(loaded, days=30)
    assert "ACME" in set(store.read(loaded, "events")["ticker"])

    strict = Config()
    strict.insider.min_value_usd = 500_000
    out = _run(loaded, days=30, cfg=strict)
    assert out["replaced"] >= 1
    assert "ACME" not in set(store.read(loaded, "events")["ticker"])


# --------------------------------------------------------------------------- the window

def test_the_window_ends_at_the_last_day_stored_not_today(loaded):
    """"The last 30 days" has to mean the last 30 days that were downloaded. Counting back from
    today reports an empty window as though nothing had been filed."""
    last_filing = date(2026, 9, 22)                        # the newest one the fixture stores
    _first, since, end = window(loaded, days=30)
    assert end == last_filing and end != date.today()
    assert since == last_filing - timedelta(days=30)


def test_no_days_means_everything_stored(loaded):
    first, since, end = window(loaded, days=None)
    assert end == date(2026, 9, 22) and since <= end and first < since


def test_an_empty_store_gives_a_window_rather_than_a_crash(tmp_path):
    db = store.connect(tmp_path / "empty.db")
    first, since, end = window(db)
    assert first < since <= end
    out = reprocess(db, log=lambda _m: None)
    assert not len(out["events"])
    db.close()


# --------------------------------------------------------------------------- what it reads

def test_insiders_come_back_cleaned_the_way_a_scan_cleans_them(loaded):
    """The table holds filings as filed, typos included. Anything that totals has to filter first."""
    store.write(loaded, "insiders", pd.DataFrame([
        {"accession": "bad", "filing_date": "2026-09-23", "ticker": "NONE", "code": "P",
         "shares": 1.0, "price": 24_035_774.0, "value": 24_035_774.0}]))
    got = sources(loaded, TODAY - timedelta(days=60), TODAY)
    assert "NONE" not in set(got["insiders"]["ticker"])


def test_the_same_contract_from_two_sources_is_one_row(loaded):
    """The primary key holds `source`, so a broker snapshot and a scan CSV can both be there.
    Counting both would double the day's volume, which is the number the flow rules judge on."""
    both = pd.DataFrame([
        {"date": "2026-09-24", "ticker": "PFE", "expiry": "2026-11-20", "type": "call",
         "strike": 65.0, "volume": 4000.0, "open_interest": 100.0, "premium": 1.0,
         "underlying": 60.0, "source": "scan"},
        {"date": "2026-09-24", "ticker": "PFE", "expiry": "2026-11-20", "type": "call",
         "strike": 65.0, "volume": 4000.0, "open_interest": 100.0, "premium": 1.0,
         "underlying": 60.0, "bid": 0.95, "ask": 1.05, "source": "etrade"}])
    store.write(loaded, "option_flow", both)

    flow = flow_between(loaded, date(2026, 9, 1), TODAY)
    assert len(flow) == 1
    assert float(flow.iloc[0]["bid"]) == 0.95             # the quoted one wins: a check can use it


def test_a_company_with_no_bars_is_skipped_and_said_out_loud(loaded):
    """It cannot be judged, and an event list that is quietly short is worse than one that says so."""
    store.write(loaded, "insiders", pd.DataFrame([
        {"accession": "n1", "filing_date": "2026-09-22", "trade_date": "2026-09-20",
         "ticker": "NOBARS", "owner_cik": "9", "code": "P", "shares": 10_000.0, "price": 30.0,
         "value": 300_000.0}]))
    said = []
    out = reprocess(loaded, days=30, end=TODAY, log=said.append)
    assert "NOBARS" in out["tickers"]
    assert "NOBARS" not in set(out["events"]["ticker"])
    assert "no price bars stored" in " ".join(said)


def test_the_universe_is_the_companies_with_something_fresh(loaded):
    src = sources(loaded, TODAY - timedelta(days=60), TODAY)
    found = candidates(src, TODAY - timedelta(days=30))
    assert found == {"PFE", "ACME"}
    assert candidates(src, TODAY + timedelta(days=1)) == set()   # nothing filed after today


def test_replacing_records_the_days_as_covered(loaded):
    out = _run(loaded, days=10)
    covered = store.covered(loaded, "events")
    assert f"{TODAY:%Y-%m-%d}" in covered or len(covered) > 0
    assert out["written"] >= 0
