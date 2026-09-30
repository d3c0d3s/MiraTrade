"""The HTTP API: everything the screens read, over the network.

It exists for one reason — away from the computer, there is no app — so it serves exactly what the
desktop screens serve: the collected rows, the events, the price bars, the finished reports, the
settings and how stale the data is. The same functions, not a second implementation of them, which
is what keeps the two front-ends from drifting.

Three rules, and the first two are enforced by tests rather than by intention:

* **It never sends an order.** Not a missing feature: a deliberate absence. Broker credentials and
  the decision to trade stay with the person, on their own machine.
* **No read ever fetches.** A page refresh from a phone must never become a request to the SEC.
  Downloading happens when a person asks for it, as a job with a state you can look at
  (:mod:`miratrade.jobs`) — which is the honest form of that rule once the web has to replace the
  desktop app rather than accompany it.
* **It verifies who Access says you are, and refuses to be reachable without it.** Cloudflare
  Access decides identity against whatever provider sits behind it — Entra, AD FS, Authentik; this
  neither knows nor cares — and signs that decision. :mod:`miratrade.web.access` verifies the
  signature. It never invents a login of its own, which really would be worse than none, and the
  server will not listen on anything but loopback unless Access is configured. A 375 MB database
  served to a whole network because somebody typed a ``--host`` is the accident that prevents.

Writes go through the core's own functions, so the validation that protects the desktop protects
this: settings through :mod:`miratrade.prefs`, paper trades through :mod:`miratrade.practice`, jobs
through :mod:`miratrade.jobs`. One thing is deliberately missing from all of it — the ``broker``
section, which holds ``live_trading``. A front-end that cannot send an order must not be able to
switch on the thing that can.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from miratrade import attempts, card, freshness, i18n, jobs, params, prefs, scanner, store
from miratrade.web import access
from miratrade.config import CAP_TIERS, REPORTS_DIR
from miratrade.scan import EVENT_KINDS, count_events, load_events, stored_days

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


class StartJob(BaseModel):
    kind: str = Field(description="download | search | analysis")
    days: int = Field(30, ge=1, le=3650)
    cap: str = "all"


class OpenTrade(BaseModel):
    """A paper position. No real money and no broker: see docs/ALCANCE.md."""
    ticker: str
    signal_date: str | None = None
    variant: str = "call45_40"
    note: str = ""


class CloseTrade(BaseModel):
    price: float | None = Field(None, description="omit to use the last stored price")


class Listing(BaseModel):
    """A page of rows, and how many there were before the limit."""
    rows: list[dict]
    total: int
    shown: int


# --------------------------------------------------------------------------- the app

def create_app(db_path: Path | None = None, reports_dir: Path | None = None,
               verifier=None) -> FastAPI:
    """The API. ``db_path`` and ``reports_dir`` exist so a test can point it at a tmp store.

    ``verifier`` is a :class:`miratrade.web.access.Verifier` when this deployment sits behind
    Cloudflare Access. ``None`` means loopback only, which :func:`serve` enforces.
    """
    reports_root = Path(reports_dir or REPORTS_DIR)

    app = FastAPI(
        title="MiraTrade",
        summary="Read the collected market data, the events and the finished analyses.",
        description="This API never places an order, and no read ever fetches. Identity comes "
                    "from Cloudflare Access and is verified here; without it the server listens "
                    "on loopback only.",
        version="0.1.0",
    )

    if verifier is not None:
        @app.middleware("http")
        async def only_through_access(request, call_next):
            """Every path, including the page itself. A token on the API and none on the HTML
            would hand the whole interface to anyone who asked for it."""
            from fastapi.responses import JSONResponse

            from miratrade.web.access import NotAllowed

            try:
                request.state.who = verifier.who(request.headers.get(access.HEADER, ""))
            except NotAllowed as refusal:
                # One refusal for every cause. Saying which check failed tells a caller how to get
                # closer to passing it.
                return JSONResponse({"detail": str(refusal)}, status_code=403)
            return await call_next(request)

    def speaking(db):
        """The interface language, from the settings, so the API answers in it.

        The catalogue lives in the core now (`miratrade/i18n.py`) rather than in the desktop
        package. It moved the moment the web became a replacement rather than a companion: the web
        cannot import from `app/`, and a second copy of the Spanish would have drifted from the
        first inside a week.
        """
        try:
            cfg, _ = prefs.read(db)
            i18n.set_language(cfg.ui.language)
        except Exception:
            pass
        return i18n.t

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
        say = speaking(db)
        state = freshness.check(db)
        return Health(schema_version=store.version(db), counts=store.counts(db),
                      fresh=state.say(say), stale=state.stale, behind=state.behind,
                      last_download=state.last.isoformat() if state.last else None,
                      events=state.rows, days_stored=stored_days(db))

    @app.get("/api/honesty")
    def honesty(db=Depends(reading)) -> dict:
        """The one sentence that goes beside every suggestion, read from the latest report.

        Served as its own endpoint so a front-end cannot forget it: there is no screen in this
        product where suggestions appear without it.
        """
        from miratrade.report import honesty_line

        return {"line": honesty_line(reports_root, translate=speaking(db))}

    # ------------------------------------------------------------------ the Scanner

    @app.get("/api/sources")
    def sources(db=Depends(reading)) -> list[dict]:
        """The six things that were collected, with how much of each and the days they cover."""
        say = speaking(db)
        out = []
        for source in scanner.SOURCES:
            out.append({"key": source.key, "label": say(source.label),
                        "filters": list(source.filters),
                        # `label` is the column's name in the frame the Scanner returns, and its
                        # heading. `sql` stays here: it is how the row is produced, not what a
                        # front-end should know or be able to influence.
                        # `name` is the column in the frame; `label` is what a person reads.
                        # They were the same string until this API had to answer in Spanish.
                        "columns": [{"name": c.label, "label": say(c.label), "kind": c.kind}
                                    for c in source.columns]})
        return out

    @app.get("/api/summary")
    def summary(db=Depends(reading)) -> list[dict]:
        say = speaking(db)
        return [{"label": say(label), "rows": n, "first": a, "last": b}
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
        # The stored `what` is English. It was written alongside `what_parts` — the template and
        # its values — precisely so a sentence saved months ago can still be read in another
        # language today, and the list is where most people read it.
        if len(found):
            say = speaking(db)
            found = found.assign(what=[card.what_of(r, say) for r in found.to_dict("records")])
        # counted separately, before the limit: a caller has to be able to tell "50 of 444" from
        # "50 of 50", and returning the page size as the total makes those look identical.
        total = count_events(db, days=days, cap_tier=cap_tier, kinds=wanted or None, ticker=ticker)
        return Listing(rows=rows(found), total=total, shown=len(found))

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
    def reports(db=Depends(reading)) -> list[dict]:
        from miratrade.report import list_reports

        return [{"name": r.name, "path": str(r.path), "start": r.start, "end": r.end,
                 "trades": r.trades, "validated": r.validated, "wf_confirmed": r.wf_confirmed,
                 "summary": r.summary, "modified": r.modified.isoformat()}
                for r in list_reports(reports_root, translate=speaking(db))]

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
        say = speaking(db)

        def describe(groups):
            return [{"title": say(g.title), "note": say(g.note),
                     "fields": [{"section": f.section, "key": f.key, "label": say(f.label),
                                 "help": say(f.help), "kind": f.kind, "low": f.low, "high": f.high,
                                 "step": f.step, "decimals": f.decimals, "suffix": say(f.suffix),
                                 "choices": [{"value": v, "label": say(lb)} for v, lb in f.choices],
                                 "value": _plain(getattr(getattr(cfg, f.section), f.key)),
                                 "default": _plain(f.default()),
                                 "changed": (f.section, f.key) in touched}
                                for f in g.fields]} for g in groups]

        # Two lists, apart on purpose. The rules are hypotheses about the market, and every change
        # to one is another test — which is what the count underneath is for. How the thing runs is
        # not a claim about anything.
        return {"rules": describe(params.ALL_GROUPS),
                "operation": describe(params.OPERATION_GROUPS),
                "ignored": unknown,
                "attempts": attempts.count(db, "search"),
                "multiple_testing": attempts.say(attempts.count(db, "search"), say)}

    @app.put("/api/settings")
    def write_setting(change: Setting, db=Depends(writing)) -> dict:
        """Change one setting. The only write this API allows.

        Through :mod:`miratrade.prefs`, so an unknown section or a misspelt key is refused here the
        same way it is refused on the desktop — a typo must never be able to quietly disable a limit.
        """
        if change.section not in params.offered():
            # Not "unknown" — refused. `broker` is a real section that the desktop can change and
            # this cannot, because it holds `live_trading`. Saying so plainly beats a 404 that
            # looks like a bug and invites somebody to route around it.
            raise HTTPException(400, f"{change.section!r} cannot be changed from here. The broker "
                                     f"settings, including live trading, stay on the machine where "
                                     f"the credentials are.")
        try:
            prefs.put(db, change.section, change.key, change.value)
        except KeyError as e:
            raise HTTPException(400, str(e)) from e
        cfg, _ = prefs.read(db)
        return {"section": change.section, "key": change.key,
                "value": _plain(getattr(getattr(cfg, change.section), change.key))}

    # ------------------------------------------------------------------ the long things

    @app.get("/api/jobs")
    def list_jobs() -> dict:
        """What is running and what just ran. ``fetches`` says which of them touches a network."""
        running = jobs.RUNNER.current()
        return {"running": running.state() if running else None,
                "recent": [j.state() for j in jobs.RUNNER.recent()]}

    @app.get("/api/jobs/{job_id}")
    def one_job(job_id: str) -> dict:
        job = jobs.RUNNER.get(job_id)
        if job is None:
            raise HTTPException(404, f"No job {job_id!r}. They are kept for a while, not for ever.")
        return job.state()

    @app.post("/api/jobs")
    def start_job(request: StartJob) -> dict:
        """Start a download, a search or a backtest.

        The only path in the API that can reach a network, it only ever does so because a person
        asked, and ``GET /api/jobs`` shows what it is doing while it does it.
        """
        if request.kind not in jobs.KINDS:
            raise HTTPException(400, f"No job called {request.kind!r}: {', '.join(jobs.KINDS)}")
        extra = {}
        if request.kind == "analysis":
            extra["out"] = reports_root / f"{datetime.now():%Y%m%d-%H%M}-{request.days}d"
        try:
            job = jobs.RUNNER.start(request.kind, days=request.days, cap=request.cap, **extra)
        except RuntimeError as e:               # one at a time: two scans is a lock fight
            raise HTTPException(409, str(e)) from e
        return job.state()

    @app.delete("/api/jobs/{job_id}")
    def cancel_job(job_id: str) -> dict:
        if not jobs.RUNNER.cancel(job_id):
            raise HTTPException(404, f"No job {job_id!r} is running.")
        return {"cancelled": job_id}

    # ------------------------------------------------------------------ the paper journal

    def last_prices(db, tickers) -> dict:
        if not tickers:
            return {}
        return {t: float(bars["close"].iloc[-1])
                for t, bars in store.prices(db, sorted(tickers)).items() if len(bars)}

    def card_for(db, ticker: str, signal_date: str | None, variant: str, cfg):
        from miratrade.report import honesty_line, latest_report_frames

        ticker = ticker.upper()
        found = load_events(db, ticker=ticker, limit=50)
        if signal_date:
            found = found[found["signal_date"].astype(str).str.startswith(signal_date)]
        event = found.iloc[0].to_dict() if len(found) else {"ticker": ticker}
        bars = store.prices(db, [ticker]).get(ticker)
        history, rules = latest_report_frames(reports_root)
        say = speaking(db)
        return card.build(event, bars, db=db, cfg=cfg, variant=variant, history=history,
                          rules=rules, honesty=honesty_line(reports_root, translate=say),
                          translate=say)

    @app.get("/api/practice")
    def practice(db=Depends(reading)) -> dict:
        """The paper trades, marked against the last stored price. No real money, ever."""
        from miratrade.practice import PRACTICE_PATH, account_equity, load, mark, summary

        cfg, _ = prefs.read(db)
        trades = load(PRACTICE_PATH)
        mark(trades, last_prices(db, {t.ticker for t in trades}), cfg=cfg)
        # never consults a broker: `size_on_balance` is off by default and a test holds it there
        equity, source = account_equity(None, cfg=cfg)
        return {"equity": equity, "equity_source": source,
                "summary": {k: _plain(v) for k, v in summary(trades, equity).items()},
                "trades": [{k: _plain(v) for k, v in vars(t).items()} for t in trades],
                "note": "No real money. A call is valued from the stock, not from a quote."}

    @app.post("/api/practice")
    def open_paper_trade(request: OpenTrade, db=Depends(reading)) -> dict:
        """Open the contract a profile would buy, as a paper position sized by the risk settings."""
        from miratrade.practice import PRACTICE_PATH, account_equity, load, open_trade, save

        cfg, _ = prefs.read(db)
        built = card_for(db, request.ticker, request.signal_date, request.variant, cfg)
        if built.contract is None:
            raise HTTPException(400, built.contract_note or "No contract for this event.")
        trades = load(PRACTICE_PATH)
        equity, _source = account_equity(None, cfg=cfg)
        c = built.contract
        try:
            trade = open_trade(trades, ticker=built.ticker, kind="call", entry=c["premium"],
                               stop=c["stop"], target=c["target"], equity=equity,
                               note=(request.note or built.what)[:120], strike=c["strike"],
                               expiry=str(c["expiry"]), iv=c["iv"], cfg=cfg)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        save(trades, PRACTICE_PATH)
        return {k: _plain(v) for k, v in vars(trade).items()}

    @app.post("/api/practice/{trade_id}/close")
    def close_paper_trade(trade_id: str, request: CloseTrade, db=Depends(reading)) -> dict:
        from miratrade.practice import PRACTICE_PATH, close_trade, load, option_value, save

        cfg, _ = prefs.read(db)
        trades = load(PRACTICE_PATH)
        trade = next((t for t in trades if t.id == trade_id), None)
        if trade is None:
            raise HTTPException(404, f"No paper trade {trade_id!r}.")
        if trade.status != "open":
            raise HTTPException(400, f"That one is already {trade.status}.")
        price = request.price
        if price is None:
            last = last_prices(db, {trade.ticker}).get(trade.ticker)
            if last is None:
                raise HTTPException(400, "No stored price for it; download data or pass a price.")
            price = option_value(trade, last, date.today(), cfg) if trade.kind == "call" else last
        close_trade(trade, float(price), reason="manual")
        save(trades, PRACTICE_PATH)
        return {k: _plain(v) for k, v in vars(trade).items()}

    # ------------------------------------------------------------------ one event in full

    @app.get("/api/signal/{ticker}")
    def signal(ticker: str, signal_date: str | None = None, variant: str = "call45_40",
               db=Depends(reading)) -> dict:
        """What was filed, what similar events did, the contract, and the reasons not to take it."""
        cfg, _ = prefs.read(db)
        built = card_for(db, ticker, signal_date, variant, cfg)
        if not built.signal_date:
            raise HTTPException(404, f"No stored event for {ticker.upper()}.")
        return built.as_dict()

    # ------------------------------------------------------------------ the page itself

    # Mounted last, so every /api route wins and the page is what is left. It is plain HTML, CSS and
    # JavaScript with no build step: the thing it has to do is read this API and draw it, and a
    # toolchain to maintain would be a second thing that can break between you and your data.
    class Fresh(StaticFiles):
        """Served with no caching, on purpose.

        These three files are a few kilobytes and they change whenever the app does. A browser
        holding on to yesterday's JavaScript means somebody updates MiraTrade and keeps running the
        old one — silently, with no symptom except behaviour that stopped matching the code. That
        cost is far larger than re-sending 20 KB.
        """

        def is_not_modified(self, *args, **kwargs) -> bool:
            return False

        async def get_response(self, path, scope):
            answer = await super().get_response(path, scope)
            answer.headers["Cache-Control"] = "no-store, must-revalidate"
            return answer

    static = Path(__file__).parent / "static"

    @app.get("/", include_in_schema=False)
    def page():
        """The page, with its script and stylesheet stamped by their own modification time.

        `no-store` fixes the future; it does nothing about a copy a browser cached before the
        header existed, and that copy can outlive several updates with no symptom except behaviour
        that stopped matching the code. A URL that changes when the file changes cannot be stale,
        whatever any browser decided earlier.
        """
        from fastapi.responses import HTMLResponse

        index = static / "index.html"
        if not index.is_file():
            raise HTTPException(404, "The web page is not installed.")
        html = index.read_text(encoding="utf-8")
        for name in ("app.css", "app.js"):
            stamp = int((static / name).stat().st_mtime) if (static / name).is_file() else 0
            html = html.replace(f'"{name}"', f'"{name}?v={stamp}"')
        return HTMLResponse(html, headers={"Cache-Control": "no-store, must-revalidate"})

    if static.is_dir():
        app.mount("/", Fresh(directory=static, html=True), name="web")

    return app


def serve(host: str = "127.0.0.1", port: int = 8787, db_path: Path | None = None,
          reports_dir: Path | None = None, log: Callable[[str], None] = print,
          settings=None) -> None:
    """Run it, refusing to be reachable off this machine without Cloudflare Access.

    That refusal is the point. A warning in a log does not prevent the accident — it scrolls past
    at three in the morning and the thing keeps serving.
    """
    import uvicorn

    settings = settings if settings is not None else access.Settings.from_env()
    verifier = None
    if access.required_for(host):
        if not settings.configured:
            raise SystemExit(
                f"Refusing to listen on {host} without Cloudflare Access.\n"
                f"  Set MIRATRADE_ACCESS_TEAM (your team name) and MIRATRADE_ACCESS_AUD (the\n"
                f"  application's Audience tag), or use --host 127.0.0.1 and reach it through a\n"
                f"  tunnel or an SSH forward.")
        verifier = access.Verifier(settings)
        log(f"  verifying Cloudflare Access tokens for team {settings.team!r}")
    else:
        log("  loopback only: reachable from this machine, and from nothing else")
    uvicorn.run(create_app(db_path, reports_dir, verifier), host=host, port=port, log_level="info")
