"""The long things, started on purpose and watched while they run.

Downloading, searching and backtesting all take longer than a click, and all three have to work from
whichever front-end a person happens to be in front of. So the argument lists and the running of
them live here, in the core, rather than in the desktop package where they started — the web cannot
import from there, and a second copy of "how do you start a scan" is a second thing to get wrong.

The rule these exist to preserve:

    **No read ever fetches.** A page refresh must never become a request to the SEC. Fetching
    happens when a person asks for it, as a job, with a state you can look at.

That is the honest version of "the API never downloads" once the web has to replace the desktop
app. What it protected — that browsing cannot quietly cost somebody else's bandwidth, or your rate
budget, or ten minutes — it still protects.

One at a time, deliberately. All three write to the same database, and two scans at once is not
twice as fast; it is one scan and a lock fight.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

LOG_LINES = 300                     # enough to see what happened, bounded so a long run cannot grow


def download(days: int, cap: str = "all", save: Path | None = None) -> list[str]:
    """Fetch the last ``days`` from the SEC and friends. The only thing here that touches a network.

    ``cap`` is "all" on purpose: company size is a view, and downloading only the tier selected
    today would leave a hole the day somebody widens the dropdown.
    """
    from miratrade.config import APP_DIR

    return ["-X", "utf8", "-W", "ignore", "-m", "miratrade.cli", "scan", "--days", str(int(days)),
            "--variant", "call45_40", "--cap", cap,
            "--save", str(save or APP_DIR / "scan")]


def search(days: int, cap: str = "all") -> list[str]:
    """Re-derive the events from what is stored, under the current settings. Never downloads."""
    return ["-X", "utf8", "-W", "ignore", "-m", "miratrade.cli", "reprocess",
            "--days", str(int(days)), "--cap", cap]


def analysis(days: int, out: Path, cap: str = "all") -> list[str]:
    """Backtest what is stored. Also never downloads — that is what `--offline` buys."""
    return ["-X", "utf8", "-W", "ignore", "-m", "miratrade.cli", "analyze", "--offline",
            "--days", str(int(days)), "--out", str(out), "--cap", cap]


# Names, not the functions themselves: `start` looks them up in this module at call time, so
# a test can replace one with something harmless and have it actually take effect.
KINDS = {"download": "download", "search": "search", "analysis": "analysis"}
FETCHES = frozenset({"download"})   # the one kind that goes out to the network


@dataclass
class Job:
    """One run, and everything a screen needs to show it."""
    id: str
    kind: str
    argv: list[str]
    started_at: str
    finished_at: str | None = None
    code: int | None = None
    log: deque = field(default_factory=lambda: deque(maxlen=LOG_LINES))
    _process: object | None = field(default=None, repr=False, compare=False)

    @property
    def running(self) -> bool:
        return self.finished_at is None

    @property
    def fetches(self) -> bool:
        return self.kind in FETCHES

    def state(self) -> dict:
        return {"id": self.id, "kind": self.kind, "running": self.running,
                "started_at": self.started_at, "finished_at": self.finished_at,
                "code": self.code, "fetches": self.fetches,
                "log": list(self.log)}


class Runner:
    """Holds the jobs. One at a time, and the last few for looking at afterwards."""

    def __init__(self, keep: int = 10):
        self._jobs: dict[str, Job] = {}
        self._order: deque = deque(maxlen=keep)
        self._lock = threading.Lock()

    def current(self) -> Job | None:
        with self._lock:
            return next((j for j in self._jobs.values() if j.running), None)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def recent(self) -> list[Job]:
        return [self._jobs[i] for i in reversed(self._order) if i in self._jobs]

    def start(self, kind: str, python: str | None = None, **params) -> Job:
        """Begin one. Raises ``RuntimeError`` if something is already running."""
        if kind not in KINDS:
            raise KeyError(f"no job called {kind!r}: {', '.join(KINDS)}")
        busy = self.current()
        if busy is not None:
            raise RuntimeError(f"a {busy.kind} is already running; wait for it or cancel it")
        # Resolved from the module rather than from the dict captured at import, so a test can
        # replace `download` with something harmless and actually have it take effect.
        argv = globals()[KINDS[kind]](**params)
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, argv=argv,
                  started_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            for gone in [i for i in self._jobs if i not in self._order]:
                self._jobs.pop(gone, None)
        process = subprocess.Popen([python or sys.executable, *argv], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                   errors="replace", bufsize=1)
        job._process = process
        threading.Thread(target=self._watch, args=(job, process), daemon=True).start()
        return job

    @staticmethod
    def _watch(job: Job, process) -> None:
        try:
            for line in process.stdout:                 # type: ignore[union-attr]
                if line.strip():
                    job.log.append(line.rstrip())
        finally:
            job.code = process.wait()
            job.finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def cancel(self, job_id: str) -> bool:
        """Stop one. ``terminate``, never ``kill``: a process killed mid-checkpoint has already
        truncated this database once, from 106 MB to 24."""
        job = self._jobs.get(job_id)
        if job is None or not job.running or job._process is None:
            return False
        job._process.terminate()                        # type: ignore[union-attr]
        return True


RUNNER = Runner()
