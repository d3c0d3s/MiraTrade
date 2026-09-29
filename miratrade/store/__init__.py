"""The shared market database: everything MiraTrade downloads and everything it works out from it.

One SQLite file, outside any checkout, described in ``docs/DATA.md``. Another app reads it without
downloading anything again::

    from miratrade.store import connect, read
    with connect(read_only=True) as db:
        buys = read(db, "insiders", "code = 'P' AND filing_date >= ?", ("2026-01-01",))

or, with no MiraTrade installed at all, with the ``sqlite3`` module of any language.
"""
from miratrade.store.db import (NoDatabase, SchemaTooNew, connect, counts, migrate, note,
                                notes, now, version)
from miratrade.store.frames import (covered, gaps, mark_covered, prices, read, to_rows, write)
from miratrade.store.schema import SCHEMA_VERSION, TABLES

__all__ = ["SCHEMA_VERSION", "NoDatabase", "SchemaTooNew", "TABLES", "connect", "counts", "covered", "gaps",
           "mark_covered", "migrate", "note", "notes", "now", "prices", "read", "to_rows",
           "version", "write"]
