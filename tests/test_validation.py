from functools import lru_cache

import numpy as np
import pandas as pd

from miratrade.backtest import build_panel, run_trades, simulate
from miratrade.cli import pipeline
from miratrade.config import Config, EdgeParams
from miratrade.edge import walk_forward
from miratrade.regimes import market_regimes, regime_baseline
from miratrade.survivorship import coverage
from miratrade.synthetic import make_market


@lru_cache(maxsize=None)
def _long_market(drift: float, seed: int = 7):
    """~1.5 years of trades with events spread across the whole window."""
    prices, insiders, flow = make_market(seed=seed, drift_after_signal=drift, n_days=500,
                                         event_days=380, events_per_ticker=10)
    cfg = Config()
    panel = build_panel(prices, insiders, flow, cfg)
    return run_trades(panel, start=prices["SPY"].index[-400], cfg=cfg)


# --- walk-forward -------------------------------------------------------------------------

def test_walk_forward_recovers_planted_edge():
    wf = walk_forward(_long_market(drift=0.004))
    s = wf["summary"]
    assert s["folds"] == 3 and s["trades"] > 50
    assert s["lift_r"] >= 0.1 and s["p"] < 0.05
    assert wf["rules"]["rule"].str.contains("ins:|flow:|event:").any()


def test_walk_forward_picks_nothing_in_pure_noise():
    s = walk_forward(_long_market(drift=0.0))["summary"]
    assert s["trades"] == 0 or s["p"] > 0.05


def test_walk_forward_purges_trades_that_overlap_the_test_slice():
    days = pd.bdate_range("2026-01-05", periods=10)
    trades = pd.DataFrame({"signal_date": days, "exit_date": days + pd.offsets.BDay(3),
                           "exit_reason": "target", "r": 1.0, "x:a": True})
    wf = walk_forward(trades, EdgeParams(wf_folds=1, wf_min_train_frac=0.5, min_trades=1))
    fold = wf["folds"].iloc[0]
    # The slice starts on day 5; only trades signalled on days 0-1 had exited (day 3-4) by then.
    assert fold["test_start"] == days[5].date() and fold["train_n"] == 2 and fold["test_n"] == 5


def test_walk_forward_handles_too_few_trades():
    wf = walk_forward(pd.DataFrame({"signal_date": pd.to_datetime([]), "exit_date": pd.to_datetime([]),
                                    "exit_reason": [], "r": []}))
    assert wf["folds"].empty and wf["summary"]["trades"] == 0


# --- market regimes -----------------------------------------------------------------------

def _spy(path: np.ndarray) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=len(path))
    return pd.DataFrame({"close": path}, index=idx)


def test_market_regimes_trend_labels():
    path = np.r_[np.linspace(100, 200, 300), np.linspace(200, 100, 300)]
    reg = market_regimes(_spy(path))
    assert reg["mkt_trend"].iat[50] == "unknown"      # 200-day average not formed yet
    assert reg["mkt_trend"].iat[280] == "bull"
    assert reg["mkt_trend"].iat[-1] == "bear"
    assert set(reg["mkt_vol"].iloc[200:]) <= {"high_vol", "low_vol"}


def test_market_regimes_are_point_in_time():
    rng = np.random.default_rng(1)
    spy = _spy(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 600))))
    full, cut = market_regimes(spy), market_regimes(spy.iloc[:400])
    pd.testing.assert_frame_equal(full.iloc[:400], cut)   # later bars never change earlier labels


def test_regime_baseline_covers_every_closed_trade():
    trades = _long_market(drift=0.004)
    base = regime_baseline(trades)
    closed = (trades["exit_reason"] != "open").sum()
    for _, g in base.groupby("dimension"):
        assert g["n"].sum() == closed


# --- survivorship -------------------------------------------------------------------------

def test_delisted_trade_is_closed_not_dropped():
    idx = pd.bdate_range("2026-01-01", periods=4)
    ind = pd.DataFrame({"open": [100, 100, 101, 101], "high": [100, 101, 102, 102],
                        "low": [99, 99.5, 100, 100], "close": [100, 101, 101, 100], "atr": 1.0}, index=idx)
    assert simulate(ind, 0, Config())["exit_reason"] == "open"
    cfg = Config()
    cfg.survivorship.delist_exit_haircut = 0.3
    t = simulate(ind, 0, cfg, delisted=True)
    assert t["exit_reason"] == "delisted" and np.isclose(t["exit"], 70.0)


def test_coverage_reports_lost_and_delisted_tickers():
    prices, insiders, flow = make_market()
    prices["T00"] = prices["T00"].iloc[:-40]              # stopped trading 40 sessions early
    prices["T01"] = prices["T01"].iloc[-30:]              # too short a history to backtest
    start = prices["SPY"].index[-90]
    gone = insiders[insiders["ticker"] == "T02"].assign(ticker="GONE")
    insiders = pd.concat([insiders, gone], ignore_index=True)
    cfg = Config()
    panel = build_panel(prices, insiders, flow, cfg)
    trades = run_trades(panel, start=start, cfg=cfg)

    assert not ((trades["ticker"] == "T00") & (trades["exit_reason"] == "open")).any()
    s = coverage(set(prices) | {"GONE"}, prices, panel, insiders, flow, trades, start, cfg)
    assert s["missing"] == ["GONE"] and s["short"] == ["T01"] and s["delisted"] == ["T00"]
    assert s["lost_insider_buys"] >= len(gone) > 0
    assert s["traded"] == s["universe"] - 2


def test_report_has_new_sections(tmp_path):
    prices, insiders, flow = make_market()
    res = pipeline(prices, insiders, flow, prices["SPY"].index[-90], tmp_path)
    for section in ("## Walk-forward validation", "## Results by market regime",
                    "## Survivorship and data coverage"):
        assert section in res["report"]
    assert (tmp_path / "walk_forward.csv").exists()
    assert {"wf_oos_n", "wf_confirmed"} <= set(res["rules"].columns)
    assert {"mkt_trend", "mkt_vol"} <= set(res["trades"].columns)
