"""The HTTP API: everything the screens read, over the network.

It exists for one reason — away from the computer, there is no app — so it serves exactly what the
desktop screens serve: the collected rows, the events, the price bars, the finished reports, the
settings and how stale the data is. The same functions, not a second implementation of them, which
is what keeps the two front-ends from drifting.

Three rules, and the first two are enforced by tests rather than by intention:

* **It never sends an order.** Not a missing feature: a deliberate absence. Broker credentials and
  the decision to trade stay with the person, on their own machine.
* **It never downloads.** Fetching is the Scanner's job on the desktop, and the scheduled task's on
  the server. An API that fetches turns a page refresh from a phone into a request to the SEC.
* **It does not authenticate, and says so.** It binds to localhost and Cloudflare Access sits in
  front of it. Writing a half-authentication here would be worse than none, because somebody would
  trust it.

Writes are limited to settings — the parameter form has to work from the web, which is the whole
reason the settings moved into the store — and they go through :mod:`miratrade.prefs`, so the same
validation that protects the desktop protects this.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from miratrade import attempts, freshness, params, prefs, scanner, store
from miratrade.config import CAP_TIERS, REPORTS_DIR
from miratrade.scan import EVENT_KINDS, load_events, stored_days

MAX_ROWS = 2000


# --------------------------------------------------------------------------- turning frames to JSON

def _plain(value: Any) -> Any:
    """One cell, as JSON can carry it.

    ``NaN`` is not JSON, and neither is a ``Timestamp``. Both arrive constantly from pandas, and a
    single one of either makes the whole response fail to serialise — usually for one row out of two
    thousand, which is a miserable thing to debug from a phone.
    """
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "item"):                    # numpy scalars
        try:
            return _plain(value.item())
        except (ValueError, AttributeError):
            pass
    return value


def rows(df: pd.DataFrame | None) -> list[dict]:
    if df is None or not len(df):
        return []
    return [{k: _plain(v) for k, v in record.items()} for record in df.to_dict("records")]


# --------------------------------------------------------------------------- what comes back

class Health(BaseModel):
    schema_version: int
    counts: dict[str, int]
    fresh: str
    stale: bool
    behind: int
    last_download: str | None
    events: int
    days_stored: int


class Setting(BaseModel):
    section: str
    key: str
    value: Any


class Listing(BaseModel):
    """A page of rows, and how many there were before the limit."""
    rows: list[dict]
    total: int
    shown: int


# --------------------------------------------------------------------------- the app

def create_app(db_path: Path | None = None, reports_dir: Path | None = None) -> FastAPI:
    """The API. ``db_path`` and ``reports_dir`` exist so a test can point it at a tmp store."""
    reports_root = Path(reports_dir or REPORTS_DIR)

    app = FastAPI(
        title="MiraTrade",
        summary="Read the collected market data, the events and the finished analyses.",
        description="This API never places an order and never downloads. It does not authenticate: "
                    "bind it to localhost and put an authenticating proxy in front.",
        version="0.1.0",
    )

    def reading():
        """A read-only connection per request, closed afterwards.

        Read-only is the file mode, not the promise: what keeps these handlers from writing is that
        they do not. The mode is a second lock on the same door, and it is cheap.
        """
        try:
            db = store.connect(db_path, read_only=True)
        except store.NoDatabase as e:
            raise HTTPException(503, f"No market database yet: {e}") from e
        try:
            yield db
        finally:
            db.close()

    def writing():
        """A writable connection, used by settings and nothing else."""
        db = store.connect(db_path)
        try:
            yield db
        finally:
            db.close()

    # ------------------------------------------------------------------ state of the data

    @app.get("/api/health", response_model=Health)
    def health(db=Depends(reading)) -> Health:
        state = freshness.check(db)
        return Health(schema_version=store.version(db), counts=store.counts(db),
                      fresh=state.say(), stale=state.stale, behind=state.behind,
                      last_download=state.last.isoformat() if state.last else None,
                      events=state.rows, days_stored=stored_days(db))

    @app.get("/api/honesty")
    def honesty() -> dict:
        """The one sentence that goes beside every suggestion, read from the latest report.

        Served as its own endpoint so a front-end cannot forget it: there is no screen in this
        product where suggestions appear without it.
        """
        from miratrade.report import honesty_line

        return {"line": honesty_line(reports_root)}

    # ------------------------------------------------------------------ the Scanner

    @app.get("/api/sources")
    def sources() -> list[dict]:
        """The six things that were collected, with how much of each and the days they cover."""
        out = []
        for source in scanner.SOURCES:
            out.append({"key": source.key, "label": source.label,
                        "filters": list(source.filters),
                        # `label` is the column's name in the frame the Scanner returns, and its
                        # heading. `sql` stays here: it is how the row is produced, not what a
                        # front-end should know or be able to influence.
                        "columns": [{"label": c.label, "kind": c.kind} for c in source.columns]})
        return out

    @app.get("/api/summary")
    def summary(db=Depends(reading)) -> list[dict]:
        return [{"label": label, "rows": n, "first": a, "last": b}
                for label, n, a, b in scanner.summary(db)]

    @app.get("/api/scanner/{source}", response_model=Listing)
    def scan_source(source: str,
                    days: int = Query(30, ge=0, le=3650),
                    ticker: str = "", text: str = "", code: str = "", role: str = "",
                    chamber: str = "", member: str = "", trade_type: str = "",
                    stake_kind: str = "", option_type: str = "",
                    min_amount: float = 0.0, min_volume: float = 0.0,
                    min_open_interest: float = 0.0,
                    exclude_plan: bool = False, exclude_passive: bool = False,
                    exclude_amendments: bool = False, new_position: bool = False,
                    limit: int = Query(MAX_ROWS, ge=1, le=MAX_ROWS),
                    db=Depends(reading)) -> Listing:
        """Rows as they were filed, narrowed in SQL.

        A source declares the filters it understands and ignores the rest, so a caller passing a
        filter that does not apply gets the unfiltered answer rather than an error — the same
        behaviour the desktop relies on, and the reason correctness never depends on the screen.
        """
        if source not in scanner.BY_KEY:
            raise HTTPException(404, f"No source called {source!r}. "
                                     f"Try one of: {', '.join(s.key for s in scanner.SOURCES)}")
        chosen = scanner.BY_KEY[source]
        f = scanner.Filters(days=days, ticker=ticker, text=text, code=code, role=role,
                            chamber=chamber, member=member, trade_type=trade_type,
                            stake_kind=stake_kind, option_type=option_type,
                            min_amount=min_amount, min_volume=min_volume,
                            min_open_interest=min_open_interest, exclude_plan=exclude_plan,
                            exclude_passive=exclude_passive,
                            exclude_amendments=exclude_amendments, new_position=new_position)
        found = scanner.run(db, chosen, f, limit)
        return Listing(rows=rows(found), total=scanner.total(db, chosen, f), shown=len(found))

    # ------------------------------------------------------------------ the events

    @app.get("/api/events", response_model=Listing)
    def events(days: int = Query(30, ge=1, le=3650),
               cap_tier: str = "all", kinds: str = "", ticker: str = "",
               limit: int = Query(500, ge=1, le=MAX_ROWS),
               db=Depends(reading)) -> Listing:
        """The events already derived, filtered. **It does not re-derive them and never downloads.**

        Company size is a view here, as it is on the desktop: the events table holds every tier, and
        narrowing happens on read. Filtering when writing as well is a bug this project has already
        made once, and it left a stored 418 events looking like 2.
        """
        if cap_tier not in CAP_TIERS:
            raise HTTPException(400, f"Unknown size {cap_tier!r}: {', '.join(CAP_TIERS)}")
        wanted = tuple(k for k in (x.strip() for x in kinds.split(",")) if k in EVENT_KINDS)
        if kinds.strip() and not wanted:
            raise HTTPException(400, f"Unknown kinds {kinds!r}: {', '.join(EVENT_KINDS)}")
        found = load_events(db, days=days, cap_tier=cap_tier, kinds=wanted or None,
                            ticker=ticker, limit=limit)
        return Listing(rows=rows(found), total=len(found), shown=len(found))

    @app.get("/api/prices/{ticker}")
    def prices(ticker: str, start: date | None = None, end: date | None = None,
               db=Depends(reading)) -> dict:
        """Daily bars for the chart, from every download ever made — not just the last one."""
        bars = store.prices(db, [ticker], start, end).get(ticker.upper())
        if bars is None or not len(bars):
            raise HTTPException(404, f"No price bars stored for {ticker.upper()}.")
        return {"ticker": ticker.upper(), "bars": rows(bars.reset_index())}

    # ------------------------------------------------------------------ the reports

    @app.get("/api/reports")
    def reports() -> list[dict]:
        from miratrade.report import list_reports

        return [{"name": r.name, "path": str(r.path), "start": r.start, "end": r.end,
                 "trades": r.trades, "validated": r.validated, "wf_confirmed": r.wf_confirmed,
                 "summary": r.summary, "modified": r.modified.isoformat()}
                for r in list_reports(reports_root)]

    @app.get("/api/reports/{name}")
    def one_report(name: str) -> dict:
        from miratrade.report import list_reports, load_report

        match = next((r for r in list_reports(reports_root) if r.name == name), None)
        if match is None:
            raise HTTPException(404, f"No report called {name!r}.")
        loaded = load_report(match.path)
        return {"name": match.name, "markdown": loaded["markdown"],
                "rules": rows(loaded["rules"]), "walk_forward": rows(loaded["walk_forward"]),
                "profiles": rows(loaded["profiles"])}

    # ------------------------------------------------------------------ the settings

    @app.get("/api/settings")
    def read_settings(db=Depends(reading)) -> dict:
        """Every setting a person can change, what it is now, and what differs from the default.

        The fields carry their own explanation, from :mod:`miratrade.params`, so the web builds the
        same form as the desktop from one description instead of two.
        """
        cfg, unknown = prefs.read(db)
        touched = prefs.changed(db)
        groups = []
        for group in params.ALL_GROUPS:
            groups.append({
                "title": group.title, "note": group.note,
                "fields": [{"section": f.section, "key": f.key, "label": f.label, "help": f.help,
                            "kind": f.kind, "low": f.low, "high": f.high, "step": f.step,
                            "decimals": f.decimals, "suffix": f.suffix,
                            "value": _plain(getattr(getattr(cfg, f.section), f.key)),
                            "default": _plain(f.default()),
                            "changed": (f.section, f.key) in touched}
                           for f in group.fields]})
        return {"groups": groups, "ignored": unknown,
                "attempts": attempts.count(db, "search"),
                "multiple_testing": attempts.say(attempts.count(db, "search"))}

    @app.put("/api/settings")
    def write_setting(change: Setting, db=Depends(writing)) -> dict:
        """Change one setting. The only write this API allows.

        Through :mod:`miratrade.prefs`, so an unknown section or a misspelt key is refused here the
        same way it is refused on the desktop — a typo must never be able to quietly disable a limit.
        """
        try:
            prefs.put(db, change.section, change.key, change.value)
        except KeyError as e:
            raise HTTPException(400, str(e)) from e
        cfg, _ = prefs.read(db)
        return {"section": change.section, "key": change.key,
                "value": _plain(getattr(getattr(cfg, change.section), change.key))}

    return app


def serve(host: str = "127.0.0.1", port: int = 8787, db_path: Path | None = None,
          reports_dir: Path | None = None, log: Callable[[str], None] = print) -> None:
    """Run it. Localhost by default, on purpose: this API has no authentication of its own."""
    import uvicorn

    if host not in ("127.0.0.1", "localhost", "::1"):
        log(f"  serving on {host}: this API does not authenticate. Put Cloudflare Access, or "
            f"another authenticating proxy, in front of it.")
    uvicorn.run(create_app(db_path, reports_dir), host=host, port=port, log_level="info")
