"""``miratrade store`` — look at the shared market database and fill it from the old file cache."""
from __future__ import annotations

from pathlib import Path

from miratrade import store
from miratrade.backup import KEEP, backup_folder, contents, list_backups, make_backup, restore
from miratrade.config import DB_PATH


def cmd_info(args) -> None:
    """Where the database is, what version it is and how much it holds."""
    path = args.db or DB_PATH
    if not path.exists():
        print(f"No database at {path} yet. It is created the first time data is downloaded, or by "
              f"`miratrade store import`.")
        return
    db = store.connect(path)
    try:
        print(f"{path}  ({path.stat().st_size / 1e6:,.1f} MB, schema v{store.version(db)})")
        for table, n in store.counts(db).items():
            print(f"  {table:<20} {n:>10,}")
        notes = store.notes(db)
        for key in ("created_at", "imported_from_cache"):
            if notes.get(key):
                print(f"  {key:<20} {notes[key]:>10}")
        covered = db.execute("SELECT source, count(*) AS days, min(day) AS first, max(day) AS last "
                             "FROM coverage GROUP BY source ORDER BY source").fetchall()
        if covered:
            print("\nDownloaded days per source:")
            for row in covered:
                print(f"  {row['source']:<20} {row['days']:>6} days   {row['first']} → {row['last']}")
    finally:
        db.close()


def cmd_import(args) -> None:
    """Bring the old ``.cache`` files in, so nothing has to be downloaded twice."""
    from miratrade.store.importer import import_cache

    db = store.connect(args.db or DB_PATH)
    try:
        import_cache(args.cache, db, source=args.source)
        print()
        cmd_info(args)
    finally:
        db.close()


def add_parser(sub) -> None:
    st = sub.add_parser("store", help="the shared market database: what it holds, and importing "
                                      "the old file cache into it")
    inner = st.add_subparsers(dest="store_cmd", required=True)

    info = inner.add_parser("info", help="where the database is and how much it holds")
    info.set_defaults(func=cmd_info)

    imp = inner.add_parser("import", help="import .cache pickles and price CSVs into the database")
    imp.add_argument("--cache", default=None, type=_path,
                     help="the cache folder to read (default: the configured one)")
    imp.add_argument("--source", default="", help="which source those prices came from "
                                                  "(schwab or research), for the licence that follows them")
    imp.set_defaults(func=cmd_import)

    bk = inner.add_parser("backup", help="one compressed, consistent copy a day of everything "
                                        "downloaded; the newest few are kept")
    bk.add_argument("--keep", type=int, default=KEEP, help=f"how many to keep (default {KEEP})")
    bk.add_argument("--into", default=None, type=_path, help="a folder other than the default")
    bk.add_argument("--force", action="store_true", help="take one even if today's exists")
    bk.set_defaults(func=cmd_backup)

    rs = inner.add_parser("restore", help="put a copy back; the database in place is kept beside it")
    rs.add_argument("file", nargs="?", default=None, help="which copy (default: the newest)")
    rs.add_argument("--into", default=None, type=_path, help="the folder the copies are in")
    rs.add_argument("--yes", action="store_true", help="required: this replaces the database")
    rs.set_defaults(func=cmd_restore)

    for p in (info, imp, bk, rs):
        p.add_argument("--db", default=None, type=_path, help="a database file other than the default")


def _path(value: str):
    from pathlib import Path

    return Path(value).expanduser()


def cmd_backup(a) -> None:
    """One compressed, consistent copy a day of everything that would hurt to lose."""
    print(f"Backing up {a.db or DB_PATH}, the paper trades, the settings and the reports")
    make_backup(a.db, a.into, keep=a.keep, force=a.force)
    copies = list_backups(a.into)
    print(f"\n{len(copies)} copies kept in {backup_folder(a.into)}:")
    for c in copies:
        print(f"  {c.name:<26} {c.stat().st_size / 1e6:>7,.0f} MB")


def cmd_restore(a) -> None:
    """Put a copy back. Whatever is in place is kept beside it, never overwritten."""
    copies = list_backups(a.into)
    chosen = Path(a.file) if a.file else (copies[0] if copies else None)
    if chosen is None:
        raise SystemExit("No backups yet. Run `miratrade store backup`.")
    print(f"{chosen.name} holds:")
    for name in contents(chosen)[:12]:
        print(f"  {name}")
    if not a.yes:
        raise SystemExit("\nNothing changed. Add --yes once you are sure. Whatever is in place now "
                         "is renamed rather than deleted, so a wrong choice is undoable.")
    restore(chosen, a.db)
