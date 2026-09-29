"""The unattended download: what it asks for, and when.

The whole value is in the first step. A task that wakes every half hour and re-downloads the same
fortnight is wasteful for us and abusive of a public service that already answered the question, so
these tests are mostly about what it *does not* fetch.
"""
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from miratrade import schedule, store
from miratrade.config import Config

FRIDAY = date(2026, 9, 25)


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / "market.db")
    yield conn
    conn.close()


def _covered(db, *days: str) -> None:
    store.mark_covered(db, "sec_form4", [date.fromisoformat(d) for d in days], rows=0)


def _all_covered(db, until: date = FRIDAY, max_days: int = schedule.MAX_CATCH_UP_DAYS) -> None:
    """Mark the whole horizon a plan looks at, so a test can then poke one hole in it.

    The horizon is not "since the first row": a day before anything was ever stored was also never
    asked about, and the plan says so. That is right — it just has to be set up deliberately.
    """
    first = until - timedelta(days=max_days * 2)
    store.mark_covered(db, "sec_form4", schedule.business_days(first, until), rows=0)


def _at(hhmm: str, day: date = FRIDAY) -> datetime:
    """A New York moment, as a scheduler would hand it over: aware, in local time."""
    stamp = pd.Timestamp(f"{day} {hhmm}", tz="America/New_York")
    return stamp.to_pydatetime()


# --------------------------------------------------------------------------- what to fetch

def test_a_day_already_downloaded_is_never_asked_for_again(db):
    _all_covered(db)
    what = schedule.plan(db, now=_at("14:00"))
    assert not what.needed
    assert "Nothing to download" in what.say()


def test_a_day_with_nothing_in_it_still_counts_as_downloaded(db):
    """Exactly why coverage records the days *asked about* rather than the rows returned. Without
    it a quiet Tuesday is re-downloaded for ever."""
    store.mark_covered(db, "sec_form4", [FRIDAY], rows=0)      # asked, found nothing
    what = schedule.plan(db, now=_at("14:00"))
    assert FRIDAY not in what.days                             # …and 0 rows is still an answer


def test_only_the_gap_is_asked_for(db):
    _all_covered(db, until=date(2026, 9, 18))
    what = schedule.plan(db, now=_at("14:00"))
    assert what.days == [date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23),
                         date(2026, 9, 24), date(2026, 9, 25)]
    assert what.last == date(2026, 9, 18)


def test_a_day_before_anything_was_stored_was_also_never_asked_about(db):
    """It reads as a gap because it is one. A first run therefore fetches the whole horizon once,
    and after that only the day that has just happened."""
    _covered(db, "2026-09-24", "2026-09-25")
    what = schedule.plan(db, now=_at("14:00"))
    assert what.needed and max(what.days) < date(2026, 9, 24)


def test_a_hole_in_the_middle_is_filled(db):
    """"Everything since the last download" would never fetch a day the machine was off for while
    later days were fetched — the gap would sit there for ever, invisible."""
    _all_covered(db)
    db.execute("DELETE FROM coverage WHERE source = 'sec_form4' AND day = '2026-09-10'")
    db.commit()
    what = schedule.plan(db, now=_at("14:00"))
    assert what.days == [date(2026, 9, 10)]


def test_the_weekend_is_not_a_gap(db):
    _all_covered(db)
    sunday = date(2026, 9, 27)
    assert not schedule.plan(db, now=_at("14:00", sunday)).needed


def test_a_catch_up_is_bounded(db):
    """A machine off for a month should fetch the month, not five years. Five years is a deliberate
    act with a progress bar, not something a background task decides on at 23:00."""
    what = schedule.plan(db, now=_at("14:00"), max_days=5)
    assert what.capped and len(what.days) == 5
    assert what.days[-1] == FRIDAY                   # the most recent ones, not the oldest


def test_nothing_is_fetched_when_nothing_is_missing(db):
    """The point of the whole module: a task waking every half hour must cost nothing when there is
    nothing to get."""
    _all_covered(db)
    calls = []
    out = schedule.run(db, schedule.plan(db, now=_at("14:00")), log=lambda _m: None,
                       fetch={"insiders": lambda *a: calls.append(1)})
    assert out["skipped"] and calls == []


# --------------------------------------------------------------------------- when to run

def test_it_runs_while_new_york_is_filing(db):
    cfg = Config()
    cfg.data.auto_refresh_from, cfg.data.auto_refresh_to = "09:00", "22:30"
    assert schedule.due(_at("14:00"), cfg) == "market open"
    assert schedule.due(_at("04:00"), cfg) is None


def test_the_evening_run_is_the_safety_net(db):
    """The daytime runs can all be missed — asleep, offline, computer off. This one asks for
    whatever they missed, and fires once however often the scheduler wakes up after 23:00."""
    cfg = Config()
    assert schedule.due(_at("23:05"), cfg) == "evening catch-up"
    assert schedule.due(_at("23:40"), cfg, last_evening=FRIDAY) is None


def test_the_weekend_gets_no_evening_run(db):
    cfg = Config()
    cfg.data.auto_refresh_weekdays_only = True
    assert schedule.due(_at("23:05", date(2026, 9, 26)), cfg) is None      # Saturday


def test_a_naive_clock_is_read_as_utc_rather_than_guessed(db):
    """A scheduler hands over whatever the machine's clock says. Guessing a zone would make the
    window mean something different on a laptop that travels."""
    cfg = Config()
    assert schedule.due(datetime(2026, 9, 25, 18, 0), cfg) is not None


# --------------------------------------------------------------------------- installing it

def test_the_commands_are_runnable_windows_as_printed():
    """A quoting mistake here fails at 23:00 with nobody watching, which is the worst place for one."""
    market, evening = schedule.schtasks_commands(r"C:\Program Files\Python\python.exe", 45)
    for command in (market, evening):
        assert command.startswith("schtasks /Create")
        assert r'\"C:\Program Files\Python\python.exe\"' in command   # escaped for cmd.exe
        assert "'" not in command                                     # never single quotes
        assert "miratrade.cli schedule run" in command
    assert "/MO 45" in market and "/ST 23:00" in evening


def test_nothing_is_installed_by_calling_it():
    """It prints. A program that quietly registers itself with the system scheduler is doing
    something its user did not watch it do."""
    import inspect

    source = inspect.getsource(schedule)
    assert "subprocess" not in source and "os.system" not in source
