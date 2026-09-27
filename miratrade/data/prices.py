"""Daily OHLCV bars, cached to disk, from the source chosen in settings (``data.price_source``).

* ``schwab`` (default): the user's OWN Schwab account through their personal developer app
  (``miratrade schwab setup`` / ``login``). Allowed by Schwab's individual-developer terms for
  the account holder's own use; the data is never shared with other users.
* ``research``: public web sources (Yahoo through yfinance, then Stooq). Their terms allow
  personal, non-commercial use at most, so this is off by default and must be switched on by
  hand for one's own research. It is never the default of a distributed app.

Each source has its own cache folder, so research data never ends up feeding the licensed path.
"""
from __future__ import annotations

import io
import time
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd

from miratrade.config import CACHE_DIR

OHLCV = ["open", "high", "low", "close", "volume"]
SOURCES = {"schwab": "Schwab (tu cuenta)", "research": "Webs públicas: Yahoo / Stooq (solo investigación personal)"}
SCHWAB_PACE_S = 0.6                     # ~100 requests/minute, under Schwab's 120/min for market data


class PriceSourceError(RuntimeError):
    """The chosen source cannot be used (not connected, or not allowed): the message says what to do."""


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


def research_fetch(ticker: str, start: date, end: date) -> pd.DataFrame | None:
    df = _from_yfinance(ticker, start, end)
    return df if df is not None else _from_stooq(ticker, start, end)


FIX_HINT = ("Conéctala en Configuración (o con `miratrade schwab setup` y `miratrade schwab login`). Solo para "
            "tu investigación personal puedes elegir la fuente «Webs públicas» en Configuración.")


def source_ready(source: str | None = None) -> tuple[bool, str]:
    """Whether the chosen price source could download right now, **without downloading anything**,
    so a long run can stop before it starts instead of after."""
    source = _source(source)
    if source == "research":
        return True, "Precios de webs públicas (Yahoo / Stooq): solo para tu investigación personal."
    try:
        from miratrade.brokers.schwab import SchwabAuth, hours_until_relogin

        auth = SchwabAuth()
        if not auth.configured():
            return False, "Los precios vienen de tu cuenta de Schwab y faltan las credenciales de tu app."
        hours = hours_until_relogin(auth)
        if hours is None:
            return False, "Los precios vienen de tu cuenta de Schwab y falta iniciar sesión."
        if hours <= 0:
            return False, "Los precios vienen de tu cuenta de Schwab y la sesión caducó."
        return True, f"Precios de tu cuenta de Schwab (sesión válida {hours / 24:.1f} días más)."
    except Exception as e:                       # keyring unavailable, schwab-py missing…
        return False, f"No se pudo comprobar la sesión de Schwab: {e}."


def schwab_fetcher(broker=None) -> Callable[[str, date, date], pd.DataFrame | None]:
    """Daily bars from the user's Schwab account; raises ``PriceSourceError`` when not connected."""
    from miratrade.brokers.schwab import SchwabAuth, SchwabBroker

    if broker is None:
        ok, why = source_ready("schwab")
        if not ok:
            raise PriceSourceError(f"{why} {FIX_HINT}")
        broker = SchwabBroker(auth=SchwabAuth())
    last = [0.0]

    def fetch(ticker: str, start: date, end: date) -> pd.DataFrame | None:
        wait = SCHWAB_PACE_S - (time.monotonic() - last[0])
        if wait > 0:
            time.sleep(wait)
        last[0] = time.monotonic()
        df = broker.price_history(ticker.replace(".", "/"), start, end)   # Schwab writes BRK/B
        return None if df is None or df.empty else _normalise(df)
    return fetch


def _source(source: str | None) -> str:
    if source is None:
        from miratrade.config import load_user_config
        source = load_user_config().data.price_source
    if source not in SOURCES:
        raise ValueError(f"Unknown price source {source!r}: use one of {', '.join(SOURCES)}")
    return source


def load_prices(tickers: list[str], start: date, end: date, cache_dir: Path = CACHE_DIR / "prices",
                source: str | None = None, fetch: Callable | None = None) -> dict[str, pd.DataFrame]:
    """Return ``{ticker: OHLCV frame}``; tickers with no data are left out. ``fetch`` overrides
    the download (tests)."""
    source = _source(source)
    # the research cache keeps its historical location; the licensed one gets its own folder
    folder = Path(cache_dir) / "schwab" if source == "schwab" else Path(cache_dir)
    folder.mkdir(parents=True, exist_ok=True)
    out, missing = {}, []
    for t in sorted(set(tickers)):
        path = folder / f"{t}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
        if path.exists():
            out[t] = pd.read_csv(path, index_col="date", parse_dates=True)
        else:
            missing.append((t, path))
    if not missing:
        return out
    if fetch is None:
        fetch = schwab_fetcher() if source == "schwab" else research_fetch
    for t, path in missing:
        try:
            df = fetch(t, start, end)
        except PriceSourceError:
            raise
        except Exception:  # one ticker failing (unknown symbol, network) must not kill the run
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
