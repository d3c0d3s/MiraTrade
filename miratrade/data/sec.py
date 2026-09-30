"""Insider transactions (SEC Form 4) from EDGAR.

Two sources, both free and official:

* The quarterly *Insider Transactions Data Sets* (bulk TSV zips) for completed quarters.
* The EDGAR daily index + each filing's Form 4 XML for the current quarter, which the
  bulk data sets do not cover yet.

Everything is normalised to one DataFrame, see ``INSIDER_COLUMNS``.
"""
from __future__ import annotations

import io
import os
import re
import threading
import time
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from miratrade.config import CACHE_DIR, SEC_USER_AGENT

INSIDER_COLUMNS = [
    "accession", "filing_date", "trade_date", "ticker", "issuer", "issuer_cik", "owner", "owner_cik",
    "is_officer", "is_director", "is_ten_pct", "title", "code", "shares", "price",
    "value", "owned_after", "delta_own_pct", "plan_10b5_1",
]

# The SEC moved the data sets from 2026 Q2 on; older quarters stay at the original path.
BULK_URLS = tuple(f"https://www.sec.gov/files/{d}/data/insider-transactions-data-sets/{{year}}q{{q}}_form345.zip"
                  for d in ("datastandardsinnovation", "structureddata"))
DAILY_INDEX_URL = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{q}/form.{ymd}.idx"
ARCHIVE_URL = "https://www.sec.gov/Archives/{path}"
SERVER_ERRORS = {500, 502, 503, 504}
# SEC fair access: a declared User-Agent with contact and at most 10 requests/second per IP,
# counting every process. MiraTrade stays under that with one budget shared by all its processes.
SEC_RATE_PER_S = 8.0
SEC_BLOCK_WAIT_S = 600.0            # after a 429 the SEC throttles the address for about ten minutes
PARALLEL_FILINGS = 6                # downloads in flight; the shared budget still caps the rate


if os.name == "nt":
    import msvcrt

    def _lock(f) -> None:
        f.seek(0)
        while True:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.02)

    def _unlock(f) -> None:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(f) -> None:
        fcntl.flock(f, fcntl.LOCK_EX)

    def _unlock(f) -> None:
        fcntl.flock(f, fcntl.LOCK_UN)


class SharedRate:
    """Request pacing shared by every MiraTrade process through a small state file (last request
    time, blocked-until time) guarded by an OS file lock. A 429 pauses all of them."""

    def __init__(self, path: Path, per_second: float = SEC_RATE_PER_S):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.interval = 1.0 / per_second

    @contextmanager
    def _locked(self):
        with open(self.lock_path, "a+b") as f:
            _lock(f)
            try:
                yield
            finally:
                _unlock(f)

    def _read(self) -> tuple[float, float]:
        try:
            last, blocked = (float(x) for x in self.path.read_text(encoding="ascii").split()[:2])
        except (OSError, ValueError):
            last, blocked = 0.0, 0.0
        return last, blocked

    def wait_turn(self) -> None:
        announced = False
        while True:
            with self._locked():
                last, blocked = self._read()
                now = time.time()
                if blocked <= now:
                    pause = last + self.interval - now
                    if pause > 0:
                        time.sleep(pause)
                    self.path.write_text(f"{time.time():.3f} {blocked:.3f}", encoding="ascii")
                    return
            if not announced:
                print(f"  SEC en pausa: se reanuda en {(blocked - now) / 60:.1f} min", flush=True)
                announced = True
            time.sleep(min(blocked - now, 30.0))    # sleep outside the lock, then look again

    def block(self, seconds: float) -> None:
        with self._locked():
            last, blocked = self._read()
            self.path.write_text(f"{last:.3f} {max(blocked, time.time() + seconds):.3f}", encoding="ascii")


def _retry_after(resp) -> float | None:
    try:
        return min(float((getattr(resp, "headers", None) or {}).get("Retry-After")), 3600.0)
    except (TypeError, ValueError):
        return None


