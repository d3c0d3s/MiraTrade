"""Practice broker: same interface as Schwab, no money. Used by the app's practice mode and tests.

Orders fill against the prices you feed it with ``mark``: a working limit buy fills when the ask
(or last) reaches the limit, then its bracket exits watch the stop and target. A price that gaps
through a level fills at that price, like the backtest.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import pandas as pd

from miratrade.brokers.base import (Account, BrokerClient, OrderPreview, OrderRequest, OrderStatus,
                                    Position, Quote)


@dataclass
class _Order:
    id: str
    req: OrderRequest
    entered: datetime
    status: str = "WORKING"
    fill_price: float | None = None
    exits: dict = field(default_factory=dict)     # "stop"/"target" -> price, once the entry fills


class SimulatedBroker(BrokerClient):
    name = "simulated"
    is_live = False

    def __init__(self, cash: float = 25_000.0, prices: dict[str, Quote] | None = None,
                 history: dict[str, pd.DataFrame] | None = None, clock=lambda: datetime.now(timezone.utc)):
        self.start_cash = cash
        self.cash = cash
        self.positions: dict[str, Position] = {}
        self.prices: dict[str, Quote] = dict(prices or {})
        self.history = history or {}
        self.clock = clock
        self._orders: list[_Order] = []
        self._fills: list[dict] = []
        self._ids = itertools.count(1)

    # ------------------------------------------------------------------ data

    def _equity(self) -> float:
        value = 0.0
        for p in self.positions.values():
            q = self.prices.get(p.symbol)
            px = (q.last if q and q.last is not None else p.avg_price) or 0.0
            value += px * p.quantity * (100 if p.asset_type == "OPTION" else 1)
        return self.cash + value

    def accounts(self) -> list[Account]:
        today = self.clock().date()
        day_pl = sum(f["pl"] for f in self._fills if f["time"].date() == today and f["pl"] is not None)
        return [Account(number_masked="…SIM", account_hash="SIM", equity=self._equity(), cash=self.cash,
                        buying_power=self.cash, day_pl=day_pl, positions=list(self.positions.values()))]

    def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        return {s: self.prices[s] for s in symbols if s in self.prices}

    def price_history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        df = self.history.get(symbol, pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))
        return df.loc[str(start):str(end)] if len(df) else df

    def option_chain(self, symbol: str, from_date: date, to_date: date, contract_type: str = "ALL") -> pd.DataFrame:
        return pd.DataFrame(columns=["symbol", "underlying", "type", "expiry", "dte", "strike", "bid", "ask",
                                     "mark", "delta", "iv", "open_interest", "volume"])

    def orders(self, account_hash: str, since: datetime, until: datetime | None = None) -> list[OrderStatus]:
        return [OrderStatus(o.id, o.req.symbol, o.status, o.req.side, o.req.quantity,
                            o.req.quantity if o.status == "FILLED" else 0, o.req.limit_price, o.entered)
                for o in self._orders if o.entered >= since and (until is None or o.entered <= until)]

    def transactions(self, account_hash: str, start: date, end: date) -> pd.DataFrame:
        rows = [f for f in self._fills if start <= f["time"].date() <= end]
        return pd.DataFrame(rows, columns=["time", "type", "description", "symbol", "quantity", "price",
                                           "net_amount", "pl"])

    # ------------------------------------------------------------------ orders

    def preview(self, account_hash: str, request: OrderRequest) -> OrderPreview:
        cost = request.cost()
        msgs = [] if cost is None or cost <= self.cash else ["REJECT: not enough cash in the practice account"]
        return OrderPreview(request, request.fingerprint(), not msgs, msgs, cost, 0.0, self.clock())

    def place(self, account_hash: str, request: OrderRequest) -> str:
        o = _Order(str(next(self._ids)), request, self.clock())
        self._orders.append(o)
        return o.id

    def cancel(self, account_hash: str, order_id: str) -> None:
        for o in self._orders:
            if o.id == order_id and o.status == "WORKING":
                o.status = "CANCELED"

    def mark(self, prices: dict[str, Quote]) -> list[dict]:
        """Feed new prices; fills whatever they trigger and returns those fills."""
        self.prices.update(prices)
        done = []
        for o in self._orders:
            q = prices.get(o.req.symbol)
            if q is None or o.status not in ("WORKING", "FILLED"):
                continue
            px = q.last if q.last is not None else q.ask
            if o.status == "WORKING" and o.req.is_entry:
                ask = q.ask if q.ask is not None else px
                if o.req.limit_price is None or ask <= o.req.limit_price:
                    fill = ask if o.req.limit_price is None else min(ask, o.req.limit_price)
                    done.append(self._fill(o, fill, "BUY"))
                    o.status, o.fill_price = "FILLED", fill
                    o.exits = {k: v for k, v in (("stop", o.req.stop_price), ("target", o.req.target_price)) if v}
            elif o.status == "FILLED" and o.exits and px is not None:
                if "stop" in o.exits and px <= o.exits["stop"]:
                    done.append(self._fill(o, px, "SELL", reason="stop"))
                    o.exits = {}
                elif "target" in o.exits and px >= o.exits["target"]:
                    done.append(self._fill(o, px, "SELL", reason="target"))
                    o.exits = {}
        return done

    def _fill(self, o: _Order, price: float, side: str, reason: str = "") -> dict:
        req, mult = o.req, o.req.multiplier
        qty = req.quantity
        pos = self.positions.get(req.symbol)
        pl = None
        if side == "BUY":
            self.cash -= price * qty * mult
            if pos is None:
                self.positions[req.symbol] = Position(req.symbol, req.asset_type, qty, price, price * qty * mult)
            else:
                total = pos.quantity + qty
                pos.avg_price = (pos.avg_price * pos.quantity + price * qty) / total
                pos.quantity = total
        else:
            self.cash += price * qty * mult
            pl = (price - (pos.avg_price if pos else price)) * qty * mult
            if pos is not None:
                pos.quantity -= qty
                if pos.quantity <= 0:
                    del self.positions[req.symbol]
        fill = {"time": self.clock(), "type": "TRADE", "description": reason or side, "symbol": req.symbol,
                "quantity": qty if side == "BUY" else -qty, "price": price,
                "net_amount": (-1 if side == "BUY" else 1) * price * qty * mult, "pl": pl}
        self._fills.append(fill)
        return fill
