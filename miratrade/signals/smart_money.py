"""Smart-money features, point-in-time.

* 13D / 13G filings are visible from their **filing date**.
* FINRA short volume for a session is published that evening, after the close and before the
  next open, so it can inform a signal taken at that close (entries fill at the next open).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from miratrade.config import SmartMoneyParams

OWNERSHIP_FEATURES = ["own_13d", "own_13g", "own_fresh"]
SHORT_FEATURES = ["short_ratio", "short_z", "short_low", "short_high"]
DARK_FEATURES = ["dark_ratio", "dark_z", "dark_low", "dark_high"]
MAX_SANE_DARK_RATIO = 1.2       # above this the two volume sources disagree (splits, adjustments)


def _window_counts(filed: np.ndarray, d: np.ndarray, window: np.timedelta64) -> np.ndarray:
    """Number of filings with ``d - window < filed <= d`` on each date (``filed`` sorted)."""
    return np.searchsorted(filed, d, side="right") - np.searchsorted(filed, d - window, side="right")


def ownership_features(filings: pd.DataFrame, dates: pd.DatetimeIndex, ticker: str,
                       p: SmartMoneyParams = SmartMoneyParams()) -> pd.DataFrame:
    """``own_13d``: 13D filings (new or amended) in the lookback; ``own_13g``: new 13Gs by
    non-index filers; ``own_fresh``: one of those new filings arrived since the previous bar."""
    out = pd.DataFrame(0.0, index=dates, columns=OWNERSHIP_FEATURES)
    if filings is None or filings.empty:
        return out
    f = filings[filings["ticker"] == ticker]
    if f.empty:
        return out
    filed = pd.to_datetime(f["filing_date"]).dt.normalize()
    d = dates.to_numpy("datetime64[ns]")
    window = np.timedelta64(pd.Timedelta(days=p.lookback_days).value, "ns")

    def sorted_dates(mask: pd.Series) -> np.ndarray:
        return np.sort(filed[mask].to_numpy("datetime64[ns]"))

    is_13d = f["kind"] == "13D"
    new = ~f["amendment"].astype(bool)
    active_13g = (f["kind"] == "13G") & new & ~f["passive"].astype(bool)
    out["own_13d"] = _window_counts(sorted_dates(is_13d), d, window)
    out["own_13g"] = _window_counts(sorted_dates(active_13g), d, window)
    fresh = sorted_dates((is_13d & new) | active_13g)
    prev = np.empty_like(d)
    if len(d):
        prev[0], prev[1:] = d[0] - window, d[:-1]
    # A new filing dated after the previous bar and on/before this one (covers weekends).
    out["own_fresh"] = (np.searchsorted(fresh, d, side="right") > np.searchsorted(fresh, prev, side="right")
                        ).astype(float)
    return out


def short_features(short_volume: pd.DataFrame, dates: pd.DatetimeIndex, ticker: str,
                   p: SmartMoneyParams = SmartMoneyParams()) -> pd.DataFrame:
    """Short-volume ratio, its z-score against the ticker's own recent sessions, and flags for
    unusually low / high shorting (``|z| >= short_z``). Missing data stays NaN / 0."""
    out = pd.DataFrame({"short_ratio": np.nan, "short_z": np.nan, "short_low": 0.0, "short_high": 0.0},
                       index=dates)
    if short_volume is None or short_volume.empty:
        return out
    s = short_volume[short_volume["ticker"] == ticker]
    if s.empty:
        return out
    s = s.groupby("date")[["short_volume", "total_volume"]].sum().sort_index()
    ratio = (s["short_volume"] / s["total_volume"].where(s["total_volume"] > 0))
    mean = ratio.rolling(p.short_window, min_periods=p.short_min_periods).mean()
    sd = ratio.rolling(p.short_window, min_periods=p.short_min_periods).std()
    z = (ratio - mean) / sd.where(sd > 0)
    out["short_ratio"] = ratio.reindex(dates)
    out["short_z"] = z.reindex(dates)
    out["short_low"] = (out["short_z"] <= -p.short_z).astype(float)
    out["short_high"] = (out["short_z"] >= p.short_z).astype(float)
    return out


def dark_features(short_volume: pd.DataFrame, volume: pd.Series, ticker: str,
                  p: SmartMoneyParams = SmartMoneyParams()) -> pd.DataFrame:
    """Share of the day's volume executed **off-exchange** — dark pools, ATS and wholesalers —
    with its z-score against the ticker's own recent sessions.

    FINRA's daily Reg SHO file reports the volume its facilities handled, which is the off-exchange
    part; ``volume`` is the consolidated volume from the price bars. Their ratio normally sits
    around 35–60 %. A jump means size was worked away from the lit market that day, which is the
    footprint institutions leave. Like the short ratio, it is only comparable with the ticker's own
    history, never across tickers.
    """
    dates = volume.index
    out = pd.DataFrame({"dark_ratio": np.nan, "dark_z": np.nan, "dark_low": 0.0, "dark_high": 0.0},
                       index=dates)
    if short_volume is None or short_volume.empty:
        return out
    s = short_volume[short_volume["ticker"] == ticker]
    if s.empty:
        return out
    off = s.groupby("date")["total_volume"].sum().sort_index().reindex(dates)
    consolidated = pd.to_numeric(volume, errors="coerce")
    ratio = off / consolidated.where(consolidated > 0)
    ratio = ratio.where((ratio > 0) & (ratio <= MAX_SANE_DARK_RATIO))
    mean = ratio.rolling(p.dark_window, min_periods=p.dark_min_periods).mean()
    sd = ratio.rolling(p.dark_window, min_periods=p.dark_min_periods).std()
    out["dark_ratio"] = ratio
    out["dark_z"] = (ratio - mean) / sd.where(sd > 0)
    out["dark_low"] = (out["dark_z"] <= -p.dark_z).astype(float)
    out["dark_high"] = (out["dark_z"] >= p.dark_z).astype(float)
    return out
