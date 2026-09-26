"""Massive client with a fake HTTP session: no request leaves the machine."""
from datetime import date

import pytest

from miratrade.data.massive import MassiveClient, occ_ticker, real_contract_bars


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class Session:
    def __init__(self, routes):
        self.headers, self.calls, self.routes = {}, [], routes

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        for fragment, reply in self.routes:
            if fragment in url:
                return reply() if callable(reply) else reply
        return Resp(404)


BAR = {"t": 1790395200000, "o": 4.9, "h": 5.6, "l": 4.8, "c": 5.5, "v": 120, "vw": 5.2, "n": 18}


def _client(tmp_path, routes, sleeps=None):
    return MassiveClient(api_key="SECRET", cache_dir=tmp_path, session=Session(routes),
                         sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_occ_ticker():
    assert occ_ticker("aapl", date(2026, 11, 20), "c", 150) == "O:AAPL261120C00150000"
    assert occ_ticker("F", date(2026, 11, 20), "C", 12.5) == "O:F261120C00012500"


def test_key_in_header_not_url_and_responses_cached(tmp_path):
    c = _client(tmp_path, [("/v2/aggs/", Resp(200, {"results": [BAR]}))])
    bars = c.daily_bars("O:ACME260821C00045000", date(2025, 7, 1), date(2025, 8, 1))   # finished: cached
    assert bars["close"].iat[0] == 5.5 and str(bars.index[0].date()) == "2026-09-26"
    url, params = c.session.calls[0]
    assert c.session.headers["Authorization"] == "Bearer SECRET"
    assert "SECRET" not in url and "SECRET" not in str(params)
    c.daily_bars("O:ACME260821C00045000", date(2025, 7, 1), date(2025, 8, 1))
    assert len(c.session.calls) == 1                                  # second time from the cache
    c.daily_bars("O:ACME261120C00045000", date(2026, 9, 1), date.today())
    c.daily_bars("O:ACME261120C00045000", date(2026, 9, 1), date.today())
    assert len(c.session.calls) == 3                                  # up to today: never cached
    assert not any("SECRET" in p.read_text() for p in tmp_path.iterdir())


def test_rate_limit_and_retry(tmp_path):
    sleeps = []
    replies = iter([Resp(429), Resp(200, {"results": []}), Resp(200, {"results": []})])
    c = _client(tmp_path, [("/v2/aggs/", lambda: next(replies))], sleeps)
    c.daily_bars("O:A", date(2026, 1, 1), date(2026, 2, 1))
    c.daily_bars("O:B", date(2026, 1, 1), date(2026, 2, 1))
    assert c.requests == 3 and len(sleeps) >= 2 and max(sleeps) >= 11     # waited for the 5/min pace


def test_bad_key_is_explained(tmp_path):
    c = _client(tmp_path, [("/v2/aggs/", Resp(401))])
    with pytest.raises(RuntimeError, match="API key"):
        c.daily_bars("O:A", date(2026, 1, 1), date(2026, 2, 1))


def test_falls_back_to_nearest_listed_strike(tmp_path):
    listed = {"results": [{"ticker": "O:ACME261120C00045000", "strike_price": 45.0},
                          {"ticker": "O:ACME261120C00047500", "strike_price": 47.5}]}
    c = _client(tmp_path, [("/v3/reference/options/contracts", Resp(200, listed)),
                           ("O:ACME261120C00047500", Resp(200, {"results": [BAR]}))])
    ticker, bars = real_contract_bars(c, "ACME", date(2026, 9, 25), date(2026, 11, 20), 47.0, date(2026, 10, 30))
    assert ticker == "O:ACME261120C00047500" and len(bars) == 1       # 47.0 isn't listed; 47.5 is


def test_missing_key(tmp_path):
    class Empty:
        def get(self, name):
            return None
    with pytest.raises(RuntimeError, match="massive setup"):
        MassiveClient(cache_dir=tmp_path, store=Empty())


def test_expired_flag_follows_the_expiry(tmp_path):
    c = _client(tmp_path, [("/v3/reference/options/contracts", Resp(200, {"results": []}))])
    c.contracts("SPY", date(2020, 1, 17))
    c.contracts("SPY", date(2099, 1, 16))
    c.contracts("SPY", date(2025, 12, 19), as_of=date(2025, 11, 3))    # live on that date
    flags = [params["expired"] for _, params in c.session.calls]
    assert flags == ["true", "false", "false"]   # expired=true returns ONLY contracts expired by as_of
