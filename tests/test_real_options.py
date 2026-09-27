"""Replaying the call profiles on real option bars."""
import json

import pandas as pd
import pytest

from miratrade.config import Config
from miratrade.real_options import cached_bars, real_call_outcome, summarise


def _bars(closes):
    return pd.DataFrame({"date": pd.bdate_range("2026-03-02", periods=len(closes)), "close": closes})


def test_real_call_outcome_follows_the_same_rules_as_the_model():
    cfg = Config()
    half = cfg.options.half_spread
    entry = 1.0 * (1 + half)                                   # what the first close costs to buy
    target_close = entry * 1.401 / (1 - half)                  # the close that reaches +40 %
    res, ret = real_call_outcome(_bars([1.0, 1.05, target_close, 0.2]), 0.40, 0.25, cfg)
    assert res == 1.0 and ret == pytest.approx(0.401, abs=1e-3)   # target first, before the collapse
    stop_close = entry * 0.749 / (1 - half)
    res, ret = real_call_outcome(_bars([1.0, stop_close, 5.0]), 0.40, 0.25, cfg)
    assert res == -1.0 and ret == pytest.approx(-0.251, abs=1e-3)  # stop first, even if it recovers
    res, ret = real_call_outcome(_bars([1.0, 1.02, 1.05]), 0.40, 0.25, cfg)
    assert res == 0.0 and -0.10 < ret < 0.10                   # neither: the last close decides


def test_real_call_outcome_respects_the_holding_limit_and_bad_input():
    cfg = Config()
    slow = [1.0] * (cfg.outcomes.call_max_hold + 1) + [99.0]   # the jump lands after the limit
    res, _ = real_call_outcome(_bars(slow), 0.40, 0.25, cfg)
    assert res == 0.0
    assert pd.isna(real_call_outcome(_bars([1.0]), 0.40, 0.25, cfg)[0])
    assert pd.isna(real_call_outcome(_bars([0.0, 1.0]), 0.40, 0.25, cfg)[0])


def test_cached_bars_reads_the_massive_cache(tmp_path):
    payload = {"results": [{"t": 1772409600000, "c": 2.5}, {"t": 1772496000000, "c": 3.0}]}
    name = "_v2_aggs_ticker_O_ACME260320C00016500_range_1_day_2026-03-02_2026-03-13_x.json"
    (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / name.replace("C00016500", "P00016500")).write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "_v2_aggs_ticker_O_BAD260320C00010000_x.json").write_text("{}", encoding="utf-8")
    bars = cached_bars(tmp_path)
    assert list(bars) == [("ACME", "2026-03-20", 16.5)]        # puts and empty files are skipped
    assert list(bars[("ACME", "2026-03-20", 16.5)]["close"]) == [2.5, 3.0]


def test_summarise_puts_both_prices_on_the_same_events():
    d = pd.DataFrame({"real_res_call45_40": [1.0, -1.0], "real_ret_call45_40": [0.4, -0.25],
                      "model_res_call45_40": [-1.0, -1.0], "model_ret_call45_40": [-0.25, -0.25],
                      "real_res_call45_30": [1.0, 0.0], "real_ret_call45_30": [0.3, 0.0],
                      "model_res_call45_30": [0.0, 0.0], "model_ret_call45_30": [0.0, 0.0],
                      "real_res_call45_50": [0.0, 0.0], "real_ret_call45_50": [0.0, 0.0],
                      "model_res_call45_50": [0.0, 0.0], "model_ret_call45_50": [0.0, 0.0]})
    s = summarise(d, 45)
    row = s[(s["perfil"] == "+40 % / −25 %") & (s["precios"] == "reales")].iloc[0]
    assert row["n"] == 2 and row["objetivo"] == 0.5 and row["medio"] == pytest.approx(0.075)
    assert set(s["precios"]) == {"modelo", "reales"} and len(s) == 6
