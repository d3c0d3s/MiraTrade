"""Massive (formerly Polygon.io) options data: real daily prices for the contracts our events buy.

The free Options Basic plan allows 5 requests a minute and 2 years of history, and does not
include flat files. That is too little to scan the whole market for unusual volume, but enough
for the event-driven question: for each event, fetch the daily bars of the one contract the
profile would have bought, and replace the Black-Scholes estimate with real prices.

* The API key lives in the Windows Credential Manager (``miratrade massive setup``) and is sent
  in the ``Authorization`` header, never in a URL.
* Every response is cached on disk, so a backfill can stop and resume; the limiter keeps to the
  plan's rate (``requests_per_minute``).
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

import pandas as pd

from miratrade.config import CACHE_DIR

BASE_URL = "https://api.massive.com"
KEY_NAME = "massive.api_key"


def occ_ticker(underlying: str, expiry: date, kind: str, strike: float) -> str:
    """Massive/OCC option ticker, e.g. ``O:AAPL261120C00150000``."""
    return f"O:{underlying.upper()}{expiry:%y%m%d}{kind.upper()}{int(round(strike * 1000)):08d}"


class MassiveClient:
    def __init__(self, api_key: str | None = None, cache_dir: Path = CACHE_DIR / "massive",
                 requests_per_minute: float = 5, session=None, sleep=time.sleep, store=None):
        if api_key is None:
            from miratrade.brokers.credentials import CredentialStore

            api_key = (store or CredentialStore()).get(KEY_NAME)
        if not api_key:
            raise RuntimeError("No Massive API key: run `miratrade massive setup`.")
        import requests

        self.session = session or requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.interval = 60.0 / requests_per_minute
        self.sleep = sleep
        self._last = -1e9
        self.requests = 0

    def get(self, path: str, params: dict | None = None) -> dict:
        key = re.sub(r"[^A-Za-z0-9._-]", "_", path + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items())))
        cached = self.cache_dir / f"{key[:180]}.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        for attempt in range(4):
            wait = self.interval - (time.monotonic() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
            resp = self.session.get(BASE_URL + path, params=params, timeout=60)
            if resp.status_code == 429 or resp.status_code >= 500:     # over the limit / transient
                self.sleep(self.interval * (2 ** attempt))
                continue
            break
        if resp.status_code in (401, 403):
            raise RuntimeError(f"Massive refused the request ({resp.status_code}): check the API key and plan.")
        if resp.status_code == 404:
            data = {"results": []}
        else:
            resp.raise_for_status()
            data = resp.json()
        cached.write_text(json.dumps(data), encoding="utf-8")
        return data

    def daily_bars(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """Daily OHLCV + VWAP of one option contract (empty if it never traded / doesn't exist)."""
        data = self.get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start:%Y-%m-%d}/{end:%Y-%m-%d}",
                        {"adjusted": "true", "sort": "asc", "limit": 50000})
        rows = data.get("results") or []
        df = pd.DataFrame(rows, columns=["t", "o", "h", "l", "c", "v", "vw", "n"])
        idx = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert("America/New_York")
        df.index = pd.DatetimeIndex(idx.dt.tz_localize(None).dt.normalize(), name="date")
        return df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
                                  "vw": "vwap", "n": "trades"}).drop(columns="t")

    def contracts(self, underlying: str, expiry: date, kind: str = "call", as_of: date | None = None) -> pd.DataFrame:
        """Listed contracts of one expiry (expired ones included), to find the real strike grid."""
        params = {"underlying_ticker": underlying.upper(), "expiration_date": f"{expiry:%Y-%m-%d}",
                  "contract_type": kind, "limit": 1000, "expired": "true"}
        if as_of:
            params["as_of"] = f"{as_of:%Y-%m-%d}"
        rows = self.get("/v3/reference/options/contracts", params).get("results") or []
        return pd.DataFrame(rows, columns=["ticker", "underlying_ticker", "expiration_date", "strike_price",
                                           "contract_type", "shares_per_contract"])


def real_contract_bars(client: MassiveClient, underlying: str, entry_day: date, expiry: date,
                       strike: float, end: date) -> tuple[str, pd.DataFrame]:
    """Bars of the modelled contract; if that exact strike isn't listed, the nearest listed one."""
    ticker = occ_ticker(underlying, expiry, "C", strike)
    bars = client.daily_bars(ticker, entry_day, end)
    if len(bars):
        return ticker, bars
    listed = client.contracts(underlying, expiry, "call", as_of=entry_day)
    if listed.empty:
        return ticker, bars
    nearest = listed.iloc[(listed["strike_price"] - strike).abs().argsort()].iloc[0]
    return nearest["ticker"], client.daily_bars(nearest["ticker"], entry_day, end)
