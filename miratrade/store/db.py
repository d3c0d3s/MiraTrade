"""Opening, creating and upgrading the shared market database.

Several processes touch this file at once — the app, an analysis started from the Reports screen and
the command line — so the connection is opened in WAL mode with a busy timeout: readers never block
the writer and a writer waits its turn instead of failing.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from miratrade.config import DB_PATH
from miratrade.store.schema import INDEXES, SCHEMA_VERSION, TABLES

# Each entry upgrades from the version that is its key to that key plus one. They run inside the one
# transaction `migrate` opens, so a failure half way leaves the file on its old version rather than
# between two.
MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        # option_flow gains `source`, and it joins the primary key: the same contract-day really can
        # come from a broker snapshot and from a historical feed, and those are two rows worth
        # keeping apart, not one overwriting the other. SQLite cannot alter a primary key, so the
        # table is rebuilt and its rows carried across.
        "DROP TABLE IF EXISTS option_flow_v1",
        "ALTER TABLE option_flow RENAME TO option_flow_v1",
        # The DDL is written out as it stood at version 2, NOT taken from TABLES. A migration that
        # reads the live schema builds today's table and then the later migrations try to add columns
        # that are already there — an old file upgrading through every step breaks, while a new one
        # never notices. Each step has to describe the shape of its own version.
        """CREATE TABLE option_flow (
            date          TEXT NOT NULL,
            ticker        TEXT NOT NULL,
            expiry        TEXT NOT NULL,
            type          TEXT NOT NULL,
            strike        REAL NOT NULL,
            volume        REAL,
            open_interest REAL,
            premium       REAL,
            underlying    REAL,
            side          TEXT,
            source        TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (date, ticker, expiry, type, strike, source)
        )""",
        "INSERT INTO option_flow (date, ticker, expiry, type, strike, volume, open_interest, "
        "premium, underlying, side, source) SELECT date, ticker, expiry, type, strike, volume, "
        "open_interest, premium, underlying, side, '' FROM option_flow_v1",
        "DROP TABLE option_flow_v1",
    ),
    # Version 3 only adds the `earnings` table, and the DDL above creates any table that is missing,
    # so there is nothing to carry across — the version still has to step for a reader to know.
    2: (),
    # option_flow gains bid and ask. The chain always had them: `chain_to_flow` used them to work out
    # the mid and then dropped them, which threw away the spread — the number that decides whether a
    # contract can be traded at all, and how much of a profit target the round trip eats.
    3: ("ALTER TABLE option_flow ADD COLUMN bid REAL",
        "ALTER TABLE option_flow ADD COLUMN ask REAL"),
    # Version 5 only adds the `settings` table, which the DDL above creates on its own. The version
    # still steps, because a reader has to know whether the file it opened can hold settings at all.
    4: (),
    # …and version 6 the `attempts` table, the same way.
    5: (),
}


class SchemaTooNew(RuntimeError):
    """The file was written by a newer MiraTrade; this one would misread it."""


class NoDatabase(FileNotFoundError):
    """Nothing has been downloaded yet. A screen should explain that, not show a SQLite error —
    "unable to open database file" tells a person neither what is missing nor where it was looked
    for."""


def connect(path: Path | str | None = None, *, read_only: bool = False) -> sqlite3.Connection:
    """A connection to the market database, created and brought up to date if needed.

    ``read_only`` is what another app should use: it opens the same file without being able to
    change it, and fails instead of creating an empty database when the path is wrong.
    """
    path = Path(path or DB_PATH)
    if read_only:
        if not path.exists():
            raise NoDatabase(f"There is no market database at {path} yet. It is created the first "
                             f"time data is downloaded — run `miratrade scan` or press «Update "
                             f"data» under Signals.")
        try:
            conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
            conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")   # WAL problems surface on first read
        except sqlite3.Error:
            # A read-only connection to a WAL database needs the -shm file and cannot build it, so it
            # fails with a bare "unable to open database file" while a writer is busy or after a
            # crash left the WAL behind. Opening normally can rebuild it. The guarantee that matters
            # is that these callers never write, and that is in their code, not in the file mode.
            conn = sqlite3.connect(path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    # FULL, not NORMAL. NORMAL survives an application crash but can leave the file damaged if the
    # process is killed during a checkpoint — which happened, and truncated a 106 MB database to 24.
    # Writes here are a handful a day; durability is worth more than the speed.
    conn.execute("PRAGMA synchronous = FULL")
    migrate(conn)
    return conn


def version(conn: sqlite3.Connection) -> int:
    """The schema version of an open database; 0 means it is empty."""
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
    if tables is None:
        return 0
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    return int(row["value"]) if row else 0


def migrate(conn: sqlite3.Connection) -> int:
    """Create the tables, or step an older file up to :data:`SCHEMA_VERSION`. Returns the version."""
    found = version(conn)
    if found > SCHEMA_VERSION:
        raise SchemaTooNew(f"the database is at schema version {found} and this MiraTrade "
                           f"understands {SCHEMA_VERSION}; update MiraTrade to open it")
    with conn:                                     # one transaction: a half-migrated file is worse
        for ddl in TABLES.values():
            conn.execute(ddl)
        for ddl in INDEXES:
            conn.execute(ddl)
        while found and found < SCHEMA_VERSION:
            for statement in MIGRATIONS.get(found, ()):
                conn.execute(statement)
            found += 1
        _set(conn, "schema_version", str(SCHEMA_VERSION))
        _set(conn, "written_by", "MiraTrade")
        if not _get(conn, "created_at"):
            _set(conn, "created_at", now())
    return SCHEMA_VERSION


def now() -> str:
    """An ISO timestamp in UTC, so timestamps from different machines can be compared."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def _set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def note(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Leave a fact about the database in ``meta``, for a person or another app reading it later."""
    _set(conn, key, value)


def notes(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    """How many rows each table holds: what to print to see whether a download landed."""
    return {name: conn.execute(f"SELECT count(*) AS n FROM {name}").fetchone()["n"]
            for name in TABLES if name != "meta"}
