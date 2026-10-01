"""Who this copy of MiraTrade is for, and which sources that rules out.

``docs/LICENCIAS.md`` says which data may be used in which mode. A document does not stop anything.
This does: the restricted sources ask before they fetch, and refuse.

Three modes, and the jump between them is a licensing question rather than a feature one:

* **personal** — one person, their own machine, their own credentials. Everything is allowed.
* **feedback** — a few invited people. Not about money: the congressional disclosures stop being
  personal use the moment somebody else reads them (5 U.S.C. app. § 105(c)), and Yahoo and Stooq
  allow personal, non-commercial use at most.
* **commercial** — subscribers. Everything above, plus every price source needs a redistribution
  licence.

**Refusing is the whole point, and refusing loudly is most of it.** A mode that merely hid the
congressional screen would leave the data flowing into the events, the emails and the backtest with
nobody noticing. So a restricted source raises, and the message says which mode forbade it and
where to read why.

What this is not: legal advice, and not a substitute for the lawyer that ``LICENCIAS.md`` marks as
necessary before anybody pays. It is the part that can be enforced in code, enforced in code.
"""
from __future__ import annotations

from dataclasses import dataclass

PERSONAL, FEEDBACK, COMMERCIAL = "personal", "feedback", "commercial"
MODES = (PERSONAL, FEEDBACK, COMMERCIAL)


@dataclass(frozen=True)
class Restriction:
    """One source, why it is limited and how far it may go."""
    key: str
    what: str
    allowed_in: tuple[str, ...]
    because: str


# Each entry is a licence, not an opinion. The wording is what to tell somebody who just hit it.
RESTRICTED: dict[str, Restriction] = {
    "congress": Restriction(
        key="congress",
        what="congressional disclosures",
        allowed_in=(PERSONAL,),
        because="the Ethics in Government Act (5 U.S.C. app. § 105(c)) restricts commercial use of "
                "these filings. They stop being personal use the moment somebody else reads them, "
                "which is why feedback mode is out too, not only commercial."),
    "research_prices": Restriction(
        key="research_prices",
        what="prices from public websites (Yahoo, Stooq)",
        allowed_in=(PERSONAL,),
        because="their terms allow personal, non-commercial use at most. What another person sees "
                "cannot come from here."),
    "broker_prices": Restriction(
        key="broker_prices",
        what="prices from your own broker account",
        allowed_in=(PERSONAL, FEEDBACK),
        because="an individual developer key covers the account holder's own use. Serving "
                "subscribers needs a vendor agreement."),
    "alpha_vantage_free": Restriction(
        key="alpha_vantage_free",
        what="the free Alpha Vantage key",
        allowed_in=(PERSONAL,),
        because="their terms define commercial use with four criteria, and a free key does not "
                "cover it. The paid plans do."),
}


class NotAllowedHere(RuntimeError):
    """This source is not licensed for the mode this copy is running in."""


def mode(cfg=None) -> str:
    """The mode in force. Anything unrecognised reads as ``personal``…

    …because that is the only reading that cannot *loosen* a restriction by accident. A typo that
    silently granted commercial rights would be the one failure this module exists to prevent.
    """
    if cfg is None:
        from miratrade.config import load_user_config

        cfg = load_user_config()
    found = str(getattr(cfg.data, "usage_mode", PERSONAL) or PERSONAL).strip().lower()
    return found if found in MODES else PERSONAL


def allows(source: str, in_mode: str) -> bool:
    limit = RESTRICTED.get(source)
    return True if limit is None else in_mode in limit.allowed_in


def why_not(source: str, in_mode: str, translate=None) -> str:
    """The refusal, in words somebody can act on."""
    from miratrade.messages import sayer

    say = sayer(translate)
    limit = RESTRICTED[source]
    return say("{what} cannot be used in «{mode}» mode: {because} See docs/LICENCIAS.md. To use "
               "it, set the usage mode back to «personal».",
               what=limit.what, mode=in_mode, because=limit.because)


def check(source: str, cfg=None, translate=None) -> None:
    """Raise unless ``source`` is licensed for the mode in force. Called before fetching, not after."""
    in_mode = mode(cfg)
    if not allows(source, in_mode):
        raise NotAllowedHere(why_not(source, in_mode, translate))


def forbidden_in(in_mode: str) -> list[Restriction]:
    """What a mode rules out, for a screen that wants to say so before somebody tries."""
    return [r for r in RESTRICTED.values() if in_mode not in r.allowed_in]


def conflicts(cfg=None) -> list[str]:
    """Settings that contradict the mode in force, so a screen can say so rather than wait.

    Switching to commercial while the price source is still Yahoo is a mistake somebody makes once;
    finding out at three in the morning when a scheduled download raises is worse than finding out
    on the settings page.
    """
    if cfg is None:
        from miratrade.config import load_user_config

        cfg = load_user_config()
    in_mode = mode(cfg)
    out = []
    if getattr(cfg.data, "price_source", "") == "research" and not allows("research_prices", in_mode):
        out.append(why_not("research_prices", in_mode))
    return out
