"""8-K items: corporate news that is point-in-time by construction.

This is where the news work starts, and it starts here rather than at a news API for four reasons
that together are hard to beat:

1. **It cannot be back-dated.** An EDGAR filing is immutable. The 8-K filed on 2023-04-11 has the
   same bytes today, and a correction arrives as an 8-K/A — a *new* filing with its own date. The
   problem that quietly ruins news backtests, where today's article describes what happened next,
   does not exist here.
2. **It carries a timestamp to the second.** ``acceptanceDateTime`` says when it became public, so
   "filed at 20:13 New York, therefore tradeable at the next open, not today's close" is a question
   with an answer rather than an assumption.
3. **It is public domain.** No licence, no redistribution clause, commercial use fine — which is
   more than can be said for any news feed (see ``docs/LICENCIAS.md``).
4. **It is already downloaded.** MiraTrade asks EDGAR for each company's submissions to find
   earnings dates, and that one response carries every other filing too. Roughly 25,000 dated
   corporate events were being parsed and thrown away on every run.

What it is not: prose. An item code says *a category of thing happened*, not what it said. A 5.02
covers a CFO resigning in disgrace and a director retiring at 70. That is a real limit, and it is
also why this is worth doing first — if the category alone moves nothing, reading the prose is
unlikely to rescue it, and we will have learned that for the cost of a parser instead of a news
subscription.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

# The 8-K taxonomy, with what each one means to somebody deciding. Only the codes worth a name are
# here; anything else is stored as filed and simply has no label.
ITEMS: dict[str, str] = {
    "1.01": "entered a material agreement",
    "1.02": "terminated a material agreement",
    "1.03": "bankruptcy or receivership",
    "1.05": "material cybersecurity incident",
    "2.01": "completed an acquisition or disposal",
    "2.02": "results of operations",
    "2.03": "took on a direct financial obligation",
    "2.04": "an obligation was accelerated",
    "2.05": "costs of exiting or disposing of a business",
    "2.06": "material impairment",
    "3.01": "notice of delisting, or failing a listing rule",
    "3.02": "unregistered sale of equity",
    "3.03": "material change to shareholder rights",
    "4.01": "changed its auditor",
    "4.02": "previously issued financials should not be relied on",
    "5.01": "change in control",
    "5.02": "a director or senior officer left or joined",
    "5.03": "amended its articles, bylaws or fiscal year",
    "5.07": "shareholder vote",
    "7.01": "Regulation FD disclosure",
    "8.01": "other events",
    "9.01": "financial statements and exhibits",
}

# Codes that say nothing on their own. 9.01 marks that documents are attached and rides along with
# almost everything; 5.07 is the routine annual meeting result. Counting them as news would drown
# the codes that mean something.
ROUTINE = frozenset({"9.01", "5.07"})

# Where the fear lives. Not a claim that these predict anything — that is what the measurement is
# for — but if corporate news moves an insider-buy outcome at all, these are where to look first.
SEVERE = frozenset({"1.03", "2.06", "3.01", "4.01", "4.02", "5.01", "5.02"})

SOURCE = "sec_8k"                       # its name in the coverage table
COLUMNS = ["accession", "ticker", "item", "form", "filing_date", "accepted_at", "report_date",
           "cik", "document"]


def label(item: str, translate=None) -> str:
    """What an item code means, in words. Unknown codes come back as the code — an honest answer."""
    from miratrade.messages import sayer

    known = ITEMS.get(item)
    return sayer(translate)(known) if known else item


def parse_submissions(payload: dict | bytes | str, ticker: str = "",
                      forms: tuple[str, ...] = ("8-K", "8-K/A")) -> pd.DataFrame:
    """Every 8-K item in one company's EDGAR submissions, one row per item.

    One row per *item* rather than per filing, because the question asked of this data is always
    "was there a 5.02 near this day", and a filing carries several items. It also makes counting a
    GROUP BY instead of string matching.

    ``tickers`` in the payload lists the common stock first and then the preferred issues
    (``['WRB', 'WRB-PE', …]``); only the first is the company as a price series knows it.
    """
    if isinstance(payload, (bytes, str)):
        payload = json.loads(payload)
    ticker = (ticker or (payload.get("tickers") or [""])[0] or "").strip().upper()
    # The archive path is keyed on the issuer's CIK, and the body lives under the primary
    # document's filename. Without both, the table says a document exists and gives no way to open
    # it — a reference with no referent.
    cik = str(payload.get("cik") or "").lstrip("0")
    recent = (payload.get("filings") or {}).get("recent") or {}
    got = recent.get("form") or []
    rows = []
    for i, form in enumerate(got):
        if form not in forms:
            continue

        def field(name, default=""):
            values = recent.get(name) or []
            return (values[i] if i < len(values) else default) or default

        accession, filed = field("accessionNumber"), field("filingDate")
        if not (ticker and accession and filed):
            continue
        codes = [c.strip() for c in str(field("items")).split(",") if c.strip()]
        for code in dict.fromkeys(codes):              # a filing can repeat an item; count it once
            rows.append({"accession": accession, "ticker": ticker, "item": code.split()[0],
                         "form": form, "filing_date": filed,
                         "accepted_at": field("acceptanceDateTime", None) or None,
                         "report_date": field("reportDate", None) or None,
                         "cik": cik or None,
                         "document": field("primaryDocument", None) or None})
    return pd.DataFrame(rows, columns=COLUMNS)


def truncated(payload: dict | bytes | str) -> bool:
    """Whether this company has older filings EDGAR did not put in ``recent``.

    ``recent`` holds the newest 1,000 filings and the rest are paginated into separate files we do
    not fetch. For a company that files constantly that can cut into the window a backtest needs,
    so the harvest reports how many companies are affected instead of quietly measuring a short
    history.
    """
    if isinstance(payload, (bytes, str)):
        payload = json.loads(payload)
    return bool((payload.get("filings") or {}).get("files"))


def harvest_cache(db, cache_dir: Path | None = None,
                  log: Callable[[str], None] = print) -> dict:
    """Parse every submissions file already on disk into the store. Downloads nothing.

    These responses were fetched to find earnings dates; the 8-K items came in the same payload and
    were discarded. This reads them back off disk, so it costs no request to anybody.
    """
    from miratrade import store
    from miratrade.config import CACHE_DIR

    folder = Path(cache_dir or Path(CACHE_DIR) / "sec")
    files = sorted(folder.glob("*submissions_CIK*.json"))
    written = companies = short = 0
    frames = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        rows = parse_submissions(payload)
        if not len(rows):
            continue
        companies += 1
        short += 1 if truncated(payload) else 0
        frames.append(rows)
        if len(frames) >= 200:                          # write in batches, not one company at a time
            written += store.write(db, "filings", pd.concat(frames, ignore_index=True))
            frames = []
    if frames:
        written += store.write(db, "filings", pd.concat(frames, ignore_index=True))
    log(f"  {written:,} 8-K items from {companies:,} companies, read off disk")
    if short:
        log(f"  {short:,} of them file often enough that EDGAR paginated their history; those are "
            f"cut at their newest 1,000 filings")
    return {"items": written, "companies": companies, "truncated": short, "files": len(files)}


SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
# The body of a filing. Accession numbers are dashed in the index and undashed in the path, which
# is a detail that costs an afternoon the first time you meet it.
BODY_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{plain}/{document}"


def body_url(cik: str, accession: str, document: str) -> str:
    return BODY_URL.format(cik=str(cik).lstrip("0"), plain=str(accession).replace("-", ""),
                           document=document)


def fetch(tickers, ciks: dict, client=None, db=None, log: Callable[[str], None] = print,
          max_age_days: int = 7) -> dict:
    """Download the submissions of companies we do not have yet, and store their 8-K items.

    One request per company, inside the SEC's rate budget and through the same cached client the
    rest of the project uses, so a company already fetched for its earnings dates costs nothing at
    all — the response is on disk and only needs parsing.

    Coverage is recorded per ticker, so this is safe to run as often as you like: a company that
    answered once is not asked again until its entry goes stale.
    """
    from miratrade import store
    from miratrade.data.sec import SecClient

    client = client or SecClient()
    owned, db = db is None, db if db is not None else store.connect()
    written = asked = 0
    missing: list[str] = []
    try:
        wanted = sorted({str(t).upper() for t in tickers if str(t).strip()})
        for ticker in wanted:
            cik = ciks.get(ticker)
            if not cik:
                missing.append(ticker)
                continue
            raw = client.get(SUBMISSIONS_URL.format(cik=str(cik).lstrip("0")),
                             max_age_days=max_age_days)
            asked += 1
            if raw is None:
                missing.append(ticker)
                continue
            rows = parse_submissions(raw, ticker)
            if len(rows):
                written += store.write(db, "filings", rows)
            # "asked and answered", including an answer of nothing: a company that files no 8-K is
            # a real answer and must not be requested again every run.
            store.mark_covered(db, SOURCE, [pd.Timestamp.now("UTC").date()], rows=len(rows),
                               scope=ticker)
        log(f"  {written:,} 8-K items from {asked:,} companies"
            + (f"; {len(missing)} with no CIK or no answer" if missing else ""))
        return {"items": written, "asked": asked, "missing": missing}
    finally:
        if owned:
            db.close()


def have(db, tickers: Iterable[str]) -> tuple[set[str], set[str]]:
    """``(companies already asked about, the rest)`` — so a run fetches only what is missing."""
    from miratrade import store

    wanted = {str(t).upper() for t in tickers if str(t).strip()}
    asked = {row["scope"] for row in
             db.execute("SELECT DISTINCT scope FROM coverage WHERE source = ?", (SOURCE,))}
    # companies whose items are already stored count as asked, even from the disk harvest
    asked |= {row["ticker"] for row in db.execute("SELECT DISTINCT ticker FROM filings")}
    return wanted & asked, wanted - asked


def near(db, ticker: str, day, before: int = 30, after: int = 0,
         items: Iterable[str] | None = None, exclude_routine: bool = True) -> pd.DataFrame:
    """The 8-K items filed around one day for one company.

    ``before``/``after`` are calendar days. ``after`` defaults to 0 and should stay there for
    anything a backtest reads: a filing from after the signal was not known at the signal.
    """
    from miratrade import store

    day = pd.Timestamp(day)
    where = ["upper(ticker) = ?", "filing_date >= ?", "filing_date <= ?"]
    params = [str(ticker).upper(), (day - pd.Timedelta(days=before)).strftime("%Y-%m-%d"),
              (day + pd.Timedelta(days=after)).strftime("%Y-%m-%d")]
    wanted = list(items) if items else []
    if wanted:
        where.append(f"item IN ({','.join('?' * len(wanted))})")
        params += wanted
    elif exclude_routine:
        where.append(f"item NOT IN ({','.join('?' * len(ROUTINE))})")
        params += sorted(ROUTINE)
    return store.read(db, "filings", " AND ".join(where), params, order="filing_date DESC")


def counts(db, item_in: Iterable[str] | None = None) -> pd.DataFrame:
    """How many of each item are stored, newest and oldest, for a look at what there is."""
    sql = ("SELECT item, count(*) AS n, count(DISTINCT ticker) AS tickers, "
           "min(filing_date) AS first, max(filing_date) AS last FROM filings")
    params: list = []
    if item_in:
        wanted = list(item_in)
        sql += f" WHERE item IN ({','.join('?' * len(wanted))})"
        params += wanted
    sql += " GROUP BY item ORDER BY n DESC"
    out = pd.read_sql_query(sql, db, params=params)
    out["means"] = [ITEMS.get(i, "") for i in out["item"]]
    return out
