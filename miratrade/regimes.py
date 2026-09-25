"""Market regime of each signal date, so results can be broken down by type of market.

Labels use only data up to the close of each bar (rolling windows, no centring), so they are
point-in-time like every other feature.

* Trend: **bull** when SPY and its 50-day average are both above the 200-day average, **bear**
  when both are below, **sideways** otherwise (a market crossing its long average).
* Volatility: **high_vol** when SPY's 20-day realised vol is above its trailing one-year median,
  **low_vol** otherwise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from miratrade.config import RegimeParams
from miratrade.edge import stats
from miratrade.options_trades import realized_vol

TRENDS = ("bull", "sideways", "bear")
VOLS = ("low_vol", "high_vol")
DIMENSIONS = {"mkt_trend": TRENDS, "mkt_vol": VOLS}


def market_regimes(market: pd.DataFrame, p: RegimeParams = RegimeParams()) -> pd.DataFrame:
    c = market["close"]
    long = c.rolling(p.trend_sma, min_periods=p.trend_min_periods).mean()
    mid = c.rolling(p.mid_sma).mean()
    trend = np.select([(c > long) & (mid > long), (c < long) & (mid < long)], ["bull", "bear"], "sideways")
    trend = np.where(long.isna() | mid.isna(), "unknown", trend)
    rv = realized_vol(c, p.vol_window)
    ref = rv.rolling(p.vol_lookback, min_periods=p.vol_min_periods).median()
    vol = np.where(rv.isna() | ref.isna(), "unknown", np.where(rv > ref, "high_vol", "low_vol"))
    return pd.DataFrame({"mkt_trend": trend, "mkt_vol": vol}, index=market.index)


def rule_mask(trades: pd.DataFrame, rule: str) -> pd.Series:
    return trades[rule.split(" & ")].all(axis=1)


def regime_baseline(trades: pd.DataFrame) -> pd.DataFrame:
    """Stats of every closed candidate trade, per regime label."""
    closed = trades[trades["exit_reason"] != "open"]
    rows = []
    for dim, labels in DIMENSIONS.items():
        if dim not in closed:
            continue
        present = [x for x in (*labels, "unknown") if (closed[dim] == x).any()]
        for label in present:
            rows.append({"dimension": dim, "regime": label, **stats(closed.loc[closed[dim] == label, "r"])})
    return pd.DataFrame(rows)


def regime_rules(trades: pd.DataFrame, rules: pd.DataFrame) -> pd.DataFrame:
    """For each rule: trades and average R in each trend and volatility regime (whole window)."""
    closed = trades[trades["exit_reason"] != "open"]
    rows = []
    for rule in rules["rule"]:
        sel = closed[rule_mask(closed, rule)]
        row = {"rule": rule}
        for dim, labels in DIMENSIONS.items():
            for label in labels:
                r = sel.loc[sel[dim] == label, "r"] if dim in sel else sel["r"].iloc[:0]
                row[f"{label}_n"] = len(r)
                row[f"{label}_avg_r"] = r.mean() if len(r) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
