"""Counting how many settings a result was chosen from, and what the form does with that.

A parameter form without this is a mining machine. Each individual run looks like one honest test;
the problem lives in the history, which nobody remembers and the app never wrote down. These tests
are about the two properties that make the count mean something: re-running the same settings is
not a new test, and changing a rule is.
"""
import pytest

from miratrade import attempts, params, prefs, store
from miratrade.config import Config


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / "market.db")
    yield conn
    conn.close()


def _with(min_value: float) -> Config:
    cfg = Config()
    cfg.insider.min_value_usd = min_value
    return cfg


# --------------------------------------------------------------------------- what counts as a try

def test_a_different_rule_is_a_new_test(db):
    for value in (25_000, 100_000, 250_000):
        attempts.record(db, _with(value), "search")
    assert attempts.count(db, "search") == 3


def test_running_the_same_settings_again_is_not(db):
    """Repeating an experiment is not testing a new hypothesis. Counting it would make the
    correction meaninglessly harsh, and a correction nobody believes is one nobody applies."""
    total, fresh = attempts.record(db, _with(100_000), "search")
    assert (total, fresh) == (1, True)
    for _ in range(5):
        total, fresh = attempts.record(db, _with(100_000), "search")
    assert (total, fresh) == (1, False)
    assert db.execute("SELECT runs FROM attempts").fetchone()["runs"] == 6   # still interesting


def test_changing_a_number_and_changing_it_back_invents_nothing(db):
    attempts.record(db, _with(25_000), "search")
    attempts.record(db, _with(500_000), "search")
    attempts.record(db, _with(25_000), "search")
    assert attempts.count(db, "search") == 2


def test_settings_that_are_not_about_the_market_are_not_hypotheses(db):
    """Changing the language or the size of the account is not a claim about anything."""
    a = Config()
    b = Config()
    b.ui.language = "en"
    b.risk.sizing_capital = 90_000
    b.data.cap_tier = "small"
    assert attempts.fingerprint(a) == attempts.fingerprint(b)


def test_searching_and_backtesting_are_counted_apart(db):
    attempts.record(db, _with(25_000), "search")
    attempts.record(db, _with(100_000), "search")
    attempts.record(db, _with(25_000), "analysis")
    assert attempts.count(db, "search") == 2
    assert attempts.count(db, "analysis") == 1
    assert attempts.count(db) == 3


def test_the_count_can_be_started_again_deliberately(db):
    """A counter that can only go up gets ignored, and a person genuinely does start a new line of
    research. It is one explicit act, with a date on the rows it replaces."""
    for value in (1, 2, 3):
        attempts.record(db, _with(value * 10_000), "search")
    assert attempts.forget(db, "search") == 3
    assert attempts.count(db, "search") == 0


def test_a_database_without_the_table_answers_zero_rather_than_crashing(tmp_path):
    import sqlite3

    conn = sqlite3.connect(tmp_path / "old.db")
    conn.row_factory = sqlite3.Row
    assert attempts.count(conn) == 0 and attempts.history(conn) == []
    conn.close()


# --------------------------------------------------------------------------- the arithmetic

def test_the_first_try_needs_no_apology(db):
    template, fields = attempts.verdict(1)
    assert "First configuration" in template and fields == {}


def test_the_correction_tightens_as_tries_pile_up():
    assert attempts.sidak(1) == pytest.approx(0.05)
    assert attempts.sidak(20) == pytest.approx(0.00256, abs=1e-4)
    assert attempts.sidak(50) < attempts.sidak(20) < attempts.sidak(5)
    # …and the t a result needs rises with it
    assert attempts.z_for(0.05) == pytest.approx(1.96, abs=0.01)
    assert attempts.z_for(attempts.sidak(20)) == pytest.approx(3.02, abs=0.05)


def test_the_number_that_changes_behaviour_is_the_chance_of_luck():
    """"Corrected alpha is 0.0026" is arithmetic. "With 20 tries something looks significant by
    chance two times in three" is a fact about what you are holding."""
    assert attempts.luck(1) == pytest.approx(0.05)
    assert attempts.luck(20) == pytest.approx(0.64, abs=0.01)
    assert attempts.luck(50) > 0.9


def test_the_sentence_says_all_three_things(db):
    for value in range(1, 21):
        attempts.record(db, _with(value * 1_000), "search")
    said = attempts.say(attempts.count(db, "search"))
    assert "20" in said and "0.0026" in said and "64" in said


# --------------------------------------------------------------------------- the form's fields

def test_every_field_points_at_a_setting_that_exists():
    """A form field pointing at a renamed setting silently does nothing, which is the worst kind of
    control: it looks like it works. This check found three the first time it ran."""
    assert params.validate() == []


def test_every_field_is_storable_and_round_trips(db):
    for field in params.fields():
        value = field.default()
        prefs.put(db, field.section, field.key, value)
    cfg, unknown = prefs.read(db)
    assert unknown == []
    for field in params.fields():
        assert getattr(getattr(cfg, field.section), field.key) == field.default()


def test_every_field_explains_itself_in_terms_of_a_trade():
    """`min_value_usd: float` is not a setting a person can reason about; "smallest purchase that
    counts, below this a director buying a few hundred dollars is noise" is."""
    for field in params.fields():
        assert field.label and not field.label.endswith(("_usd", "_pct", "_days"))
        assert len(field.help) > 40, f"{field.section}.{field.key} explains nothing"


# --------------------------------------------------------------------------- the form on screen

def test_the_form_draws_saves_only_what_changed_and_resets(qtbot, db):
    """The three promises the dialog makes: nothing is written until Save, a changed field is
    marked, and Back to defaults really forgets rather than writing today's defaults down."""
    from miratrade.app.pages.paramform import ParamForm

    form = ParamForm(params.ALL_GROUPS, db, kind="search")
    qtbot.addWidget(form)
    assert len(form.editors) == len(params.fields())

    box = form.editors[("insider", "min_value_usd")]
    box.setValue(250_000)
    assert prefs.stored(db) == 0                       # typing writes nothing

    form.save()
    cfg, _ = prefs.read(db)
    assert cfg.insider.min_value_usd == 250_000
    assert prefs.stored(db) == 1                       # and only the one field that moved

    again = ParamForm(params.ALL_GROUPS, db, kind="search")
    qtbot.addWidget(again)
    assert "250,000" in again.marks[("insider", "min_value_usd")].text() or \
           "25,000" in again.marks[("insider", "min_value_usd")].text()
    again._reset()
    assert prefs.read(db)[0].insider.min_value_usd == Config().insider.min_value_usd


def test_cancelling_changes_nothing(qtbot, db):
    from miratrade.app.pages.paramform import ParamForm

    form = ParamForm(params.ALL_GROUPS, db, kind="search")
    qtbot.addWidget(form)
    form.editors[("trade", "stop_atr")].setValue(4.0)
    form.reject()
    assert prefs.stored(db) == 0
    assert prefs.read(db)[0].trade.stop_atr == Config().trade.stop_atr


def test_the_attempt_count_is_on_the_form(qtbot, db):
    """Shown at the moment somebody is about to try another configuration, which is the moment it
    means something — not buried in a report they have to think to open."""
    from miratrade.app.pages.paramform import ParamForm

    for value in range(1, 8):
        attempts.record(db, _with(value * 10_000), "search")
    form = ParamForm(params.ALL_GROUPS, db, kind="search")
    qtbot.addWidget(form)
    assert "7" in form.attempts_line.text()
    assert form.forget_btn.isEnabled()