class SecClient:
    """Polite EDGAR client: declared User-Agent, a request budget shared by all processes,
    on-disk cache, backoff on server errors, and a real pause when the SEC answers 429."""

    def __init__(self, user_agent: str = SEC_USER_AGENT, cache_dir: Path = CACHE_DIR / "sec",
                 retries: int = 4, backoff: float = 2.0, block_wait: float = SEC_BLOCK_WAIT_S,
                 per_second: float = SEC_RATE_PER_S):
        self.user_agent = user_agent
        self._local = threading.local()
        self._local.session = self._new_session()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.retries, self.backoff, self.block_wait = retries, backoff, block_wait
        self.rate = SharedRate(self.cache_dir / ".sec_rate", per_second)

    def _new_session(self):
        import requests

        s = requests.Session()
        s.headers["User-Agent"] = self.user_agent
        s.headers["Accept-Encoding"] = "gzip, deflate"
        return s

    @property
    def session(self):
        """One session per thread: several downloads may be in flight at once, and the shared
        budget — not the number of threads — is what keeps the rate under the SEC's limit."""
        s = getattr(self._local, "session", None)
        if s is None:
            s = self._local.session = self._new_session()
        return s

    def _throttled_get(self, url: str):
        self.rate.wait_turn()
        return self.session.get(url, timeout=60)

    def get(self, url: str, cache: bool = True, missing: tuple[int, ...] = (404,),
            max_age_days: float | None = None) -> bytes | None:
        """``None`` when the response status is in ``missing``. EDGAR's archive answers a
        file that does not exist (e.g. the daily index of a holiday) with 403, not 404.
        ``max_age_days``: refetch a cached copy older than this (data that changes, e.g. XBRL)."""
        import requests

        key = self.cache_dir / re.sub(r"[^A-Za-z0-9._-]", "_", url.split("://", 1)[-1])
        fresh = max_age_days is None or (key.exists() and time.time() - key.stat().st_mtime < max_age_days * 86400)
        if cache and key.exists() and fresh:
            return key.read_bytes()
        paused = False
        for attempt in range(self.retries + 1):
            try:
                resp = self._throttled_get(url)
            except requests.ConnectionError:
                if attempt == self.retries:
                    raise
                time.sleep(self.backoff * 2 ** attempt)
                continue
            if resp.status_code == 429 and not paused:
                # Retrying at once would only extend the block: pause every process instead.
                wait = _retry_after(resp)
                wait = self.block_wait if wait is None else wait
                print(f"  La SEC pide bajar el ritmo (429): pausa de {wait / 60:.1f} min para todos los procesos",
                      flush=True)
                self.rate.block(wait)
                paused = True
                continue
            if resp.status_code in SERVER_ERRORS and attempt < self.retries:
                time.sleep(self.backoff * 2 ** attempt)
                continue
            break
        if resp.status_code in missing:
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
        "issuer_cik": df["ISSUERCIK"].str.lstrip("0") if "ISSUERCIK" in df else "",
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
        # 10b5-1 plan checkbox (Form 4 since April 2023; absent, hence False, before that)
        "plan_10b5_1": (df["AFF10B5ONE"].fillna("").str.strip().str.lower().isin({"1", "true"})
                        if "AFF10B5ONE" in df else False),
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
    plan = _flag(root, "aff10b5One")
    rows = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        rows.append({
            "accession": accession,
            "filing_date": filing_date,
            "trade_date": _text(tx, "transactionDate"),
            "ticker": _text(issuer, "issuerTradingSymbol").upper(),
            "issuer": _text(issuer, "issuerName"),
            "issuer_cik": _text(issuer, "issuerCik").lstrip("0"),
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
            "plan_10b5_1": plan,
        })
    df = pd.DataFrame(rows, columns=[c for c in INSIDER_COLUMNS if c not in ("value", "delta_own_pct")])
    df["plan_10b5_1"] = df["plan_10b5_1"].astype(bool)
    for col in ("shares", "price", "owned_after"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("filing_date", "trade_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return _finish(df)


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # The two parsers have to agree on a missing ticker. The Form 4 XML gives "" for an absent
    # issuerTradingSymbol; the quarterly TSV gives NaN, which is NULL, which the schema refuses —
    # so a whole quarter of history died on the 0.14% of rows that are non-traded REITs with no
    # trading symbol at all. One shape, decided here, and `clean_insiders` drops them on read.
    df["ticker"] = df["ticker"].fillna("").astype(str).str.upper().str.strip()
    df["value"] = df["shares"] * df["price"]
    prior = df["owned_after"] - df["shares"]
    df["delta_own_pct"] = (df["shares"] / prior.where(prior > 0)).fillna(1.0)  # new position = +100%
    return df[INSIDER_COLUMNS]


def parse_daily_index(text: str) -> list[tuple[str, str]]:
    """Return ``(accession_path, date_filed)`` for every Form 4 in a ``form.YYYYMMDD.idx``.

    The index lists one line per filer, so a Form 4 appears twice — once under the company's CIK and
    once under the insider's — as two paths to the very same document. Deduplicating by accession
    rather than by path halves the filings to download, which is most of what a scan spends its time
    on, and keeps the same transaction from being counted twice.
    """
    out, seen = [], set()
    for line in text.splitlines():
        if not line.startswith("4 "):
            continue
        path = line.split()[-1]
        date_filed = line.split()[-2]
        accession = Path(path).stem
        if path.startswith("edgar/") and accession not in seen:
            seen.add(accession)
            out.append((path, date_filed))
    return out


# --------------------------------------------------------------------------- orchestration

SOURCE = "sec_form4"        # the name this source has in the store's coverage table


def _quarter_days(year: int, q: int) -> list[date]:
    start = date(year, 3 * q - 2, 1)
    end = date(year + (q == 4), 1 if q == 4 else 3 * q + 1, 1) - timedelta(days=1)
    return list(pd.bdate_range(start, end).date)


def _parse_day(client: SecClient, year: int, q: int, day: date) -> tuple[pd.DataFrame | None, int]:
    """Every Form 4 filed on one day, from the daily index. ``None`` means the index itself was not
    there, which is not the same as a day on which nothing was filed."""
    idx = client.get(DAILY_INDEX_URL.format(year=year, q=q, ymd=day.strftime("%Y%m%d")),
                     missing=(403, 404))
    if idx is None:
        return None, 0
    filings = parse_daily_index(idx.decode("latin-1"))
    print(f"  {day}: {len(filings)} Form 4 filings", flush=True)

    def download(item):
        path, filed = item
        try:
            return path, filed, client.get(ARCHIVE_URL.format(path=path))
        except Exception as e:          # one filing must not kill the run; counted and reported
            return path, filed, e

    with ThreadPoolExecutor(max_workers=PARALLEL_FILINGS) as pool:
        fetched = list(pool.map(download, filings))
    frames, failed = [], 0
    for path, filed, raw in fetched:
        if isinstance(raw, Exception):
            failed += 1
            print(f"    skipped {path}: {raw}", flush=True)
            continue
        if raw is None:
            continue
        m = re.search(rb"<ownershipDocument>.*?</ownershipDocument>", raw, re.S)
        if not m:
            continue
        try:
            frames.append(parse_form4_xml(m.group(0).decode("utf-8", "replace"),
                                          accession=Path(path).stem, filing_date=filed))
        except ET.ParseError:
            continue
    rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=INSIDER_COLUMNS)
    return rows, failed


def fetch_insiders(start: date, end: date, client: SecClient | None = None,
                   codes: tuple[str, ...] = ("P", "S"), today: date | None = None,
                   db=None) -> pd.DataFrame:
    """All insider transactions with these ``codes`` filed between ``start`` and ``end`` (inclusive).

    Raw filings are cached, but rebuilding a table from each of a thousand XMLs a day is what
    actually costs the time. So a day that is over — and cannot gain filings — is parsed once, its
    rows go into the shared market database and the day is marked covered; later runs read them back
    with a query. ``today`` says which day and quarter are still open, and both are always re-read.

    Everything parsed is stored, not just the ``codes`` asked for, so a second app finds the whole
    picture in the database instead of having to download it again.
    """
    from miratrade import store

    client = client or SecClient()
    today = today or date.today()
    current_q = (today.year, (today.month - 1) // 3 + 1)
    owned = db is None
    db = db if db is not None else store.connect()
    failed = 0
    try:
        wanted = [d for d in pd.bdate_range(start, end).date if d < today]
        todo = set(store.gaps(db, SOURCE, wanted))
        for year, q in sorted({(d.year, (d.month - 1) // 3 + 1) for d in wanted if d in todo}):
            blob = None
            if (year, q) != current_q:
                for url in BULK_URLS:
                    blob = client.get(url.format(year=year, q=q))
                    if blob is not None:
                        break
            if blob is not None:
                # One zip holds the whole quarter, so every business day in it is now covered.
                rows = parse_bulk_zip(blob)
                store.write(db, "insiders", rows)
                store.mark_covered(db, SOURCE, _quarter_days(year, q), rows=len(rows))
                continue
            # Bulk set not published yet: walk the daily index for the days still missing.
            for day in sorted(d for d in wanted if d in todo
                              and (d.year, (d.month - 1) // 3 + 1) == (year, q)):
                rows, day_failed = _parse_day(client, year, q, day)
                failed += day_failed
                if rows is None:
                    continue                       # no index published for that day: ask again later
                store.write(db, "insiders", rows)
                if not day_failed:                 # a partial day must not be remembered as complete
                    store.mark_covered(db, SOURCE, [day], rows=len(rows))

        if today <= end:                           # today can still gain filings: never cached
            year, q = current_q
            rows, day_failed = _parse_day(client, year, q, today)
            failed += day_failed
            store.write(db, "insiders", rows)

        if failed:
            print(f"  {failed} Form 4 filings could not be downloaded and were skipped; "
                  "re-run later to fill them in (the rest is stored).", flush=True)
        df = store.read(db, "insiders",
                        f"filing_date >= ? AND filing_date <= ? AND code IN ({','.join('?' * len(codes))})",
                        [start.isoformat(), end.isoformat(), *codes], order="filing_date, ticker")
    finally:
        if owned:
            db.close()
    df = df.reindex(columns=INSIDER_COLUMNS)
    for col in ("is_officer", "is_director", "is_ten_pct", "plan_10b5_1"):
        df[col] = df[col].fillna(0).astype(bool)
    df["ticker"] = primary_ticker(df["ticker"])
    df = df[df["ticker"].str.fullmatch(r"[A-Z.]{1,6}", na=False)]
    return df.drop_duplicates().reset_index(drop=True)


def primary_ticker(tickers: pd.Series) -> pd.Series:
    """The first symbol when a filing lists several share classes in its ticker field.

    A company with two classes is sometimes filed as ``"LEN, LEN.B"``, and rejecting that as
    malformed threw the row away: Berkshire Hathaway's first Form 4 for Lennar — $212M of
    open-market buying — was invisible to MiraTrade for exactly this reason.

    The transaction is in one class and the field does not say which, so the first symbol is taken.
    That can attribute a purchase of the B shares to the A shares; for the question MiraTrade asks —
    did someone buy a lot of this company — that is a far smaller error than losing the filing.
    The store keeps the field as filed; this normalisation is on the way out of it.
    """
    return (tickers.fillna("").astype(str).str.upper().str.strip()   # strip first: " PFE " would
            .str.split(r"[,/;\s]+", regex=True).str[0])              # otherwise split to an empty [0]


# Placeholder tickers filers type when the issuer has none.
# "" belongs here as much as "NONE" does: a transaction with no trading symbol at all — a
# non-traded REIT, a private issuer — cannot be attributed to a security, so nothing downstream can
# do anything with it except count it.
_NO_TICKER = {"", "NONE", "NA", "N", "NAN", "NULL", "TBD"}


def clean_insiders(insiders: pd.DataFrame, max_price: float = 10_000,
                   max_bad_value: float = 1e8) -> tuple[pd.DataFrame, dict]:
    """Drop rows that are filing errors or not stocks. Returns the rows kept and counts.

    * Placeholder tickers ("NONE") and mutual-fund tickers (four letters + X, e.g. ``PBLSX``).
    * A per-share price above ``max_price`` on a trade worth more than ``max_bad_value``: the
      filer typed the *total* amount into the price field (``$24,035,774`` a share). A real
      high-priced stock (BRK.A) trades a handful of shares, so its value stays under the cap.
    """
    t = insiders["ticker"].fillna("")
    placeholder = t.isin(_NO_TICKER)
    fund = t.str.fullmatch(r"[A-Z]{4}X")
    total_as_price = (insiders["price"] > max_price) & (insiders["value"] > max_bad_value)
    bad = placeholder | fund | total_as_price
    stats = {"placeholder_ticker": int(placeholder.sum()), "fund_ticker": int((fund & ~placeholder).sum()),
             "total_as_price": int((total_as_price & ~placeholder & ~fund).sum())}
    return insiders[~bad].reset_index(drop=True), stats
