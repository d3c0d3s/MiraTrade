"""What kind of issuer a ticker is: an operating company, a fund (closed-end fund, ETF, BDC,
interval fund) or a SPAC. Insider buys in funds and SPACs say little about a business, so the
event filters can drop them.

Primary source: the SEC company profile (``data.sec.gov/submissions``: SIC code and entity type),
cached on disk. When the profile is unavailable the issuer's name decides.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Iterable

import pandas as pd

SPAC_SIC = {"6770"}                                   # blank checks
FUND_SIC = {"6722", "6726", "6799"}                   # open-end / closed-end investment offices, investors NEC
_FUND_NAME = re.compile(r"\b(FUND|FUNDS|ETF|MUNICIPAL|MUNI|TERM TRUST|INCOME TRUST|INCOME SECURITIES|"
                        r"OPPORTUNITIES TRUST|STRATEGIES TRUST|STRATEGY TRUST|BDC|INTERVAL|PORTFOLIO)\b", re.I)
_SPAC_NAME = re.compile(r"\bACQUISITION(S)?\s+(CORP|CORPORATION|CO|COMPANY|HOLDINGS|LTD|LIMITED|INC)\b|"
                        r"\bBLANK CHECK\b", re.I)


def kind_from_name(name: str) -> str:
    name = str(name or "")
    if _SPAC_NAME.search(name):
        return "spac"
    if _FUND_NAME.search(name):
        return "fund"
    return "company"


def kind_from_profile(profile: dict, name: str = "") -> str:
    sic = str(profile.get("sic") or "").strip()
    if sic in SPAC_SIC:
        return "spac"
    if sic in FUND_SIC:
        return "fund"
    by_name = kind_from_name(profile.get("name") or name)
    if sic or by_name != "company":
        return by_name if not sic else "company"
    # Registered investment companies carry no SIC code; operating companies almost always do.
    return "company" if str(profile.get("entityType") or "").lower() == "operating" else "fund"


def classify_issuers(issuers: pd.DataFrame, fetch_profile: Callable[[str], dict | None] | None = None,
                     log: Callable[[str], None] = lambda m: None) -> pd.DataFrame:
    """``issuers``: columns ``ticker``, ``issuer_cik``, ``issuer``. Returns ``ticker, kind, source``."""
    rows = []
    failed = 0
    for r in issuers.drop_duplicates("ticker").itertuples(index=False):
        prof = None
        if fetch_profile is not None and r.issuer_cik and failed < 20:
            try:
                prof = fetch_profile(str(r.issuer_cik))
            except Exception:                           # blocked or down: fall back to the name
                failed += 1
        if prof:
            rows.append((r.ticker, kind_from_profile(prof, r.issuer), "sec"))
        else:
            rows.append((r.ticker, kind_from_name(r.issuer), "name"))
    if failed >= 20:
        log("  perfil de la SEC no disponible: el tipo de emisor sale del nombre")
    return pd.DataFrame(rows, columns=["ticker", "kind", "source"])


def sec_profile_fetcher(client) -> Callable[[str], dict | None]:
    def fetch(cik: str) -> dict | None:
        raw = client.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
        if raw is None:
            return None
        d = json.loads(raw)
        return {k: d.get(k) for k in ("sic", "sicDescription", "entityType", "name")}
    return fetch


FUND_FORMS = ("N-PORT", "N-CEN", "N-CSR", "N-2", "N-54A", "40-17G", "485BPOS", "497")
_INDEX_LINE = re.compile(r"^(\S+(?: \S+)*?)\s{2,}.+?\s{2,}(\d+)\s+\d{4}-?\d{2}-?\d{2}\s+\S+\s*$")
FORM_INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/form.gz"


def fund_ciks_from_index(text: str) -> set[str]:
    """CIKs that filed any registered-fund form (N-PORT, N-CEN, N-CSR, N-2, BDC election N-54A …)
    in an EDGAR ``form.idx``."""
    out = set()
    for line in text.splitlines():
        if not line.startswith(("N-", "40-17G", "485", "497")):
            continue
        m = _INDEX_LINE.match(line)
        if m and m.group(1).startswith(FUND_FORMS):
            out.add(m.group(2).lstrip("0"))
    return out


def fetch_fund_ciks(client, years: Iterable[int], quarter: int = 2) -> set[str]:
    """Registered funds seen in one quarter of each year (every live fund files N-PORT quarterly)."""
    import gzip

    ciks: set[str] = set()
    for y in years:
        raw = client.get(FORM_INDEX_URL.format(year=y, q=quarter), missing=(403, 404))
        if raw is None:
            continue
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        ciks |= fund_ciks_from_index(raw.decode("latin-1"))
    return ciks


def classify_by_index(issuers: pd.DataFrame, fund_ciks: set[str]) -> pd.DataFrame:
    """``kind`` per ticker: SPAC by name, fund if its CIK filed fund forms (or its name says so)."""
    rows = []
    for r in issuers.drop_duplicates("ticker").itertuples(index=False):
        k = kind_from_name(r.issuer)
        if k == "company" and str(r.issuer_cik or "").lstrip("0") in fund_ciks:
            k = "fund"
        rows.append((r.ticker, k, "índice EDGAR" if str(r.issuer_cik or "").lstrip("0") in fund_ciks else "nombre"))
    return pd.DataFrame(rows, columns=["ticker", "kind", "source"])


def issuer_table(insiders: pd.DataFrame, tickers: Iterable[str] | None = None) -> pd.DataFrame:
    """The latest issuer name and CIK per ticker from the insider filings."""
    df = insiders[["ticker", "issuer_cik", "issuer", "filing_date"]].dropna(subset=["ticker"])
    if tickers is not None:
        df = df[df["ticker"].isin(set(tickers))]
    return df.sort_values("filing_date").drop_duplicates("ticker", keep="last")[["ticker", "issuer_cik", "issuer"]]
