"""Events in the shared market database: a round trip must not change their shape, and the filters
the screens offer have to narrow in SQL exactly as the in-memory ones did."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from miratrade import store
from miratrade.scan import (events_to_rows, filter_events, load_events, rows_to_events, store_scan,
                            stored_days)

END = date(2026, 9, 25)


def _events() -> pd.DataFrame:
    """Three events shaped the way a scan really produces them, sizes included."""
    return pd.DataFrame([
        {"ticker": "PFE", "signal_date": pd.Timestamp("2026-09-24"), "close": 26.5,
         "mkt_cap": 150e9, "what": "1 insider bought $1.0M",
         "what_parts": '[["1 insider bought {amount}", {"amount": 1000920.0}]]',
         "event:insider_buy": True, "event:flow": False, "event:13dg": False,
         "ins:exec_buy": True, "ins:big_250k+": True, "trend:up": True, "rsi:<40": False,
         "events_in_window": 2},
        {"ticker": "KLTR", "signal_date": pd.Timestamp("2026-09-20"), "close": 3.1,
         "mkt_cap": 400e6, "what": "ACTIVIST LP filed a 13D", "what_parts": "[]",
         "event:insider_buy": False, "event:flow": False, "event:13dg": True,
         "ins:exec_buy": False, "ins:big_250k+": False, "trend:up": False, "rsi:<40": True,
         "events_in_window": 1},
        {"ticker": "ACME", "signal_date": pd.Timestamp("2026-09-01"), "close": 10.2,
         "mkt_cap": np.nan, "what": "options with unusual volume", "what_parts": "[]",
         "event:insider_buy": False, "event:flow": True, "event:13dg": False,
         "ins:exec_buy": False, "ins:big_250k+": False, "trend:up": True, "rsi:<40": False,
         "events_in_window": 1},
    ])


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / "market.db")
    yield conn
    conn.close()


def test_an_event_survives_the_round_trip_with_every_flag(db):
    original = _events()
    assert store.write(db, "events", events_to_rows(original)) == 3

    back = load_events(db)
    assert len(back) == 3
    pfe = back[back["ticker"] == "PFE"].iloc[0]
    assert pfe["close"] == 26.5 and pfe["mkt_cap"] == 150e9
    assert pfe["what"] == "1 insider bought $1.0M"
    assert "1 insider bought" in pfe["what_parts"]          # the pieces, for translating on screen
    assert bool(pfe["event:insider_buy"]) and not bool(pfe["event:13dg"])
    assert bool(pfe["ins:exec_buy"]) and bool(pfe["trend:up"]) and not bool(pfe["rsi:<40"])
    assert pfe["events_in_window"] == 2                    # a flag that is not a boolean
    assert pfe["signal_date"] == pd.Timestamp("2026-09-24")


def test_a_new_condition_needs_no_migration(db):
    """Flags travel as JSON, so a condition invented tomorrow stores and reads without a schema
    change — which is the whole reason they are not columns."""
    events = _events()
    events["cong:committee_match"] = [True, False, False]
    store.write(db, "events", events_to_rows(events))

    back = load_events(db)
    assert bool(back[back["ticker"] == "PFE"].iloc[0]["cong:committee_match"])
    assert store.version(db) == store.SCHEMA_VERSION       # unchanged


def test_running_the_same_scan_again_replaces_its_events(db):
    store.write(db, "events", events_to_rows(_events()))
    again = _events()
    again.loc[0, "close"] = 27.0
    store.write(db, "events", events_to_rows(again))

    back = load_events(db)
    assert len(back) == 3                                  # one row per ticker and day, not six
    assert back[back["ticker"] == "PFE"].iloc[0]["close"] == 27.0


# --------------------------------------------------------------------------- the filters

def test_the_window_counts_from_the_last_day_downloaded_not_from_today(db):
    """Asking for 7 days must mean the last 7 days that were downloaded. Counting from today would
    empty the list whenever the data is a few days old."""
    store.write(db, "events", events_to_rows(_events()))
    assert len(load_events(db, days=7)) == 2               # 24 and 20 September, not 1 September
    assert len(load_events(db, days=30)) == 3
    assert len(load_events(db, days=None)) == 3


def test_the_size_filter_leaves_out_an_event_with_no_size_at_all(db):
    store.write(db, "events", events_to_rows(_events()))
    assert sorted(load_events(db, cap_tier="all")["ticker"]) == ["ACME", "KLTR", "PFE"]
    assert load_events(db, cap_tier="large")["ticker"].tolist() == ["PFE"]
    assert load_events(db, cap_tier="small")["ticker"].tolist() == ["KLTR"]
    assert load_events(db, cap_tier="mega")["ticker"].tolist() == []
    # ACME has no market capitalisation, so only "all" keeps it
    assert "ACME" not in load_events(db, cap_tier="mid_plus")["ticker"].tolist()


def test_the_kind_of_event_narrows_and_an_unknown_kind_shows_nothing(db):
    store.write(db, "events", events_to_rows(_events()))
    assert load_events(db, kinds=("event:insider_buy",))["ticker"].tolist() == ["PFE"]
    assert load_events(db, kinds=("event:13dg",))["ticker"].tolist() == ["KLTR"]
    assert sorted(load_events(db, kinds=("event:flow", "event:13dg"))["ticker"]) == ["ACME", "KLTR"]
    assert load_events(db, kinds=("event:nonsense",))["ticker"].tolist() == []


def test_the_ticker_filter_takes_one_or_several(db):
    store.write(db, "events", events_to_rows(_events()))
    assert load_events(db, ticker="pfe")["ticker"].tolist() == ["PFE"]
    assert sorted(load_events(db, ticker="PFE, ACME")["ticker"]) == ["ACME", "PFE"]
    assert load_events(db, ticker="NOPE")["ticker"].tolist() == []
    assert len(load_events(db, ticker="  ")) == 3


def test_the_filters_combine_and_the_newest_event_comes_first(db):
    store.write(db, "events", events_to_rows(_events()))
    rows = load_events(db, days=30, cap_tier="large", kinds=("event:insider_buy",))
    assert rows["ticker"].tolist() == ["PFE"]
    everything = load_events(db)
    assert everything["signal_date"].tolist() == sorted(everything["signal_date"], reverse=True)


def test_the_sql_filters_agree_with_the_in_memory_ones_they_replace(db):
    """The screen used to narrow a saved CSV in pandas. The answers must not change."""
    events = _events()
    store.write(db, "events", events_to_rows(events))
    for days in (None, 7, 30, 365):
        for tier in ("all", "large", "small", "mid_plus"):
            in_memory = filter_events(events, days=days, cap_tier=tier, end=END)
            in_sql = load_events(db, days=days, cap_tier=tier, end=END)
            assert sorted(in_memory["ticker"]) == sorted(in_sql["ticker"]), (days, tier)


def test_nothing_stored_is_an_empty_answer_not_a_failure(db):
    assert len(load_events(db)) == 0
    assert len(load_events(db, days=7, cap_tier="mega", ticker="PFE")) == 0
    assert stored_days(db) == 0
    assert len(rows_to_events(pd.DataFrame())) == 0
    assert "ticker" in rows_to_events(pd.DataFrame()).columns      # empty, but still the right shape
    assert len(events_to_rows(pd.DataFrame())) == 0
    assert len(events_to_rows(None)) == 0


def test_a_whole_scan_goes_in_with_its_prices_and_the_days_it_covered(db):
    idx = pd.date_range("2026-09-21", periods=5, freq="B")
    bars = pd.DataFrame({"open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "volume": 1e6},
                        index=idx)
    bars.index.name = "date"
    written = store_scan({"events": _events(), "prices": {"PFE": bars},
                          "since": date(2026, 9, 21), "end": date(2026, 9, 25)}, db)

    # it reports every table it wrote, including the raw filings behind the events
    assert written["events"] == 3 and written["prices"] == 5
    assert set(written) >= {"events", "prices", "ownership", "shares", "short_volume"}
    assert len(store.prices(db, ["PFE"])["PFE"]) == 5
    assert store.covered(db, "events") == {"2026-09-21", "2026-09-22", "2026-09-23",
                                           "2026-09-24", "2026-09-25"}
    assert stored_days(db) == 24                  # 1 to 24 September inclusive


def test_a_scan_with_no_events_still_records_that_it_looked(db):
    store_scan({"events": pd.DataFrame(), "prices": {}, "since": date(2026, 9, 21),
                "end": date(2026, 9, 22)}, db)
    assert len(store.covered(db, "events")) == 2 and len(load_events(db)) == 0


def test_the_snapshot_universe_comes_from_events_that_were_already_known(db):
    """A broker chain is one request per ticker, so the universe is a decision. Taking it from the
    events already stored looks only at what was knowable on the day — no outcome is involved — so
    it cannot leak lookahead into a later backtest."""
    from miratrade import store
    from miratrade.flow import flow_universe

    events = _events()
    events = pd.concat([events, events.assign(signal_date=pd.Timestamp("2026-09-23"),
                                              ticker="PFE")], ignore_index=True)
    store.write(db, "events", events_to_rows(events))

    assert flow_universe(["pfe", "aapl"], 30, 60, db) == ["PFE", "AAPL"]      # named wins
    assert flow_universe(["a", "b", "c"], 30, 2, db) == ["A", "B"]            # and is capped

    chosen = flow_universe(None, 30, 60, db)
    assert chosen[0] == "PFE"                       # the busiest name first, so a cap keeps it
    assert sorted(chosen) == ["ACME", "KLTR", "PFE"]
    assert flow_universe(None, 30, 1, db) == ["PFE"]
    # the window counts back from the last event stored, not from today, so a short one still
    # finds the most recent names rather than nothing
    assert flow_universe(None, 1, 60, db) == ["PFE"]
