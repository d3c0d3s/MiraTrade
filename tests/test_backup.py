"""The daily copy of everything that would hurt to lose.

Most of the data could be downloaded again; the paper trades could not, and neither could the volume
of an option session, which is readable only while that session is the last one.
"""
import json
import zipfile
from datetime import date

import pandas as pd
import pytest

from miratrade import store
from miratrade.backup import (KEEP, backup_path, contents, extras, list_backups, make_backup, prune,
                              restore)


@pytest.fixture
def home(tmp_path):
    """A whole MiraTrade on disk: the database, the paper trades, the settings and a report."""
    app = tmp_path / "app"
    reports = tmp_path / "reports"
    (reports / "5y").mkdir(parents=True)
    app.mkdir()
    db = store.connect(tmp_path / "market.db")
    store.write(db, "insiders", pd.DataFrame([
        {"accession": "0001-26-1", "filing_date": "2026-08-14", "ticker": "PFE", "code": "P",
         "shares": 38000.0, "price": 26.34, "value": 1_000_920.0}]))
    db.close()
    (app / "practice.json").write_text(json.dumps([{"ticker": "PFE", "status": "open"}]),
                                       encoding="utf-8")
    (app / "settings.json").write_text(json.dumps({"risk": {"sizing_capital": 30000}}),
                                       encoding="utf-8")
    (reports / "5y" / "edge_report.md").write_text("# a finished analysis", encoding="utf-8")
    (reports / "5y" / "rules.csv").write_text("rule,validated\nx,True\n", encoding="utf-8")
    return {"db": tmp_path / "market.db", "app": app, "reports": reports,
            "into": tmp_path / "backups"}


def _make(home, **kw):
    return make_backup(home["db"], home["into"], app_dir=home["app"], reports_dir=home["reports"],
                       log=lambda _m: None, **kw)


def test_the_copy_holds_the_data_the_trades_the_settings_and_the_reports(home):
    made = _make(home)
    assert made is not None and made.exists()

    inside = set(contents(made))
    assert "market.db" in inside                       # everything downloaded
    assert "practice.json" in inside                   # the paper trades: nobody else has these
    assert "settings.json" in inside                   # the risk limits and the capital
    assert "reports/5y/edge_report.md" in inside       # hours of downloading and simulating
    assert "reports/5y/rules.csv" in inside


def test_the_database_is_snapshotted_through_sqlite_not_copied_as_bytes(home):
    """A WAL database being written to holds part of its state in -wal, so a byte copy can be torn
    while looking perfectly fine. The copy has to be readable on its own."""
    live = store.connect(home["db"])                   # a writer is open the whole time
    store.write(live, "insiders", pd.DataFrame([
        {"accession": "0001-26-2", "filing_date": "2026-08-15", "ticker": "ACME", "code": "P"}]))
    made = _make(home)
    live.close()

    out = home["into"] / "unpacked"
    with zipfile.ZipFile(made) as bundle:
        bundle.extract("market.db", out)
    restored = store.connect(out / "market.db")
    assert len(store.read(restored, "insiders")) == 2  # both rows, and the file opens at all
    restored.close()


def test_one_copy_a_day_and_calling_it_again_changes_nothing(home):
    first = _make(home)
    assert _make(home) is None                         # already done today: harmless to repeat
    assert len(list_backups(home["into"])) == 1
    again = _make(home, force=True)                    # unless asked
    assert again == first and len(list_backups(home["into"])) == 1


def test_only_the_newest_are_kept(home):
    for day in range(1, 11):
        _make(home, day=date(2026, 9, day))
    kept = list_backups(home["into"])
    assert len(kept) == KEEP == 7
    assert kept[0].name.endswith("20260910.zip")       # newest first
    assert kept[-1].name.endswith("20260904.zip")      # and the oldest three are gone


def test_how_many_to_keep_is_a_choice(home):
    for day in range(1, 8):
        _make(home, day=date(2026, 9, day), keep=3)
    assert len(list_backups(home["into"])) == 3
    assert prune(keep=1, root=home["into"], log=lambda _m: None)
    assert len(list_backups(home["into"])) == 1


