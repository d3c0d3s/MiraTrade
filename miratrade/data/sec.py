"""Insider transactions (SEC Form 4) from EDGAR.

Two sources, both free and official:

* The quarterly *Insider Transactions Data Sets* (bulk TSV zips) for completed quarters.
* The EDGAR daily index + each filing's Form 4 XML for the current quarter, which the
  bulk data sets do not cover yet.

Everything is normalised to one DataFrame, see ``INSIDER_COLUMNS``.
"""
from __future__ import annotations

import io
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from miratrade.config import CACHE_DIR, SEC_USER_AGENT

INSIDER_COLUMNS = [
    "accession", "filing_date", "trade_date", "ticker", "issuer", "owner", "owner_cik",
    "is_officer", "is_director", "is_ten_pct", "title", "code", "shares", "price",
    "value", "owned_after", "delta_own_pct",
]

BULK_URL = ("https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/"
            "{year}q{q}_form345.zip")
DAILY_INDEX_URL = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{q}/form.{ymd}.idx"
ARCHIVE_URL = "https://www.sec.gov/Archives/{path}"


class SecClient:
    """Polite EDGAR client: required User-Agent, <=8 req/s, on-disk cache."""

    def __init__(self, user_agent: str = SEC_USER_AGENT, cache_dir: Path = CACHE_DIR / "sec"):
        import requests

        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last = 0.0

    def get(self, url: str, cache: bool = True) -> bytes | None:
        key = self.cache_dir / re.sub(r"[^A-Za-z0-9._-]", "_", url.split("://", 1)[-1])
        if cache and key.exists():
            return key.read_bytes()
        wait = 0.125 - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        resp = self.session.get(url, timeout=60)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        if cache:
            key.write_bytes(resp.content)
        return resp.content


# --------------------------------------------------------------------------- bulk data sets

def _parse_sec_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="%d-%b-%Y", errors="coerce")


