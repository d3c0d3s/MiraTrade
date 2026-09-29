"""Whether a contract can actually be traded, and what the spread costs against the target.

Everything else in MiraTrade asks whether a move is likely. This asks a different question that is
easier to answer and just as capable of deciding the result: **if the move happened, could you get in
and out, and how much of the gain would the quotes take?**

The number that matters is not the spread on its own. Our profiles aim for +30 % to +40 % on the
premium, so a round trip costing 10 % has eaten a quarter of the target before the stock has moved at
all — and the backtest never charged it, because it priced every contract at a modelled mid. That gap
is what :func:`target_eaten` measures.

Open interest matters for a separate reason. A contract with almost none has nobody on the other
side, so the quote is decoration: you move the price yourself getting in and find no bid getting out.
It is also the caveat the volume/open-interest filter needs, since an open interest of 3 produces a
spectacular ratio on almost no money.

Nothing here predicts anything. It only says whether a suggestion is one a person could act on.
"""
from __future__ import annotations

from typing import NamedTuple

import pandas as pd

from miratrade.config import Config
from miratrade.messages import sayer


class Verdict(NamedTuple):
    """Whether a contract is tradeable and why.

    The reason travels as an English template plus its values, the same way the rest of the domain
    carries a sentence, so a screen can show it translated and the console can print it as it is. A
    suggestion dropped without a reason teaches nothing.
    """
    ok: bool
    template: str
    fields: dict
    spread_pct: float | None = None       # the quoted spread as a share of the mid, in %
    eats_target: float | None = None      # the round trip as a share of the profile's target, in %
    open_interest: float | None = None

    @property
    def measured(self) -> bool:
        """Whether anything was actually measured. An unmeasured contract has not passed."""
        return self.spread_pct is not None or self.open_interest is not None

    def say(self, translate=None, number=None) -> str:
        """The reason, in the interface's language and its number format.

        The fields hold raw numbers, not formatted text, so the figures come out in the reader's own
        convention — writing "87,350" inside a Spanish sentence is wrong twice over.
        """
        write = number or (lambda v: f"{v:,.0f}")
        filled = {k: write(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
                  for k, v in self.fields.items()}
        return sayer(translate)(self.template, **filled)

    def __str__(self) -> str:
        return self.say()


def mid(bid, ask) -> float | None:
    """The midpoint, or ``None`` when the quotes do not make a market (crossed, missing, zero ask)."""
    if bid is None or ask is None or not pd.notna(bid) or not pd.notna(ask):
        return None
    bid, ask = float(bid), float(ask)
    return (bid + ask) / 2 if ask > 0 and bid >= 0 and ask >= bid else None


def spread_pct(bid, ask) -> float | None:
    """The gap between the quotes as a percentage of the mid."""
    m = mid(bid, ask)
    return None if m is None or m <= 0 else (float(ask) - float(bid)) / m * 100


def round_trip_pct(bid, ask) -> float | None:
    """What buying at the ask and selling at the bid costs, as a percentage of the mid.

    It is the whole spread, not half of it: you cross it going in and again coming out.
    """
    return spread_pct(bid, ask)


def target_eaten(bid, ask, target_pct: float) -> float | None:
    """The share of a profile's target the round trip consumes, in per cent.

    ``target_pct`` is the profile's aim as a fraction (0.40 for +40 %). A round trip of 10 % against a
    40 % target gives 25: a quarter of the intended gain is gone before the stock moves.
    """
    cost = round_trip_pct(bid, ask)
    return None if cost is None or not target_pct else cost / (float(target_pct) * 100) * 100


def check_contract(bid=None, ask=None, open_interest=None, target_pct: float = 0.0,
                   cfg: Config | None = None) -> Verdict:
    """The verdict on one contract, from its quotes and its open interest.

    With neither known the verdict is **not** a pass: it says it was never checked, so a caller can
    tell "fine" from "unmeasured" and put the right thing on screen.
    """
    p = (cfg or Config()).liquidity
    oi = float(open_interest) if open_interest is not None and pd.notna(open_interest) else None
    gap = spread_pct(bid, ask)
    eats = target_eaten(bid, ask, target_pct) if target_pct else None
    numbers = {"spread_pct": gap, "eats_target": eats, "open_interest": oi}

    if gap is None and oi is None:
        return Verdict(False, "Not checked: no quotes and no open interest stored for this contract. "
                              "That is not the same as fine.", {}, **numbers)
    if oi is not None and oi < p.min_open_interest:
        return Verdict(False, "Open interest of {oi} is under {floor}: with almost nobody on the "
                              "other side the quote is decoration — you move the price getting in "
                              "and find no bid getting out.",
                       {"oi": oi, "floor": p.min_open_interest}, **numbers)
    if gap is not None and gap > p.max_spread_pct:
        if eats is not None:
            return Verdict(False, "The spread is {gap} % of the mid, so entering and leaving costs "
                                  "{eats} % of this profile's whole target before the stock moves.",
                           {"gap": round(gap), "eats": round(eats)}, **numbers)
        return Verdict(False, "The spread is {gap} % of the mid, over the {cap} % limit.",
                       {"gap": round(gap), "cap": round(p.max_spread_pct)}, **numbers)
    if eats is not None and eats > p.max_target_eaten_pct:
        return Verdict(False, "Entering and leaving costs {eats} % of this profile's whole target: "
                              "the move has to be that much bigger just to break even.",
                       {"eats": round(eats)}, **numbers)
    if gap is None:
        return Verdict(True, "Open interest of {oi} is enough; the spread is not stored, so what the "
                             "round trip costs is unknown.", {"oi": oi}, **numbers)
    return Verdict(True, "Tradeable: spread {gap} % of the mid"
                         + (", {eats} % of the target" if eats is not None else "")
                         + (", open interest {oi}" if oi is not None else "") + ".",
                   {k: v for k, v in (("gap", round(gap)),
                                      ("eats", round(eats) if eats is not None else None),
                                      ("oi", oi))
                    if v is not None}, **numbers)


def stored_quotes(db, ticker: str, expiry, strike: float, kind: str = "call") -> dict | None:
    """The most recent stored quotes and open interest for one contract, or ``None``.

    This is what the daily chain capture is for: without it the only thing known about a suggested
    contract is what Black-Scholes made up, which has no spread and no open interest at all.
    """
    row = db.execute(
        "SELECT bid, ask, open_interest, volume, date FROM option_flow "
        "WHERE upper(ticker) = ? AND expiry = ? AND abs(strike - ?) < 0.005 "
        "AND lower(substr(type, 1, 1)) = ? ORDER BY date DESC LIMIT 1",
        (ticker.upper(), pd.Timestamp(expiry).strftime("%Y-%m-%d"), float(strike),
         kind[0].lower())).fetchone()
    return dict(row) if row is not None else None


def check_stored(db, ticker: str, expiry, strike: float, target_pct: float = 0.0,
                 kind: str = "call", cfg: Config | None = None) -> Verdict:
    """The verdict for a contract using whatever the chain capture stored for it."""
    found = stored_quotes(db, ticker, expiry, strike, kind) if db is not None else None
    if found is None:
        return check_contract(target_pct=target_pct, cfg=cfg)
    return check_contract(found.get("bid"), found.get("ask"), found.get("open_interest"),
                          target_pct=target_pct, cfg=cfg)


def underlying_liquidity(bars: pd.DataFrame, cfg: Config | None = None) -> Verdict:
    """A fallback when nothing is known about the chain: is the *stock* liquid enough to have one?

    A share trading thirty thousand times a day does not have an option market worth the name. This
    says nothing about a particular contract, and it is reported as the weaker statement it is.
    """
    p = (cfg or Config()).liquidity
    if bars is None or not len(bars) or "volume" not in bars:
        return Verdict(False, "No price history, so not even the stock's liquidity is known.", {})
    typical = float(pd.to_numeric(bars["volume"], errors="coerce").tail(20).median())
    if not pd.notna(typical):
        return Verdict(False, "No price history, so not even the stock's liquidity is known.", {})
    if typical < p.min_underlying_volume:
        return Verdict(False, "The share trades about {vol} a day, under {floor}: a stock this thin "
                              "rarely has an option market worth using.",
                       {"vol": typical, "floor": p.min_underlying_volume})
    return Verdict(True, "The share trades about {vol} a day. Nothing is stored about the contract "
                         "itself, so its spread is unknown.", {"vol": typical})
