"""Synthetic market with a *planted* edge, used by tests and ``miratrade demo``.

Insider cluster buys and bullish unusual call flow are followed by positive drift; everything
else is a random walk. A working pipeline must rediscover those two effects out of sample.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def make_market(n_tickers: int = 40, n_days: int = 320, seed: int = 7,
                drift_after_signal: float = 0.004, event_days: int = 90,
                events_per_ticker: int = 3) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Events land in the last ``event_days`` sessions (bar the final 20)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-07-01", periods=n_days)
    prices, ins_rows, flow_rows = {}, [], []
    tickers = [f"T{i:02d}" for i in range(n_tickers)] + ["SPY"]
    for k, t in enumerate(tickers):
        rets = rng.normal(0.0, 0.018, n_days)
        if t != "SPY":
            for ev in rng.choice(np.arange(n_days - event_days, n_days - 20), size=events_per_ticker,
                                 replace=False):
                kind = rng.integers(2)
                d = dates[ev]
                if kind == 0:
                    for j, owner in enumerate(("CEO", "CFO", "Director")):
                        ins_rows.append({
                            "accession": f"{t}-{ev}-{j}", "filing_date": d, "trade_date": d - pd.Timedelta(days=2),
                            "ticker": t, "issuer": t, "owner": f"{t} {owner}", "owner_cik": f"{k}{j}",
                            "is_officer": owner != "Director", "is_director": owner == "Director",
                            "is_ten_pct": False, "title": owner if owner != "Director" else "",
                            "code": "P", "shares": 10_000, "price": 50.0, "value": 500_000.0,
                            "owned_after": 60_000, "delta_own_pct": 0.2})
                else:
                    flow_rows.append({"date": d, "ticker": t, "expiry": d + pd.Timedelta(days=30),
                                      "type": "C", "strike": 100.0, "volume": 5_000,
                                      "open_interest": 500, "premium": 2_000_000.0,
                                      "underlying": 100.0, "side": "ask"})
                rets[ev + 1: ev + 16] += drift_after_signal
        close = 100 * np.exp(np.cumsum(rets))
        open_ = close * np.exp(rng.normal(0, 0.004, n_days))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.008, n_days)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.008, n_days)))
        prices[t] = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                                  "volume": rng.integers(1_000_000, 3_000_000, n_days)},
                                 index=pd.DatetimeIndex(dates, name="date"))
    return prices, pd.DataFrame(ins_rows), pd.DataFrame(flow_rows)
