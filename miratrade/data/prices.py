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
# Shown in the Settings screen, which translates them.
SOURCES = {"schwab": "Schwab (your account)",
           "research": "Public websites: Yahoo / Stooq (personal research only)"}
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


FIX_HINT = ("Connect it under Settings (or with `miratrade schwab setup` and `miratrade schwab "
            "login`). For your personal research only, you can choose the «Public websites» source "
            "under Settings.")


def source_ready(source: str | None = None, translate=None) -> tuple[bool, str]:
    """Whether the chosen price source could download right now, **without downloading anything**,
    so a long run can stop before it starts instead of after. ``translate`` is the interface's
    ``t()`` when the answer is shown on screen."""
    from miratrade.messages import sayer

    say = sayer(translate)
    source = _source(source)
    if source == "research":
        return True, say("Prices from public websites (Yahoo / Stooq): for your personal research "
                         "only.")
    try:
        from miratrade.brokers.schwab import SchwabAuth, hours_until_relogin

        auth = SchwabAuth()
        if not auth.configured():
            return False, say("Prices come from your Schwab account and your app credentials are "
                              "missing.")
        hours = hours_until_relogin(auth)
        if hours is None:
            return False, say("Prices come from your Schwab account and you have not signed in yet.")
        if hours <= 0:
            return False, say("Prices come from your Schwab account and the session expired.")
        return True, say("Prices from your Schwab account (session good for {days} more days).",
                         days=f"{hours / 24:.1f}")
    except Exception as e:                       # keyring unavailable, schwab-py missing…
        return False, say("Could not check the Schwab session: {error}.", error=e)


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


PRICE_SOURCE = "prices"          # coverage rows: the window each ticker has been ASKED for


def asked_span(db, tickers) -> dict[str, tuple[date, date]]:
    """The window each ticker has already been asked for, which is not the same as what came back.

    A company listed last month has no bars before it listed, and one that was delisted has none
    after. Judging by the stored bars alone, those tickers look short of the window for ever and are
    re-downloaded on every run — so what was *requested* is recorded, two rows per ticker.
    """
    names = sorted({str(t).upper() for t in tickers})
    if not names:
        return {}
    spans = {}
    for chunk in (names[i:i + 400] for i in range(0, len(names), 400)):
        marks = ",".join("?" * len(chunk))
        rows = db.execute(f"SELECT scope, min(day) a, max(day) b FROM coverage "
                          f"WHERE source = ? AND scope IN ({marks}) GROUP BY scope",
                          [PRICE_SOURCE, *chunk])
        for row in rows:
            if row["a"]:
                spans[row["scope"]] = (date.fromisoformat(row["a"]), date.fromisoformat(row["b"]))
    return spans


def load_prices(tickers: list[str], start: date, end: date, cache_dir: Path = CACHE_DIR / "prices",
                source: str | None = None, fetch: Callable | None = None,
                db=None) -> dict[str, pd.DataFrame]:
    """``{ticker: OHLCV frame}`` for the window, downloading only the days not stored yet.

    What is already in the market database is used, and a download asks only for the span missing at
    either edge — which in normal use is the handful of days since the last run. The old cache kept a
    CSV per ticker **per requested range**, so a window one day wider re-downloaded years of history:
    908 tickers had produced 1,486 files of overlapping data.

    A ticker with a hole in the middle of its stored history is refetched whole; that is rare, and
    cheaper to accept than to track every missing day separately.

    ``fetch`` overrides the download (tests) and ``db`` the database (tests, and callers that already
    have one open).
    """
    from miratrade import store

    source = _source(source)
    names = sorted({str(t).upper() for t in tickers})
    owned, db = db is None, db if db is not None else store.connect()
    try:
        spans = asked_span(db, names)
        wanted = []
        for t in names:
            span = spans.get(t)
            if span is None:
                wanted.append((t, start, end))
            elif start < span[0] or end > span[1]:
                # one call covering both edges, not the whole window again for every extra day
                wanted.append((t, min(start, span[0]), max(end, span[1])))
        if wanted:
            if fetch is None:
                fetch = schwab_fetcher() if source == "schwab" else research_fetch
            for t, first, last in wanted:
                try:
                    df = fetch(t, first, last)
                except PriceSourceError:
                    raise
                except Exception:      # one ticker failing must not kill the run
                    df = None
                if df is not None and not df.empty:
                    store.write(db, "prices", df.assign(ticker=t, source=source))
                # the window is recorded either way: a ticker with nothing to give must not be
                # asked again every run
                store.mark_covered(db, PRICE_SOURCE, [first, last],
                                   rows=0 if df is None else len(df), scope=t)
        return store.prices(db, names, start, end)
    finally:
        if owned:
            db.close()


def load_prices_csv(directory: Path) -> dict[str, pd.DataFrame]:
    """Load ``<TICKER>.csv`` files (date,open,high,low,close,volume) from a directory."""
    return {p.stem.upper(): _normalise(pd.read_csv(p, index_col=0))
            for p in sorted(Path(directory).glob("*.csv"))}