def parse_bulk_zip(data: bytes) -> pd.DataFrame:
    """Parse one quarterly ``form345.zip`` into normalised insider rows."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        def read(name: str) -> pd.DataFrame:
            member = next(n for n in zf.namelist() if n.upper().endswith(name))
            return pd.read_csv(zf.open(member), sep="\t", dtype=str, quoting=3)

        sub = read("SUBMISSION.TSV")
        owners = read("REPORTINGOWNER.TSV")
        trans = read("NONDERIV_TRANS.TSV")

    owners = owners.groupby("ACCESSION_NUMBER", as_index=False).first()
    df = trans.merge(sub, on="ACCESSION_NUMBER").merge(owners, on="ACCESSION_NUMBER")
    rel = df["RPTOWNER_RELATIONSHIP"].fillna("")
    out = pd.DataFrame({
        "accession": df["ACCESSION_NUMBER"],
        "filing_date": _parse_sec_date(df["FILING_DATE"]),
        "trade_date": _parse_sec_date(df["TRANS_DATE"]),
        "ticker": df["ISSUERTRADINGSYMBOL"].str.upper().str.strip(),
        "issuer": df["ISSUERNAME"],
        "owner": df["RPTOWNERNAME"],
        "owner_cik": df["RPTOWNERCIK"],
        "is_officer": rel.str.contains("Officer"),
        "is_director": rel.str.contains("Director"),
        "is_ten_pct": rel.str.contains("TenPercent"),
        "title": df.get("RPTOWNER_TITLE", pd.Series("", index=df.index)).fillna(""),
        "code": df["TRANS_CODE"],
        "shares": pd.to_numeric(df["TRANS_SHARES"], errors="coerce"),
        "price": pd.to_numeric(df["TRANS_PRICEPERSHARE"], errors="coerce"),
        "owned_after": pd.to_numeric(df["SHRS_OWND_FOLWNG_TRANS"], errors="coerce"),
    })
    return _finish(out)


# --------------------------------------------------------------------------- Form 4 XML

def _text(node: ET.Element | None, path: str) -> str:
    if node is None:
        return ""
    found = node.find(path)
    if found is None:
        return ""
    value = found.find("value")
    return ((value if value is not None else found).text or "").strip()


def _flag(node: ET.Element | None, path: str) -> bool:
    return _text(node, path).lower() in {"1", "true"}


def parse_form4_xml(xml: str, accession: str = "", filing_date: str | None = None) -> pd.DataFrame:
    """Parse one ``<ownershipDocument>`` into normalised non-derivative transaction rows."""
    root = ET.fromstring(xml)
    issuer = root.find("issuer")
    owner = root.find("reportingOwner")
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    rows = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        rows.append({
            "accession": accession,
            "filing_date": filing_date,
            "trade_date": _text(tx, "transactionDate"),
            "ticker": _text(issuer, "issuerTradingSymbol").upper(),
            "issuer": _text(issuer, "issuerName"),
            "owner": _text(owner, "reportingOwnerId/rptOwnerName"),
            "owner_cik": _text(owner, "reportingOwnerId/rptOwnerCik"),
            "is_officer": _flag(rel, "isOfficer"),
            "is_director": _flag(rel, "isDirector"),
            "is_ten_pct": _flag(rel, "isTenPercentOwner"),
            "title": _text(rel, "officerTitle"),
            "code": _text(tx, "transactionCoding/transactionCode"),
            "shares": _text(tx, "transactionAmounts/transactionShares"),
            "price": _text(tx, "transactionAmounts/transactionPricePerShare"),
            "owned_after": _text(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction"),
        })
    df = pd.DataFrame(rows, columns=[c for c in INSIDER_COLUMNS if c not in ("value", "delta_own_pct")])
    for col in ("shares", "price", "owned_after"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("filing_date", "trade_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return _finish(df)


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["value"] = df["shares"] * df["price"]
    prior = df["owned_after"] - df["shares"]
    df["delta_own_pct"] = (df["shares"] / prior.where(prior > 0)).fillna(1.0)  # new position = +100%
    return df[INSIDER_COLUMNS]


def parse_daily_index(text: str) -> list[tuple[str, str]]:
    """Return ``(accession_path, date_filed)`` for every Form 4 in a ``form.YYYYMMDD.idx``."""
    out, seen = [], set()
    for line in text.splitlines():
        if not line.startswith("4 "):
            continue
        path = line.split()[-1]
        date_filed = line.split()[-2]
        if path.startswith("edgar/") and path not in seen:
            seen.add(path)
            out.append((path, date_filed))
    return out


# --------------------------------------------------------------------------- orchestration

def fetch_insiders(start: date, end: date, client: SecClient | None = None,
                   codes: tuple[str, ...] = ("P", "S")) -> pd.DataFrame:
    """All open-market insider buys/sells filed between ``start`` and ``end`` (inclusive)."""
    client = client or SecClient()
    frames = []
    today = date.today()
    current_q = (today.year, (today.month - 1) // 3 + 1)

    quarters = sorted({(d.year, (d.month - 1) // 3 + 1)
                       for d in pd.date_range(start, end, freq="D").date})
    for year, q in quarters:
        blob = None if (year, q) == current_q else client.get(BULK_URL.format(year=year, q=q))
        if blob is not None:
            frames.append(parse_bulk_zip(blob))
            continue
        # Bulk set not published yet: walk the daily index for that quarter's days.
        q_start = max(start, date(year, 3 * q - 2, 1))
        q_end = min(end, (date(year + (q == 4), 1 if q == 4 else 3 * q + 1, 1) - timedelta(days=1)))
        for day in pd.bdate_range(q_start, q_end).date:
            idx = client.get(DAILY_INDEX_URL.format(year=year, q=q, ymd=day.strftime("%Y%m%d")))
            if idx is None:
                continue
            filings = parse_daily_index(idx.decode("latin-1"))
            print(f"  {day}: {len(filings)} Form 4 filings", flush=True)
            for path, filed in filings:
                raw = client.get(ARCHIVE_URL.format(path=path))
                if raw is None:
                    continue
                m = re.search(rb"<ownershipDocument>.*?</ownershipDocument>", raw, re.S)
                if not m:
                    continue
                try:
                    frames.append(parse_form4_xml(m.group(0).decode("utf-8", "replace"),
                                                  accession=Path(path).stem,
                                                  filing_date=filed))
                except ET.ParseError:
                    continue

    if not frames:
        return pd.DataFrame(columns=INSIDER_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    mask = (df["filing_date"].dt.date >= start) & (df["filing_date"].dt.date <= end)
    df = df[mask & df["code"].isin(codes) & df["ticker"].str.fullmatch(r"[A-Z.]{1,6}", na=False)]
    return df.drop_duplicates().reset_index(drop=True)
