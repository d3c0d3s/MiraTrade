"""Announcing a new event: enough detail to decide, never twice, and never as a recommendation."""
import pandas as pd
import pytest

from miratrade import store
from miratrade.config import Config
from miratrade.notify import already_sent, compose, detail, mark_sent, notify_new, send_ntfy


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / "market.db")
    from miratrade.scan import events_to_rows

    store.write(conn, "events", events_to_rows(pd.DataFrame([
        {"ticker": "PFE", "signal_date": pd.Timestamp("2026-09-24"), "close": 26.5,
         "what": "1 insider bought $1.0M", "what_parts": "[]", "event:insider_buy": True},
        {"ticker": "ACME", "signal_date": pd.Timestamp("2026-09-23"), "close": 10.0,
         "what": "options with unusual volume", "what_parts": "[]", "event:flow": True}])))
    yield conn
    conn.close()


def test_nothing_is_announced_twice(db):
    from miratrade.scan import load_events

    events = load_events(db)
    assert len(already_sent(db, events)) == 2          # nothing said yet

    mark_sent(db, events.head(1))
    left = already_sent(db, load_events(db))
    assert len(left) == 1 and left.iloc[0]["ticker"] == "ACME"

    mark_sent(db, left)
    assert len(already_sent(db, load_events(db))) == 0
    assert len(already_sent(db, pd.DataFrame())) == 0


def test_the_message_always_says_that_nothing_has_been_validated(db):
    """A list of tickers sent to a phone reads as a recommendation unless it is told otherwise."""
    honesty = "The latest analysis validated no rule out of sample."
    title, short, long = compose([{"ticker": "PFE", "date": "2026-09-24", "what": "1 insider bought",
                                   "close": 26.5, "contract": None, "evidence": None,
                                   "liquidity": None, "earnings": None}], honesty)
    assert honesty in short and honesty in long
    assert "1 new event" in title                       # singular, for one
    assert "modelled from the share, not quotes" in long
    assert "Analysis, not advice" in long


def test_the_detail_carries_the_contract_the_liquidity_and_the_earnings(db):
    from datetime import date

    from miratrade.liquidity import Verdict

    items = [{"ticker": "PFE", "date": date(2026, 9, 24), "what": "1 insider bought $1.0M",
              "close": 26.5, "evidence": None,
              "contract": {"strike": 26.0, "expiry": pd.Timestamp("2026-11-20"), "dte": 57,
                           "premium": 2.25, "delta": 0.63, "target": 3.15, "stop": 1.69,
                           "target_pct": 0.40, "stop_pct": 0.25},
              "liquidity": Verdict(False, "Open interest of {oi} is under {floor}.",
                                   {"oi": 12, "floor": 200}),
              "earnings": date(2026, 11, 3)}]
    _title, _short, long = compose(items, "no rule validated")
    assert "26 C expiring 2026-11-20 (57 days)" in long
    assert "premium $2.25" in long and "delta 0.63" in long
    assert "sell at $3.15 (+40%)" in long and "stop $1.69 (−25%)" in long
    assert "NOT TRADEABLE" in long                      # said plainly, not hidden
    assert "REPORTS 2026-11-03" in long


def test_a_push_carries_the_tickers_and_the_caveat_and_nothing_else(db):
    items = [{"ticker": t, "date": "2026-09-24", "what": "", "close": None, "contract": None,
              "evidence": None, "liquidity": None, "earnings": None}
             for t in ("PFE", "ACME", "KLTR")]
    _title, short, long = compose(items, "no rule validated")
    assert short.startswith("PFE, ACME, KLTR") and "no rule validated" in short
    assert len(short) < len(long)                       # the detail is for the mail


def test_sending_nothing_when_there_is_nothing_new(db, tmp_path):
    from miratrade.scan import load_events

    mark_sent(db, load_events(db))
    said = []
    out = notify_new(db, Config(), log=said.append)
    assert out == {"sent": 0, "push": False, "email": False}
    assert "nothing new" in " ".join(said)


def test_a_channel_that_fails_does_not_lose_the_other(db):
    cfg = Config()
    cfg.notify.ntfy_topic = "a-topic"
    cfg.notify.email_to = "me@example.com"
    cfg.notify.only_tradeable = False
    said, mailed = [], []

    def broken_push(*a, **k):
        raise OSError("no network")

    out = notify_new(db, cfg, log=said.append, ntfy_opener=broken_push,
                     email_sender=lambda msg, pw: mailed.append(msg) or True)
    assert out["email"] is True and out["push"] is False
    assert "push failed" in " ".join(said)
    assert mailed and "MiraTrade" in mailed[0]["Subject"]
    # and because something went out, those events are not announced again
    assert out["sent"] > 0
    assert notify_new(db, cfg, log=said.append, ntfy_opener=broken_push,
                      email_sender=lambda m, p: True)["sent"] == 0


def test_a_dry_run_sends_nothing(db):
    cfg = Config()
    cfg.notify.ntfy_topic = "a-topic"
    cfg.notify.only_tradeable = False
    out = notify_new(db, cfg, log=lambda _m: None, dry_run=True)
    assert out["sent"] and not out["push"] and not out["email"]
    assert "body" in out
    # nothing was marked, so it would still be announced for real later
    from miratrade.scan import load_events

    assert len(already_sent(db, load_events(db))) == out["sent"]


def test_no_topic_means_no_push():
    assert send_ntfy("", "t", "b") is False
