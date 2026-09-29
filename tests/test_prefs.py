"""Settings in the market database, and how old that database is.

Both exist for the same reason: the screens stopped downloading. Parameters have to live where
both front-ends can reach them, and a screen that only reads has to say how old what it is showing
is. Neither is interesting on its own; both are the difference between an app that is honest about
its data and one that looks instant while answering last week's question.
"""
import json
from datetime import date

import pytest

from miratrade import freshness, prefs, store
from miratrade.config import Config


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / "market.db")
    yield conn
    conn.close()


# --------------------------------------------------------------------------- settings

def test_a_setting_survives_the_round_trip_as_what_it_was(db):
    """Types matter here more than anywhere: `false` read back as text is the string "false",
    which is true, and that is how a limit gets quietly disabled."""
    prefs.put(db, "risk", "size_on_balance", True)
    prefs.put(db, "insider", "min_value_usd", 250_000.0)
    prefs.put(db, "smart", "passive_filers", ["VANGUARD", "BLACKROCK"])
    prefs.put(db, "data", "cap_tier", "small")

    cfg, unknown = prefs.read(db)
    assert cfg.risk.size_on_balance is True
    assert cfg.insider.min_value_usd == 250_000.0
    assert cfg.smart.passive_filers == ["VANGUARD", "BLACKROCK"]
    assert cfg.data.cap_tier == "small"
    assert unknown == []


def test_one_row_per_setting_so_two_clients_do_not_undo_each_other(db):
    """A whole-file save is what makes the desktop app and the web page fight over a JSON blob."""
    prefs.write(db, Config())
    before = prefs.stored(db)

    prefs.put(db, "risk", "max_positions", 3)              # one client
    prefs.put(db, "data", "scan_days", 45)                 # the other, at the same time

    cfg, _ = prefs.read(db)
    assert (cfg.risk.max_positions, cfg.data.scan_days) == (3, 45)
    assert prefs.stored(db) == before                      # updated in place, not appended


def test_only_settings_a_person_can_change_are_storable(db):
    with pytest.raises(KeyError, match="not a section"):
        prefs.put(db, "edge", "min_support", 5)            # the shape of an analysis, not a choice
    with pytest.raises(KeyError, match="no setting"):
        prefs.put(db, "risk", "max_positons", 3)           # a typo


def test_what_differs_from_the_default_is_known(db):
    assert prefs.changed(db) == {}
    prefs.put(db, "risk", "max_positions", 3)
    prefs.put(db, "risk", "risk_per_trade_pct", Config().risk.risk_per_trade_pct)   # same as default

    touched = prefs.changed(db)
    assert list(touched) == [("risk", "max_positions")]
    value, default, when = touched[("risk", "max_positions")]
    assert (value, default) == (3, 5) and when


def test_resetting_brings_the_default_back(db):
    prefs.put(db, "risk", "max_positions", 3)
    prefs.put(db, "risk", "risk_per_trade_pct", 0.4)
    assert prefs.reset(db, "risk", "max_positions") == 1
    assert prefs.read(db)[0].risk.max_positions == 5
    assert prefs.reset(db, "risk") == 1                    # the rest of the section
    assert prefs.read(db)[0].risk.risk_per_trade_pct == Config().risk.risk_per_trade_pct


