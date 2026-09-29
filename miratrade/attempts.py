"""How many different settings have been tried, and what that does to a result.

This is the part of a parameter form that makes it honest rather than dangerous.

A form that lets somebody retune "what counts as an event" and press search again is a machine for
mining. Try enough thresholds and one of them looks good on any data at all: with 20 independent
tries, the best of them clears p < 0.05 by chance about two-thirds of the time. Nothing about the
form warns you, because each individual run looks like a single honest test — the problem lives in
the *history*, which nobody remembers and the app never wrote down.

So it writes it down. Every distinct configuration that produces a search or an analysis is one
row. Re-running the same settings is **not** a new attempt: repeating an experiment is not testing a
new hypothesis, and counting it would make the correction meaninglessly harsh. What counts is the
number of distinct settings a result was selected from.

The correction is then the honest arithmetic of that number, shown beside the count so nobody has
to recall it: Šidák for the significance a result needs, and the plain statement that looking at
many and reporting the best is not the same as testing one.

This does not stop anyone trying things — trying things is how research works. It stops the
seventeenth try being reported as though it were the first.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict
from datetime import date
from typing import Any

from miratrade.config import Config

# The sections that decide *what counts as an event or a trade*. A change to any of them is a new
# hypothesis about the market. Changing the language, the broker or how much capital to size on is
# not, however often it is changed, so those sections are deliberately left out.
TESTED_SECTIONS = ("insider", "flow", "smart", "trade", "options", "liquidity")
ALPHA = 0.05


def fingerprint(cfg: Config, sections=TESTED_SECTIONS) -> str:
    """A short, stable id for one configuration of the rules.

    Two runs with the same thresholds have the same fingerprint however they were reached, so
    changing a number and changing it back does not invent an attempt that never happened.
    """
    payload = {name: asdict(getattr(cfg, name)) for name in sections}
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def settings_of(cfg: Config, sections=TESTED_SECTIONS) -> dict[str, Any]:
    return {name: asdict(getattr(cfg, name)) for name in sections}


def record(db, cfg: Config, kind: str = "search", days: int | None = None, events: int = 0,
           note: str = "") -> tuple[int, bool]:
    """Remember that these settings were tried. Returns ``(distinct attempts, is this one new)``.

    ``kind`` separates searching from backtesting: they are different questions and neither should
    inflate the other's count.
    """
    from miratrade.store.db import now

    mark = fingerprint(cfg)
    row = db.execute("SELECT id FROM attempts WHERE kind = ? AND fingerprint = ?",
                     (kind, mark)).fetchone()
    with db:
        if row is None:
            db.execute("INSERT INTO attempts (kind, fingerprint, settings, at, last_at, runs, days, "
                       "events, note) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
                       (kind, mark, json.dumps(settings_of(cfg)), now(), now(), days, events, note))
        else:
            # A repeat, not a new hypothesis. The run count is kept because it is interesting, but
            # it does not enter the correction.
            db.execute("UPDATE attempts SET last_at = ?, runs = runs + 1, events = ?, days = ? "
                       "WHERE id = ?", (now(), events, days, row["id"]))
    return count(db, kind), row is None


def count(db, kind: str | None = None) -> int:
    """How many **distinct** configurations have been tried."""
    try:
        if kind is None:
            return int(db.execute("SELECT count(*) AS n FROM attempts").fetchone()["n"])
        return int(db.execute("SELECT count(*) AS n FROM attempts WHERE kind = ?",
                              (kind,)).fetchone()["n"])
    except Exception:                    # a database from before this table existed
        return 0


def history(db, kind: str | None = None, limit: int = 50) -> list[dict]:
    """The attempts, newest first, for a screen that shows what has been tried."""
    sql = "SELECT * FROM attempts"
    params: list = []
    if kind:
        sql += " WHERE kind = ?"
        params.append(kind)
    sql += f" ORDER BY last_at DESC LIMIT {int(limit)}"
    try:
        return [dict(r) for r in db.execute(sql, params)]
    except Exception:
        return []


def forget(db, kind: str | None = None) -> int:
    """Start the count again.

    Offered because a person genuinely does start a fresh line of research, and a counter that can
    only ever go up gets ignored. It is a deliberate act with a date on it, not a side effect.
    """
    with db:
        if kind:
            cursor = db.execute("DELETE FROM attempts WHERE kind = ?", (kind,))
        else:
            cursor = db.execute("DELETE FROM attempts")
    return cursor.rowcount or 0


# --------------------------------------------------------------------------- the arithmetic

def sidak(n: int, alpha: float = ALPHA) -> float:
    """The per-test significance that keeps the *family* at ``alpha`` over ``n`` tries.

    Šidák rather than Bonferroni: it is exact for independent tests and slightly less punishing,
    and successive tunings of a threshold are closer to independent than to perfectly correlated.
    Neither is right when the tries overlap heavily; both are far better than pretending n is 1.
    """
    n = max(1, int(n))
    return 1.0 - (1.0 - alpha) ** (1.0 / n)


def bonferroni(n: int, alpha: float = ALPHA) -> float:
    return alpha / max(1, int(n))


def z_for(p: float) -> float:
    """The two-sided normal quantile for ``p``: roughly the t a result needs with a real sample.

    An inverse normal by bisection, to avoid a dependency for one number. Accurate to well under a
    hundredth, which is far finer than the question deserves — the point is "about 2" against
    "about 3.5", not a third decimal.
    """
    target = 1.0 - p / 2.0
    low, high = 0.0, 10.0
    for _ in range(80):
        mid = (low + high) / 2.0
        if 0.5 * (1.0 + math.erf(mid / math.sqrt(2.0))) < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def luck(n: int, alpha: float = ALPHA) -> float:
    """The chance that at least one of ``n`` independent tries clears ``alpha`` by pure luck.

    This is the number that changes behaviour. "Corrected α is 0.0026" is arithmetic; "with 20
    tries, something looks significant by chance two times in three" is a fact about what you are
    holding.
    """
    return 1.0 - (1.0 - alpha) ** max(1, int(n))


def verdict(n: int, alpha: float = ALPHA) -> tuple[str, dict]:
    """One sentence for a screen, as ``(template, fields)`` so it can be translated at render time."""
    if n <= 1:
        return ("First configuration tried: a result means what it says.", {})
    return ("{count} configurations tried. A result now needs p < {alpha} to mean what p < {plain} "
            "would have meant on the first — about t = {t}. With this many tries, something clears "
            "{plain} by luck alone {chance} % of the time.",
            {"count": n, "alpha": f"{sidak(n, alpha):.4f}", "plain": f"{alpha:g}",
             "t": f"{z_for(sidak(n, alpha)):.1f}", "chance": f"{luck(n, alpha) * 100:.0f}"})


def say(n: int, translate=None, alpha: float = ALPHA) -> str:
    from miratrade.messages import sayer

    template, fields = verdict(n, alpha)
    return sayer(translate)(template, **fields)


def dated(row: dict) -> date | None:
    value = row.get("at") or ""
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
