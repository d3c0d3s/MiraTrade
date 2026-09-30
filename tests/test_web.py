"""The HTTP API.

Two of these are not about behaviour but about what the API refuses to be: it never sends an order
and it never downloads. Both are absences, and an absence is exactly the kind of thing that gets
added back by accident six months later, so they are asserted rather than trusted.
"""
from datetime import date

import pandas as pd
import pytest

from miratrade import prefs, store

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient          # noqa: E402

from miratrade.web.api import create_app, rows     # noqa: E402


@pytest.fixture
def filled(tmp_path):
    """A store with a little of everything the screens read."""
    path = tmp_path / "market.db"
    db = store.connect(path)
    index = pd.bdate_range(end="2026-09-25", periods=300)
    close = pd.Series([40 + i * 0.05 for i in range(len(index))], index=index)
    for ticker in ("PFE", "ACME"):
        store.write(db, "prices", pd.DataFrame(
            {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
             "volume": 3_000_000.0}, index=index).assign(ticker=ticker, source="test"))
    store.write(db, "insiders", pd.DataFrame([
        {"accession": "a1", "filing_date": "2026-09-22", "trade_date": "2026-09-18",
         "ticker": "PFE", "owner_cik": "1", "owner": "A Director", "code": "P",
         "shares": 20_000.0, "price": 60.0, "value": 1_200_000.0, "is_officer": 1},
        {"accession": "a2", "filing_date": "2026-09-22", "trade_date": "2026-09-18",
         "ticker": "ACME", "owner_cik": "2", "owner": "The CFO", "code": "P",
         "shares": 500.0, "price": 60.0, "value": 30_000.0, "is_officer": 1}]))
    store.write(db, "events", pd.DataFrame([
        {"ticker": "PFE", "signal_date": "2026-09-22", "insider_buy": 1, "flow": 0,
         "ownership": 0, "congress": 0, "mkt_cap": 3.2e11, "close": 60.0,
         "what": "1 insider bought $1.2M", "what_parts": "[]", "flags": "{}"},
        {"ticker": "ACME", "signal_date": "2026-09-21", "insider_buy": 1, "flow": 0,
         "ownership": 0, "congress": 0, "mkt_cap": 4.0e8, "close": 12.0,
         "what": "1 insider bought $30k", "what_parts": "[]", "flags": "{}"}]))
    store.mark_covered(db, "sec_form4", [date(2026, 9, 25)], rows=2)
    db.close()
    return path


@pytest.fixture
def client(filled, tmp_path):
    reports = tmp_path / "reports" / "5y"
    reports.mkdir(parents=True)
    (reports / "edge_report.md").write_text(
        "# report\n\nWindow: **2021-09-01 → 2026-09-01**\n", encoding="utf-8")
    (reports / "rules.csv").write_text("rule,validated,wf_confirmed\nx,False,False\n",
                                       encoding="utf-8")
    (reports / "trades.csv").write_text("r\n1\n2\n", encoding="utf-8")
    return TestClient(create_app(filled, tmp_path / "reports"))


# --------------------------------------------------------------------------- what it refuses to be

def test_it_can_never_send_an_order(client):
    """A deliberate absence, not a missing feature. Broker credentials and the decision to trade
    stay with the person, on their own machine."""
    paths = {r.path for r in client.app.routes}
    assert not [p for p in paths if any(w in p.lower()
                                        for w in ("order", "trade/", "buy", "sell", "execute"))]
    import miratrade.web.api as api
    source = __import__("inspect").getsource(api)
    for forbidden in ("place_order", "SchwabBroker", "EtradeBroker", "brokers"):
        assert forbidden not in source, f"the API reaches for {forbidden}"


