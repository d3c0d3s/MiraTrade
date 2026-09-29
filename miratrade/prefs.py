"""Every setting a person changes, kept in the market database rather than in a local file.

Settings used to live in ``%APPDATA%/MiraTrade/settings.json``, which works for exactly one program
on exactly one machine. The moment a second front-end exists — a web page served from the server
that holds the data — "where are the parameters" has an answer or it does not, and two answers is
worse than either. They go where the data is.

Three things follow from that, and they are the whole design:

* **One row per setting**, not one blob. Two clients each changing a different thing must not have
  one silently undo the other, and a whole-file save does exactly that. It also means a change is a
  fact with a timestamp, which is what a parameter form needs to say "this is not the default".
* **Values are JSON.** ``false`` read back as plain text is the string ``"false"``, which is true —
  that is how a risk limit gets quietly disabled. A list (``passive_filers``) survives too.
* **The file is still written.** It is the fallback when the database cannot be opened, it is
  readable by a person, and it is in the daily backup. The store wins when they disagree, because
  the store is the one both front-ends can reach.

Only the sections in :data:`USER_SECTIONS` are stored. The rest of ``Config`` is the shape of an
analysis rather than a preference, and writing it down would freeze today's internals into a file
that outlives them.
"""
from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from miratrade.config import APP_DIR, Config, load_user_config

# What a person can change, and where from:
#   risk, broker, data, ui, notify   the Settings screen
#   insider, flow, smart             what counts as an event   (the Signals parameter form)
#   trade, options, liquidity        what contract, and its exits
USER_SECTIONS = ("risk", "broker", "data", "ui", "notify",
                 "insider", "flow", "smart", "trade", "options", "liquidity")
JSON_PATH = APP_DIR / "settings.json"
IMPORTED = "settings_imported_from"          # a note in `meta`, so the import happens once


def sections(cfg: Config | None = None) -> dict[str, Any]:
    cfg = cfg or Config()
    return {name: getattr(cfg, name) for name in USER_SECTIONS}


def defaults() -> dict[tuple[str, str], Any]:
    """Every stored setting's default, so a screen can say what is and is not the default."""
    out = {}
    for name, section in sections().items():
        for f in fields(section):
            out[(name, f.name)] = getattr(section, f.name)
    return out


def _apply(cfg: Config, section: str, key: str, value: Any) -> bool:
    """Set one value on ``cfg``; ``False`` when the section or the key is not one we know.

    A setting that no longer exists is skipped rather than raised on: an older file may carry one,
    and refusing to start because of a leftover row is a worse failure than ignoring it.
    """
    target = getattr(cfg, section, None)
    if target is None or section not in USER_SECTIONS or not hasattr(target, key):
        return False
    setattr(target, key, value)
    return True


def read(db, cfg: Config | None = None) -> tuple[Config, list[str]]:
    """``cfg`` (a fresh ``Config`` by default) with the stored settings laid over it.

    Also returns the rows that were skipped, so ``miratrade store settings`` can show them instead
    of a person wondering why a value they set does nothing.
    """
    cfg = cfg or Config()
    unknown = []
    for row in db.execute("SELECT section, key, value FROM settings ORDER BY section, key"):
        try:
            value = json.loads(row["value"])
        except (TypeError, ValueError):
            unknown.append(f"{row['section']}.{row['key']} (not JSON)")
            continue
        if not _apply(cfg, row["section"], row["key"], value):
            unknown.append(f"{row['section']}.{row['key']}")
    return cfg, unknown


def put(db, section: str, key: str, value: Any) -> None:
    """Change one setting. This is what a parameter form saves: one field, one row, one timestamp."""
    from miratrade.store.db import now

    if section not in USER_SECTIONS:
        raise KeyError(f"{section!r} is not a section a person can change: {', '.join(USER_SECTIONS)}")
    if not hasattr(getattr(Config(), section), key):
        raise KeyError(f"no setting called {section}.{key}")
    with db:
        db.execute("INSERT INTO settings (section, key, value, updated_at) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT(section, key) DO UPDATE SET value=excluded.value, "
                   "updated_at=excluded.updated_at",
                   (section, key, json.dumps(value), now()))


