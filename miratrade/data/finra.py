"""FINRA Reg SHO daily short-sale volume (free, published each evening for that session).

Each file covers the volume reported to FINRA's facilities (off-exchange and some exchanges),
not the whole market, so the *ratio* of short to total volume is the usable number, compared
with the ticker's own recent history rather than across tickers.

Raw day files are cached gzip-compressed; a day with no file (a holiday) is skipped.
"""
from __future__ import annotations

import gzip
import io
import time
from datetime import date
from pathlib import Path

import pandas as pd

from miratrade.config import CACHE_DIR

SHORT_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt"
SHORT_COLUMNS = ["date", "ticker", "short_volume", "total_volume"]


def parse_short_volume(text: str, tickers: set[str] | None = None) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text), sep="|", dtype={"Date": str, "Symbol": str})
    df = df[df["Date"].str.fullmatch(r"\d{8}", na=False)]   # drops the trailing record-count line
    if tickers is not None:
        df = df[df["Symbol"].isin(tickers)]
    return pd.DataFrame({"date": pd.to_datetime(df["Date"], format="%Y%m%d"),
                         "ticker": df["Symbol"].str.upper(),
                         "short_volume": pd.to_numeric(df["ShortVolume"], errors="coerce"),
                         "total_volume": pd.to_numeric(df["TotalVolume"], errors="coerce")},
                        columns=SHORT_COLUMNS)


def fetch_short_volume(start: date, end: date, tickers: set[str] | None = None,
                       cache_dir: Path = CACHE_DIR / "finra", session=None,
                       min_interval: float = 0.1) -> pd.DataFrame:
    """Daily short volume for ``tickers`` (all symbols if ``None``) between two dates."""
    import requests

    session = session or requests.Session()
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames, last = [], 0.0
    for day in pd.bdate_range(start, end).date:
        path = cache_dir / f"shvol_{day:%Y%m%d}.txt.gz"
        if path.exists():
            text = gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
        else:
            if day >= date.today():             # today's file appears in the evening
                continue
            time.sleep(max(0.0, min_interval - (time.monotonic() - last)))
            last = time.monotonic()
            try:
                resp = session.get(SHORT_URL.format(ymd=f"{day:%Y%m%d}"), timeout=60)
            except requests.RequestException:
                continue
            if resp.status_code != 200 or not resp.text.startswith("Date|"):
                continue                        # holiday or not published
            text = resp.text
            path.write_bytes(gzip.compress(text.encode("utf-8")))
        frames.append(parse_short_volume(text, tickers))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SHORT_COLUMNS)
