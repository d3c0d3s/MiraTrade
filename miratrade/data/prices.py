"""Daily OHLCV bars. yfinance if installed, otherwise Stooq CSV; either way cached to disk."""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pandas as pd

from miratrade.config import CACHE_DIR

OHLCV = ["open", "high", "low", "close", "volume"]


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    return df[OHLCV].dropna().sort_index()


def _from_yfinance(ticker: str, start: date, end: date) -> pd.DataFrame | None:
    try:
        import yfinance as yf
    except ImportError:
        return None
    df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
    return None if df.empty else _normalise(df)


def _from_stooq(ticker: str, start: date, end: date) -> pd.DataFrame | None:
    import requests

    url = (f"https://stooq.com/q/d/l/?s={ticker.lower().replace('.', '-')}.us&i=d"
           f"&d1={start:%Y%m%d}&d2={end:%Y%m%d}")
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200 or not resp.text.startswith("Date"):
        return None
    return _normalise(pd.read_csv(io.StringIO(resp.text), index_col="Date"))


def load_prices(tickers: list[str], start: date, end: date,
                cache_dir: Path = CACHE_DIR / "prices") -> dict[str, pd.DataFrame]:
    """Return ``{ticker: OHLCV frame}``; tickers with no data are silently dropped."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for t in sorted(set(tickers)):
        path = cache_dir / f"{t}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
        if path.exists():
            df = pd.read_csv(path, index_col="date", parse_dates=True)
        else:
            try:
                df = _from_yfinance(t, start, end)
                if df is None:
                    df = _from_stooq(t, start, end)
            except Exception:  # network/data errors on one ticker must not kill the run
                df = None
            if df is None or df.empty:
                continue
            df.to_csv(path)
        out[t] = df
    return out


def load_prices_csv(directory: Path) -> dict[str, pd.DataFrame]:
    """Load ``<TICKER>.csv`` files (date,open,high,low,close,volume) from a directory."""
    return {p.stem.upper(): _normalise(pd.read_csv(p, index_col=0))
            for p in sorted(Path(directory).glob("*.csv"))}
