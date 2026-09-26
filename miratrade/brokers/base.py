"""Broker-independent types and the ``BrokerClient`` interface.

The desktop app and the CLI talk only to this interface; ``schwab.py`` implements it against
the Schwab Trader API and ``simulated.py`` for practice and tests. Orders never go to a broker
directly: they pass through ``guard.OrderGuard`` (risk checks, mandatory preview, confirmation).
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

import pandas as pd


@dataclass
class Quote:
    symbol: str
    bid: float | None
    ask: float | None
    last: float | None
    change_pct: float | None = None
    volume: float | None = None
    time: datetime | None = None


@dataclass
class Position:
    symbol: str
    asset_type: str                     # EQUITY | OPTION | ...
    quantity: float                     # negative when short
    avg_price: float | None
    market_value: float | None
    day_pl: float | None = None


@dataclass
class Account:
    number_masked: str                  # "…1234": the full number is never shown or logged
    account_hash: str                   # what the API takes in URLs
    equity: float | None
    cash: float | None
    buying_power: float | None
    day_pl: float | None = None
    positions: list[Position] = field(default_factory=list)


@dataclass
class OrderRequest:
    """One entry order with its exits. ``stop_price`` / ``target_price`` are on the traded
    instrument: the stock price for shares, the option premium for options."""
    symbol: str                         # stock ticker, or Schwab option symbol ("AAPL  261016C00150000")
    quantity: int
    limit_price: float | None
    asset_type: str = "EQUITY"          # EQUITY | OPTION
    side: str = "BUY"                   # BUY opens (BUY / BUY_TO_OPEN); SELL closes
    stop_price: float | None = None
    target_price: float | None = None
    underlying: str | None = None       # for options: the stock, used by risk checks
    note: str = ""                      # e.g. the rule that produced the signal

    @property
    def multiplier(self) -> int:
        return 100 if self.asset_type == "OPTION" else 1

    @property
    def is_entry(self) -> bool:
        return self.side == "BUY"

    def risk_per_unit(self) -> float | None:
        if self.limit_price is None or self.stop_price is None:
            return None
        return (self.limit_price - self.stop_price) * self.multiplier

    def cost(self) -> float | None:
        return None if self.limit_price is None else self.limit_price * self.quantity * self.multiplier

    def fingerprint(self) -> str:
        """Stable hash of everything that defines the order: a preview is only valid for the
        exact order that was previewed."""
        d = {k: v for k, v in asdict(self).items() if k != "note"}
        return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]

    def describe(self) -> str:
        px = "market" if self.limit_price is None else f"limit {self.limit_price:g}"
        exits = []
        if self.stop_price is not None:
            exits.append(f"stop {self.stop_price:g}")
        if self.target_price is not None:
            exits.append(f"target {self.target_price:g}")
        return f"{self.side} {self.quantity} {self.symbol} {px}" + (f" ({', '.join(exits)})" if exits else "")


@dataclass
class OrderPreview:
    request: OrderRequest
    fingerprint: str
    accepted: bool                      # the broker would accept it
    messages: list[str]                 # broker rejects / warnings, and our own risk notes
    est_cost: float | None
    est_commission: float | None
    created_at: datetime
    raw: dict | None = None


@dataclass
class OrderStatus:
    order_id: str
    symbol: str
    status: str                         # WORKING, FILLED, CANCELED, REJECTED, ...
    side: str
    quantity: float
    filled: float
    price: float | None
    entered: datetime | None


OPEN_STATUSES = {"AWAITING_PARENT_ORDER", "AWAITING_CONDITION", "AWAITING_STOP_CONDITION",
                 "AWAITING_MANUAL_REVIEW", "ACCEPTED", "AWAITING_UR_OUT", "PENDING_ACTIVATION",
                 "QUEUED", "WORKING", "NEW", "AWAITING_RELEASE_TIME", "PENDING_ACKNOWLEDGEMENT"}


class BrokerClient(ABC):
    name: str = "broker"
    is_live: bool = False               # True: orders move real money

    @abstractmethod
    def accounts(self) -> list[Account]: ...

    @abstractmethod
    def quotes(self, symbols: list[str]) -> dict[str, Quote]: ...

    @abstractmethod
    def price_history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Daily OHLCV indexed by date."""

    @abstractmethod
    def option_chain(self, symbol: str, from_date: date, to_date: date,
                     contract_type: str = "ALL") -> pd.DataFrame:
        """One row per contract: symbol, underlying, type, expiry, dte, strike, bid, ask, mark,
        delta, iv, open_interest, volume."""

    @abstractmethod
    def orders(self, account_hash: str, since: datetime, until: datetime | None = None) -> list[OrderStatus]: ...

    @abstractmethod
    def transactions(self, account_hash: str, start: date, end: date) -> pd.DataFrame: ...

    @abstractmethod
    def preview(self, account_hash: str, request: OrderRequest) -> OrderPreview: ...

    @abstractmethod
    def place(self, account_hash: str, request: OrderRequest) -> str:
        """Send the order; returns the broker's order id. Called only by ``OrderGuard``."""

    @abstractmethod
    def cancel(self, account_hash: str, order_id: str) -> None: ...
