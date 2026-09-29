"""Move what earlier versions cached as files into the shared market database.

Before the database there were pickles of each parsed Form 4 day and one CSV per price download.
Those files hold real downloads that cost hours of SEC and broker time, so they are imported rather
than thrown away: nothing is fetched again, and afterwards the cache folder can be deleted.

Importing is safe to repeat — rows are replaced by filing, and a day already covered stays covered.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from miratrade import store
from miratrade.config import CACHE_DIR

PRICE_FILE = re.compile(r"^(?P<ticker>[A-Z.\-]+)_(?P<start>\d{8})_(?P<end>\d{8})$")
INSIDER_SOURCE = "sec_form4"


def import_parsed_days(cache_dir: Path | None = None, db=None, log=print) -> dict:
    """Load ``.cache/sec/parsed/form4_YYYYMMDD.pkl`` into ``insiders`` and mark those days covered."""
    folder = Path(cache_dir or CACHE_DIR) / "sec" / "parsed"
    owned, db = db is None, db if db is not None else store.connect()
    found = sorted(folder.glob("form4_*.pkl"))
    days, rows = [], 0
    try:
        for path in found:
            try:
                df = pd.read_pickle(path)
            except Exception as e:                 # another pandas, or half written: re-download it
                log(f"  skipped {path.name}: {e}")
                continue
            if not isinstance(df, pd.DataFrame):
                continue
            day = pd.Timestamp(path.stem.removeprefix("form4_")).date()
            rows += store.write(db, "insiders", df)
            days.append(day)
        if days:
            store.mark_covered(db, INSIDER_SOURCE, days, rows=rows)
        log(f"  Form 4: {len(days)} days, {rows} rows imported from {folder}")
    finally:
        if owned:
            db.close()
    return {"files": len(found), "days": len(days), "rows": rows}


def import_price_csvs(cache_dir: Path | None = None, db=None, log=print, source: str = "") -> dict:
    """Load ``.cache/prices/<TICKER>_<start>_<end>.csv`` into ``prices``.

    The same ticker was downloaded over many overlapping windows, so the newest file for a ticker is
    read last and its bars win — a later download is the one adjusted for any split since.
    """
    folder = Path(cache_dir or CACHE_DIR) / "prices"
    owned, db = db is None, db if db is not None else store.connect()
    files = sorted(folder.glob("*.csv"), key=lambda p: (p.stem.split("_")[0], p.stat().st_mtime))
    tickers, rows, skipped = set(), 0, 0
    try:
        for path in files:
            m = PRICE_FILE.match(path.stem)
            if not m:
                skipped += 1
                continue
            try:
                bars = pd.read_csv(path, index_col=0, parse_dates=True)
            except Exception as e:
                log(f"  skipped {path.name}: {e}")
                skipped += 1
                continue
            if not len(bars) or "close" not in bars.columns:
                continue
            bars.index.name = "date"
            ticker = m.group("ticker")
            rows += store.write(db, "prices", bars.assign(ticker=ticker, source=source))
            tickers.add(ticker)
        log(f"  Prices: {len(tickers)} tickers, {rows} bars imported from {folder}"
            + (f" ({skipped} files skipped)" if skipped else ""))
    finally:
        if owned:
            db.close()
    return {"files": len(files), "tickers": len(tickers), "rows": rows, "skipped": skipped}


def import_scan_events(scan_dir: Path | None = None, db=None, log=print) -> dict:
    """Load the last saved scan's ``events.csv`` into the ``events`` table.

    The screens read events from the database now, so without this the Signals list would be empty
    until the next download even though the events are sitting on disk.
    """
    from miratrade.config import APP_DIR
    from miratrade.scan import load_scan, store_scan

    folder = Path(scan_dir or APP_DIR / "scan")
    owned, db = db is None, db if db is not None else store.connect()
    try:
        scan = load_scan(folder)
        if not scan or not len(scan.get("events", [])):
            log(f"  Events: no saved scan in {folder}")
            return {"events": 0, "prices": 0}
        written = store_scan(scan, db)
        log(f"  Events: {written['events']} events and {written['prices']} bars imported from {folder}")
        return written
    finally:
        if owned:
            db.close()


def import_cache(cache_dir: Path | None = None, db=None, log=print, source: str = "",
                 scan_dir: Path | None = None) -> dict:
    """Everything the file cache holds, in one go."""
    owned, db = db is None, db if db is not None else store.connect()
    try:
        log("Importing the file cache into the market database …")
        out = {"insiders": import_parsed_days(cache_dir, db, log),
               "prices": import_price_csvs(cache_dir, db, log, source),
               "events": import_scan_events(scan_dir, db, log)}
        store.note(db, "imported_from_cache", store.now())
        log("Done. The cache folder can be deleted; the database now holds it.")
    finally:
        if owned:
            db.close()
    return out
