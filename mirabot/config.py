"""Tunable parameters for signal detection, trade simulation and edge discovery."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

CACHE_DIR = Path(os.environ.get("MIRABOT_CACHE", ".cache"))

# SEC requires a descriptive User-Agent with contact info on every request.
SEC_USER_AGENT = os.environ.get("MIRABOT_SEC_UA", "MiraBot research contact@example.com")


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
class EdgeParams:
    min_trades: int = 12                # smallest bucket reported as a rule
    train_frac: float = 0.6             # first 60% of the window discovers, last 40% validates
    max_rule_size: int = 3              # combine up to 3 conditions per rule
    min_lift_r: float = 0.10            # must beat the baseline by this much in train AND test
    fdr: float = 0.10                   # Benjamini-Hochberg false discovery rate


@dataclass
class Config:
    insider: InsiderParams = field(default_factory=InsiderParams)
    flow: FlowParams = field(default_factory=FlowParams)
    trade: TradeParams = field(default_factory=TradeParams)
    edge: EdgeParams = field(default_factory=EdgeParams)
