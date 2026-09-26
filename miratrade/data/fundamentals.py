"""Shares outstanding from the SEC's XBRL API (``data.sec.gov``), point in time by filing date,
so market capitalisation on a day = the shares known that day × that day's close.

Source: the cover-page tag ``dei:EntityCommonStockSharesOutstanding`` of each 10-K / 10-Q
(official SEC API, no key; fair access = declared User-Agent and ≤ 10 requests/second, which
``SecClient`` enforces for every process together). Cached on disk and refreshed weekly.
"""
from __future__ import annotations

import json
from typing import Callable

import pandas as pd

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
            log(f"  sin acciones en circulación para {t}: {e}")
            continue
        if raw is None:
            continue
        s = parse_shares(json.loads(raw))
        if len(s):
            frames.append(s.assign(ticker=t))
    return pd.concat(frames, ignore_index=True)[SHARES_COLUMNS] if frames else pd.DataFrame(columns=SHARES_COLUMNS)


def market_cap(dates: pd.DatetimeIndex, close: pd.Series, shares: pd.DataFrame | None, ticker: str) -> pd.Series:
    """Point-in-time market capitalisation (NaN before the first known filing)."""
    out = pd.Series(float("nan"), index=dates)
    if shares is None or shares.empty:
        return out
    s = shares[shares["ticker"] == ticker].sort_values("filed")
    if s.empty:
        return out
    known = pd.merge_asof(pd.DataFrame({"date": dates}), s.rename(columns={"filed": "date"})[["date", "shares"]],
                          on="date", direction="backward")
    return pd.Series(known["shares"].to_numpy() * close.to_numpy(), index=dates)