def test_a_half_written_copy_is_never_left_behind(home, monkeypatch):
    """The zip is built under another name and renamed last, so an interrupted run leaves nothing
    that looks like a finished backup."""
    import miratrade.backup as backup

    def explode(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(backup.zipfile.ZipFile, "write", explode)
    with pytest.raises(OSError):
        _make(home)
    assert list_backups(home["into"]) == []
    assert not list(home["into"].glob("*.part"))


def test_nothing_to_back_up_is_said_rather_than_failing(tmp_path):
    said = []
    assert make_backup(tmp_path / "absent.db", tmp_path / "into", app_dir=tmp_path / "none",
                       reports_dir=tmp_path / "none", log=said.append) is None
    assert "nothing to back up" in " ".join(said)


def test_extras_leaves_out_what_is_not_there(home):
    (home["app"] / "practice.json").unlink()
    names = [name for _src, name in extras(home["app"], home["reports"])]
    assert "practice.json" not in names and "settings.json" in names


# --------------------------------------------------------------------------- putting it back

def test_restoring_keeps_what_was_there_rather_than_destroying_it(home):
    """Restoring the wrong day and losing the newer data in the same move is exactly the accident a
    backup exists to prevent, so nothing is deleted."""
    made = _make(home)
    (home["app"] / "practice.json").write_text(json.dumps([{"ticker": "NEW"}]), encoding="utf-8")
    db = store.connect(home["db"])
    store.write(db, "insiders", pd.DataFrame([
        {"accession": "later", "filing_date": "2026-09-01", "ticker": "LATER", "code": "P"}]))
    db.close()

    restore(made, home["db"], home["app"], home["reports"], log=lambda _m: None)

    assert json.loads((home["app"] / "practice.json").read_text(encoding="utf-8"))[0]["ticker"] == "PFE"
    kept = list(home["app"].glob("practice-replaced-*.json"))
    assert len(kept) == 1                              # the newer one is still on disk
    assert json.loads(kept[0].read_text(encoding="utf-8"))[0]["ticker"] == "NEW"

    db = store.connect(home["db"])
    assert set(store.read(db, "insiders")["ticker"]) == {"PFE"}   # back to the backed-up state
    db.close()
    assert list(home["db"].parent.glob("market-replaced-*.db"))


def test_restoring_a_backup_that_is_not_there_says_so(home):
    with pytest.raises(FileNotFoundError, match="No backup at"):
        restore(home["into"] / "miratrade-20200101.zip", home["db"], log=lambda _m: None)


def test_the_daily_job_takes_the_copy_before_it_writes_anything(home, monkeypatch, tmp_path):
    """The capture already runs every day. A backup that only happens when a capture succeeds is not
    a daily backup, so it is taken first and a failure there never stops the capture."""
    import miratrade.backup as backup
    from miratrade.flow import daily_capture

    taken = []
    monkeypatch.setattr(backup, "make_backup", lambda **k: taken.append(1))
    db = store.connect(tmp_path / "flow.db")
    daily_capture([], None, db=db, now="2026-09-28 22:30Z", log=lambda _m: None)
    db.close()
    assert taken == [1]


def test_a_failing_backup_never_stops_the_capture(monkeypatch, tmp_path):
    import miratrade.backup as backup
    from miratrade.flow import daily_capture

    def explode(**k):
        raise OSError("disk full")

    monkeypatch.setattr(backup, "make_backup", explode)
    said = []
    db = store.connect(tmp_path / "flow.db")
    out = daily_capture([], None, db=db, now="2026-09-28 22:30Z", log=said.append)
    db.close()
    assert "backup failed" in " ".join(said)
    assert out["why"]                                  # and the capture still reported its own state


def test_a_damaged_database_is_not_backed_up_over_the_good_copies(home, monkeypatch):
    """Backing up a damaged file would quietly push the last good copy a day closer to deletion.
    This is not hypothetical: a process killed during a checkpoint truncated a 106 MB database."""
    import miratrade.backup as backup

    good = _make(home, day=date(2026, 9, 26))
    assert good is not None

    monkeypatch.setattr(backup, "integrity",
                        lambda conn: "*** in database main *** page 3 is never used")
    with pytest.raises(RuntimeError, match="database is damaged"):
        _make(home, day=date(2026, 9, 27))

    kept = list_backups(home["into"])
    assert len(kept) == 1 and kept[0] == good          # the good one is untouched
    assert not list(home["into"].glob("*.part"))


def test_a_healthy_database_passes_the_check(home):
    import sqlite3

    from miratrade.backup import integrity

    conn = sqlite3.connect(home["db"])
    assert integrity(conn) == "ok"
    conn.close()
    assert "unreadable" in integrity(None)              # not even readable is an answer, not a crash
