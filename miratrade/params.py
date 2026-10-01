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


# --------------------------------------------------------------------------- running it

# These are not hypotheses about the market — they are how the thing runs — so they are kept apart
# from ALL_GROUPS and are deliberately NOT in `attempts.TESTED_SECTIONS`: changing the language or
# the size of the account is not a claim about anything and must not tighten a correction.
OPERATION_GROUPS: tuple[Group, ...] = (
    Group("Risk", "What a suggestion is allowed to cost. Nothing here reaches your broker: these "
                  "size an illustration, and the decision and the order are yours.",
          (Field("risk", "sizing_capital", "Capital to size on", "The figure positions are sized "
                 "against. It is a number you type, not your real balance — sizing a suggestion to "
                 "somebody's actual account is a different thing to be doing.",
                 kind="money", low=0.0, high=100_000_000.0, step=1_000.0),
           Field("risk", "size_on_balance", "Use the broker balance instead",
                 "Off by default and worth leaving off. On, positions are sized against the real "
                 "account, which turns an analysis into advice about your money.", kind="bool"),
           Field("risk", "risk_per_trade_pct", "Risk per trade", "How much of the capital a single "
                 "trade may lose at its stop. 1 % is the usual starting point; above 2 % a normal "
                 "losing streak becomes hard to sit through.",
                 kind="percent", low=0.05, high=25.0, step=0.1, decimals=2, suffix=" %"),
           Field("risk", "max_positions", "Most positions at once", "More positions is less "
                 "concentration and also less attention per position.",
                 kind="integer", low=1, high=100),
           Field("risk", "daily_loss_limit_pct", "Stop for the day at", "A day's losses past this "
                 "and nothing new is suggested.",
                 kind="percent", low=0.1, high=100.0, step=0.5, decimals=1, suffix=" %"),
           Field("risk", "max_order_value_pct", "Most of the capital in one position",
                 "A cap on size regardless of what the stop distance allows.",
                 kind="percent", low=1.0, high=100.0, step=1.0, decimals=0, suffix=" %"))),

    Group("Data", "Where prices come from and how far back to fetch. The source matters legally as "
                  "well as practically — see docs/LICENCIAS.md.",
          (Field("data", "usage_mode", "Who this copy is for",
                 "A licensing question, not a feature one. Outside «only me» the congressional "
                 "disclosures and the public-website prices stop being allowed, and the restricted "
                 "sources refuse rather than quietly carry on. See docs/LICENCIAS.md.",
                 kind="choice", choices=(("personal", "Only me"),
                                         ("feedback", "A few invited people"),
                                         ("commercial", "Subscribers"))),
           Field("data", "price_source", "Price source", "«Your account» uses your own broker data, "
                 "which its terms allow for you. «Public websites» is Yahoo and Stooq, whose terms "
                 "allow personal, non-commercial use at most.",
                 kind="choice", choices=(("schwab", "Your Schwab account"),
                                         ("research", "Public websites (personal research only)"))),
           Field("data", "scan_days", "Days to download", "How far back «Update data» asks for. "
                 "Days already downloaded are skipped, so raising it is cheap.",
                 kind="integer", low=1, high=3650, suffix=" days"),
           Field("data", "cap_tier", "Company size shown", "A view over what is stored, never a "
                 "reason to download. Insiders buy mostly in small companies — which is also where "
                 "options often cannot be traded, and the liquidity check is what should decide "
                 "that, not this.",
                 kind="choice", choices=(("all", "All"), ("mega", "Mega"), ("large", "Large"),
                                         ("mid", "Mid"), ("small", "Small"), ("micro", "Micro"),
                                         ("mid_plus", "Mid and up"))),
           Field("data", "auto_refresh_minutes", "Download by itself every", "0 turns it off. It "
                 "only runs while New York is still filing.",
                 kind="integer", low=0, high=1440, suffix=" min"))),

    Group("Notifications", "Where a new event is announced. Every message carries the honest note, "
                           "because a list of tickers reads as a recommendation unless it is told "
                           "otherwise.",
          (Field("notify", "ntfy_topic", "ntfy topic", "A push to your phone. A public ntfy topic "
                 "is readable by anyone who knows its name, so use a long random one.", kind="text"),
           Field("notify", "email_to", "Send email to", "Email carries the detail: the evidence, "
                 "the contract, the exits and the warnings.", kind="text"),
           Field("notify", "email_from", "Send email from", "The account that sends it.",
                 kind="text"),
           Field("notify", "smtp_host", "SMTP server", "For Gmail, an app password — never the "
                 "account password. It goes in the credential manager, never in a file.",
                 kind="text"),
           Field("notify", "smtp_port", "SMTP port", "587 for STARTTLS, 465 for SSL.",
                 kind="integer", low=1, high=65535),
           Field("notify", "only_tradeable", "Only what can be traded", "Leaves out events whose "
                 "contract fails the liquidity check. A signal you cannot get filled on is not a "
                 "signal.", kind="bool"),
           Field("notify", "max_events", "Most events per message", "A long list stops being read.",
                 kind="integer", low=1, high=500))),

    Group("Interface", "How the app presents itself.",
          (Field("ui", "language", "Language", "English is the source language of every screen; "
                 "Spanish is translated.",
                 kind="choice", choices=(("en", "English"), ("es", "Español"))),)),
)

