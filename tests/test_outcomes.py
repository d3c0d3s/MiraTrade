from functools import lru_cache

import numpy as np
import pandas as pd
import pytest

from miratrade.backtest import build_panel
from miratrade.config import Config
from miratrade.outcomes import build_outcomes, call_outcome, mine_profiles, stock_outcome, summarize, variants
from miratrade.synthetic import make_market


def _arr(*xs):
    return tuple(np.array(x, dtype=float) for x in xs)


def test_stock_outcome_paths():
    o, h, l, c = _arr([100, 101, 110], [101, 131, 111], [99, 100, 109], [100, 130, 110])
    assert stock_outcome(o, h, l, c, 0, 2, 0.30, 0.20) == (1.0, 0.30)            # target touched
    o, h, l, c = _arr([100, 100], [101, 131], [99, 79], [100, 100])
    assert stock_outcome(o, h, l, c, 0, 1, 0.30, 0.20) == (-1.0, -0.20)          # both on one bar: stop
    o, h, l, c = _arr([100, 70], [101, 72], [99, 69], [100, 71])
    res, ret = stock_outcome(o, h, l, c, 0, 1, 0.30, 0.20)
    assert res == -1 and ret == pytest.approx(-0.30)                              # gap fills at the open
    o, h, l, c = _arr([100, 101], [102, 103], [99, 100], [100, 105])
    res, ret = stock_outcome(o, h, l, c, 0, 1, 0.30, 0.20)
    assert res == 0 and ret == pytest.approx(0.05)                                # neither: last close


def _bars(closes):
    idx = pd.bdate_range("2026-01-05", periods=len(closes))
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c}, index=idx)


def test_call_outcome_target_stop_and_time():
    p = Config().options
    up = _bars(np.linspace(100, 125, 30))
    res, ret = call_outcome(up, 0, 0.3, 45, 0.30, 0.20, p, 20, 7)
    assert res == 1 and ret >= 0.30
    down = _bars(np.linspace(100, 85, 30))
    res, ret = call_outcome(down, 0, 0.3, 45, 0.30, 0.20, p, 20, 7)
    assert res == -1 and ret <= -0.20
    flat = _bars([100.0] * 30)
    res, ret = call_outcome(flat, 0, 0.3, 45, 0.30, 0.20, p, 3, 7)
    assert res == 0 and -0.20 < ret < 0                                             # spread + a little decay
    res, ret = call_outcome(flat, 0, 0.3, 45, 0.30, 0.20, p, 20, 7)
    assert res == -1                        # a stock that doesn't move: spread + theta hit the -20% stop


@lru_cache(maxsize=None)
def _events(drift: float):
    prices, insiders, flow = make_market(seed=7, drift_after_signal=drift, n_days=500, event_days=380,
                                         events_per_ticker=10, noise_events_per_ticker=10)
    cfg = Config()
    return (build_outcomes(build_panel(prices, insiders, flow, cfg), cfg, prices["SPY"].index[-400]),
            prices["SPY"].index[-1])


def test_build_outcomes_one_row_per_move_and_all_variants():
    ev, data_end = _events(0.006)
    cfg = Config()
    assert {f"ret_{v}" for v in variants(cfg)} <= set(ev.columns) and len(variants(cfg)) == 12
    for _, g in ev.groupby("ticker"):
        gaps = g["signal_date"].sort_values().diff().dt.days.dropna()
        assert (gaps >= 20).all()                                                   # cooldown: ≥ 20 sessions apart
    late = ev["entry_date"] + pd.DateOffset(months=12) > data_end
    assert ev.loc[late, "res_stock12m_30"].isna().all()                             # horizon past the data
    assert ev.loc[~late, "res_stock12m_30"].notna().all()


def test_planted_event_edge_shows_in_call_profiles():
    ev, _ = _events(0.006)
    s = summarize(ev).set_index("variant")
    assert s.loc["call30_30", "events"] > 100
    mined = mine_profiles(ev)
    hits = [v for v, m in mined.items()
            if not m["rules"].empty and (m["rules"]["validated"] & m["rules"]["rule"].str.contains("ins:cluster|ins:exec|ins:big|flow:|event:flow")).any()]
    assert any(v.startswith("call") for v in hits), hits


def test_no_profile_rule_in_pure_noise():
    mined = mine_profiles(_events(0.0)[0])
    validated = {v: m["rules"].loc[m["rules"]["validated"], "rule"].tolist() for v, m in mined.items()
                 if not m["rules"].empty}
    assert sum(len(r) for r in validated.values()) <= 2, validated
