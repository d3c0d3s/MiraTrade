"""Price-action indicators and swing-trade setup detection (all computed on closed bars)."""
from __future__ import annotations

import numpy as np
import pandas as pd

SETUPS = ("breakout", "pullback", "oversold_bounce")


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0).where(loss.notna())


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["close"]
    out["sma20"] = c.rolling(20).mean()
    out["sma50"] = c.rolling(50).mean()
    out["sma200"] = c.rolling(200, min_periods=120).mean()
    out["atr"] = atr(out)
    out["rsi"] = rsi(c)
    out["ret_20d"] = c.pct_change(20)
    out["rel_volume"] = out["volume"] / out["volume"].rolling(20).mean().shift()
    out["high_20_prior"] = out["high"].rolling(20).max().shift()
    return out


def detect_setups(ind: pd.DataFrame) -> pd.DataFrame:
    """Boolean column per setup, True on the bar where the setup completes."""
    c = ind["close"]
    uptrend = (c > ind["sma50"]) & (ind["sma20"] > ind["sma50"])
    setups = pd.DataFrame(index=ind.index)
    setups["breakout"] = (c > ind["high_20_prior"]) & (ind["rel_volume"] >= 1.5)
    # Pulled back into the 20-day average inside an uptrend, then closed green.
    near_sma20 = (ind["low"] <= ind["sma20"] + 0.25 * ind["atr"]) & (c >= ind["sma20"])
    setups["pullback"] = uptrend & near_sma20 & (c > ind["open"]) & ind["rsi"].between(40, 60)
    # RSI crossed back above 30 from oversold.
    setups["oversold_bounce"] = (ind["rsi"] > 30) & (ind["rsi"].shift() <= 30)
    return setups.fillna(False)
