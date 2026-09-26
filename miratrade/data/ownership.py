"""Schedule 13D / 13G filings: someone crossed 5% of a company's shares.

* **13D**: an owner who may try to influence the company (activists) — the stronger signal.
* **13G**: a passive owner. The index giants file one for nearly every stock they hold past 5%,
  so their 13Gs are flagged ``passive`` and carry little information.

Source: EDGAR's quarterly ``full-index/form.gz``. It lists each filing once per party — the
*subject* company and the *filer* — under each party's own folder but with the same file name
(the accession number), so the subject is the party that
has a stock ticker, without downloading every filing. Only when both parties have a ticker is
the filing's header fetched to tell them apart.

Completed quarters are cached as small CSVs of the 13D/13G rows; the current quarter's index
grows daily and is always fetched again.
"""
from __future__ import annotations

import gzip
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from miratrade.config import CACHE_DIR
from miratrade.data.sec import ARCHIVE_URL, SecClient

FULL_INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/form.gz"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
OWNERSHIP_COLUMNS = ["accession", "filing_date", "ticker", "subject_cik", "filer", "kind",
                     "amendment", "passive"]

_LINE = re.compile(r"^(SC 13[DG](?:/A)?|SCHEDULE 13[DG](?:/A)?)\s{2,}(.+?)\s{2,}(\d+)\s+"
                   r"(\d{4}-?\d{2}-?\d{2})\s+(edgar/\S+)\s*$")
_SUBJECT = re.compile(rb"SUBJECT COMPANY:.*?CENTRAL INDEX KEY:\s*(\d+)", re.S)


def parse_13dg_index(text: str) -> pd.DataFrame:
    """13D/13G lines of an EDGAR ``form.idx``: one row per (filing, party)."""
    rows = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if m:
            form, name, cik, filed, path = m.groups()
            rows.append({"form": form, "name": name.strip(), "cik": cik.lstrip("0"),
                         "filing_date": pd.Timestamp(filed), "path": path})
    return pd.DataFrame(rows, columns=["form", "name", "cik", "filing_date", "path"])


def cik_ticker_map(client: SecClient | None = None, insiders: pd.DataFrame | None = None) -> dict[str, str]:
    """CIK -> ticker. The SEC's current list first; issuers seen in insider filings fill in
    companies that no longer trade (their ticker as of their latest filing)."""
    out: dict[str, str] = {}
    if insiders is not None and len(insiders) and "issuer_cik" in insiders:
        known = insiders[insiders["issuer_cik"].astype(str).str.len() > 0].sort_values("filing_date")
        out.update(dict(zip(known["issuer_cik"].astype(str), known["ticker"])))
    if client is not None:
        raw = client.get(TICKERS_URL, cache=False)
        if raw:
            rows = json.loads(raw).values()
            current: dict[str, str] = {}
            for r in rows:                      # several share classes: keep the first listed
                current.setdefault(str(r["cik_str"]), r["ticker"].upper().replace("-", "."))
            out.update(current)
    return out


def resolve_subjects(rows: pd.DataFrame, cik_map: dict[str, str], fetch_header=None,
                     passive_filers: tuple[str, ...] = ()) -> tuple[pd.DataFrame, dict]:
    """One row per filing with the subject's ticker. ``fetch_header(path) -> bytes`` breaks
    ties when several parties have a ticker; without it those filings are skipped."""
    out, unresolved, ambiguous = [], 0, 0
    passive_re = re.compile("|".join(map(re.escape, passive_filers)), re.I) if passive_filers else None
    # Each party's line has its own folder (edgar/data/<its CIK>/<accession>.txt): group on the file name.
    rows = rows.assign(accession=rows["path"].map(lambda p: Path(p).stem))
    for accession, g in rows.groupby("accession", sort=False):
        path = g["path"].iat[0]
        parties = g.drop_duplicates("cik")
        listed = parties[parties["cik"].isin(cik_map)]
        subject = None
        if len(listed) == 1:
            subject = listed.iloc[0]
        elif len(listed) > 1:
            ambiguous += 1
            head = fetch_header(path) if fetch_header else None
            m = _SUBJECT.search(head or b"")
            if m:
                cik = m.group(1).decode().lstrip("0")
                hit = listed[listed["cik"] == cik]
                subject = hit.iloc[0] if len(hit) else None
        else:
            unresolved += 1
        if subject is None:
            continue
        filer = "; ".join(parties.loc[parties["cik"] != subject["cik"], "name"]) or subject["name"]
        form = g["form"].iat[0]
        out.append({
            "accession": accession, "filing_date": g["filing_date"].min(),
            "ticker": cik_map[subject["cik"]], "subject_cik": subject["cik"], "filer": filer,
            "kind": "13D" if "13D" in form else "13G", "amendment": form.endswith("/A"),
            "passive": bool(passive_re and passive_re.search(filer)),
        })
    stats = {"filings": rows["accession"].nunique() if len(rows) else 0, "resolved": len(out),
             "unresolved": unresolved, "ambiguous": ambiguous}
    return pd.DataFrame(out, columns=OWNERSHIP_COLUMNS), stats


def _quarter_rows(client: SecClient, year: int, q: int, current: bool, cache_dir: Path) -> pd.DataFrame:
    path = cache_dir / f"13dg_{year}q{q}.csv"
    if not current and path.exists():
        return pd.read_csv(path, dtype={"cik": str}, parse_dates=["filing_date"], keep_default_na=False)
    raw = client.get(FULL_INDEX_URL.format(year=year, q=q), cache=False)
    if raw is None:
        return parse_13dg_index("")
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    rows = parse_13dg_index(raw.decode("latin-1"))
    if not current:
        rows.to_csv(path, index=False)
    return rows


def fetch_ownership(start: date, end: date, cik_map: dict[str, str], client: SecClient | None = None,
                    passive_filers: tuple[str, ...] = (), cache_dir: Path = CACHE_DIR / "sec",
                    max_header_fetches: int = 5_000) -> tuple[pd.DataFrame, dict]:
    """All 13D/13G filings filed between ``start`` and ``end`` whose subject has a ticker."""
    client = client or SecClient()
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    today = date.today()
    current_q = (today.year, (today.month - 1) // 3 + 1)
    quarters = sorted({(d.year, (d.month - 1) // 3 + 1) for d in pd.date_range(start, end, freq="D").date})
    rows = pd.concat([_quarter_rows(client, y, q, (y, q) == current_q, cache_dir) for y, q in quarters],
                     ignore_index=True)
    rows = rows[(rows["filing_date"].dt.date >= start) & (rows["filing_date"].dt.date <= end)]

    budget = [max_header_fetches]

    def header(path: str) -> bytes | None:
        if budget[0] <= 0:
            return None
        budget[0] -= 1
        try:
            return client.get(ARCHIVE_URL.format(path=path))
        except Exception:  # one unreadable filing must not kill the run
            return None

    return resolve_subjects(rows, cik_map, header, passive_filers)
