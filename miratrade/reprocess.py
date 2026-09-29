"""Run the event rules again over data that is already downloaded, without touching the network.

Changing what counts as an event — a larger minimum purchase, executives only, no 10b5-1 plans — is
a change to the *rules*, not to the data. The filings do not change once they are filed. Until now
the only way to see the effect of such a change was :func:`miratrade.scan.run_scan`, which downloads
first and reasons afterwards, so retuning a threshold meant asking the SEC for the same two months
of Form 4s all over again: minutes of waiting, and a request to a public service that had already
answered it.

This module is the second half of that scan on its own. It reads the raw filings, bars, chains and
volumes from the market database, runs exactly the same pipeline — ``build_panel``, then
``recent_events``, then ``describe`` — and writes the events back. The same ``Config`` in gives the
same events out; a different ``Config`` gives the events that config would have found, over the
whole history, in seconds.

**It never downloads.** Not as an implementation detail but as the point: it is what makes a
parameter something you can try. A test asserts that no HTTP request is made.

What it cannot do is invent data that was never fetched. Reprocessing five years of insider buys
needs five years of insider buys in the store; a condition on option flow stays False on every day
no chain was captured, and that is a missing answer, not a negative one — :func:`sources` reports
what it found so the caller can say which conditions had anything to read.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Callable

import pandas as pd

from miratrade.config import Config

# The bars before the window that the indicators need: a 200-day average on the first day of the
# window, plus the year of chart the screens draw. The same figure `run_scan` uses.
WARMUP_DAYS = 400
FLOW_KEY = ["date", "ticker", "expiry", "type", "strike"]


def span(db, table: str = "insiders", column: str = "filing_date") -> tuple[date | None, date | None]:
    """The first and last day ``table`` holds, or ``(None, None)`` when it is empty.

    Used to default the window to "everything stored", which is what reprocessing is usually for.
    """
    row = db.execute(f"SELECT min({column}) AS a, max({column}) AS b FROM {table}").fetchone()
    if row is None or not row["a"]:
        return None, None
    return date.fromisoformat(row["a"][:10]), date.fromisoformat(row["b"][:10])


def window(db, days: int | None = None, end: date | None = None,
           cfg: Config = Config()) -> tuple[date, date, date]:
    """``(first_filing, since, end)`` for a reprocess.

    ``end`` defaults to the last filing in the store rather than today, so "the last 30 days" means
    the last 30 days that were **downloaded**. Asking for today when nothing has been fetched this
    week would otherwise report an empty window as though nothing had happened.
    """
    first_stored, last_stored = span(db)
    end = end or last_stored or date.today()
    look = max(cfg.insider.lookback_days, cfg.smart.lookback_days)
    if days is None:
        since = first_stored + timedelta(days=look) if first_stored else end
        # everything stored, minus the warm-up at the start that has no history behind it
        since = min(since, end)
    else:
        since = end - timedelta(days=days)
    return since - timedelta(days=look), since, end


def _between(db, table: str, column: str, first: date, last: date) -> pd.DataFrame:
    from miratrade import store

    return store.read(db, table, f"{column} >= ? AND {column} <= ?",
                      (first.isoformat(), last.isoformat()))


def flow_between(db, first: date, last: date) -> pd.DataFrame:
    """Option chains from the store as the flow pipeline expects them, one row per contract-day.

    The primary key holds ``source``, so the same contract can be there twice: once from a broker
    snapshot and once from a scan's CSV. Those are two records of one thing, and counting both
    would double the day's volume — exactly the number ``unusual_prints`` judges on. The row that
    carries a quote wins, because it is the one a liquidity check can use.
    """
    from miratrade.data.options import FLOW_COLUMNS

    df = _between(db, "option_flow", "date", first, last)
    if not len(df):
        return pd.DataFrame(columns=FLOW_COLUMNS)
    quoted = df["bid"].notna() & df["ask"].notna() if {"bid", "ask"} <= set(df.columns) else False
    df = df.assign(_quoted=quoted).sort_values([*FLOW_KEY, "_quoted"])
    df = df.drop_duplicates(FLOW_KEY, keep="last").drop(columns="_quoted")
    for missing in (c for c in FLOW_COLUMNS if c not in df.columns):
        df[missing] = None
    return df[FLOW_COLUMNS].reset_index(drop=True)


def sources(db, first: date, end: date, cfg: Config = Config()) -> dict:
    """Every raw frame the pipeline needs, read from the store for ``[first, end]``.

    ``insiders`` comes back **cleaned**, the same way a scan cleans it before reasoning on it: the
    table holds filings as filed, placeholder tickers and price/total typos included, so anything
    that totals or compares has to filter first.
    """
    from miratrade import store
    from miratrade.data.sec import clean_insiders

    raw = _between(db, "insiders", "filing_date", first, end)
    insiders, _stats = clean_insiders(raw) if len(raw) else (raw, {})
    return {"insiders": insiders,
            "ownership": _between(db, "ownership", "filing_date", first, end),
            "flow": flow_between(db, first, end),
            "short_volume": _between(db, "short_volume", "date", first, end),
            # shares outstanding are point-in-time by filing date and a company files them a few
            # times a year, so the window would throw away the figure in force. All of them.
            "shares": store.read(db, "shares_outstanding")}


def candidates(src: dict, since: date, cfg: Config = Config()) -> set[str]:
    """The companies with something fresh in the window: the only ones worth pricing.

    The same three ways a scan finds them — a new purchase over the minimum, a new active 13D/G,
    a day of unusual option volume — so that reprocessing and scanning agree on the universe.
    """
    insiders, ownership, flow = src["insiders"], src["ownership"], src["flow"]
    tickers: set[str] = set()
    if len(insiders):
        fresh = insiders[(insiders["code"] == "P")
                         & (insiders["value"] >= cfg.insider.min_value_usd)
                         & (pd.to_datetime(insiders["filing_date"]).dt.date >= since)]
        tickers |= set(fresh["ticker"].dropna())
    if len(ownership):
        active = ownership[(pd.to_datetime(ownership["filing_date"]).dt.date >= since)
                           & ~ownership["amendment"].astype(bool)
                           & ~ownership["passive"].astype(bool)]
        tickers |= set(active["ticker"].dropna())
    if len(flow):
        from miratrade.signals.options_flow import unusual_prints

        u = unusual_prints(flow, cfg.flow)
        if len(u) and "date" in u:
            tickers |= set(u.loc[pd.to_datetime(u["date"]).dt.date >= since, "ticker"].dropna())
    return {str(t).upper() for t in tickers if str(t).strip()}


def earnings_for(db, prices: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
    """Days until the next announcement, per ticker, aligned to that ticker's bars.

    Empty when no calendar has been fetched: ``build_panel`` then leaves the feature out entirely
    rather than filling it with zeros, so a condition on it cannot fire on missing data.
    """
    from miratrade.data.earnings import covered_tickers, days_to_earnings

    if not covered_tickers(db):
        return {}
    return {t: days_to_earnings(db, t, bars.index) for t, bars in prices.items() if len(bars)}


def reprocess(db=None, days: int | None = None, end: date | None = None, cfg: Config = Config(),
              cap_tier: str | None = None, log: Callable[[str], None] = print,
              write: bool = True) -> dict:
    """Rebuild the ``events`` table from what is already stored, under ``cfg``.

    Returns ``{"events", "since", "end", "tickers", "replaced", "written", "have"}``. With
    ``write=False`` nothing is saved, which is how a parameter form can show what a change would
    find before anybody commits to it. ``db`` defaults to the shared market database.
    """
    from miratrade import store

    owned, db = db is None, db if db is not None else store.connect()
    try:
        return _reprocess(db, days, end, cfg, cap_tier, log, write)
    finally:
        if owned:
            db.close()


def _reprocess(db, days, end, cfg, cap_tier, log, write) -> dict:
    from miratrade import store
    from miratrade.backtest import build_panel
    from miratrade.messages import note
    from miratrade.scan import describe, recent_events

    first, since, end = window(db, days, end, cfg)
    log(f"Reprocessing events from {since} to {end} out of the store, with filings back to {first}. "
        f"Nothing is downloaded.")
    src = sources(db, first, end, cfg)
    have = {name: len(df) for name, df in src.items()}
    log("  " + ", ".join(f"{n:,} {name}" for name, n in have.items()))

    tickers = candidates(src, since, cfg)
    tier = cap_tier if cap_tier is not None else cfg.data.cap_tier
    if tier != "all" and tickers:
        from miratrade.data.fundamentals import cap_from_filings, filter_by_tier, tier_report

        tickers, stats = filter_by_tier(tickers, cap_from_filings(src["insiders"], src["shares"]),
                                        tier)
        log("  " + tier_report(stats, tier))
    prices = store.prices(db, tickers | {"SPY"}, since - timedelta(days=WARMUP_DAYS), end)
    thin = sorted(tickers - set(prices))
    if thin:
        # Not a failure: a company whose bars were never downloaded simply cannot be judged, and
        # saying so is better than an event list that is quietly short.
        log(f"  {len(thin)} companies have no price bars stored and were skipped"
            f"{': ' + ', '.join(thin[:8]) if len(thin) <= 8 else ''}")
    log(f"  {len(prices)} companies with bars; building the panel …")

    panel = build_panel(prices, src["insiders"], src["flow"], cfg, ownership=src["ownership"],
                        short_volume=src["short_volume"], shares=src["shares"],
                        earnings=earnings_for(db, prices) or None)
    events = recent_events({t: p for t, p in panel.items() if t != "SPY"}, pd.Timestamp(since))
    if len(events):
        parts = [describe(e, src["insiders"], src["ownership"], pd.Timestamp(since),
                          cfg.insider.min_value_usd)
                 for e in events.to_dict("records")]
        events["what"] = [note(p) for p in parts]
        events["what_parts"] = [json.dumps(p) for p in parts]
    log(f"{len(events)} events under these settings.")

    out = {"events": events, "since": since, "end": end, "tickers": sorted(tickers), "have": have,
           "replaced": 0, "written": 0}
    if write:
        out["replaced"], out["written"] = replace_events(db, events, since, end)
        log(f"  {out['written']} written, {out['replaced']} older ones in the window removed.")
    return out


def replace_events(db, events: pd.DataFrame, since: date, end: date) -> tuple[int, int]:
    """Swap the events of a window for a freshly computed set, in one transaction.

    The old rows are **deleted**, not merged over. A stricter rule finds fewer events, and an
    upsert would leave the ones it no longer finds sitting in the table looking current — the
    screen would show a signal the settings say is not a signal.
    """
    from miratrade import store
    from miratrade.scan import events_to_rows

    rows = events_to_rows(events)
    with db:
        cursor = db.execute("DELETE FROM events WHERE signal_date >= ? AND signal_date <= ?",
                            (since.isoformat(), end.isoformat()))
        replaced = cursor.rowcount or 0
    written = store.write(db, "events", rows)
    store.mark_covered(db, "events", pd.bdate_range(since, end).date, rows=written)
    return replaced, written
