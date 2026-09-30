"""Who is asking: the Cloudflare Access token, verified rather than trusted.

The tests sign real tokens with a throwaway key and serve the matching public key as Cloudflare
would, because the only thing worth testing here is what a *forged* token does. A check that only
ever sees well-formed input is not a check.

The property that matters most is the last one: the server refuses to listen anywhere but loopback
without Access configured. Everything else in this file protects a door; that one is what stops
the door being left off its hinges.
"""
import time

import pytest

joserfc = pytest.importorskip("joserfc")
from joserfc import jwt                              # noqa: E402
from joserfc.jwk import RSAKey                       # noqa: E402

from miratrade.web import access                     # noqa: E402

TEAM = "miratech"
AUD = "0123456789abcdef"


@pytest.fixture(scope="module")
def signing():
    return RSAKey.generate_key(2048, parameters={"kid": "test-key"})


@pytest.fixture(scope="module")
def other_key():
    """Somebody else's key. A token signed with this must never be accepted."""
    return RSAKey.generate_key(2048, parameters={"kid": "not-cloudflare"})


@pytest.fixture
def verifier(signing):
    keys = {"keys": [signing.as_dict(private=False)]}
    return access.Verifier(access.Settings(team=TEAM, audience=AUD), fetch=lambda _url: keys)


def token(key, *, aud=AUD, iss=None, exp=None, nbf=None, email="denis@example.com"):
    now = int(time.time())
    claims = {"aud": aud, "iss": iss if iss is not None else access.ISSUER.format(team=TEAM),
              "exp": exp if exp is not None else now + 3600,
              "nbf": nbf if nbf is not None else now - 10,
              "iat": now, "email": email, "sub": "abc"}
    return jwt.encode({"alg": "RS256", "kid": key.kid}, claims, key)


# --------------------------------------------------------------------------- a good token

def test_a_token_from_your_team_for_this_app_is_accepted(verifier, signing):
    assert verifier.who(token(signing)) == "denis@example.com"


def test_the_signing_keys_are_cached_not_fetched_per_request(signing):
    calls = []

    def fetch(url):
        calls.append(url)
        return {"keys": [signing.as_dict(private=False)]}

    v = access.Verifier(access.Settings(team=TEAM, audience=AUD), fetch=fetch)
    for _ in range(5):
        v.who(token(signing))
    assert len(calls) == 1 and TEAM in calls[0]


def test_the_keys_are_refetched_once_they_go_stale(signing):
    """Cloudflare rotates them. A cache with no expiry works until the day it does not."""
    clock = [1000.0]
    calls = []

    def fetch(_url):
        calls.append(1)
        return {"keys": [signing.as_dict(private=False)]}

    v = access.Verifier(access.Settings(team=TEAM, audience=AUD), fetch=fetch, now=lambda: clock[0])
    v.keys()
    clock[0] += access.KEYS_TTL_S + 1
    v.keys()
    assert len(calls) == 2


# --------------------------------------------------------------------------- forgeries

def test_a_token_signed_by_anybody_else_is_refused(verifier, other_key):
    """The header proves nothing — anyone can send a header. Only the signature does."""
    with pytest.raises(access.NotAllowed):
        verifier.identity(token(other_key))


def test_a_token_for_another_of_your_apps_does_not_open_this_one(verifier, signing):
    """Same team, same signing key, different audience. Without this check every application
    behind your Access account shares one door."""
    with pytest.raises(access.NotAllowed):
        verifier.identity(token(signing, aud="a-different-application"))


def test_a_token_from_another_team_is_refused(verifier, signing):
    with pytest.raises(access.NotAllowed):
        verifier.identity(token(signing, iss="https://someone-else.cloudflareaccess.com"))


def test_an_expired_token_is_refused(verifier, signing):
    with pytest.raises(access.NotAllowed):
        verifier.identity(token(signing, exp=int(time.time()) - 1))


def test_a_token_from_the_future_is_refused_but_a_minute_of_skew_is_forgiven(verifier, signing):
    with pytest.raises(access.NotAllowed):
        verifier.identity(token(signing, nbf=int(time.time()) + 600))
    assert verifier.who(token(signing, nbf=int(time.time()) + 30))     # clocks are never exact


def test_no_token_at_all_is_refused(verifier):
    with pytest.raises(access.NotAllowed):
        verifier.identity("")


def test_every_refusal_says_the_same_kind_of_nothing(verifier, signing, other_key):
    """Telling a caller *which* check their token failed tells them how to get closer to passing
    it. Every failure is the same refusal from outside."""
    reasons = []
    for bad in ("", "garbage", token(other_key), token(signing, aud="other"),
                token(signing, exp=int(time.time()) - 1)):
        with pytest.raises(access.NotAllowed) as refusal:
            verifier.identity(bad)
        reasons.append(str(refusal.value))
    assert all("secret" not in r and "key" not in r.lower() for r in reasons)
    assert all(len(r) < 80 for r in reasons)          # a refusal, not a diagnosis


# --------------------------------------------------------------------------- the invariant

@pytest.mark.parametrize("host,needed", [("127.0.0.1", False), ("localhost", False),
                                         ("::1", False), ("0.0.0.0", True),
                                         ("192.168.150.210", True)])
def test_anything_off_this_machine_needs_access(host, needed):
    assert access.required_for(host) is needed


def test_the_server_refuses_to_listen_outside_without_access(monkeypatch):
    """The one that matters. A 375 MB database served to a whole network because somebody typed a
    --host is the accident this prevents, and a warning in a log does not prevent it: it scrolls
    past at three in the morning and the thing keeps serving."""
    import miratrade.web.api as api

    started = []
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: started.append(1))

    with pytest.raises(SystemExit, match="Refusing to listen"):
        api.serve(host="192.168.150.210", settings=access.Settings())
    assert started == []

    api.serve(host="127.0.0.1", settings=access.Settings(), log=lambda _m: None)
    assert started == [1]                              # loopback needs nothing


def test_configured_access_lets_it_listen_outside(monkeypatch):
    import miratrade.web.api as api

    started = []
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: started.append(k or a))
    api.serve(host="0.0.0.0", settings=access.Settings(team=TEAM, audience=AUD),
              log=lambda _m: None)
    assert len(started) == 1


def test_where_access_is_configured_from(monkeypatch):
    """From the environment, not from the settings the web can change. Somebody who got in must
    not be able to switch off the thing that keeps them out — the same reason `broker` is not in
    the forms."""
    from miratrade import prefs

    assert "access" not in prefs.USER_SECTIONS
    got = access.Settings.from_env({"MIRATRADE_ACCESS_TEAM": " miratech ",
                                    "MIRATRADE_ACCESS_AUD": "abc"})
    assert got.team == "miratech" and got.configured
    assert not access.Settings.from_env({}).configured


# --------------------------------------------------------------------------- through the app

def test_the_whole_app_is_behind_it_including_the_page(verifier, signing, tmp_path):
    """A token on the API and none on the HTML would hand the interface to anyone who asked."""
    from fastapi.testclient import TestClient

    from miratrade.web.api import create_app

    client = TestClient(create_app(tmp_path / "m.db", tmp_path / "reports", verifier),
                        raise_server_exceptions=False)
    for path in ("/", "/app.js", "/api/health", "/api/settings"):
        assert client.get(path).status_code == 403, path

    good = {access.HEADER: token(signing)}
    assert client.get("/", headers=good).status_code == 200
    # /api/health needs a database; what matters is that it got past the door
    assert client.get("/api/health", headers=good).status_code != 403