def test_it_can_never_download(client, monkeypatch):
    """A page refresh from a phone must not become a request to the SEC. Every way out to the
    network is made to explode, and every endpoint still has to answer."""
    import socket
    import urllib.request

    import requests

    def refuse(*a, **k):
        raise AssertionError("the API tried to reach the network")

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", refuse)
    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)

    # Loopback is allowed through: on Windows the test client's own event loop builds a socketpair
    # over 127.0.0.1, and blocking that catches the harness rather than the API. Anything leaving
    # the machine still fails.
    real_connect = socket.socket.connect

    def only_loopback(self, address, *a, **k):
        host = address[0] if isinstance(address, tuple) else ""
        if str(host) not in ("127.0.0.1", "::1", "localhost"):
            refuse()
        return real_connect(self, address, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", only_loopback)

    for path in ("/api/health", "/api/honesty", "/api/sources", "/api/summary",
                 "/api/events", "/api/scanner/insiders", "/api/prices/PFE",
                 "/api/reports", "/api/settings"):
        assert client.get(path).status_code == 200, path


def test_every_write_is_one_of_three_things(client):
    """Settings, a job, or a paper trade. Once the web has to replace the desktop app those three
    have to work from it; nothing else may.

    `broker` is missing from all of them on purpose: it holds `live_trading`, and a front-end that
    cannot send an order must not be able to switch on the thing that can.
    """
    writes = {(r.path, m) for r in client.app.routes
              for m in getattr(r, "methods", set()) if m in ("POST", "PUT", "PATCH", "DELETE")}
    assert writes == {("/api/settings", "PUT"),
                      ("/api/jobs", "POST"), ("/api/jobs/{job_id}", "DELETE"),
                      ("/api/practice", "POST"), ("/api/practice/{trade_id}/close", "POST")}

    from miratrade import params
    sections = {f.section for g in (params.ALL_GROUPS + params.OPERATION_GROUPS) for f in g.fields}
    assert "broker" not in sections
    assert client.put("/api/settings", json={"section": "broker", "key": "live_trading",
                                             "value": True}).status_code == 400


# --------------------------------------------------------------------------- what it serves

def test_health_says_how_old_the_data_is(client):
    body = client.get("/api/health").json()
    assert body["schema_version"] == store.SCHEMA_VERSION
    assert body["counts"]["insiders"] == 2 and body["events"] == 2
    assert body["last_download"] == "2026-09-25"
    assert "2026-09-25" in body["fresh"]


def test_the_honest_line_has_an_endpoint_of_its_own(client):
    """So a front-end cannot forget it: there is no screen in this product where suggestions appear
    without it."""
    line = client.get("/api/honesty").json()["line"]
    assert "validated no rule" in line or "no analysis" in line.lower()


def test_events_come_back_filtered(client):
    body = client.get("/api/events", params={"days": 3650}).json()
    assert {r["ticker"] for r in body["rows"]} == {"PFE", "ACME"}

    big = client.get("/api/events", params={"days": 3650, "cap_tier": "mega"}).json()
    assert {r["ticker"] for r in big["rows"]} == {"PFE"}

    one = client.get("/api/events", params={"days": 3650, "ticker": "ACME"}).json()
    assert {r["ticker"] for r in one["rows"]} == {"ACME"}


def test_events_are_never_re_derived_by_reading_them(client):
    """Reading is reading. Re-deriving belongs to `reprocess`, which a person runs on purpose."""
    before = client.get("/api/health").json()["events"]
    for _ in range(3):
        client.get("/api/events", params={"days": 3650, "cap_tier": "mega"})
    assert client.get("/api/health").json()["events"] == before


def test_an_unknown_size_or_kind_is_refused_rather_than_ignored(client):
    assert client.get("/api/events", params={"cap_tier": "enormous"}).status_code == 400
    assert client.get("/api/events", params={"kinds": "event:vibes"}).status_code == 400


def test_the_scanner_serves_the_rows_as_filed(client):
    body = client.get("/api/scanner/insiders", params={"days": 3650}).json()
    assert body["total"] == 2 and len(body["rows"]) == 2
    narrowed = client.get("/api/scanner/insiders",
                          params={"days": 3650, "min_amount": 100_000}).json()
    assert narrowed["total"] == 1


def test_a_filter_a_source_does_not_understand_is_ignored_not_fatal(client):
    """The same behaviour the desktop relies on, and the reason correctness never depends on the
    screen deciding which controls to show."""
    body = client.get("/api/scanner/insiders",
                      params={"days": 3650, "chamber": "house", "option_type": "call"}).json()
    assert body["total"] == 2


def test_an_unknown_source_says_which_ones_exist(client):
    answer = client.get("/api/scanner/nonsense")
    assert answer.status_code == 404 and "insiders" in answer.json()["detail"]


def test_price_bars_come_from_every_download_ever_made(client):
    body = client.get("/api/prices/pfe").json()
    assert body["ticker"] == "PFE" and len(body["bars"]) == 300
    assert set(body["bars"][0]) >= {"date", "open", "high", "low", "close", "volume"}
    assert client.get("/api/prices/NOPE").status_code == 404


def test_reports_are_listed_and_readable(client):
    listed = client.get("/api/reports").json()
    assert [r["name"] for r in listed] == ["5y"]
    assert listed[0]["start"] == "2021-09-01"
    one = client.get("/api/reports/5y").json()
    assert "# report" in one["markdown"]
    assert client.get("/api/reports/missing").status_code == 404


# --------------------------------------------------------------------------- the settings

def test_settings_carry_their_own_explanation(client):
    """So the web builds the same form as the desktop from one description instead of two."""
    from miratrade import params

    body = client.get("/api/settings").json()
    rules = [f for g in body["rules"] for f in g["fields"]]
    running = [f for g in body["operation"] for f in g["fields"]]
    assert len(rules) == len(params.fields())
    assert len(running) == len(params.fields(params.OPERATION_GROUPS))
    one = next(f for f in rules if f["key"] == "min_value_usd")
    assert one["label"] and len(one["help"]) > 40 and one["changed"] is False
    # …and the two lists are apart because only one of them is a claim about the market
    assert {f["section"] for f in running}.isdisjoint({f["section"] for f in rules})


def test_a_setting_can_be_changed_and_comes_back_changed(client, filled):
    answer = client.put("/api/settings", json={"section": "insider", "key": "min_value_usd",
                                               "value": 250_000})
    assert answer.status_code == 200 and answer.json()["value"] == 250_000

    db = store.connect(filled)
    assert prefs.read(db)[0].insider.min_value_usd == 250_000
    db.close()

    field = next(f for g in client.get("/api/settings").json()["rules"]
                 for f in g["fields"] if f["key"] == "min_value_usd")
    assert field["changed"] is True and field["default"] == 25_000


def test_a_typo_is_refused_here_too(client):
    """The same validation that protects the desktop. A misspelt key must never be able to quietly
    disable a limit, whichever front-end typed it."""
    assert client.put("/api/settings", json={"section": "risk", "key": "max_positons",
                                             "value": 3}).status_code == 400
    assert client.put("/api/settings", json={"section": "edge", "key": "min_support",
                                             "value": 3}).status_code == 400


def test_the_settings_carry_the_multiple_testing_count(client):
    """It belongs wherever somebody is about to change a threshold, and that now includes a phone."""
    body = client.get("/api/settings").json()
    assert "multiple_testing" in body and body["attempts"] == 0


# --------------------------------------------------------------------------- serialising

def test_pandas_values_json_cannot_carry_become_null_not_a_crash():
    """One NaN makes a whole response fail to serialise — usually for one row out of two thousand,
    which is a miserable thing to debug from a phone."""
    import numpy as np

    df = pd.DataFrame([{"a": np.nan, "b": pd.Timestamp("2026-09-25"), "c": np.int64(3),
                        "d": pd.NaT, "e": float("inf"), "f": np.True_}])
    assert rows(df) == [{"a": None, "b": "2026-09-25", "c": 3, "d": None, "e": None, "f": True}]
    assert rows(None) == [] and rows(pd.DataFrame()) == []


def test_no_database_is_explained_rather_than_crashing(tmp_path):
    client = TestClient(create_app(tmp_path / "nowhere" / "market.db", tmp_path / "reports"))
    answer = client.get("/api/health")
    assert answer.status_code == 503 and "market database" in answer.json()["detail"]


def test_a_page_says_how_many_there_really_were(client):
    """"50 of 444" and "50 of 50" must not look the same. Returning the page size as the total is
    how a list quietly hides three hundred rows."""
    body = client.get("/api/events", params={"days": 3650, "limit": 1}).json()
    assert body["shown"] == 1 and body["total"] == 2
