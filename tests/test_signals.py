import numpy as np
import pandas as pd

from miratrade.backtest import simulate
from miratrade.config import Config
from miratrade.signals.insider import insider_features
from miratrade.signals.options_flow import unusual_prints


def _ins(filing, trade, owner, value=100_000, code="P", title="CEO"):
    return {"ticker": "ACME", "filing_date": pd.Timestamp(filing), "trade_date": pd.Timestamp(trade),
            "owner_cik": owner, "code": code, "value": value, "title": title, "delta_own_pct": 0.2}


def test_insider_features_are_point_in_time():
    ins = pd.DataFrame([_ins("2026-08-05", "2026-08-03", "a"), _ins("2026-08-07", "2026-08-06", "b", title="")])
    dates = pd.bdate_range("2026-08-03", "2026-08-10")
    f = insider_features(ins, dates, "ACME")
    assert f.loc["2026-08-04", "ins_buy_value"] == 0          # not filed yet
    assert f.loc["2026-08-05", "ins_fresh"] == 1 and f.loc["2026-08-05", "ins_cluster"] == 1
    assert f.loc["2026-08-06", "ins_fresh"] == 0
    assert f.loc["2026-08-07", "ins_cluster"] == 2 and f.loc["2026-08-07", "ins_buyers"] == 2
    assert f.loc["2026-08-10", "ins_exec_buy"] == 1


def test_small_buys_ignored():
    ins = pd.DataFrame([_ins("2026-08-05", "2026-08-03", "a", value=5_000)])
    f = insider_features(ins, pd.bdate_range("2026-08-03", "2026-08-10"), "ACME")
    assert f["ins_buy_value"].sum() == 0


def test_unusual_prints_filters_and_direction():
    base = {"date": pd.Timestamp("2026-09-01"), "ticker": "X", "expiry": pd.Timestamp("2026-09-19"),
            "strike": 100.0, "volume": 1000, "open_interest": 100, "premium": 500_000.0, "underlying": 100.0}
    flow = pd.DataFrame([
        {**base, "type": "C", "side": "ask"},                     # bullish
        {**base, "type": "P", "side": "ask"},                     # bearish
        {**base, "type": "P", "side": "bid"},                     # sold puts: bullish
        {**base, "type": "C", "side": "ask", "premium": 10_000},  # too small
        {**base, "type": "C", "side": "ask", "open_interest": 5000},  # closing/rolling, not opening
        {**base, "type": "C", "side": "ask", "strike": 150.0},    # far OTM
    ])
    u = unusual_prints(flow)
    assert list(u["direction"]) == [1.0, -1.0, 1.0]


def _bars(o, h, l, c, atr=1.0):
    idx = pd.bdate_range("2026-01-01", periods=len(o))
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "atr": atr}, index=idx)


def test_simulate_target_and_stop():
    cfg = Config()
    # entry 100, stop 98.5, target 103
    up = _bars([100, 100, 101, 102], [100, 101, 103.5, 104], [99, 99.5, 100.5, 101], [100, 100.5, 103, 103])
    t = simulate(up, 0, cfg)
    assert t["exit_reason"] == "target" and t["exit"] == 103 and np.isclose(t["r"], 2.0)
    both = _bars([100, 100, 100], [100, 104, 100], [99, 98, 99], [100, 100, 100])
    assert simulate(both, 0, cfg)["exit_reason"] == "stop"   # ambiguous bar -> assume the worse fill
    gap = _bars([100, 100, 95], [100, 100.5, 96], [99, 99.5, 94], [100, 100, 95])
    t = simulate(gap, 0, cfg)
    assert t["exit_reason"] == "stop" and t["exit"] == 95     # gap fills at the open, not the stop