# `broker` is deliberately absent from both lists. It holds `live_trading`, and a front-end that
# cannot send an order must not be able to switch on the thing that can. That stays where the
# credentials are: on the machine, in front of the person.


NEWS_GROUPS: tuple[Group, ...] = (
    Group("News (FinBERT)",
          "Reads the prose of an 8-K and says whether it is worded positively or negatively. "
          "It is OFF by default, and that is the honest setting: no news signal here has survived "
          "an out-of-sample test. What it shows is what was published — never a forecast.",
          (Field("sentiment", "enabled", "Read the filings",
                 "On, each event shows how the filings around it are worded. It changes nothing "
                 "about which events are found, and no number on any screen depends on it.",
                 kind="bool"),
           Field("sentiment", "backend", "How to run the model",
                 "ONNX installs about 250 MB and gives the same answer as the full framework, "
                 "which installs about 2.5 GB. Use the heavy one only if ONNX will not build.",
                 kind="choice", choices=(("onnx", "ONNX (light)"),
                                         ("transformers", "Full framework (heavy)"))),
           Field("sentiment", "model", "Model", "FinBERT is a classifier trained on financial "
                 "language: it returns positive, negative or neutral. It is not a chat model and "
                 "cannot be prompted.", kind="text"),
           Field("sentiment", "min_confidence", "Least confidence to call it",
                 "Below this the answer is «unclear», which is a real answer. A weak guess dressed "
                 "as a verdict is worse than no verdict.",
                 kind="number", low=0.0, high=1.0, step=0.05, decimals=2),
           Field("sentiment", "neutral_band", "Treat as neutral within",
                 "How far from the middle the wording has to lean before it counts as leaning at "
                 "all.", kind="number", low=0.0, high=1.0, step=0.05, decimals=2),
           Field("sentiment", "window_days", "Filings from the last",
                 "How far back from an event a filing is read.",
                 kind="integer", low=1, high=180, suffix=" days"),
           Field("sentiment", "max_headlines", "Most passages per event",
                 "A long filing is scored in pieces and averaged, so one strongly worded sentence "
                 "does not decide the whole thing.", kind="integer", low=1, high=200))),
)


def offered(groups=None) -> frozenset[str]:
    """The sections a form offers, and therefore the only ones a front-end may write.

    `broker` is not among them and that is the point: it holds `live_trading`, and a front-end that
    cannot send an order must not be able to switch on the thing that can. Deciding this from the
    form definitions rather than from a second hand-written list means the two cannot drift, and
    the one that would drift silently is the safety one.
    """
    chosen = groups if groups is not None else (ALL_GROUPS + OPERATION_GROUPS + NEWS_GROUPS)
    return frozenset(f.section for g in chosen for f in g.fields)
