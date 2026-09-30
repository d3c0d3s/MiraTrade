"""Who is asking: the Cloudflare Access token, verified rather than trusted.

I argued earlier that this API should not authenticate, because half an authentication is worse
than none — somebody would trust it. That argument was about *inventing* a login here. This is the
opposite: Cloudflare Access already decided who you are, against whatever identity provider sits
behind it (Entra, AD FS, Authentik — the API neither knows nor cares), and it signs that decision.
Verifying a signature from your own identity provider is delegated authentication, not a home-made
one.

What it checks, in the order that matters:

* the token is signed by a key Cloudflare publishes for **your** team, fetched over HTTPS;
* its audience is **your** application's tag, so a token minted for another of your apps does not
  open this one;
* its issuer is your team, and it is neither expired nor not-yet-valid.

The header is ``Cf-Access-Jwt-Assertion``, and its presence proves nothing on its own — anyone can
send a header. Only the signature does.

**The invariant worth more than all of it:** the server refuses to start listening on anything but
loopback unless this is configured. An API that quietly serves a 375 MB database to the whole LAN
because somebody typed a ``--host`` is the accident this prevents, and a comment in a README does
not prevent it.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

CERTS = "https://{team}.cloudflareaccess.com/cdn-cgi/access/certs"
ISSUER = "https://{team}.cloudflareaccess.com"
HEADER = "cf-access-jwt-assertion"
KEYS_TTL_S = 3600                  # Cloudflare rotates its signing keys; an hour is their guidance
LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


class NotAllowed(Exception):
    """The request does not carry a token this deployment accepts."""


@dataclass(frozen=True)
class Settings:
    """Where Access lives, from the environment rather than from the settings the web can change.

    Deliberately NOT in ``prefs.USER_SECTIONS``: somebody who got in must not be able to switch off
    the thing that keeps them out. Same reason ``broker`` is not there.
    """
    team: str = ""
    audience: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.team and self.audience)

    @classmethod
    def from_env(cls, env=None) -> "Settings":
        env = env if env is not None else os.environ
        return cls(team=(env.get("MIRATRADE_ACCESS_TEAM") or "").strip(),
                   audience=(env.get("MIRATRADE_ACCESS_AUD") or "").strip())


def required_for(host: str) -> bool:
    """Whether a listener on ``host`` must verify tokens. Anything off this machine must."""
    return str(host).strip().lower() not in LOOPBACK


class Verifier:
    """Verifies Access tokens, caching the signing keys for an hour."""

    def __init__(self, settings: Settings, fetch=None, now=None):
        self.settings = settings
        self._fetch = fetch or self._download
        self._now = now or time.time
        self._keys = None
        self._fetched_at = 0.0

    @staticmethod
    def _download(url: str) -> dict:
        import httpx

        answer = httpx.get(url, timeout=10)
        answer.raise_for_status()
        return answer.json()

    def keys(self) -> dict:
        if self._keys is None or self._now() - self._fetched_at > KEYS_TTL_S:
            self._keys = self._fetch(CERTS.format(team=self.settings.team))
            self._fetched_at = self._now()
        return self._keys

    def identity(self, token: str) -> dict:
        """The claims of a valid token, or :class:`NotAllowed`.

        Every failure is the same refusal from outside. Telling a caller *why* their token was
        rejected — wrong audience, expired, bad signature — is telling them how to get closer.
        """
        from joserfc import jwt
        from joserfc.jwk import KeySet

        if not token:
            raise NotAllowed("no Cloudflare Access token")
        try:
            decoded = jwt.decode(token, KeySet.import_key_set(self.keys()))
            claims = decoded.claims
        except Exception as e:                       # bad signature, unknown key, malformed
            raise NotAllowed("the token could not be verified") from e

        audiences = claims.get("aud") or []
        if isinstance(audiences, str):
            audiences = [audiences]
        if self.settings.audience not in audiences:
            raise NotAllowed("the token was not minted for this application")
        if claims.get("iss") != ISSUER.format(team=self.settings.team):
            raise NotAllowed("the token was not minted by this team")

        now = self._now()
        if float(claims.get("exp", 0)) <= now:
            raise NotAllowed("the token has expired")
        if float(claims.get("nbf", 0)) > now + 60:   # a minute of clock skew
            raise NotAllowed("the token is not valid yet")
        return dict(claims)

    def who(self, token: str) -> str:
        """The email Access says this is. Used for the log, never for a decision."""
        return str(self.identity(token).get("email") or "unknown")
