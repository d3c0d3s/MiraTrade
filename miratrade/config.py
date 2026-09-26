"""Tunable parameters for signal detection, trade simulation and edge discovery."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

CACHE_DIR = Path(os.environ.get("MIRATRADE_CACHE", ".cache"))

# SEC requires a descriptive User-Agent with contact info on every request.
SEC_USER_AGENT = os.environ.get("MIRATRADE_SEC_UA", "MiraTrade research contact@example.com")


@dataclass
class InsiderParams:
    cluster_window_days: int = 10       # insiders buying within this window count as a cluster
    min_value_usd: float = 25_000       # ignore token purchases
    lookback_days: int = 30             # a signal stays "active" this long after the filing
    rank_cap_usd: float = 50_000_000    # one purchase counts at most this much when picking the
                                        # universe, so a takeover-sized buy doesn't crowd others out


@dataclass
class FlowParams:
    min_premium_usd: float = 100_000    # smallest single print considered
    min_vol_oi_ratio: float = 1.5       # volume must exceed open interest (opening positions)
    max_dte: int = 60                   # short-dated = more conviction / time-sensitive
    max_otm_pct: float = 0.15           # strikes more than 15% OTM are lottery tickets, skipped
    lookback_days: int = 5


@dataclass
class SmartMoneyParams:
    lookback_days: int = 30             # a 13D/13G filing stays "active" this long after it is filed
    # Index giants file 13Gs for every stock they hold past 5%: no information in those.
    passive_filers: tuple[str, ...] = ("VANGUARD", "BLACKROCK", "STATE STREET")
    short_window: int = 20              # short-volume ratio z-score against this many sessions
    short_min_periods: int = 10
    short_z: float = 1.0                # |z| at or above this counts as unusually low / high shorting


@dataclass
class TradeParams:
    stop_atr: float = 1.5               # initial stop distance in ATRs
    target_atr: float = 3.0             # profit target in ATRs (2R)
    max_hold_days: int = 15             # time stop
    min_price: float = 5.0              # skip signals on stocks below this (illiquid, few options)
    # Only events (insider buy, unusual flow, 13D/13G) open trades; technical setups are context
    # conditions of those events. True restores setups as triggers of their own.
    setups_trigger: bool = False
    entry: str = "next_open"            # enter at next session's open to avoid look-ahead bias


@dataclass
class OptionParams:
    enabled: bool = True
    target_delta: float = 0.65          # in-the-money-ish call: less theta decay, tracks the stock
    target_dte: int = 45                # monthly expiry nearest 45 days, so a 15-day swing
    min_dte: int = 30                   # never spends its last, fastest-decaying weeks
    iv_mult: float = 1.15               # implied vol usually trades above realised vol
    vol_floor: float = 0.15
    vol_cap: float = 1.50
    half_spread: float = 0.025          # paid on entry and exit (fraction of mid)
    rate: float = 0.04                  # risk-free rate for Black-Scholes


@dataclass
class EdgeParams:
    min_trades: int = 12                # smallest bucket reported as a rule
    train_frac: float = 0.6             # first 60% of the window discovers, last 40% validates
    max_rule_size: int = 3              # combine up to 3 conditions per rule
    min_lift_r: float = 0.10            # must beat the baseline by this much in train AND test
    fdr: float = 0.10                   # Benjamini-Hochberg false discovery rate
    wf_folds: int = 3                   # walk-forward: re-mine on all prior data, test the next slice
    wf_min_train_frac: float = 0.4      # the first fold trains on the first 40% of trades


@dataclass
class OutcomeParams:
    """"High profit" profiles measured for every event (see ``outcomes.py``)."""
    # (target, stop) pairs: the stop scales with the target (~1.6:1 reward to risk).
    targets: tuple[tuple[float, float], ...] = ((0.30, 0.20), (0.40, 0.25), (0.50, 0.30))
    long_months: int = 12               # long-term stock horizon
    call_dtes: tuple[int, ...] = (30, 45, 60)
    call_max_hold: int = 20             # sessions
    call_exit_days_before_expiry: int = 7
    event_cooldown: int = 20            # sessions: later events on the same ticker are the same move
    min_lift: float = 0.03              # a rule must beat the average event by 3 points of return
    enabled: bool = True


@dataclass
class ExperimentParams:
    """Stock-driven experiments (``experiments.py``): the event is read on the stock; the call is
    the vehicle. Pre-registered grid: change it here, never after looking at the results."""
    deltas: tuple[float, ...] = (0.50, 0.65, 0.80)
    dtes: tuple[int, ...] = (45, 60, 90, 120)       # monthly expiry at least this many days out
    stops: tuple[str, ...] = ("none", "pct10", "atr2", "atr3")
    exits: tuple[str, ...] = ("premium40_25", "fixed30", "run30_sma10", "run30_chandelier", "run30_macd")
    activation: float = 0.30            # "run" exits: from +30 % on, let the winner run …
    floor: float = 0.20                 # … but sell if it falls back to +20 %
    chandelier_atr: float = 2.0
    max_hold: int = 60                  # sessions
    exit_days_before_expiry: int = 14   # never hold a call into its last two weeks
    train_fraction: float = 0.6         # first 60 % of the window chooses, the rest confirms
    min_n: int = 100                    # a configuration needs this many trades to be ranked


@dataclass
class RegimeParams:
    trend_sma: int = 200                # bull/bear: SPY and its 50-day vs the 200-day average
    trend_min_periods: int = 120
    mid_sma: int = 50
    vol_window: int = 20                # high/low vol: 20-day realised vol vs its trailing median
    vol_lookback: int = 252
    vol_min_periods: int = 60


@dataclass
class SurvivorshipParams:
    min_history_bars: int = 60          # shorter price histories are dropped (and reported)
    delist_gap_days: int = 5            # data ending this many sessions before the rest = delisted
    delist_exit_haircut: float = 0.0    # extra loss on the last close for a delisted exit (0.3 = -30%)


@dataclass
class RiskParams:
    """Checked before any order reaches a broker (see ``brokers/guard.py``)."""
    risk_per_trade_pct: float = 1.0     # loss at the stop, as % of account equity
    risk_warn_pct: float = 2.0          # hard ceiling: above this the order is refused
    max_positions: int = 5
    daily_loss_limit_pct: float = 3.0   # today's loss past this % of equity: alerts only
    max_order_value_pct: float = 25.0   # one order's cost as % of equity
    min_price: float = 5.0
    allow_market_orders: bool = False   # entries are limit orders: no surprise fills
    require_stop: bool = True           # every entry carries its exit orders (bracket)


@dataclass
class BrokerParams:
    live_trading: bool = False          # real orders need this AND a typed confirmation per order
    preview_ttl_s: int = 120            # a preview is valid this long; place() needs a fresh one
    token_warn_hours: int = 24          # warn when the 7-day Schwab refresh token is this close
    callback_url: str = "https://127.0.0.1:8182"


# User settings (live trading on/off, risk limits) live outside the repo.
APP_DIR = Path(os.environ.get("MIRATRADE_HOME", Path(os.environ.get("APPDATA", Path.home())) / "MiraTrade"))


@dataclass
class Config:
    insider: InsiderParams = field(default_factory=InsiderParams)
    flow: FlowParams = field(default_factory=FlowParams)
    smart: SmartMoneyParams = field(default_factory=SmartMoneyParams)
    trade: TradeParams = field(default_factory=TradeParams)
    options: OptionParams = field(default_factory=OptionParams)
    edge: EdgeParams = field(default_factory=EdgeParams)
    outcomes: OutcomeParams = field(default_factory=OutcomeParams)
    experiment: ExperimentParams = field(default_factory=ExperimentParams)
    regime: RegimeParams = field(default_factory=RegimeParams)
    survivorship: SurvivorshipParams = field(default_factory=SurvivorshipParams)
    risk: RiskParams = field(default_factory=RiskParams)
    broker: BrokerParams = field(default_factory=BrokerParams)


def load_user_config(path: Path | None = None) -> Config:
    """Defaults overlaid with ``%APPDATA%/MiraTrade/settings.json`` (``{"risk": {...},
    "broker": {...}}``). Unknown keys are rejected so a typo can't silently disable a limit."""
    import json

    cfg = Config()
    path = path or APP_DIR / "settings.json"
    if not path.exists():
        return cfg
    data = json.loads(path.read_text(encoding="utf-8"))
    for section, values in data.items():
        target = getattr(cfg, section, None)
        if target is None:
            raise ValueError(f"settings.json: unknown section {section!r}")
        for key, value in values.items():
            if not hasattr(target, key):
                raise ValueError(f"settings.json: unknown setting {section}.{key}")
            setattr(target, key, value)
    return cfg