def test_the_existing_file_is_imported_once_and_never_again(db, tmp_path):
    """A second import would resurrect a value the person has since changed in the store, which is
    the one thing a migration must not do."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"risk": {"max_positions": 2}}), encoding="utf-8")

    assert prefs.import_json(db, path) > 0
    assert prefs.read(db)[0].risk.max_positions == 2

    prefs.put(db, "risk", "max_positions", 7)              # the person changes it afterwards
    assert prefs.import_json(db, path) == 0                # the file is not read again
    assert prefs.read(db)[0].risk.max_positions == 7


def test_an_unreadable_file_is_not_a_reason_to_refuse_to_start(db, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json at all", encoding="utf-8")
    assert prefs.import_json(db, path) == 0
    assert prefs.read(db)[0].risk.max_positions == 5       # defaults, and the app comes up


def test_the_file_is_still_written_because_it_is_the_fallback(db, tmp_path):
    path = tmp_path / "mirror.json"
    cfg = Config()
    cfg.risk.max_positions = 4
    prefs.save(cfg, db=db, json_path=path)

    assert json.loads(path.read_text(encoding="utf-8"))["risk"]["max_positions"] == 4
    assert prefs.read(db)[0].risk.max_positions == 4


def test_the_store_wins_over_the_file(db, tmp_path):
    """They are two answers to one question, and the store is the one both front-ends can reach."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"risk": {"max_positions": 2}}), encoding="utf-8")
    prefs.import_json(db, path)
    prefs.put(db, "risk", "max_positions", 9)
    path.write_text(json.dumps({"risk": {"max_positions": 2}}), encoding="utf-8")   # file unchanged

    assert prefs.load(db=db, json_path=path).risk.max_positions == 9


def test_settings_that_no_longer_exist_are_ignored_and_reported(db):
    """Refusing to start over a leftover row from an older version is the worse failure of the two;
    silence is what leaves someone wondering why a value they set does nothing."""
    db.execute("INSERT INTO settings VALUES ('risk', 'gone_in_v2', '1', '2026-01-01')")
    db.execute("INSERT INTO settings VALUES ('nowhere', 'x', '1', '2026-01-01')")
    cfg, unknown = prefs.read(db)
    assert cfg.risk.max_positions == 5
    assert sorted(unknown) == ["nowhere.x", "risk.gone_in_v2"]


# --------------------------------------------------------------------------- freshness

def _fetched(db, day: str, source: str = "sec_form4") -> None:
    store.mark_covered(db, source, [day], rows=0)


def test_nothing_downloaded_is_said_plainly(db):
    state = freshness.check(db, now=date(2026, 9, 28))
    assert state.never and state.stale
    assert "Scanner" in state.say()


def test_up_to_date_is_not_an_alert(db):
    _fetched(db, "2026-09-25")                             # a Friday
    state = freshness.check(db, now=date(2026, 9, 26))     # the Saturday after
    assert not state.stale and state.behind == 0


def test_the_weekend_is_not_a_reason_to_warn(db):
    """Asking why Sunday has no filings is not a question anyone needs the app to raise."""
    _fetched(db, "2026-09-25")                             # Friday
    for day in (date(2026, 9, 26), date(2026, 9, 27)):     # Saturday, Sunday
        assert freshness.last_session(day) == date(2026, 9, 25)
        assert not freshness.check(db, now=day).stale


def test_being_days_behind_says_how_many_and_where_to_go(db):
    _fetched(db, "2026-09-21")                             # Monday
    state = freshness.check(db, now=date(2026, 9, 25))     # the Friday
    assert state.stale and state.behind == 4
    said = state.say()
    assert "4" in said and "Scanner" in said


def test_one_session_behind_is_tolerated(db):
    """A market holiday looks exactly like a day nobody fetched, so one is not worth an alert."""
    _fetched(db, "2026-09-24")
    assert not freshness.check(db, now=date(2026, 9, 25)).stale


def test_it_measures_downloads_not_events(db):
    """"No new events" and "nobody downloaded since Tuesday" look identical in a list and mean
    opposite things, so the measure comes from coverage — which records a day of nothing as a real
    answer — and never from how many events are stored."""
    _fetched(db, "2026-09-25")                             # asked, found nothing
    state = freshness.check(db, now=date(2026, 9, 25))
    assert state.rows == 0 and not state.stale


def test_a_database_it_cannot_read_still_draws_the_screen(tmp_path):
    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("locked")

    state = freshness.check(Broken(), now=date(2026, 9, 25))
    assert state.never and state.rows == 0                 # an answer, not an exception
