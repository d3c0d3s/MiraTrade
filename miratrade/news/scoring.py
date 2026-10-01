"""Fetch the body of a filing, score it, store the score — and nothing else.

The text is not kept. EDGAR's copy is free to fetch again and the HTTP cache keeps it anyway;
re-scoring three thousand documents is minutes of CPU. So the expensive half is stored and the
cheap half is not, which is the opposite of what feels natural and the right way round.

Each row records **which settings produced it**. A sentiment score read months later under
different thresholds is a number whose meaning nobody can reconstruct, and re-scoring without
noticing the settings changed is how a study quietly compares two different experiments.

What this does **not** do is decide anything. The scores sit beside events. Whether they mean
anything is :mod:`miratrade.news.study`'s question, and the answer there so far has been no.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Callable, Iterable

import pandas as pd

from miratrade.config import Config
from miratrade.news import filings
from miratrade.news.sentiment import Sentiment, Unavailable

WINDOW = 45          # days before a day that a filing still counts towards it


def wanted(db, window: int = WINDOW, include_placebos: bool = True,
           seed: int = 7) -> pd.DataFrame:
    """The filings a study would need: those near an event, and those near its placebo days.

    Both sides, always. Scoring only the event side and comparing against nothing is how the 8-K
    work went wrong the first time — a rate with nothing to measure against can only agree with
    itself.
    """
    near_events = pd.read_sql_query(
        """SELECT DISTINCT f.accession, f.cik, f.document, f.ticker, f.filing_date
           FROM filings f JOIN events e ON f.ticker = e.ticker
           WHERE f.item NOT IN ('9.01','5.07')
             AND f.cik IS NOT NULL AND f.document IS NOT NULL
             AND f.filing_date <= e.signal_date
             AND f.filing_date > date(e.signal_date, '-' || ? || ' day')""",
        db, params=[window])
    if not include_placebos:
        return near_events

    from miratrade.news.study import build_sample

    sample = build_sample(db, seed=seed)
    if sample.placebos.empty:
        return near_events
    days = sample.placebos.assign(day=lambda d: d["signal_date"].dt.strftime("%Y-%m-%d"))
    table = pd.read_sql_query(
        """SELECT accession, cik, document, ticker, filing_date FROM filings
           WHERE item NOT IN ('9.01','5.07') AND cik IS NOT NULL AND document IS NOT NULL""", db)
    table["filing_date"] = pd.to_datetime(table["filing_date"])
    by_ticker = {t: g for t, g in table.groupby("ticker")}
    rows = []
    for ticker, day in zip(days["ticker"], days["signal_date"]):
        group = by_ticker.get(ticker)
        if group is None:
            continue
        low = day - pd.Timedelta(days=window)
        rows.append(group[(group["filing_date"] > low) & (group["filing_date"] <= day)])
    near_placebos = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if near_placebos.empty:
        return near_events
    near_placebos["filing_date"] = near_placebos["filing_date"].dt.strftime("%Y-%m-%d")
    both = pd.concat([near_events, near_placebos], ignore_index=True)
    return both.drop_duplicates("accession").reset_index(drop=True)


def already(db, model: str) -> set[str]:
    """Accessions already scored under this model, so a second run costs nothing."""
    try:
        return {r["accession"] for r in
                db.execute("SELECT accession FROM filing_sentiment WHERE model = ?", (model,))}
    except Exception:
        return set()


def score_all(db, cfg: Config | None = None, client=None, engine: Sentiment | None = None,
              window: int = WINDOW, limit: int | None = None,
              log: Callable[[str], None] = print) -> dict:
    """Score every filing a study would need, skipping what is already done.

    Safe to interrupt: each document is written as it is scored, and the next run picks up where
    this one stopped. Three thousand documents is twenty minutes of CPU, and losing it to a
    terminal closing would be a silly way to lose twenty minutes.
    """
    from miratrade import store
    from miratrade.data.sec import SecClient
    from miratrade.store.db import now

    cfg = cfg or Config()
    engine = engine or Sentiment(cfg.sentiment)
    if not engine.enabled:
        raise Unavailable("sentiment is switched off in the settings; nothing was scored")
    client = client or SecClient()
    model = cfg.sentiment.model
    settings = json.dumps(asdict(cfg.sentiment), sort_keys=True)

    todo = wanted(db, window)
    done = already(db, model)
    todo = todo[~todo["accession"].isin(done)]
    if limit:
        todo = todo.head(limit)
    log(f"  {len(todo):,} to score, {len(done):,} already done under {model}")

    written = failed = thin = 0
    batch = []
    for row in todo.itertuples(index=False):
        url = filings.body_url(row.cik, row.accession, row.document)
        try:
            raw = client.get(url, missing=(403, 404))
        except Exception:
            raw = None
        if raw is None:
            failed += 1
            continue
        verdict = engine.of_filing(raw)
        if verdict.passages == 0:
            thin += 1
        batch.append({"accession": row.accession, "ticker": row.ticker,
                      "filing_date": row.filing_date, "label": verdict.label,
                      "score": verdict.score, "confidence": verdict.confidence,
                      "passages": verdict.passages, "model": model,
                      "settings": settings, "scored_at": now()})
        if len(batch) >= 200:
            written += store.write(db, "filing_sentiment", pd.DataFrame(batch))
            batch = []
            log(f"  {written:,} scored, {failed} unreachable, {thin} with no prose")
    if batch:
        written += store.write(db, "filing_sentiment", pd.DataFrame(batch))
    log(f"  {written:,} scored, {failed} unreachable, {thin} with no prose")
    return {"scored": written, "failed": failed, "no_prose": thin, "model": model}


def of_days(db, days: pd.DataFrame, window: int = WINDOW,
            model: str | None = None) -> pd.Series:
    """The average sentiment of the filings before each day, aligned to ``days``.

    ``NaN`` where nothing was filed, and that is an unknown rather than a neutral. A study that
    treats "no filing" as "neutral news" has invented a data point.
    """
    from miratrade import store

    where = "model = ?" if model else ""
    scores = store.read(db, "filing_sentiment", where, (model,) if model else ())
    if scores.empty or days.empty:
        return pd.Series(float("nan"), index=days.index)
    scores = scores[scores["label"] != "unclear"]
    by_ticker = {t: g for t, g in scores.groupby("ticker")}
    out = []
    for ticker, day in zip(days["ticker"], days["signal_date"]):
        group = by_ticker.get(ticker)
        if group is None:
            out.append(float("nan"))
            continue
        low = pd.Timestamp(day) - pd.Timedelta(days=window)
        near = group[(group["filing_date"] > low) & (group["filing_date"] <= pd.Timestamp(day))]
        out.append(float(near["score"].mean()) if len(near) else float("nan"))
    return pd.Series(out, index=days.index, dtype="float64")
