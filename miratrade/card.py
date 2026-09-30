"""Everything shown about one event, assembled in one place.

The Signals screen shows an event as four things: what was filed, what similar events did, the
contract a profile would buy, and the two reasons not to take it — the spread and a results
announcement inside the holding period. Each of those already exists as a function somewhere in the
core; this is the assembly, so that a screen, a web page and an email all show the same event the
same way instead of three near-copies drifting apart.

Two habits it keeps, and both matter more than they look:

* **Missing is not false.** A contract with no stored chain gets the share's own liquidity and says
  that is what it is. No earnings calendar means "not known", never "no report due". An absent
  warning is not a promise, and a screen that cannot tell the difference will eventually present
  one as the other.
* **Nothing here is a quote.** The contract is modelled from the stock with Black-Scholes on its
  realised volatility, exactly as the backtest priced it. It says so, every time.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from miratrade.config import Config
from miratrade.scan import DEFAULT_VARIANT, contract_for, evidence


@dataclass
class Card:
    """One event, with everything known about it and nothing invented."""
    ticker: str
    signal_date: str
    close: float | None = None
    what: str = ""
    kinds: list[str] = field(default_factory=list)
    contract: dict | None = None
    contract_note: str = ""
    evidence: dict | None = None
    tradeable: dict | None = None
    earnings: dict | None = None
    honesty: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def what_of(event: dict, translate=None) -> str:
    """What was filed, in the reader's language.

    The scan stores both the rendered English (`what`) and the pieces it was built from
    (`what_parts`, a JSON list of template plus values) precisely so that a sentence written
    months ago can still be read in another language today. Prefer the pieces; fall back to the
    rendered text when an old row has none.
    """
    import json

    from miratrade.messages import money, note

    parts = event.get("what_parts")
    if parts:
        try:
            loaded = json.loads(parts) if isinstance(parts, str) else parts
            if loaded:
                return note([(t, f) for t, f in loaded], translate, money)
        except (TypeError, ValueError):
            pass
    return str(event.get("what") or "")


def _plain(value: Any) -> Any:
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return _plain(value.item())
        except (ValueError, AttributeError):
            pass
    return value


def build(event: dict, bars: pd.DataFrame | None, db=None, cfg: Config | None = None,
          variant: str = DEFAULT_VARIANT, history: pd.DataFrame | None = None,
          rules: pd.DataFrame | None = None, honesty: str = "", translate=None) -> Card:
    """Assemble one event's card. Reads; never downloads, never prices from a broker.

    ``translate`` is whoever is showing it. The sentences travel as English source and are turned
    into the reader's language here, the same arrangement the rest of the core uses, so a card is
    not built twice to be read in two languages.
    """
    from miratrade.messages import sayer
    from miratrade.scan import EVENT_LABELS

    say = sayer(translate)
    cfg = cfg or Config()
    ticker = str(event.get("ticker", "")).upper()
    when = event.get("signal_date")
    card = Card(ticker=ticker, signal_date=str(_plain(when) or ""),
                close=_plain(event.get("close")),
                what=what_of(event, translate),
                kinds=[say(label) for key, label in EVENT_LABELS.items() if event.get(key)],
                honesty=honesty)

    # What similar past events did. With no report to compare against this stays None rather than
    # becoming a confident-looking row of zeros.
    if history is not None and len(history):
        found = evidence(event, history, variant, rules)
        card.evidence = {"variant": variant, "n": found.n,
                         "target": _plain(found.target), "stop": _plain(found.stop),
                         "neither": _plain(found.neither),
                         "mean_return": _plain(found.mean_return),
                         "similar_to": list(found.similar_to), "rules": list(found.rules),
                         "sentence": found.say(translate)}

    if bars is None or not len(bars):
        card.contract_note = say("No price bars stored for this company, so no contract can be "
                                 "shown.")
        return card

    contract = contract_for(bars, when, variant, cfg)
    if contract is None:
        card.contract_note = say("This profile buys the shares, not an option.")
    else:
        card.contract = {k: _plain(v) for k, v in contract.items()}
        card.contract_note = say("Modelled from the stock with Black-Scholes on its realised "
                                 "volatility, the same way the analysis priced it. Not a quote.")
        card.tradeable = _tradeable(db, ticker, contract, bars, cfg, translate)
        card.earnings = _earnings(db, ticker, contract, translate)
    return card


def _tradeable(db, ticker: str, contract: dict, bars: pd.DataFrame, cfg: Config,
               translate=None) -> dict | None:
    """The spread verdict, from the stored chain if there is one and from the share if not.

    Both are reported even when they pass, because "checked and fine" and "never checked" must not
    look the same.
    """
    from miratrade.liquidity import check_stored, underlying_liquidity

    try:
        verdict = None
        if db is not None and contract.get("expiry") is not None:
            verdict = check_stored(db, ticker, contract["expiry"], contract["strike"],
                                   target_pct=contract.get("target_pct", 0.0), cfg=cfg)
            if not verdict.measured:
                verdict = None
        if verdict is None:
            verdict = underlying_liquidity(bars, cfg)
        return {"ok": bool(verdict.ok), "reason": verdict.say(translate, None),
                "measured": bool(verdict.measured),
                "spread_pct": _plain(verdict.spread_pct),
                "open_interest": _plain(verdict.open_interest),
                "eats_target": _plain(verdict.eats_target)}
    except Exception:
        return None


def _earnings(db, ticker: str, contract: dict, translate=None) -> dict | None:
    """The report this contract would sit through, or that we do not know of one.

    ``known`` is the whole point of this shape: a missing calendar and a company that does not
    report look identical from here, and only one of them is good news.
    """
    from miratrade.data.earnings import covered_tickers, crosses_earnings
    from miratrade.messages import sayer

    say = sayer(translate)
    if db is None or contract.get("expiry") is None:
        return None
    try:
        expiry = pd.Timestamp(contract["expiry"]).date()
        known = bool(covered_tickers(db))
        crossing = crosses_earnings(db, ticker, date.today(), expiry) if known else None
        return {"known": known, "date": crossing.isoformat() if crossing else None,
                "note": (say("Reports on this date, before the contract expires: the premium "
                             "usually falls sharply the morning after.") if crossing else
                         "" if known else
                         say("No earnings calendar downloaded, so this is not known — which is not "
                             "the same as there being no report due."))}
    except Exception:
        return None
