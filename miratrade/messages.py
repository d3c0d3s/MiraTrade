"""Sentences the interface may translate.

The domain layer is written in English and composes its sentences from English templates plus their
values, never from already-formatted prose. Something that shows a sentence on screen passes the
interface's ``t()`` as ``translate`` and gets it in the user's language; the console tools pass
nothing and get the English. That keeps the language out of the domain without losing translation.
"""
from __future__ import annotations

from typing import Callable, Iterable, Sequence

Translate = Callable[..., str]


def plain(template: str, **fields) -> str:
    """The English sentence: what the console prints and what a language with no entry falls to."""
    return template.format(**fields) if fields else template


def sayer(translate: Translate | None) -> Translate:
    return translate or plain


def money(v: float) -> str:
    """A short amount for a crowded line, in the English convention: $1.4M or $250k."""
    return f"${v / 1e6:,.1f}M" if abs(v) >= 1e6 else f"${v / 1e3:,.0f}k"


Part = tuple[str, dict]


def note(parts: Sequence[Part] | Iterable[Part], translate: Translate | None = None,
         amount: Callable[[float], str] | None = None) -> str:
    """Join the pieces of an event note. The pieces travel as ``(template, fields)`` so they can be
    saved with the scan and still be translated whenever they are shown; a field called ``amount``
    holds raw dollars and is written by ``amount``, which the interface passes in its own style."""
    say, cash = sayer(translate), amount or money
    pieces = [say(template, **{k: cash(v) if k == "amount" else v for k, v in fields.items()})
              for template, fields in parts]
    return "; ".join(pieces) or say("new event")
