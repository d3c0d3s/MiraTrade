"""Shares outstanding from the SEC's XBRL API (``data.sec.gov``), point in time by filing date,
so market capitalisation on a day = the shares known that day × that day's close.

Source: the cover-page tag ``dei:EntityCommonStockSharesOutstanding`` of each 10-K / 10-Q
(official SEC API, no key; fair access = declared User-Agent and ≤ 10 requests/second, which
``SecClient`` enforces for every process together). Cached on disk and refreshed weekly.
"""
from __future__ import annotations

import json
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from miratrade.config import CAP_TIERS

SHARES_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/dei/EntityCommonStockSharesOutstanding.json"
SHARES_COLUMNS = ["ticker", "filed", "shares"]


def parse_shares(payload: dict) -> pd.DataFrame:
    """``filed``, ``shares`` per filing. Companies with several share classes report one value
    per class on the cover: those are summed."""
    rows = payload.get("units", {}).get("shares", [])
    if not rows:
        return pd.DataFrame(columns=["filed", "shares"])
    df = pd.DataFrame(rows)
    df = df[pd.to_numeric(df["val"], errors="coerce") > 0]
    if df.empty:
        return pd.DataFrame(columns=["filed", "shares"])
    per = (df.groupby(["accn", "end"], as_index=False)
             .agg(shares=("val", "sum"), filed=("filed", "first"))
             .sort_values("end").groupby("accn").tail(1))           # one cover date per filing
    per["filed"] = pd.to_datetime(per["filed"])
    return per.sort_values("filed").drop_duplicates("filed", keep="last")[["filed", "shares"]].reset_index(drop=True)


def ticker_ciks(insiders: pd.DataFrame | None, tickers_json: dict | None = None,
                ownership: pd.DataFrame | None = None) -> dict[str, str]:
    """Ticker → CIK: the issuer CIK on its latest Form 4, else the 13D subject, else the SEC's
    ``company_tickers.json``."""
    out: dict[str, str] = {}
    if tickers_json:
        out.update({v["ticker"].upper(): str(v["cik_str"]) for v in tickers_json.values()})
    if ownership is not None and len(ownership):
        o = ownership.dropna(subset=["subject_cik"]).drop_duplicates("ticker", keep="last")
        out.update(dict(zip(o["ticker"], o["subject_cik"].astype(str))))
    if insiders is not None and len(insiders):
        i = insiders[insiders["issuer_cik"].astype(str).str.fullmatch(r"\d+")]
        i = i.sort_values("filing_date").drop_duplicates("ticker", keep="last")
        out.update(dict(zip(i["ticker"], i["issuer_cik"].astype(str))))
    return {t: c.lstrip("0") for t, c in out.items() if c.strip("0")}


def fetch_shares(tickers, ciks: dict[str, str], client, log: Callable[[str], None] = print) -> pd.DataFrame:
    """Shares outstanding history for each ticker that has a CIK (companies without XBRL cover
    data, e.g. most funds and foreign filers, are simply missing)."""
    frames = []
    for t in sorted(set(tickers)):
        cik = ciks.get(t)
        if not cik:
            continue
        try:
            raw = client.get(SHARES_URL.format(cik=int(cik)), missing=(404,), max_age_days=7)
        except Exception as e:                               # one company failing must not stop the run
            log(f"  no shares outstanding for {t}: {e}")
            continue
        if raw is None:
            continue
        s = parse_shares(json.loads(raw))
        if len(s):
            frames.append(s.assign(ticker=t))
    return pd.concat(frames, ignore_index=True)[SHARES_COLUMNS] if frames else pd.DataFrame(columns=SHARES_COLUMNS)


def cap_from_filings(insiders: pd.DataFrame | None, shares: pd.DataFrame | None) -> pd.Series:
    """Rough market capitalisation per ticker **without downloading any market data**: the price
    on the latest Form 4 open-market transaction × the shares outstanding known by then. It is a
    filing-day price, not today's, which is accurate enough to sort companies into size bands."""
    empty = pd.Series(dtype=float)
    if insiders is None or not len(insiders) or shares is None or shares.empty:
        return empty
    px = insiders[pd.to_numeric(insiders["price"], errors="coerce") > 0].copy()
    if px.empty:
        return empty
    px["filing_date"] = pd.to_datetime(px["filing_date"])
    px = px.sort_values("filing_date").drop_duplicates("ticker", keep="last")
    known = shares.sort_values("filed")
    out = {}
    for r in px.itertuples():
        hist = known[(known["ticker"] == r.ticker) & (known["filed"] <= r.filing_date)]
        if len(hist):
            out[r.ticker] = float(hist["shares"].iat[-1]) * float(r.price)
    return pd.Series(out, dtype=float)


def in_tier(cap: float | None, tier: str) -> bool:
    """Whether ``cap`` falls in the size band ``tier``. An unknown size is only kept by "all"."""
    low, high, _ = CAP_TIERS[tier]
    if tier == "all":
        return True
    if cap is None or not np.isfinite(cap):
        return False
    return (low is None or cap >= low) and (high is None or cap < high)


def filter_by_tier(tickers: Iterable[str], caps: pd.Series, tier: str) -> tuple[set[str], dict]:
    """The tickers to keep, plus counts for the log (kept, dropped by size, dropped for having no
    size at all) so nothing disappears silently."""
    tickers = set(tickers)
    if tier == "all":
        return tickers, {"kept": len(tickers), "too_big_or_small": 0, "unknown": 0}
    kept, unknown, off_band = set(), 0, 0
    for t in tickers:
        cap = caps.get(t)
        if cap is None or not np.isfinite(cap):
            unknown += 1
        elif in_tier(float(cap), tier):
            kept.add(t)
        else:
            off_band += 1
    return kept, {"kept": len(kept), "too_big_or_small": off_band, "unknown": unknown}


def tier_report(stats: dict, tier: str, translate=None) -> str:
    """How many companies the size filter kept. ``translate`` is the interface's ``t()``."""
    from miratrade.messages import sayer

    say = sayer(translate)
    if tier == "all":
        return say("Every size: {kept} companies.", kept=stats["kept"])
    return say("Size «{tier}»: {kept} companies; {off} outside the band and {unknown} with no size "
               "figure.", tier=say(CAP_TIERS[tier][2]), kept=stats["kept"],
               off=stats["too_big_or_small"], unknown=stats["unknown"])


def market_cap(dates: pd.DatetimeIndex, close: pd.Series, shares: pd.DataFrame | None, ticker: str) -> pd.Series:
    """Point-in-time market capitalisation (NaN before the first known filing)."""
    out = pd.Series(float("nan"), index=dates)
    if shares is None or shares.empty:
        return out
    s = shares[shares["ticker"] == ticker].sort_values("filed")
    if s.empty:
        return out
    # Price indexes and filing dates reach here with different datetime units depending on whether
    # the bars were cached or freshly downloaded; merge_asof refuses to mix them.
    left = pd.DataFrame({"date": pd.DatetimeIndex(dates).astype("datetime64[ns]")})
    right = pd.DataFrame({"date": pd.to_datetime(s["filed"]).astype("datetime64[ns]"),
                          "shares": s["shares"].to_numpy()})
    known = pd.merge_asof(left, right, on="date", direction="backward")
    return pd.Series(known["shares"].to_numpy() * close.to_numpy(), index=dates)
