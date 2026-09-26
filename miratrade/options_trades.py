"""Option swing trades: express each stock swing signal as a long call.

There is no free history of option prices, so contracts are priced with Black-Scholes using
the underlying's realised volatility scaled by ``iv_mult`` as a stand-in for implied volatility,
plus a bid/ask cost on each side. This is an approximation: use it to compare instruments and
rank rules, and check real quotes (or real historical option data) before trusting the numbers.

The option trade shares the stock trade's timing: it opens at the stock entry and closes when
the stock hits its stop, target or time stop. R is measured against the premium that would be
lost if the stock hit its stop right after entry, so it is comparable with the stock R.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import NormalDist

import numpy as np
import pandas as pd

from miratrade.config import OptionParams

_N = NormalDist()


def bs_price(s: float, k: float, t: float, r: float, sigma: float, kind: str = "C") -> float:
    if s <= 0:  # a stop below zero: the stock is worthless there
        return 0.0 if kind == "C" else k * math.exp(-r * max(t, 0))
    if t <= 0 or sigma <= 0:
        return max(0.0, s - k) if kind == "C" else max(0.0, k - s)
    d1 = (math.log(s / k) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    if kind == "C":
        return s * _N.cdf(d1) - k * math.exp(-r * t) * _N.cdf(d2)
    return k * math.exp(-r * t) * _N.cdf(-d2) - s * _N.cdf(-d1)


def bs_delta(s: float, k: float, t: float, r: float, sigma: float, kind: str = "C") -> float:
    d1 = (math.log(s / k) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    return _N.cdf(d1) if kind == "C" else _N.cdf(d1) - 1


def strike_increment(s: float) -> float:
    return 0.5 if s < 25 else 1.0 if s < 100 else 2.5 if s < 250 else 5.0


def strike_for_delta(s: float, t: float, r: float, sigma: float, delta: float) -> float:
    """Listed-style strike closest to the target call delta."""
    d1 = _N.inv_cdf(delta)
    k = s * math.exp(-(d1 * sigma * math.sqrt(t) - (r + 0.5 * sigma ** 2) * t))
    inc = strike_increment(s)
    return max(inc, round(k / inc) * inc)


def third_friday(year: int, month: int) -> date:
    d = date(year, month, 15)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def monthly_expiry(on: date, target_dte: int, min_dte: int) -> date:
    """Standard monthly expiry nearest to ``target_dte`` days out, at least ``min_dte`` away."""
    best = None
    y, m = on.year, on.month
    for _ in range(6):
        exp = third_friday(y, m)
        dte = (exp - on).days
        if dte >= min_dte and (best is None or abs(dte - target_dte) < abs((best - on).days - target_dte)):
            best = exp
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return best


def realized_vol(close: pd.Series, n: int = 20) -> pd.Series:
    return np.log(close).diff().rolling(n).std() * math.sqrt(252)


def option_contract(s: float, on: date, vol: float, p: OptionParams) -> dict:
    """The call MiraTrade would buy at price ``s`` on ``on`` given realised vol ``vol``."""
    sigma = float(np.clip(vol * p.iv_mult, p.vol_floor, p.vol_cap))
    expiry = monthly_expiry(on, p.target_dte, p.min_dte)
    t = (expiry - on).days / 365
    k = strike_for_delta(s, t, p.rate, sigma, p.target_delta)
    mid = bs_price(s, k, t, p.rate, sigma)
    return {"strike": k, "expiry": expiry, "sigma": sigma, "t": t, "mid": mid,
            "ask": mid * (1 + p.half_spread), "delta": bs_delta(s, k, t, p.rate, sigma)}


def simulate_option(trade: dict, vol: float, p: OptionParams) -> dict:
    """Long-call version of a simulated stock trade (see ``backtest.simulate``)."""
    entry_day = pd.Timestamp(trade["entry_date"]).date()
    exit_day = pd.Timestamp(trade["exit_date"]).date()
    c = option_contract(trade["entry"], entry_day, vol, p)
    t_exit = max((c["expiry"] - exit_day).days, 0) / 365
    exit_bid = bs_price(trade["exit"], c["strike"], t_exit, p.rate, c["sigma"]) * (1 - p.half_spread)
    stop_bid = bs_price(trade["stop"], c["strike"], c["t"], p.rate, c["sigma"]) * (1 - p.half_spread)
    risk = c["ask"] - stop_bid
    return {
        "opt_strike": c["strike"], "opt_expiry": pd.Timestamp(c["expiry"]),
        "opt_delta": round(c["delta"], 2), "opt_iv": round(c["sigma"], 3),
        "opt_entry": c["ask"], "opt_exit": exit_bid,
        "opt_ret": exit_bid / c["ask"] - 1 if c["ask"] > 0 else np.nan,
        "opt_r": (exit_bid - c["ask"]) / risk if risk > 0 else np.nan,
    }
