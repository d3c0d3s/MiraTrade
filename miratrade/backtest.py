"""Build the point-in-time feature panel and simulate ATR-bracketed swing trades.

Entry candidates on a bar ``i`` (known at its close) are:
  * a technical setup (breakout / pullback / oversold bounce), or
  * a fresh event (a new insider buy filing, a new day of bullish unusual flow, or a new
    13D / non-index 13G ownership filing).
Every candidate is traded the same way so that the *conditions* around it can be compared.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from miratrade.config import Config
from miratrade.options_trades import realized_vol, simulate_option
from miratrade.regimes import market_regimes
from miratrade.signals.insider import insider_features
from miratrade.signals.options_flow import flow_features, unusual_prints
from miratrade.signals.smart_money import ownership_features, short_features
from miratrade.signals.technical import SETUPS, detect_setups, indicators
from miratrade.survivorship import delisted_tickers


def build_panel(prices: dict[str, pd.DataFrame], insiders: pd.DataFrame, flow: pd.DataFrame,
                cfg: Config = Config(), market: str = "SPY", ownership: pd.DataFrame | None = None,
                short_volume: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """``ownership`` (13D/13G filings) and ``short_volume`` (FINRA) are optional; without them
    their features are zero / NaN and the matching conditions never fire."""
    unusual = unusual_prints(flow, cfg.flow)
    mkt = None
    if market in prices:
        m = indicators(prices[market])
        mkt = pd.DataFrame({"mkt_up": (m["close"] > m["sma50"]).astype(float)})
        mkt = mkt.join(market_regimes(prices[market], cfg.regime))
    panel = {}
    for t, df in prices.items():
        if len(df) < cfg.survivorship.min_history_bars:
            continue
        ind = indicators(df)
        ind["rv20"] = realized_vol(ind["close"])
        ind = ind.join(detect_setups(ind).add_prefix("setup_").astype(float))
        ind = ind.join(insider_features(insiders, ind.index, t, cfg.insider))
        ind = ind.join(flow_features(unusual, ind.index, t, cfg.flow))
        ind = ind.join(ownership_features(ownership, ind.index, t, cfg.smart))
        ind = ind.join(short_features(short_volume, ind.index, t, cfg.smart))
        if mkt is not None:
            ind = ind.join(mkt).fillna({"mkt_up": 0.0, "mkt_trend": "unknown", "mkt_vol": "unknown"})
        panel[t] = ind
    return panel


def simulate(ind: pd.DataFrame, i: int, cfg: Config, delisted: bool = False) -> dict | None:
    """Trade signalled on bar ``i``: enter next open, stop/target in ATRs, time stop.

    ``delisted``: the ticker stopped trading at its last bar, so a trade still open there is
    closed at that close (less ``delist_exit_haircut``) instead of being left ``open``."""
    p = cfg.trade
    if i + 1 >= len(ind) or not np.isfinite(ind["atr"].iat[i]) or ind["atr"].iat[i] <= 0:
        return None
    o, h, l, c = (ind[k].to_numpy() for k in ("open", "high", "low", "close"))
    entry = o[i + 1]
    stop = entry - p.stop_atr * ind["atr"].iat[i]
    target = entry + p.target_atr * ind["atr"].iat[i]
    last = min(i + p.max_hold_days, len(ind) - 1)
    exit_px, reason, j = None, None, i + 1
    for j in range(i + 1, last + 1):
        if j > i + 1 and o[j] <= stop:          # gapped through the stop
            exit_px, reason = o[j], "stop"
        elif j > i + 1 and o[j] >= target:      # gapped through the target
            exit_px, reason = o[j], "target"
        elif l[j] <= stop:                      # both touched intraday -> assume the worse one
            exit_px, reason = stop, "stop"
        elif h[j] >= target:
            exit_px, reason = target, "target"
        if exit_px is not None:
            break
    if exit_px is None:
        exit_px, j = c[last], last
        if last == i + p.max_hold_days:
            reason = "time"
        elif delisted:
            exit_px, reason = c[last] * (1 - cfg.survivorship.delist_exit_haircut), "delisted"
        else:
            reason = "open"
    risk = entry - stop
    return {
        "entry_date": ind.index[i + 1], "exit_date": ind.index[j], "entry": entry,
        "stop": stop, "target": target, "exit": exit_px, "exit_reason": reason,
        "ret": exit_px / entry - 1, "r": (exit_px - entry) / risk, "bars": j - i,
    }


def conditions(row: pd.Series) -> dict[str, bool]:
    """Boolean conditions attached to each trade; the edge miner combines these."""
    c = {f"setup:{s}": bool(row.get(f"setup_{s}", 0)) for s in SETUPS}
    c["event:insider_buy"] = bool(row["ins_fresh"])
    c["event:flow"] = bool(row["flow_fresh"])
    c["ins:any_buy"] = row["ins_buy_value"] > 0
    c["ins:cluster2+"] = row["ins_cluster"] >= 2
    c["ins:exec_buy"] = bool(row["ins_exec_buy"])
    c["ins:big_250k+"] = row["ins_buy_value"] >= 250_000
    c["ins:stake+10%"] = row["ins_max_delta_own"] >= 0.10
    c["ins:heavy_selling"] = row["ins_sell_value"] >= 1_000_000 and row["ins_buy_value"] == 0
    c["flow:bullish"] = row["flow_bull_prem"] > max(row["flow_bear_prem"], 0) and row["flow_n_unusual"] > 0
    c["flow:bull_1m+"] = row["flow_bull_prem"] >= 1_000_000
    c["flow:bearish"] = row["flow_bear_prem"] > row["flow_bull_prem"]
    c["event:13dg"] = bool(row.get("own_fresh", 0))
    c["own:13d"] = row.get("own_13d", 0) > 0
    c["own:13g_active"] = row.get("own_13g", 0) > 0
    c["short:low"] = bool(row.get("short_low", 0))
    c["short:high"] = bool(row.get("short_high", 0))
    c["trend:up"] = row["close"] > row["sma50"] and row["sma20"] > row["sma50"]
    c["trend:above_200"] = bool(row["close"] > row["sma200"]) if np.isfinite(row["sma200"]) else False
    c["mom:ret20>0"] = row["ret_20d"] > 0
    c["rsi:<40"] = row["rsi"] < 40
    c["rsi:>60"] = row["rsi"] > 60
    c["vol:rel>1.5"] = row["rel_volume"] > 1.5
    if "mkt_up" in row:
        c["mkt:spy_above_50d"] = bool(row["mkt_up"])
    return c


def entry_trigger(ind: pd.DataFrame) -> pd.Series:
    """Bars on which a candidate trade is taken: a setup completed or a fresh event arrived."""
    setup_cols = [f"setup_{s}" for s in SETUPS]
    fresh = ind["ins_fresh"] + ind["flow_fresh"] + ind.get("own_fresh", 0)
    return (ind[setup_cols].sum(axis=1) > 0) | (fresh > 0)


def run_trades(panel: dict[str, pd.DataFrame], start: pd.Timestamp | None = None,
               cfg: Config = Config()) -> pd.DataFrame:
    """Simulate every candidate; one open trade per ticker at a time."""
    rows = []
    delisted = delisted_tickers(panel, cfg.survivorship.delist_gap_days)
    for t, ind in panel.items():
        trigger = entry_trigger(ind)
        busy_until = -1
        for i in np.flatnonzero(trigger.to_numpy()):
            if i <= busy_until or (start is not None and ind.index[i] < start):
                continue
            trade = simulate(ind, i, cfg, delisted=t in delisted)
            if trade is None:
                continue
            busy_until = ind.index.get_loc(trade["exit_date"])
            row = ind.iloc[i]
            if cfg.options.enabled and np.isfinite(row.get("rv20", np.nan)):
                trade.update(simulate_option(trade, row["rv20"], cfg.options))
            regime = {k: row.get(k, "unknown") for k in ("mkt_trend", "mkt_vol")}
            rows.append({"ticker": t, "signal_date": ind.index[i], **trade, **regime, **conditions(row)})
    return pd.DataFrame(rows)
