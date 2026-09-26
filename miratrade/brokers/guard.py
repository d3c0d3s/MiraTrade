"""The only way an order reaches a broker.

1. **Risk checks** (``RiskParams``): a stop on every entry, risk per trade against equity, order
   size, open positions, today's loss, minimum price, no market entries.
2. **Preview first**: ``place`` needs an accepted preview of the *identical* order made in the
   last ``preview_ttl_s`` seconds. A preview is used once.
3. **Live money** needs ``BrokerParams.live_trading`` switched on *and*, per order, the typed
   confirmation ``"BUY 10 ACME"`` (side, quantity, symbol).
4. **No automatic retries.** If sending fails midway the order may or may not exist: the guard
   looks it up and reports, and never sends a second copy by itself.
5. **Stop everything**: ``stop_all`` cancels every pending entry and blocks new entries until
   ``resume``; the stops protecting open positions stay. The block survives restarts (a file
   in the app folder).
6. **Journal**: every preview, submission, result and cancel is appended to ``orders.jsonl``
   (masked account, no credentials).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from miratrade.brokers.base import OPEN_STATUSES, Account, BrokerClient, OrderPreview, OrderRequest
from miratrade.config import APP_DIR, Config


ENTRY_SIDES = {"BUY", "BUY_TO_OPEN"}


class OrderRefused(RuntimeError):
    """The guard would not send the order; nothing reached the broker."""


class OrderUncertain(RuntimeError):
    """The order was sent but the outcome is unknown; check the broker before doing anything."""


@dataclass
class CheckResult:
    refusals: list[str]                 # any of these blocks the order
    notes: list[str]                    # shown to the user, do not block
    risk_usd: float | None = None
    risk_pct: float | None = None

    @property
    def ok(self) -> bool:
        return not self.refusals


def expected_confirmation(req: OrderRequest) -> str:
    return f"{req.side} {req.quantity} {req.symbol}"


def _norm(text: str) -> str:
    return " ".join(text.upper().split())


class OrderGuard:
    def __init__(self, broker: BrokerClient, cfg: Config | None = None, app_dir: Path | None = None,
                 clock=lambda: datetime.now(timezone.utc)):
        self.broker = broker
        self.cfg = cfg or Config()
        self.app_dir = Path(app_dir or APP_DIR)
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._previews: dict[str, OrderPreview] = {}

    # ------------------------------------------------------------------ checks

    @property
    def halt_file(self) -> Path:
        return self.app_dir / f"HALTED-{self.broker.name}"

    def halted(self) -> bool:
        return self.halt_file.exists()

    def suggest_quantity(self, account: Account, entry: float, stop: float, multiplier: int = 1) -> int:
        """Units that risk ``risk_per_trade_pct`` of equity between entry and stop."""
        per_unit = (entry - stop) * multiplier
        if not account.equity or per_unit <= 0:
            return 0
        return max(0, math.floor(account.equity * self.cfg.risk.risk_per_trade_pct / 100 / per_unit))

    def check(self, account: Account, req: OrderRequest) -> CheckResult:
        r = self.cfg.risk
        refusals, notes = [], []
        if req.quantity < 1 or int(req.quantity) != req.quantity:
            refusals.append("Quantity must be a whole number of at least 1.")
        if not req.is_entry:
            return CheckResult(refusals, notes)         # closing orders only reduce risk

        if self.halted():
            refusals.append("Trading is stopped ('Detener todo'). Resume it before opening positions.")
        if req.limit_price is None and not r.allow_market_orders:
            refusals.append("Entries must be limit orders (market entries are disabled).")
        if req.asset_type == "EQUITY" and req.limit_price is not None and req.limit_price < r.min_price:
            refusals.append(f"Price below the ${r.min_price:g} minimum.")
        if r.require_stop and req.stop_price is None:
            refusals.append("Every entry needs a stop (bracket order).")
        if req.stop_price is not None and req.limit_price is not None and req.stop_price >= req.limit_price:
            refusals.append("The stop must be below the entry price.")
        if req.target_price is not None and req.limit_price is not None and req.target_price <= req.limit_price:
            refusals.append("The target must be above the entry price.")

        equity = account.equity
        if not equity or equity <= 0:
            refusals.append("Account equity unknown: cannot size the risk.")
            return CheckResult(refusals, notes)

        risk_usd = risk_pct = None
        per_unit = req.risk_per_unit()
        if per_unit is not None and per_unit > 0:
            risk_usd = per_unit * req.quantity
            risk_pct = risk_usd / equity * 100
            if risk_pct > r.risk_warn_pct:
                refusals.append(f"Risk {risk_pct:.1f}% of the account exceeds the {r.risk_warn_pct:g}% ceiling.")
            elif risk_pct > r.risk_per_trade_pct:
                notes.append(f"Risk {risk_pct:.1f}% is above your {r.risk_per_trade_pct:g}% per-trade target.")
        cost = req.cost()
        if cost is not None:
            if cost > equity * r.max_order_value_pct / 100:
                refusals.append(f"Order value ${cost:,.0f} exceeds {r.max_order_value_pct:g}% of the account.")
            if account.buying_power is not None and cost > account.buying_power:
                refusals.append(f"Order value ${cost:,.0f} exceeds buying power ${account.buying_power:,.0f}.")
        held = {p.symbol for p in account.positions if p.quantity}
        if req.symbol not in held and len(held) >= r.max_positions:
            refusals.append(f"Already {len(held)} open positions (limit {r.max_positions}).")
        if account.day_pl is not None and account.day_pl < -equity * r.daily_loss_limit_pct / 100:
            refusals.append(f"Today's loss ${-account.day_pl:,.0f} passed the {r.daily_loss_limit_pct:g}% "
                            "daily limit: alerts only until tomorrow.")
        return CheckResult(refusals, notes, risk_usd, risk_pct)

    # ------------------------------------------------------------------ preview / place

    def preview(self, account: Account, req: OrderRequest) -> tuple[OrderPreview, CheckResult]:
        check = self.check(account, req)
        if not check.ok:
            self._log("refused", account, req, messages=check.refusals)
            raise OrderRefused(" ".join(check.refusals))
        preview = self.broker.preview(account.account_hash, req)
        preview.messages = check.notes + preview.messages
        if preview.accepted:
            self._previews[preview.fingerprint] = preview
        self._log("preview", account, req, messages=preview.messages, accepted=preview.accepted,
                  est_cost=preview.est_cost)
        return preview, check

    def place(self, account: Account, req: OrderRequest, confirmation: str = "") -> str:
        fp = req.fingerprint()
        preview = self._previews.get(fp)
        if preview is None:
            raise OrderRefused("Preview this exact order first.")
        if self.clock() - preview.created_at > timedelta(seconds=self.cfg.broker.preview_ttl_s):
            del self._previews[fp]
            raise OrderRefused("The preview expired; preview again to see current prices.")
        check = self.check(account, req)               # the account may have changed since
        if not check.ok:
            raise OrderRefused(" ".join(check.refusals))
        if self.broker.is_live:
            if not self.cfg.broker.live_trading:
                raise OrderRefused("Live trading is off (settings.json: broker.live_trading).")
            if _norm(confirmation) != _norm(expected_confirmation(req)):
                raise OrderRefused(f"Type '{expected_confirmation(req)}' to confirm this real-money order.")

        del self._previews[fp]                          # one preview, one submission
        sent_at = self.clock()
        self._log("submit", account, req)
        try:
            order_id = self.broker.place(account.account_hash, req)
        except Exception as e:
            found = self._reconcile(account, req, sent_at)
            self._log("uncertain", account, req, messages=[str(e)[:300]], found=found)
            raise OrderUncertain(
                f"Sending failed ({e}). Orders found for {req.symbol} since then: {found or 'none'}. "
                "Check the broker before trying again; nothing will be resent automatically.") from e
        self._log("placed", account, req, order_id=order_id)
        return order_id

    def _reconcile(self, account: Account, req: OrderRequest, since: datetime) -> list[str]:
        try:
            orders = self.broker.orders(account.account_hash, since - timedelta(minutes=1))
        except Exception:
            return []
        return [f"{o.order_id} {o.status}" for o in orders if o.symbol == req.symbol and o.quantity == req.quantity]

    # ------------------------------------------------------------------ stop everything

    def stop_all(self, account: Account) -> list[str]:
        """Block new entries and cancel every open *entry* order (a working buy, which takes its
        unfilled bracket with it). Exit orders — the stops and targets protecting positions
        already held — are left in place on purpose: cancelling them would leave those positions
        unprotected."""
        self.halt_file.write_text(self.clock().isoformat(), encoding="utf-8")
        cancelled, failed = [], []
        for o in self.broker.orders(account.account_hash, self.clock() - timedelta(days=60)):
            if o.status in OPEN_STATUSES and o.side in ENTRY_SIDES:
                try:
                    self.broker.cancel(account.account_hash, o.order_id)
                    cancelled.append(o.order_id)
                except Exception as e:
                    failed.append(f"{o.order_id}: {e}")
        self._log("stop_all", account, None, cancelled=cancelled, failed=failed)
        if failed:
            raise OrderUncertain("Some orders could not be cancelled: " + "; ".join(failed))
        return cancelled

    def resume(self) -> None:
        self.halt_file.unlink(missing_ok=True)

    # ------------------------------------------------------------------ journal

    def _log(self, event: str, account: Account | None, req: OrderRequest | None, **extra) -> None:
        rec = {"time": self.clock().isoformat(), "event": event, "broker": self.broker.name,
               "live": self.broker.is_live, "account": account.number_masked if account else None}
        if req is not None:
            rec.update(order=req.describe(), fingerprint=req.fingerprint(), note=req.note)
        rec.update(extra)
        with open(self.app_dir / "orders.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
