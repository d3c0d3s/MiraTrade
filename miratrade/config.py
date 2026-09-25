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


@dataclass
class FlowParams:
    min_premium_usd: float = 100_000    # smallest single print considered
    min_vol_oi_ratio: float = 1.5       # volume must exceed open interest (opening positions)
    max_dte: int = 60                   # short-dated = more conviction / time-sensitive
    max_otm_pct: float = 0.15           # strikes more than 15% OTM are lottery tickets, skipped
    lookback_days: int = 5


@dataclass
class TradeParams:
    stop_atr: float = 1.5               # initial stop distance in ATRs
    target_atr: float = 3.0             # profit target in ATRs (2R)
    max_hold_days: int = 15             # time stop
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
class Config:
    insider: InsiderParams = field(default_factory=InsiderParams)
    flow: FlowParams = field(default_factory=FlowParams)
    trade: TradeParams = field(default_factory=TradeParams)
    options: OptionParams = field(default_factory=OptionParams)
    edge: EdgeParams = field(default_factory=EdgeParams)
    regime: RegimeParams = field(default_factory=RegimeParams)
    survivorship: SurvivorshipParams = field(default_factory=SurvivorshipParams)
