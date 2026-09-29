"""What the parameter forms offer, described once, away from Qt.

The Signals and Reports screens each get a form of the settings that decide what they do — the
shape of a TradingView indicator's settings dialog. The description of those fields lives here, not
in the widget, for three reasons: the web front-end will need exactly the same list, a test can
check the whole set without starting a window, and the sentence explaining a threshold belongs next
to the threshold rather than three files away.

Every field says what it *means for a trade*, not what it does to the code. "Smallest purchase that
counts" with "below this, a director buying a few hundred dollars of stock is noise, not a signal"
is a setting someone can reason about. ``min_value_usd: float`` is not.

Nothing here validates a value into safety: the ranges stop a typo, not a bad idea. What stops a
bad idea is :mod:`miratrade.attempts`, which counts how many of these a result was chosen from.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from miratrade.config import Config


@dataclass(frozen=True)
class Field:
    """One setting, as a person meets it."""
    section: str
    key: str
    label: str                       # English source; the screen translates it
    help: str                        # why it matters for a trade
    kind: str = "number"             # number | money | percent | integer | bool | choice | text
    low: float = 0.0
    high: float = 1_000_000_000.0
    step: float = 1.0
    decimals: int = 0
    choices: tuple[tuple[str, str], ...] = ()      # (value, label) for kind="choice"
    suffix: str = ""

    def default(self) -> Any:
        return getattr(getattr(Config(), self.section), self.key)


@dataclass(frozen=True)
class Group:
    """A box in the form. One idea per box, in the order a person thinks about them."""
    title: str
    note: str
    fields: tuple[Field, ...]


# --------------------------------------------------------------------------- what counts as an event

EVENT_GROUPS: tuple[Group, ...] = (
    Group("Insider purchases", "Form 4 code P: an open-market buy with the insider's own money. "
                               "Awards, exercises and gifts are never counted, whatever these say.",
          (Field("insider", "min_value_usd", "Smallest purchase that counts", "Below this, a "
                 "director buying a few hundred dollars of stock is noise. Raising it keeps the "
                 "purchases somebody had to think about — and drops most of the events.",
                 kind="money", low=0, high=10_000_000, step=5_000),
           Field("insider", "cluster_window_days", "Days that make a cluster", "Several insiders "
                 "buying within this many days of each other is treated as one decision by the "
                 "people who know the company, not as several unrelated ones.",
                 kind="integer", low=1, high=120, suffix=" days"),
           Field("insider", "lookback_days", "How long a purchase keeps counting", "A filing stays "
                 "'active' this long. Longer finds more events per company and makes each one mean "
                 "less; shorter is stricter about what is recent.",
                 kind="integer", low=1, high=365, suffix=" days"))),

    Group("Unusual option flow", "Volume above open interest means positions being opened, not "
                                 "closed. Chains are only read for days that were captured.",
          (Field("flow", "min_premium_usd", "Smallest print", "The total paid for one print. Small "
                 "prints are retail; the premise of this signal is somebody putting real money on "
                 "a short clock.", kind="money", low=0, high=50_000_000, step=25_000),
           Field("flow", "min_vol_oi_ratio", "Volume over open interest", "Above 1, more contracts "
                 "traded today than were open at the start: new positions. Under 1 it can all be "
                 "closing.", kind="number", low=0.1, high=20.0, step=0.1, decimals=1),
           Field("flow", "min_open_interest", "Least open interest", "A contract with almost no "
                 "open interest gives a spectacular ratio on almost no money. This is the floor "
                 "under the arithmetic.", kind="integer", low=0, high=100_000),
           Field("flow", "max_dte", "Longest expiry", "Short-dated is more time-sensitive and "
                 "usually more conviction; it is also where hedging lives, so this cuts both ways.",
                 kind="integer", low=1, high=730, suffix=" days"),
           Field("flow", "max_otm_pct", "Furthest out of the money", "Strikes beyond this are "
                 "lottery tickets. 0.15 = 15 % above the share price.",
                 kind="number", low=0.0, high=2.0, step=0.05, decimals=2))),

    Group("Smart money", "13D means an active stake with intent; 13G is usually an index fund "
                         "crossing 5 % mechanically. FINRA's off-exchange volume is not short "
                         "interest.",
          (Field("smart", "lookback_days", "How long a filing keeps counting", "As with insiders: "
                 "how long a new stake stays an active event.",
                 kind="integer", low=1, high=365, suffix=" days"),)),
)

# --------------------------------------------------------------------------- what is then traded

TRADE_GROUPS: tuple[Group, ...] = (
    Group("Entry and exits", "Every event is traded the same way, so that the conditions around it "
                             "can be compared. These are multiples of the stock's own volatility "
                             "(ATR), not fixed percentages: a 5 % stop means something different on "
                             "a utility and on a biotech.",
          (Field("trade", "stop_atr", "Stop, in ATR", "Below this much of the daily range, the "
                 "trade is wrong. Tighter stops out more often on noise alone.",
                 kind="number", low=0.2, high=10.0, step=0.1, decimals=1),
           Field("trade", "target_atr", "Target, in ATR", "Where it is taken. Together with the "
                 "stop this sets how often it has to work to pay.",
                 kind="number", low=0.2, high=20.0, step=0.1, decimals=1),
           Field("trade", "max_hold_days", "Time stop", "Sessions after which it is closed whatever "
                 "it is doing. Capital held in a trade that is going nowhere is capital.",
                 kind="integer", low=1, high=500, suffix=" sessions"),
           Field("trade", "min_price", "Cheapest share", "Signals on shares under this are skipped: "
                 "they are thin, the spread is a large part of the price, and most have no usable "
                 "option market at all.", kind="money", low=0.0, high=1_000.0, step=1.0,
                 decimals=2))),

    Group("Contract", "What a profile buys when the instrument is an option. Prices in the "
                      "backtest are modelled from the stock, never quotes.",
          (Field("options", "target_delta", "Delta", "How much of the share's move the option "
                 "follows. 0.75–0.85 behaves like the stock with leverage; 0.30 is mostly a "
                 "lottery ticket with a deadline.",
                 kind="number", low=0.05, high=0.95, step=0.05, decimals=2),
           Field("options", "target_dte", "Days to expiry", "Longer costs more and decays slower. "
                 "If an effect takes two months, a 30-day call cannot express it.",
                 kind="integer", low=1, high=900, suffix=" days"),
           Field("options", "min_dte", "Never closer than", "A contract is not chosen inside this "
                 "many days of expiry, where decay is fastest and a few quiet sessions cost more "
                 "than the move is worth.", kind="integer", low=1, high=400, suffix=" days"))),

    Group("Tradeable at all", "A signal you cannot get filled on is not a signal. These are "
                              "checked against the stored chain, and the verdict says so plainly "
                              "on the contract card.",
          (Field("liquidity", "max_spread_pct", "Widest spread", "Bid to ask as a percentage of "
                 "the mid. You pay half of it getting in and half getting out.",
                 kind="percent", low=0.0, high=100.0, step=0.5, decimals=1, suffix=" %"),
           Field("liquidity", "min_open_interest", "Least open interest", "How many contracts are "
                 "open. Thin contracts move on your own order.",
                 kind="integer", low=0, high=100_000),
           Field("liquidity", "max_target_eaten_pct", "Most of the target the round trip may eat",
                 "The backtest charged no spread. If getting in and out costs a third of what you "
                 "were aiming for, the edge it measured was never there to take.",
                 kind="percent", low=0.0, high=100.0, step=1.0, decimals=0, suffix=" %"))),
)

ALL_GROUPS = EVENT_GROUPS + TRADE_GROUPS


def fields(groups=ALL_GROUPS) -> tuple[Field, ...]:
    return tuple(f for g in groups for f in g.fields)


def validate(groups=ALL_GROUPS) -> list[str]:
    """Every field names a setting that really exists, and its default sits inside its range.

    A form field pointing at a setting that was renamed silently does nothing — the worst kind of
    control, because it looks like it works. A test runs this.
    """
    from miratrade.prefs import USER_SECTIONS

    problems = []
    for f in fields(groups):
        if f.section not in USER_SECTIONS:
            problems.append(f"{f.section}.{f.key}: {f.section} is not a storable section")
            continue
        section = getattr(Config(), f.section, None)
        if section is None or not hasattr(section, f.key):
            problems.append(f"{f.section}.{f.key}: no such setting")
            continue
        value = f.default()
        if f.kind in ("number", "money", "percent", "integer") and not (f.low <= value <= f.high):
            problems.append(f"{f.section}.{f.key}: default {value} is outside {f.low}–{f.high}")
    return problems
