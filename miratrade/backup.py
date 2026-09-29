"""A daily copy of everything MiraTrade would hurt to lose, and how many to keep.

What goes in, and why each one:

* **market.db** — every filing, price bar and option chain downloaded. Most of it could be fetched
  again, but **the volume of an option session cannot**: it is readable only while that session is
  the last one, and no free source sells it back afterwards.
* **practice.json** — the paper trades. Nobody else has this. It is the only record of what was
  decided and what came of it, which is the thing the whole exercise is for.
* **settings.json** — the risk limits, the capital, the window, the language. Small, and annoying to
  reconstruct exactly.
* **reports/** — finished analyses. Recomputing one means hours of downloading and simulating.

Deliberately **not** included: the raw HTTP cache (large, and it re-downloads) and the saved scan
(rebuilt from the database in seconds). Credentials are never in a backup — they live in the Windows
Credential Manager and must stay there.

Two things make a copy trustworthy. The database is taken with SQLite's **online backup**, not copied
as bytes: a WAL database being written to holds part of its state in ``-wal``, so a byte copy can be
torn while looking perfectly fine. And the whole set goes into one **zip**, which Windows opens with
no tools at all — the moment you need a backup is the worst moment to need software to read it.

**Seven daily copies** is the default. A week covers the realistic accident, breaking something on
Monday and noticing on Friday. Fewer stops covering it; many more only holds older copies of data
that is mostly append-only anyway. ``--keep`` changes it.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Callable

from miratrade.config import APP_DIR, DATA_HOME, DB_PATH, REPORTS_DIR

KEEP = 7
FOLDER = "backups"
STEM = "miratrade-"
SUFFIX = ".zip"
DB_NAME = "market.db"


def integrity(conn) -> str:
    """SQLite's own verdict on a database: "ok", or what is wrong with it.

    The snapshot is checked before it is kept, because backing up a damaged database quietly pushes
    the last good copy one day closer to being deleted — which is the one failure a backup scheme
    cannot survive.
    """
    try:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    except Exception as e:                    # it cannot even be read: that is an answer too
        return f"unreadable: {e}"


def backup_folder(root: Path | None = None) -> Path:
    return Path(root) if root else DATA_HOME / FOLDER


def backup_path(day: date | None = None, root: Path | None = None) -> Path:
    return backup_folder(root) / f"{STEM}{(day or date.today()):%Y%m%d}{SUFFIX}"


def list_backups(root: Path | None = None) -> list[Path]:
    """Newest first."""
    folder = backup_folder(root)
    return sorted(folder.glob(f"{STEM}*{SUFFIX}"), reverse=True) if folder.exists() else []


def extras(app_dir: Path | None = None, reports_dir: Path | None = None) -> list[tuple[Path, str]]:
    """The files beside the database that are worth keeping, as ``(on disk, name in the zip)``."""
    app = Path(app_dir or APP_DIR)
    out = [(app / "practice.json", "practice.json"), (app / "settings.json", "settings.json")]
    reports = Path(reports_dir or REPORTS_DIR)
    if reports.exists():
        out += [(f, f"reports/{f.relative_to(reports).as_posix()}")
                for f in sorted(reports.rglob("*")) if f.is_file()]
    return [(src, name) for src, name in out if src.exists()]


def prune(keep: int = KEEP, root: Path | None = None, log: Callable[[str], None] = print) -> list[Path]:
    """Delete all but the newest ``keep`` copies. Returns what was removed."""
    removed = []
    for old in list_backups(root)[max(0, keep):]:
        try:
            old.unlink()
            removed.append(old)
        except OSError as e:                  # one held open elsewhere is left for the next run
            log(f"  could not remove {old.name}: {e}")
    return removed


def make_backup(db_path: Path | None = None, root: Path | None = None, day: date | None = None,
                keep: int = KEEP, force: bool = False, app_dir: Path | None = None,
                reports_dir: Path | None = None, log: Callable[[str], None] = print) -> Path | None:
    """One consistent, compressed copy of everything for ``day``, then prune to ``keep``.

    Returns the copy, or ``None`` when today's already exists — this is called from whatever runs
    daily, so calling it repeatedly has to be harmless.
    """
    source = Path(db_path or DB_PATH)
    target = backup_path(day, root)
    if target.exists() and not force:
        log(f"  today's copy already exists: {target.name}")
        return None
    beside = extras(app_dir, reports_dir)
    if not source.exists() and not beside:
        log(f"  nothing to back up yet: no database at {source}")
        return None
    target.parent.mkdir(parents=True, exist_ok=True)

    partial = target.with_suffix(".part")
    snapshot = None
    try:
        if source.exists():
            # through SQLite, so writers may carry on while the snapshot is taken. Both connections
            # are closed by hand: `with sqlite3.connect(...)` commits the transaction and leaves the
            # connection open, and on Windows an open handle makes the file impossible to delete.
            handle, temp = tempfile.mkstemp(suffix=".db", dir=str(target.parent))
            os.close(handle)
            snapshot = Path(temp)
            live = copy = None
            try:
                live, copy = sqlite3.connect(source), sqlite3.connect(snapshot)
                live.backup(copy)
                verdict = integrity(copy)
                if verdict != "ok":
                    raise RuntimeError(f"the database is damaged ({verdict}); today's copy was not "
                                       f"taken, so the ones already kept are still good. Put one "
                                       f"back with `miratrade store restore`.")
            finally:
                for conn in (copy, live):
                    if conn is not None:
                        conn.close()
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            if snapshot is not None:
                bundle.write(snapshot, DB_NAME)
            for src, name in beside:
                bundle.write(src, name)
        partial.replace(target)               # renamed last: a half-written copy is never found
    finally:
        if snapshot is not None:
            snapshot.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)

    raw = (source.stat().st_size if source.exists() else 0) + sum(s.stat().st_size for s, _ in beside)
    log(f"  {target.name}: {target.stat().st_size / 1e6:,.0f} MB from {raw / 1e6:,.0f} MB, "
        f"{len(beside) + (1 if snapshot else 0)} items")
    for gone in prune(keep, root, log):
        log(f"  removed {gone.name}, past the {keep} kept")
    return target


def contents(backup: Path) -> list[str]:
    with zipfile.ZipFile(backup) as bundle:
        return bundle.namelist()


def restore(backup: Path, db_path: Path | None = None, app_dir: Path | None = None,
            reports_dir: Path | None = None, log: Callable[[str], None] = print) -> list[Path]:
    """Put a copy back, keeping whatever is in place beside it rather than overwriting it.

    Restoring the wrong day and destroying the newer data in the same move is exactly the accident a
    backup exists to prevent, so nothing is deleted: what was there is renamed with today's date.
    """
    backup = Path(backup)
    if not backup.exists():
        raise FileNotFoundError(f"No backup at {backup}")
    target_db = Path(db_path or DB_PATH)
    app = Path(app_dir or APP_DIR)
    reports = Path(reports_dir or REPORTS_DIR)
    written = []
    with zipfile.ZipFile(backup) as bundle:
        for name in bundle.namelist():
            if name == DB_NAME:
                destination = target_db
            elif name.startswith("reports/"):
                destination = reports / name[len("reports/"):]
            else:
                destination = app / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                aside = destination.with_name(
                    f"{destination.stem}-replaced-{date.today():%Y%m%d}{destination.suffix}")
                destination.replace(aside)
                log(f"  kept the existing {destination.name} as {aside.name}")
            if destination == target_db:      # they belong to the database that was just moved aside
                for leftover in ("-wal", "-shm"):
                    destination.with_name(destination.name + leftover).unlink(missing_ok=True)
            with bundle.open(name) as inside, open(destination, "wb") as out:
                import shutil

                shutil.copyfileobj(inside, out, length=4 << 20)
            written.append(destination)
    log(f"  restored {len(written)} items from {backup.name}")
    return written
