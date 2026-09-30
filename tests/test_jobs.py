"""Starting the long things, and watching them.

These exist because of one rule, and the tests are mostly about it: **no read ever fetches**.
Downloading happens when a person asks, as a job with a visible state. So what matters here is
which job is allowed to reach a network, that only one runs at a time, and that cancelling never
reaches for `kill`.
"""
import sys
import time
from pathlib import Path

import pytest

from miratrade import jobs


def _wait(job, seconds: float = 20.0):
    deadline = time.time() + seconds
    while job.running and time.time() < deadline:
        time.sleep(0.05)
    return job


@pytest.fixture
def runner():
    return jobs.Runner(keep=3)


# --------------------------------------------------------------------------- what each one is

def test_only_the_download_touches_a_network():
    """The distinction the whole design rests on. A search and a backtest read what is stored;
    exactly one kind goes out, and it says so on its own state."""
    assert jobs.FETCHES == {"download"}
    assert "--offline" in jobs.analysis(365, Path("out"))
    assert "reprocess" in jobs.search(30)
    assert "scan" in jobs.download(30)


def test_a_download_asks_for_every_size():
    """Company size is a view. Downloading only the tier selected today would leave a hole the day
    somebody widens the dropdown."""
    argv = jobs.download(30, cap="mega")
    assert argv[argv.index("--cap") + 1] == "mega"          # when asked
    assert jobs.download(30)[jobs.download(30).index("--cap") + 1] == "all"   # but not by default


def test_an_unknown_kind_is_refused_by_name(runner):
    with pytest.raises(KeyError, match="no job called"):
        runner.start("vibes", days=30)


# --------------------------------------------------------------------------- running them

def test_a_job_runs_captures_its_output_and_finishes(runner, monkeypatch):
    monkeypatch.setattr(jobs, "search", lambda days, cap="all":
                        ["-c", "print('hello'); print('done')"])
    job = _wait(runner.start("search", days=1))
    assert not job.running and job.code == 0
    assert list(job.log) == ["hello", "done"]
    assert job.finished_at and job.started_at <= job.finished_at


def test_a_job_never_reaches_the_real_database(runner, monkeypatch, tmp_path):
    """Patching module attributes stops at the process boundary. A jobs test once ran a real
    reprocess and rewrote a window of the user's events table; the environment variables the
    conftest sets are what actually cross it."""
    monkeypatch.setattr(jobs, "search", lambda days, cap="all":
                        ["-c", "import os; print(os.environ['MIRATRADE_DB'])"])
    job = _wait(runner.start("search", days=1))
    assert str(tmp_path) in job.log[-1]


def test_only_one_at_a_time(runner, monkeypatch):
    """All three write to the same database. Two scans at once is not twice as fast; it is one
    scan and a lock fight."""
    monkeypatch.setattr(jobs, "search", lambda days, cap="all": ["-c", "import time; time.sleep(3)"])
    first = runner.start("search", days=1)
    try:
        with pytest.raises(RuntimeError, match="already running"):
            runner.start("search", days=1)
        assert runner.current() is first
    finally:
        runner.cancel(first.id)
        _wait(first)


def test_cancelling_terminates_and_never_kills(runner, monkeypatch):
    """`terminate`, not `kill`. A process killed mid-checkpoint has already truncated this database
    once, from 106 MB to 24."""
    import inspect

    source = inspect.getsource(jobs)
    assert ".terminate()" in source and ".kill()" not in source

    monkeypatch.setattr(jobs, "search", lambda days, cap="all": ["-c", "import time; time.sleep(30)"])
    job = runner.start("search", days=1)
    assert runner.cancel(job.id) is True
    _wait(job)
    assert not job.running


def test_cancelling_something_that_is_not_running_says_no(runner):
    assert runner.cancel("nonexistent") is False


def test_the_log_is_captured_and_bounded(runner, monkeypatch):
    monkeypatch.setattr(jobs, "search", lambda days, cap="all":
                        ["-c", f"[print(i) for i in range({jobs.LOG_LINES + 50})]"])
    job = _wait(runner.start("search", days=1))
    assert len(job.log) == jobs.LOG_LINES                   # bounded: a long run cannot grow for ever
    assert job.log[-1] == str(jobs.LOG_LINES + 49)          # and it is the END that is kept


def test_recent_jobs_are_remembered_and_then_forgotten(runner, monkeypatch):
    monkeypatch.setattr(jobs, "search", lambda days, cap="all": ["-c", "pass"])
    made = []
    for _ in range(5):
        made.append(_wait(runner.start("search", days=1)))
    remembered = runner.recent()
    assert len(remembered) == 3                             # keep=3
    assert [j.id for j in remembered] == [j.id for j in reversed(made[-3:])]   # newest first
    assert runner.get(made[0].id) is None


def test_the_state_says_whether_it_fetched(runner, monkeypatch):
    monkeypatch.setattr(jobs, "search", lambda days, cap="all": ["-c", "pass"])
    state = _wait(runner.start("search", days=1)).state()
    assert state["fetches"] is False and state["kind"] == "search"
    assert set(state) == {"id", "kind", "running", "started_at", "finished_at", "code",
                          "fetches", "log"}
