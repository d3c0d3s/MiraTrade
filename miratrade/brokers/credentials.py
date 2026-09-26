"""Secrets in the Windows Credential Manager (via ``keyring``), never in files or logs.

Windows caps one credential at 2,560 bytes (about 1,280 characters), less than a Schwab OAuth
token, so long values are split into numbered chunks: ``<name>#n`` holds the chunk count and
``<name>#0``, ``<name>#1``… the pieces.
"""
from __future__ import annotations

import json

SERVICE = "MiraTrade"
CHUNK = 1000


class CredentialStore:
    def __init__(self, service: str = SERVICE, backend=None):
        import keyring

        self.service = service
        self.kr = backend or keyring

    def set(self, name: str, value: str) -> None:
        self.delete(name)
        parts = [value[i:i + CHUNK] for i in range(0, len(value), CHUNK)] or [""]
        for i, part in enumerate(parts):
            self.kr.set_password(self.service, f"{name}#{i}", part)
        self.kr.set_password(self.service, f"{name}#n", str(len(parts)))

    def get(self, name: str) -> str | None:
        n = self.kr.get_password(self.service, f"{name}#n")
        if n is None:
            return None
        parts = [self.kr.get_password(self.service, f"{name}#{i}") for i in range(int(n))]
        if any(p is None for p in parts):
            return None                     # half-written: treat as missing, force a new login
        return "".join(parts)

    def delete(self, name: str) -> None:
        n = self.kr.get_password(self.service, f"{name}#n")
        keys = [f"{name}#{i}" for i in range(int(n))] + [f"{name}#n"] if n is not None else []
        for key in keys:
            try:
                self.kr.delete_password(self.service, key)
            except Exception:               # already gone
                pass

    def set_json(self, name: str, value: dict) -> None:
        self.set(name, json.dumps(value))

    def get_json(self, name: str) -> dict | None:
        raw = self.get(name)
        return None if raw is None else json.loads(raw)
