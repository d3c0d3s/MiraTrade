"""Scoring the prose of a filing, and storing what that cost.

The decisions worth testing here are not about FinBERT — a fake backend stands in for it — but
about what gets stored, what gets skipped, and what a missing score is allowed to look like.
"""
from datetime import date, timedelta

import pandas as pd
import pytest

from miratrade import store
from miratrade.config import Config
from miratrade.news import scoring
from miratrade.news.sentiment import Sentiment, Unavailable

BODY = ("<html><body><p>The Company announced that it has entered into a definitive agreement "
        "to acquire all outstanding shares of the target for cash.</p></body></html>")


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / "m.db")
    index = pd.bdate_range(end="2026-09-25", periods=400)
    close = pd.Series([20.0] * len(index), index=index)
    store.write(conn, "prices", pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1e6},
        index=index).assign(ticker="AAA", source="t"))
    store.write(conn, "events", pd.DataFrame([{
        "ticker": "AAA", "signal_date": "2026-09-10", "insider_buy": 1, "flow": 0,
        "ownership": 0, "congress": 0, "mkt_cap": 1e9, "close": 20.0,
        "what": "", "what_parts": "[]", "flags": "{}"}]))
    store.write(conn, "filings", pd.DataFrame([{
        "accession": "0000012345-26-000001", "ticker": "AAA", "item": "1.01", "form": "8-K",
        "filing_date": "2026-09-05", "accepted_at": None, "report_date": None,
        "cik": "12345", "document": "aaa-20260905.htm"}]))
    yield conn
    conn.close()


def loud(label="positive", probability=0.92):
    cfg = Config()
    cfg.sentiment.enabled = True
    return cfg, Sentiment(cfg.sentiment, backend=lambda p: [(label, probability)] * len(p))


class Client:
    def __init__(self, body=BODY):
        self.body, self.asked = body, []

    def get(self, url, **kw):
        self.asked.append(url)
        return self.body


# --------------------------------------------------------------------------- what it scores

def test_it_scores_both_sides_of_the_comparison(db):
    """Scoring only the event side and comparing against nothing is how the 8-K work went wrong
    the first time: a rate with nothing to measure against can only agree with itself."""
    both = scoring.wanted(db, include_placebos=True)
    one = scoring.wanted(db, include_placebos=False)
    assert len(both) >= len(one)


def test_a_filing_with_no_reachable_document_is_never_asked_for(db):
    store.write(db, "filings", pd.DataFrame([{
        "accession": "no-doc", "ticker": "AAA", "item": "8.01", "form": "8-K",
        "filing_date": "2026-09-06", "accepted_at": None, "report_date": None,
        "cik": None, "document": None}]))
    assert "no-doc" not in set(scoring.wanted(db)["accession"])


def test_routine_items_are_never_scored(db):
    store.write(db, "filings", pd.DataFrame([{
        "accession": "routine", "ticker": "AAA", "item": "9.01", "form": "8-K",
        "filing_date": "2026-09-06", "accepted_at": None, "report_date": None,
        "cik": "12345", "document": "x.htm"}]))
    assert "routine" not in set(scoring.wanted(db)["accession"])


# --------------------------------------------------------------------------- what it stores

def test_the_score_is_kept_and_the_text_is_not(db):
    """The expensive half is stored and the cheap half is not, which is the opposite of what feels
    natural: EDGAR's copy is free to fetch again, re-scoring thousands of documents is not."""
    cfg, engine = loud()
    out = scoring.score_all(db, cfg, Client(), engine, log=lambda _m: None)
    assert out["scored"] >= 1

    rows = store.read(db, "filing_sentiment")
    assert len(rows) >= 1
    row = rows.iloc[0]
    assert row["label"] == "positive" and row["passages"] >= 1
    assert "text" not in rows.columns and "body" not in rows.columns


def test_each_row_records_the_settings_that_produced_it(db):
    """A score read months later under different thresholds is a number whose meaning nobody can
    reconstruct."""
    import json

    cfg, engine = loud()
    cfg.sentiment.min_confidence = 0.77
    scoring.score_all(db, cfg, Client(), engine, log=lambda _m: None)
    stored = json.loads(store.read(db, "filing_sentiment").iloc[0]["settings"])
    assert stored["min_confidence"] == 0.77 and stored["model"] == cfg.sentiment.model


def test_running_it_again_costs_nothing(db):
    cfg, engine = loud()
    client = Client()
    scoring.score_all(db, cfg, client, engine, log=lambda _m: None)
    first = len(client.asked)
    again = scoring.score_all(db, cfg, client, engine, log=lambda _m: None)
    assert again["scored"] == 0 and len(client.asked) == first


def test_it_refuses_rather_than_scoring_nothing_when_switched_off(db):
    off = Config()
    with pytest.raises(Unavailable, match="switched off"):
        scoring.score_all(db, off, Client(), log=lambda _m: None)


def test_an_unreachable_document_is_counted_not_fatal(db):
    class Gone(Client):
        def get(self, url, **kw):
            return None

    cfg, engine = loud()
    out = scoring.score_all(db, cfg, Gone(), engine, log=lambda _m: None)
    assert out["failed"] >= 1 and out["scored"] == 0


# --------------------------------------------------------------------------- reading them back

def test_no_filing_before_a_day_is_unknown_not_neutral(db):
    """A study that treats "no filing" as "neutral news" has invented a data point."""
    cfg, engine = loud()
    scoring.score_all(db, cfg, Client(), engine, log=lambda _m: None)

    days = pd.DataFrame([{"ticker": "AAA", "signal_date": pd.Timestamp("2026-09-10")},
                         {"ticker": "AAA", "signal_date": pd.Timestamp("2025-01-10")},
                         {"ticker": "NOBODY", "signal_date": pd.Timestamp("2026-09-10")}])
    got = scoring.of_days(db, days)
    assert got.iloc[0] > 0            # the filing five days before
    assert pd.isna(got.iloc[1])       # nothing filed before that day
    assert pd.isna(got.iloc[2])       # a company with nothing at all


def test_unclear_scores_are_left_out_of_the_average(db):
    """"We could not tell" must not be averaged in as zero, which would pull every company towards
    neutral in proportion to how unreadable its filings are."""
    store.write(db, "filing_sentiment", pd.DataFrame([
        {"accession": "a", "ticker": "AAA", "filing_date": "2026-09-05", "label": "positive",
         "score": 0.8, "confidence": 0.9, "passages": 3, "model": "m", "settings": "{}",
         "scored_at": "2026-09-30T00:00:00Z"},
        {"accession": "b", "ticker": "AAA", "filing_date": "2026-09-06", "label": "unclear",
         "score": 0.0, "confidence": 0.1, "passages": 0, "model": "m", "settings": "{}",
         "scored_at": "2026-09-30T00:00:00Z"}]))
    days = pd.DataFrame([{"ticker": "AAA", "signal_date": pd.Timestamp("2026-09-10")}])
    assert scoring.of_days(db, days, model="m").iloc[0] == pytest.approx(0.8)
