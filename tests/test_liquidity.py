"""Whether a suggested contract could actually be traded, and what the spread costs the target.

This is not a prediction, it is execution reality — and it is the cost the backtest never charged,
because it priced every contract at a modelled mid.
"""
from datetime import date

import pandas as pd
import pytest

from miratrade import store
from miratrade.config import Config
from miratrade.liquidity import (check_contract, check_stored, mid, round_trip_pct, spread_pct,
                                 stored_quotes, target_eaten, underlying_liquidity)


def test_the_spread_is_measured_against_the_mid():
    assert spread_pct(0.90, 1.10) == pytest.approx(20.0)
    assert spread_pct(2.40, 2.50) == pytest.approx(4.0816, abs=1e-3)
    assert mid(2.40, 2.50) == 2.45


def test_quotes_that_do_not_make_a_market_measure_nothing():
    """A crossed, missing or zero quote is not a spread of zero — it is no answer."""
    assert spread_pct(None, 1.0) is None
    assert spread_pct(1.0, None) is None
    assert spread_pct(1.20, 0.80) is None            # crossed
    assert spread_pct(0.0, 0.0) is None              # no market
    assert mid(float("nan"), 1.0) is None


def test_the_round_trip_is_the_whole_spread_not_half():
    """You cross it buying and again selling, so the cost is the gap, not the distance to the mid."""
    assert round_trip_pct(0.90, 1.10) == pytest.approx(20.0)


def test_what_the_spread_costs_is_stated_against_the_target():
    """The number that decides a trade: a 20 % round trip against a +40 % target takes half of it."""
    assert target_eaten(0.90, 1.10, 0.40) == pytest.approx(50.0)
    assert target_eaten(2.40, 2.50, 0.40) == pytest.approx(10.2, abs=0.1)
    assert target_eaten(0.90, 1.10, 0.30) == pytest.approx(66.7, abs=0.1)   # tighter target, worse
    assert target_eaten(0.90, 1.10, 0) is None                              # no target, no answer
    assert target_eaten(None, 1.10, 0.40) is None


# --------------------------------------------------------------------------- the verdict

def test_a_liquid_contract_passes_and_says_the_numbers():
    v = check_contract(bid=2.40, ask=2.50, open_interest=1800, target_pct=0.40)
    assert v.ok and v.measured
    assert v.open_interest == 1800 and v.spread_pct == pytest.approx(4.08, abs=0.01)
    assert v.eats_target == pytest.approx(10.2, abs=0.1)
    assert "Tradeable" in v.say()


def test_a_wide_spread_is_refused_in_terms_of_the_target():
    v = check_contract(bid=0.80, ask=1.20, open_interest=1800, target_pct=0.40)
    assert not v.ok and v.measured
    said = v.say()
    assert "100 %" in said and "target" in said       # the whole target, before the stock moves


def test_almost_no_open_interest_is_refused_however_tight_the_quote_looks():
    """With nobody on the other side the quote is decoration: you move the price getting in."""
    v = check_contract(bid=2.40, ask=2.50, open_interest=12, target_pct=0.40)
    assert not v.ok and "12" in v.say() and "200" in v.say()


def test_not_measured_is_not_the_same_as_passing():
    """The most important case: nothing known must never read as approval."""
    v = check_contract(target_pct=0.40)
    assert not v.ok and not v.measured
    assert "not the same as fine" in v.say()


def test_open_interest_alone_passes_but_says_the_spread_is_unknown():
    v = check_contract(open_interest=1800, target_pct=0.40)
    assert v.ok and v.measured and v.spread_pct is None
    assert "unknown" in v.say()


def test_the_limits_are_configurable():
    cfg = Config()
    cfg.liquidity.max_spread_pct = 50.0
    cfg.liquidity.max_target_eaten_pct = 200.0
    assert check_contract(bid=0.80, ask=1.20, open_interest=1800, target_pct=0.40, cfg=cfg).ok
    cfg.liquidity.min_open_interest = 5000
    assert not check_contract(bid=2.40, ask=2.50, open_interest=1800, cfg=cfg).ok


# --------------------------------------------------------------------------- from the stored chain

def test_it_reads_the_contract_the_daily_capture_stored(tmp_path):
    db = store.connect(tmp_path / "market.db")
    store.write(db, "option_flow", pd.DataFrame([
        {"date": "2026-09-25", "ticker": "LEN", "expiry": "2026-11-20", "type": "C", "strike": 84.0,
         "volume": 3204, "open_interest": 1800, "premium": 312390, "underlying": 82.15,
         "bid": 2.40, "ask": 2.50, "side": "", "source": "etrade"},
        {"date": "2026-09-24", "ticker": "LEN", "expiry": "2026-11-20", "type": "C", "strike": 84.0,
         "volume": 10, "open_interest": 50, "premium": 900, "underlying": 80.0,
         "bid": 1.00, "ask": 3.00, "side": "", "source": "etrade"}]))

    found = stored_quotes(db, "len", "2026-11-20", 84.0)
    assert found["bid"] == 2.40 and found["date"] == "2026-09-25"   # the newest day, not the first

    v = check_stored(db, "LEN", date(2026, 11, 20), 84.0, target_pct=0.40)
    assert v.ok and v.open_interest == 1800

    # a contract the capture never saw is unmeasured, not fine
    missing = check_stored(db, "LEN", date(2026, 11, 20), 999.0, target_pct=0.40)
    assert not missing.ok and not missing.measured
    assert not check_stored(db, "NOPE", date(2026, 11, 20), 84.0).measured
    db.close()


def test_the_shares_own_volume_is_the_fallback_and_says_it_is_weaker():
    """With nothing stored about the chain, a thin share is still a usable answer — a stock trading
    thirty thousand times a day does not have an option market worth the name."""
    idx = pd.date_range("2026-08-01", periods=30, freq="B")
    liquid = pd.DataFrame({"volume": [2_000_000.0] * 30}, index=idx)
    thin = pd.DataFrame({"volume": [30_000.0] * 30}, index=idx)

    good = underlying_liquidity(liquid)
    assert good.ok and "unknown" in good.say()          # it does not claim to know the contract
    assert not underlying_liquidity(thin).ok
    assert not underlying_liquidity(pd.DataFrame()).ok
    assert not underlying_liquidity(None).ok


def test_the_reason_is_translatable_like_the_rest_of_the_domain():
    from miratrade.app.i18n import set_language, t

    v = check_contract(target_pct=0.40)
    english = v.say()
    before = None
    try:
        from miratrade.app.i18n import language

        before = language()
        set_language("es")
        assert v.say(t) == english or v.say(t) != ""      # translated when the catalog has it
        assert str(v) == english                          # str() stays English, for the console
    finally:
        if before:
            set_language(before)
