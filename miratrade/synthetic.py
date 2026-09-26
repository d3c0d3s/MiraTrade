"""Synthetic market with a *planted* edge, used by tests and ``miratrade demo``.

Insider cluster buys and bullish unusual call flow are followed by positive drift. Lone small
director buys are events too but carry *no* drift, so a working pipeline must tell the good
events from the others out of sample; everything else is a random walk.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def make_market(n_tickers: int = 40, n_days: int = 320, seed: int = 7,
                drift_after_signal: float = 0.004, event_days: int = 90,
                events_per_ticker: int = 3, noise_events_per_ticker: int = 3
                ) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Events land in the last ``event_days`` sessions (bar the final 20). Noise events come from
    their own random stream, so the rest of the market is the same with or without them."""
    rng = np.random.default_rng(seed)
    noise_rng = np.random.default_rng(seed + 1_000)
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
            for ev in noise_rng.choice(np.arange(n_days - event_days, n_days - 20),
                                       size=noise_events_per_ticker, replace=False):
                d = dates[ev]
                ins_rows.append({
                    "accession": f"{t}-{ev}-n", "filing_date": d, "trade_date": d - pd.Timedelta(days=2),
                    "ticker": t, "issuer": t, "owner": f"{t} Director {ev}", "owner_cik": f"{k}n{ev}",
                    "is_officer": False, "is_director": True, "is_ten_pct": False, "title": "",
                    "code": "P", "shares": 800, "price": 50.0, "value": 40_000.0,
                    "owned_after": 40_000, "delta_own_pct": 0.02})
        close = 100 * np.exp(np.cumsum(rets))
        open_ = close * np.exp(rng.normal(0, 0.004, n_days))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.008, n_days)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.008, n_days)))
        prices[t] = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                                  "volume": rng.integers(1_000_000, 3_000_000, n_days)},
                                 index=pd.DatetimeIndex(dates, name="date"))
    return prices, pd.DataFrame(ins_rows), pd.DataFrame(flow_rows)


def make_13d_market(n_tickers: int = 40, n_days: int = 320, seed: int = 11,
                    drift_after_signal: float = 0.004, event_days: int = 200,
                    events_per_ticker: int = 6) -> tuple[dict, pd.DataFrame]:
    """Random-walk market where new 13D filings are followed by positive drift. Also plants
    active (non-index) 13Gs with *no* drift — events the pipeline must learn to rank below the
    13Ds — and passive index-fund 13Gs, which the features must ignore."""
    from miratrade.data.ownership import OWNERSHIP_COLUMNS

    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-07-01", periods=n_days)
    prices, rows = {}, []
    for t in [f"S{i:02d}" for i in range(n_tickers)] + ["SPY"]:
        rets = rng.normal(0.0, 0.018, n_days)
        if t != "SPY":
            for j, ev in enumerate(rng.choice(np.arange(n_days - event_days, n_days - 20),
                                              size=events_per_ticker, replace=False)):
                activist, passive = j % 3 == 0, j % 3 == 1
                filer = "Activist LP" if activist else "VANGUARD GROUP" if passive else "Growth Fund LP"
                rows.append({"accession": f"{t}-{ev}", "filing_date": dates[ev], "ticker": t,
                             "subject_cik": t, "filer": filer, "kind": "13D" if activist else "13G",
                             "amendment": False, "passive": passive})
                if activist:
                    rets[ev + 1: ev + 16] += drift_after_signal
        close = 100 * np.exp(np.cumsum(rets))
        open_ = close * np.exp(rng.normal(0, 0.004, n_days))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.008, n_days)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.008, n_days)))
        prices[t] = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                                  "volume": rng.integers(1_000_000, 3_000_000, n_days)},
                                 index=pd.DatetimeIndex(dates, name="date"))
    return prices, pd.DataFrame(rows, columns=OWNERSHIP_COLUMNS)
