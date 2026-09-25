"""Survivorship bias: what the backtest cannot see because a company stopped trading.

Free price sources (yfinance, Stooq) usually return nothing for delisted tickers, and a stock
that was acquired or went bankrupt mid-window has a price history that simply ends. Both are
more common among losers than winners, so silently dropping them flatters the results.

* Tickers whose data ends well before the rest of the universe are treated as **delisted**:
  a trade still open at their last bar is closed there (``exit_reason == "delisted"``) instead
  of being discarded as ``open``.
* Tickers with no (or too little) price data are counted, together with the insider buys and
  unusual option prints on them that the backtest never got to trade.
"""
from __future__ import annotations

import pandas as pd
from pandas.tseries.offsets import BDay

from miratrade.config import Config
from miratrade.signals.options_flow import unusual_prints


def delisted_tickers(frames: dict[str, pd.DataFrame], gap_days: int) -> set[str]:
    """Tickers whose last bar is more than ``gap_days`` sessions before the latest bar overall."""
    if not frames:
        return set()
    end = max(df.index[-1] for df in frames.values())
    return {t for t, df in frames.items() if df.index[-1] < end - BDay(gap_days)}


def coverage(universe: set[str], prices: dict[str, pd.DataFrame], panel: dict[str, pd.DataFrame],
             insiders: pd.DataFrame, flow: pd.DataFrame, trades: pd.DataFrame,
             start: pd.Timestamp, cfg: Config = Config()) -> dict:
    """Which tickers the backtest lost, and how many tradeable signals went with them."""
    universe = set(universe)
    missing = sorted(universe - set(prices))
    short = sorted(t for t in universe & set(prices) if t not in panel)
    delisted = sorted(delisted_tickers({t: panel[t] for t in universe & set(panel)},
                                       cfg.survivorship.delist_gap_days))
    lost = set(missing) | set(short)

    buys = insiders.iloc[:0]
    if len(insiders):
        buys = insiders[(insiders["code"] == "P") & (insiders["value"] >= cfg.insider.min_value_usd)
                        & (insiders["filing_date"] >= start) & insiders["ticker"].isin(universe)]
    unusual = unusual_prints(flow, cfg.flow)
    if len(unusual):
        unusual = unusual[(unusual["date"] >= start) & unusual["ticker"].isin(universe)]
    lost_buys = buys[buys["ticker"].isin(lost)]
    lost_flow = unusual[unusual["ticker"].isin(lost)] if len(unusual) else unusual
    d = trades[trades["exit_reason"] == "delisted"] if len(trades) else trades
    return {
        "universe": len(universe), "traded": len(universe & set(panel)),
        "missing": missing, "short": short, "delisted": delisted,
        "insider_buys": len(buys), "lost_insider_buys": len(lost_buys),
        "lost_insider_value": float(lost_buys["value"].sum()) if len(lost_buys) else 0.0,
        "unusual_prints": len(unusual), "lost_unusual_prints": len(lost_flow),
        "delisted_trades": len(d), "delisted_avg_r": float(d["r"].mean()) if len(d) else float("nan"),
        "haircut": cfg.survivorship.delist_exit_haircut,
    }
