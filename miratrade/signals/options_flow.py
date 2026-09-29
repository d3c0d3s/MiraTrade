"""Unusual options activity: filter for opening, sizeable, near-dated, near-the-money prints."""
from __future__ import annotations

import numpy as np
import pandas as pd

from miratrade.config import FlowParams

FLOW_FEATURES = ["flow_bull_prem", "flow_bear_prem", "flow_n_unusual", "flow_fresh"]


def unusual_prints(flow: pd.DataFrame, p: FlowParams = FlowParams()) -> pd.DataFrame:
    """Rows of ``flow`` that qualify as unusual, with a ``direction`` of +1 / -1."""
    if flow.empty:
        return flow.assign(direction=pd.Series(dtype=float))
    f = flow.copy()
    dte = (pd.to_datetime(f["expiry"]) - pd.to_datetime(f["date"])).dt.days
    oi = f["open_interest"].fillna(0)
    vol_oi = np.where(oi > 0, f["volume"] / oi.where(oi > 0, 1), np.inf)
    otm = np.where(f["type"] == "C", f["strike"] / f["underlying"] - 1, 1 - f["strike"] / f["underlying"])
    otm = pd.Series(otm, index=f.index).fillna(0)  # unknown spot: don't filter on moneyness
    mask = ((f["premium"] >= p.min_premium_usd) & (vol_oi >= p.min_vol_oi_ratio)
            & dte.between(1, p.max_dte) & (otm <= p.max_otm_pct)
            # a ratio computed against an open interest of 3 is arithmetic, not a signal; a brand new
            # contract (open interest 0) is exempt, because it is opening by definition
            & ((oi >= p.min_open_interest) | (oi <= 0)))
    f = f[mask].copy()
    # Buying calls / selling puts is bullish; unknown aggressor is treated as a buyer.
    buyer = f["side"] != "bid"
    is_call = f["type"] == "C"
    f["direction"] = np.where(is_call == buyer, 1.0, -1.0)
    return f


def flow_features(unusual: pd.DataFrame, dates: pd.DatetimeIndex, ticker: str,
                  p: FlowParams = FlowParams()) -> pd.DataFrame:
    out = pd.DataFrame(0.0, index=dates, columns=FLOW_FEATURES)
    u = unusual[unusual["ticker"] == ticker]
    if u.empty:
        return out
    daily = u.assign(bull=u["premium"].where(u["direction"] > 0, 0),
                     bear=u["premium"].where(u["direction"] < 0, 0),
                     n=1).groupby("date")[["bull", "bear", "n"]].sum()
    # Align prints to trading dates (a print dated on a holiday rolls to the next session).
    pos = dates.searchsorted(daily.index)
    keep = pos < len(dates)
    daily = daily[keep].groupby(dates[pos[keep]]).sum().reindex(dates, fill_value=0)
    roll = daily.rolling(p.lookback_days, min_periods=1).sum()
    out["flow_bull_prem"] = roll["bull"]
    out["flow_bear_prem"] = roll["bear"]
    out["flow_n_unusual"] = roll["n"]
    out["flow_fresh"] = (daily["bull"] > daily["bear"]).astype(float)
    return out
