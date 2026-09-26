"""Stock-driven experiment engine: pricing, exits and the grid."""
import numpy as np
import pandas as pd
import pytest

from miratrade.backtest import build_panel
from miratrade.config import Config
from miratrade.experiments import (Instrument, Position, bs_call, clean, extract_events, run_exit, run_grid,
                                   split_date, stats, stop_price, summarize, technicals)
from miratrade.options_trades import bs_price
from miratrade.synthetic import make_market


def test_vectorised_black_scholes_matches_the_scalar_one():
    s = np.array([80.0, 100.0, 120.0])
    for t in (0.1, 0.5):
        got = bs_call(s, 100.0, t, 0.04, 0.35)
        want = [bs_price(x, 100.0, t, 0.04, 0.35) for x in s]
        assert np.allclose(got, want, rtol=1e-9)
    assert np.allclose(bs_call(s, 100.0, 0.0, 0.04, 0.35), [0, 0, 20])       # expiry: intrinsic


def _ind(closes, opens=None, lows=None):
    idx = pd.bdate_range("2025-01-01", periods=len(closes))
    c = np.asarray(closes, float)
    o = np.asarray(opens if opens is not None else c, float)
    lo = np.asarray(lows if lows is not None else np.minimum(o, c) * 0.999, float)
    df = pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.001, "low": lo, "close": c, "volume": 1e6}, index=idx)
    df["atr"] = 2.0
    return df


def _run(ind, rule, stop=None, i=1, cfg=Config()):
    pos = Position(Instrument("stock"), ind, i, 0.3, cfg)
    arr = {k: ind[k].to_numpy(float) for k in ("open", "high", "low", "close")}
    return run_exit(pos, arr, technicals(ind), pos.close_returns(arr["close"]), stop, rule, cfg)


def test_stop_gap_fills_at_the_open():
    closes = [100] * 70
    opens = [100, 100, 85] + [100] * 67
    ind = _ind(closes, opens)
    res = _run(ind, "fixed30", stop=stop_price("pct10", 100.0, 2.0))
    assert res["reason"] == "stop" and res["days"] == 1 and res["ret"] == pytest.approx(-0.15)
    intraday = _ind(closes, lows=[99, 99, 88] + [99] * 67)
    res = _run(intraday, "fixed30", stop=90.0)
    assert res["reason"] == "stop" and res["ret"] == pytest.approx(-0.10)


def test_fixed_target_versus_letting_it_run():
    up = list(100 * 1.02 ** np.arange(25))                      # +2 % a day, reaches +30 % on day 14
    closes = [100] + up + [up[-1] * 0.97 ** k for k in range(1, 45)]
    ind = _ind(closes)
    fixed = _run(ind, "fixed30")
    assert fixed["reason"] == "objetivo" and 0.30 <= fixed["ret"] < 0.33
    run = _run(ind, "run30_sma10")
    assert run["reached30"] and run["ret"] > fixed["ret"] and run["reason"] in ("bajo media 10", "suelo +20 %")
    assert run["days"] > fixed["days"]


def test_time_exit_and_stop_levels():
    ind = _ind([100] * 70)
    res = _run(ind, "run30_chandelier")
    assert res["reason"] == "tiempo" and res["days"] == Config().experiment.max_hold and res["ret"] == 0
    assert stop_price("none", 100, 2) is None and stop_price("atr3", 100, 2) == 94
    assert stop_price("atr3", 5, 2) is None                      # a stop below zero is no stop


def test_call_position_respects_expiry_and_prices_from_the_stock():
    cfg = Config()
    ind = _ind(list(np.linspace(100, 130, 120)))
    pos = Position(Instrument("call", 0.65, 45), ind, 1, 0.3, cfg)
    exp_limit = pd.Timestamp(pos.contract["expiry"]) - pd.Timedelta(days=cfg.experiment.exit_days_before_expiry)
    assert pos.ok and ind.index[pos.last] <= exp_limit and (pos.contract["expiry"] - ind.index[1].date()).days >= 45
    closes = ind["close"].to_numpy()
    rets = pos.close_returns(closes)
    stock = closes[pos.last] / ind["open"].iat[1] - 1
    assert rets[0] < 0                                           # the spread is paid at entry
    assert rets[-1] > 3 * stock > 0                              # a Δ0.65 call levers the stock's rise


def test_grid_on_synthetic_events():
    cfg = Config()
    prices, insiders, flow = make_market(n_tickers=12)
    insiders = insiders.assign(plan_10b5_1=False)
    insiders.loc[insiders.index[:5], "plan_10b5_1"] = True
    panel = build_panel(prices, insiders, flow, cfg)
    kinds = {"T00": "fund"}
    ev = extract_events(panel, cfg, insiders=insiders, issuer_kind=kinds)
    assert len(ev) and ev["ticker"].isin(prices).all() and (ev.loc[ev["ticker"] == "T00", "issuer_kind"] == "fund").all()
    trades = run_grid(panel, ev, cfg)
    configs = trades.groupby(["instrument", "stop", "exit"]).ngroups
    assert configs > 100 and trades["ret"].notna().all()
    assert not (trades["instrument"].eq("acción") & trades["exit"].eq("premium40_25")).any()
    assert "T00" not in set(clean(trades)["ticker"])
    s = summarize(trades, ["instrument"])
    assert set(s.columns) >= {"n", "media", "acierto", "pf", "t", "llega30"}
    assert ev["signal_date"].min() < split_date(ev, cfg) < ev["signal_date"].max()


def test_stats():
    s = stats(pd.Series([0.3, -0.1, -0.1, 0.1]))
    assert s["n"] == 4 and s["media"] == pytest.approx(0.05) and s["pf"] == pytest.approx(2.0)
    assert s["acierto"] == 0.5


def test_report_on_synthetic_events():
    from miratrade.experiments import report

    cfg = Config()
    prices, insiders, flow = make_market(n_tickers=12)
    panel = build_panel(prices, insiders.assign(plan_10b5_1=False), flow, cfg)
    ev = extract_events(panel, cfg, insiders=insiders)
    md, wide = report(run_grid(panel, ev, cfg), ev, cfg, {"start": "2025-07-01", "end": "2026-09-01"})
    assert "## Prueba 1" in md and "## Prueba 2" in md and "## Prueba 3" in md and "call Δ0.65 60d" in md
    assert {"media_train", "media_test", "n_train"} <= set(wide.columns)


def test_fund_index_parsing():
    from miratrade.data.issuers import classify_by_index, fund_ciks_from_index, kind_from_name

    idx = ("N-PORT-P         SOME INCOME FUND                                    846676      2026-05-01  edgar/data/846676/x.txt\n"
           "10-K             LENNAR CORP /NEW/                                   920760      2026-01-20  edgar/data/920760/y.txt\n"
           "N-2              ARES CAPITAL CORP                                   1287750     2026-04-02  edgar/data/1287750/z.txt\n")
    funds = fund_ciks_from_index(idx)
    assert funds == {"846676", "1287750"}
    iss = pd.DataFrame({"ticker": ["AEF", "LEN", "ARCC", "XYZ"], "issuer_cik": ["846676", "920760", "1287750", "1"],
                        "issuer": ["abrdn Fund", "LENNAR CORP", "ARES CAPITAL CORP", "Nova Acquisition Corp"]})
    k = dict(zip(*classify_by_index(iss, funds)[["ticker", "kind"]].T.values))
    assert k == {"AEF": "fund", "LEN": "company", "ARCC": "fund", "XYZ": "spac"}
    assert kind_from_name("Fundamental Global Inc") == "company"
