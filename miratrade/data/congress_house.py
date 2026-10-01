"""Periodic Transaction Reports filed by members of the House of Representatives.

LEGAL — PERSONAL USE ONLY. See the notice at the top of ``congress.py``: the Ethics in Government
Act, 5 U.S.C. app. § 105(c), makes it unlawful to obtain or use these reports for any commercial
purpose other than by news media. This module, ``congress_senate`` and ``congress`` are the only
parts of MiraTrade under that restriction and must come out before the app is sold.

Source: the Clerk of the House publishes, for each year, a ZIP holding an XML index of every
financial disclosure filed, and one PDF per filing. Both are ordinary public downloads with no
agreement to accept and no key. Filing type ``P`` is a PTR — the report that lists transactions.

What the data is worth knowing before trusting it: the STOCK Act gives members **30 to 45 days** to
file, and the PDF shows both the transaction date and the notification date, so the lag is visible
per row. Amounts are disclosed as **ranges**, never exact figures, so position size is a band. A
handful of filings are scanned paper and have no machine-readable text; those are skipped and said so.
"""
from __future__ import annotations

import io
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd

from miratrade.config import CACHE_DIR, SEC_USER_AGENT

SOURCE = "congress_house"
INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
PTR_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"
TRADE_COLUMNS = ["doc_id", "row_in_doc", "filing_date", "trade_date", "member", "bioguide_id",
                 "chamber", "ticker", "asset", "type", "owner", "amount_low", "amount_high",
                 "filing_url"]

# The spine of a transaction row: what it was, when it happened, when it was notified, how much.
# Everything before it on the line is the asset, everything after is the start of the amount.
SPINE = re.compile(r"\b(?P<type>P|S|E|S \(partial\))\s+"
                   r"(?P<trade>\d{2}/\d{2}/\d{4})\s+(?P<notified>\d{2}/\d{2}/\d{4})\s*(?P<rest>.*)$")
TICKER = re.compile(r"\(([A-Z][A-Z.\-]{0,5})\)")        # Apple Inc. - Common Stock (AAPL) [ST]
ASSET_TYPE = re.compile(r"\[([A-Z]{2})\]")              # ST stock, GS government security, OP option…
OWNER_CODE = re.compile(r"^(SP|DC|JT)\s+")              # spouse, dependent child, joint; blank = the member
MONEY = re.compile(r"\$([\d,]+(?:\.\d{2})?)")
TYPES = {"P": "purchase", "S": "sale", "S (partial)": "partial sale", "E": "exchange"}
OWNERS = {"SP": "spouse", "DC": "dependent child", "JT": "joint", "": "self"}

# The form's own headings end a transaction; the rest of a wrapped asset name continues it. The PDF
# renders those headings in spaced small caps ("F  I  L  I  N  G   S  T  A  T  U  S :"), which comes
# out of the extractor as single letters, so they are recognised by that shape rather than by their
# exact spacing — matching the spacing is what made "Common Stock…" look like the "COMMENTS" heading.
LABEL = re.compile(r"^(?:[A-Z] ){1,6}:")             # "F S : New", "D : Sale from…", "S O : Schwab"
SPACED_CAPS = re.compile(r"^(?:[A-Z] ?){1,6}$")      # a heading alone on its line: "C", "I P O"
BREAK_TEXT = ("* For the complete", "ID Owner Asset", "Type Date", "Gains >", "I CERTIFY",
              "Digitally Signed", "Yes No", "SUBHOLDING OF", "LOCATION", "DESCRIPTION",
              "FILING STATUS", "COMMENTS", "ASSET CLASS DETAILS")


def _is_break(line: str) -> bool:
    """Whether a line is one of the form's headings rather than the rest of a wrapped row."""
    flat = _clean(line)
    return bool(LABEL.match(flat) or SPACED_CAPS.match(flat)
                or any(flat.startswith(text) for text in BREAK_TEXT))


CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _clean(text: str) -> str:
    """Readable text out of the PDF's own.

    The form's small-caps headings come out padded with NUL bytes rather than spaces
    ("F\\x00\\x00\\x00\\x00\\x00 S\\x00\\x00\\x00\\x00\\x00: New" is "Filing Status: New"), and
    ``str.split`` does not treat NUL as whitespace, so they are turned into spaces first. Skipping
    that is what let a heading be read as part of the asset name it follows.
    """
    return " ".join(CONTROL.sub(" ", str(text or "")).split())


def _money(text: str) -> tuple[float | None, float | None]:
    """``$15,001 - $50,000`` → (15001, 50000); a single figure is both ends of the range."""
    figures = [float(m.replace(",", "")) for m in MONEY.findall(text)]
    if not figures:
        return None, None
    return figures[0], figures[-1]


def _date(text: str):
    stamp = pd.to_datetime(_clean(text), format="%m/%d/%Y", errors="coerce")
    return None if pd.isna(stamp) else stamp


def parse_ptr_text(text: str, doc_id: str = "", member: str = "", filing_date=None,
                   url: str = "") -> pd.DataFrame:
    """The transactions in one PTR's extracted text.

    A row wraps over two lines: the first carries the owner, the start of the asset name and the
    spine; the second carries the rest of the asset name and the rest of the amount, split at the
    first ``$``. Working from the spine outwards is what makes it survive the wrapping.
    """
    lines = [line for line in (text or "").splitlines() if line.strip()]
    rows: list[dict] = []
    for i, line in enumerate(lines):
        m = SPINE.search(line)
        if not m:
            continue
        head = line[:m.start()]
        owner_code = (OWNER_CODE.match(head).group(1) if OWNER_CODE.match(head) else "")
        asset = OWNER_CODE.sub("", head)
        amount = m.group("rest")
        for follow in lines[i + 1:]:                      # gather what wrapped onto later lines
            if SPINE.search(follow) or _is_break(follow):
                break
            before, dollar, after = follow.partition("$")
            asset += " " + before
            if dollar:
                amount += " " + dollar + after
        asset = _clean(asset)
        ticker = TICKER.search(asset)
        kind = ASSET_TYPE.search(asset)
        low, high = _money(amount)
        rows.append({
            "doc_id": str(doc_id), "row_in_doc": len(rows),
            "filing_date": filing_date, "trade_date": _date(m.group("trade")),
            "member": member, "bioguide_id": None, "chamber": "house",
            "ticker": ticker.group(1) if ticker and kind and kind.group(1) in ("ST", "OP") else None,
            "asset": asset, "type": TYPES.get(m.group("type"), m.group("type")),
            "owner": OWNERS.get(owner_code, owner_code), "amount_low": low, "amount_high": high,
            "filing_url": url})
    return pd.DataFrame(rows, columns=TRADE_COLUMNS)