def write(db, cfg: Config, only: tuple[str, ...] | None = None) -> int:
    """Store every setting of ``cfg`` (or only some sections). Returns how many rows were written.

    Values equal to the default are stored too, on purpose: "the default changed under me" is a
    surprise nobody wants from a number they typed once and trusted.
    """
    from miratrade.store.db import now

    stamp = now()
    rows = []
    for name in (only or USER_SECTIONS):
        for key, value in asdict(getattr(cfg, name)).items():
            rows.append((name, key, json.dumps(value), stamp))
    with db:
        db.executemany("INSERT INTO settings (section, key, value, updated_at) VALUES (?, ?, ?, ?) "
                       "ON CONFLICT(section, key) DO UPDATE SET value=excluded.value, "
                       "updated_at=excluded.updated_at", rows)
    return len(rows)


def reset(db, section: str, key: str | None = None) -> int:
    """Forget a setting, or a whole section, so the default applies again."""
    with db:
        if key is None:
            cursor = db.execute("DELETE FROM settings WHERE section = ?", (section,))
        else:
            cursor = db.execute("DELETE FROM settings WHERE section = ? AND key = ?", (section, key))
    return cursor.rowcount or 0


def changed(db) -> dict[tuple[str, str], tuple[Any, Any, str]]:
    """The settings that differ from the default, as ``{(section, key): (value, default, when)}``.

    What a screen shows to mark a field as touched, and what an analysis should print beside its
    numbers — a result obtained under settings nobody wrote down is not reproducible.
    """
    base = defaults()
    out = {}
    for row in db.execute("SELECT section, key, value, updated_at FROM settings"):
        pair = (row["section"], row["key"])
        if pair not in base:
            continue
        try:
            value = json.loads(row["value"])
        except (TypeError, ValueError):
            continue
        if value != base[pair]:
            out[pair] = (value, base[pair], row["updated_at"])
    return out


def stored(db) -> int:
    row = db.execute("SELECT count(*) AS n FROM settings").fetchone()
    return int(row["n"]) if row else 0


def import_json(db, path: Path | None = None) -> int:
    """Bring an existing ``settings.json`` into the store, once.

    Recorded in ``meta`` so it never runs twice: a second import would resurrect a value the person
    has since changed in the store, which is the one thing a migration must not do.
    """
    from miratrade.store.db import note, notes

    path = Path(path or JSON_PATH)
    if notes(db).get(IMPORTED) or not path.exists():
        return 0
    try:
        cfg = load_user_config(path)
    except Exception:                       # a file we cannot read is not a reason to refuse to start
        note(db, IMPORTED, f"{path} (unreadable)")
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    present = tuple(s for s in data if s in USER_SECTIONS)
    written = write(db, cfg, only=present) if present else 0
    note(db, IMPORTED, str(path))
    return written


def save_json(cfg: Config, path: Path | None = None) -> None:
    """Mirror the stored settings to the readable file, which is also the fallback and the backup."""
    path = Path(path or JSON_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {name: asdict(getattr(cfg, name)) for name in USER_SECTIONS}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    load_user_config(tmp)                   # raises if something is off; the old file stays
    tmp.replace(path)


# --------------------------------------------------------------------------- what the app calls

def load(db=None, json_path: Path | None = None) -> Config:
    """The settings in force: the store, seeded once from ``settings.json``.

    Falls back to the file when the database cannot be opened. A screen that cannot read a
    preference should come up with the defaults and let the person fix it, not refuse to start.
    """
    from miratrade import store

    owned = db is None
    if owned:
        try:
            db = store.connect()
        except Exception:
            return load_user_config(json_path or JSON_PATH)
    try:
        import_json(db, json_path)
        cfg, _unknown = read(db)
        return cfg
    finally:
        if owned:
            db.close()


def save(cfg: Config, db=None, json_path: Path | None = None) -> None:
    """Store the settings, and mirror them to the file. The store is what the two front-ends read."""
    from miratrade import store

    owned = db is None
    if owned:
        db = store.connect()
    try:
        write(db, cfg)
        from miratrade.store.db import note, notes

        if not notes(db).get(IMPORTED):     # saved before anything was imported: nothing left to import
            note(db, IMPORTED, "written by the app")
    finally:
        if owned:
            db.close()
    save_json(cfg, json_path)