def _get(url: str, cache_dir: Path, max_age_days: float | None = None) -> bytes | None:
    """Download with the declared User-Agent, keeping a copy on disk. A filed PDF never changes, so
    the cached copy is used for ever unless ``max_age_days`` says otherwise."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = cache_dir / re.sub(r"[^A-Za-z0-9._-]", "_", url.split("://", 1)[-1])
    if key.exists():
        import time
        if max_age_days is None or time.time() - key.stat().st_mtime < max_age_days * 86400:
            return key.read_bytes()
    request = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            blob = response.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None
        raise
    key.write_bytes(blob)
    return blob


def fetch_index(year: int, cache_dir: Path | None = None, current: bool = False) -> pd.DataFrame:
    """Every PTR filed in ``year``: who filed it, when, and its document id.

    A past year's index is final and cached for ever; the current year is re-read daily.
    """
    folder = Path(cache_dir or CACHE_DIR) / "congress"
    blob = _get(INDEX_URL.format(year=year), folder, max_age_days=1 if current else None)
    if blob is None:
        return pd.DataFrame(columns=["doc_id", "member", "filing_date", "year"])
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next((n for n in z.namelist() if n.lower().endswith(".xml")), None)
        if name is None:
            return pd.DataFrame(columns=["doc_id", "member", "filing_date", "year"])
        root = ET.fromstring(z.read(name))
    rows = []
    for record in root:
        if _clean(record.findtext("FilingType")) != "P":          # only Periodic Transaction Reports
            continue
        name = " ".join(_clean(record.findtext(tag) or "") for tag in ("First", "Last", "Suffix"))
        rows.append({"doc_id": _clean(record.findtext("DocID")), "member": _clean(name),
                     "filing_date": _date(record.findtext("FilingDate")), "year": year})
    return pd.DataFrame(rows, columns=["doc_id", "member", "filing_date", "year"]).dropna(subset=["doc_id"])


def page_lines(page, tolerance: float = 2.5) -> list[str]:
    """The visible lines of a page, rebuilt from where the words actually sit.

    Some filings carry no line breaks at all in their text layer: ``extract_text`` hands back the
    whole page as a single line, and a parser that trusts newlines then reads one transaction where
    there are twenty. Grouping the words by their vertical position gives the same lines a reader
    sees, whatever the PDF's internals look like.
    """
    rows: dict[int, list] = {}
    for word in page.extract_words(use_text_flow=False, keep_blank_chars=False):
        rows.setdefault(round(word["top"] / tolerance), []).append(word)
    return [" ".join(w["text"] for w in sorted(group, key=lambda w: w["x0"]))
            for _, group in sorted(rows.items())]


def parse_ptr_pdf(blob: bytes, **fields) -> pd.DataFrame | None:
    """The transactions in a PTR PDF, or ``None`` when it is a scan with no text to read."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        lines = [line for page in pdf.pages for line in page_lines(page)]
    text = "\n".join(lines)
    if len(_clean(text)) < 80:                     # a scanned or handwritten filing: nothing to parse
        return None
    return parse_ptr_text(text, **fields)


def fetch_trades(start: date, end: date, db=None, cache_dir: Path | None = None,
                 log: Callable[[str], None] = print, today: date | None = None,
                 limit: int | None = None) -> int:
    """Download and store every House PTR filed between ``start`` and ``end``. Returns rows written.

    Each document is fetched once: the PDF is cached and the document is marked covered, so a later
    run only picks up filings that are new. A scan with no readable text is marked too, otherwise it
    would be downloaded again for ever.
    """
    from miratrade import usage

    usage.check("congress")

    from miratrade import store
    from miratrade.data.congress import match_member, member_lookup

    owned, db = db is None, db if db is not None else store.connect()
    today = today or date.today()
    folder = Path(cache_dir or CACHE_DIR) / "congress"
    written, scanned, seen = 0, 0, 0
    try:
        names = member_lookup(db)
        done = store.covered(db, SOURCE)                   # scope is the document id
        index = pd.concat([fetch_index(y, cache_dir, current=(y == today.year))
                           for y in range(start.year, end.year + 1)], ignore_index=True)
        if not len(index):
            log("  no House index published for those years")
            return 0
        window = index[(index["filing_date"].dt.date >= start) & (index["filing_date"].dt.date <= end)]
        todo = [r for r in window.to_dict("records")
                if not store.covered(db, SOURCE, scope=str(r["doc_id"]))]
        log(f"  House: {len(window)} PTR filings in the window, {len(todo)} to download")
        for record in todo[:limit]:
            doc_id, year = str(record["doc_id"]), int(record["year"])
            url = PTR_URL.format(year=year, doc_id=doc_id)
            blob = _get(url, folder)
            if blob is None:
                continue                                   # not published yet: try again next run
            seen += 1
            try:
                rows = parse_ptr_pdf(blob, doc_id=doc_id, member=record["member"],
                                     filing_date=record["filing_date"], url=url)
            except Exception as e:                         # one malformed PDF must not stop the run
                log(f"    could not read {doc_id}: {e}")
                continue
            if rows is None:
                scanned += 1
            else:
                rows["bioguide_id"] = rows["member"].map(lambda n: match_member(n, names))
                written += store.write(db, "congress_trades", rows)
            store.mark_covered(db, SOURCE, [record["filing_date"]], rows=0 if rows is None else len(rows),
                               scope=doc_id)
        log(f"  House: {written} transactions from {seen} filings"
            + (f"; {scanned} were scans with no readable text" if scanned else ""))
    finally:
        if owned:
            db.close()
    return written
