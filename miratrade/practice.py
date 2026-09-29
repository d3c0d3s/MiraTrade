"""Practice trades: a paper journal that survives closing the app.

``SimulatedBroker`` already fills orders and tracks positions, but only in memory and only while
something feeds it prices. Practice needs less and needs it to persist: what you decided to buy,
at what price, with which stop and target, which event produced it, and what it is worth now.

An option's current value is **modelled** with Black-Scholes on the underlying's price, the same
way the analysis prices contracts, and every screen that shows it says so. A share is worth its
last price. Positions close by themselves when a mark reaches the stop or the target, at that
mark, the way the backtest fills a gap.

The file lives in ``APP_DIR/practice.json``; it is small, human-readable, and losing it costs
nothing real.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from miratrade.config import APP_DIR, Config

PRACTICE_PATH = APP_DIR / "practice.json"
OPEN, CLOSED = "open", "closed"
# English source wording; the screens translate it (see app/i18n.py).
REASONS = {"target": "target", "stop": "stop", "expiry": "expiry", "manual": "manual close"}


@dataclass
class PaperTrade:
    """One practice position. Prices are per share or per contract, never per lot."""
    id: str
    opened: str                         # ISO date
    ticker: str                         # the underlying
    kind: str                           # "accion" | "call"
    quantity: int                       # shares, or contracts
    entry: float
    stop: float
    target: float
    note: str = ""                      # the event that produced it
    strike: float | None = None
    expiry: str | None = None
    iv: float | None = None
    status: str = OPEN
    last: float | None = None           # latest mark, per share/contract
    closed: str | None = None
    exit_price: float | None = None
    exit_reason: str | None = None

    @property
    def multiplier(self) -> int:
        return 100 if self.kind == "call" else 1

    @property
    def cost(self) -> float:
        return self.entry * self.quantity * self.multiplier

    @property
    def value(self) -> float:
        price = self.exit_price if self.status == CLOSED else self.last
        return (price if price is not None else self.entry) * self.quantity * self.multiplier

    @property
    def profit(self) -> float:
        return self.value - self.cost

    @property
    def profit_pct(self) -> float:
        return self.profit / self.cost if self.cost else 0.0

    @property
    def risk(self) -> float:
        """What reaching the stop would cost from here."""
        return max(0.0, (self.entry - self.stop) * self.quantity * self.multiplier)



# --------------------------------------------------------------------------- storage

def load(path: Path = PRACTICE_PATH) -> list[PaperTrade]:
    path = Path(path)
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    fields = set(PaperTrade.__dataclass_fields__)
    return [PaperTrade(**{k: v for k, v in row.items() if k in fields}) for row in rows if "id" in row]


def save(trades: list[PaperTrade], path: Path = PRACTICE_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(t) for t in trades], indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def next_id(trades: list[PaperTrade]) -> str:
    used = {int(t.id) for t in trades if str(t.id).isdigit()}
    return str(max(used) + 1 if used else 1)


# --------------------------------------------------------------------------- opening

def size_for(equity: float, entry: float, stop: float, multiplier: int, cfg: Config = Config()) -> int:
    """How many units risk ``risk_per_trade_pct`` of equity between entry and stop, capped by
    ``max_order_value_pct`` so one position cannot swallow the account."""
    per_unit = (entry - stop) * multiplier
    if per_unit <= 0 or entry <= 0:
        return 0
    by_risk = equity * cfg.risk.risk_per_trade_pct / 100 / per_unit
    by_value = equity * cfg.risk.max_order_value_pct / 100 / (entry * multiplier)
    return max(0, int(min(by_risk, by_value)))


def open_trade(trades: list[PaperTrade], *, ticker: str, kind: str, entry: float, stop: float, target: float,
               equity: float, note: str = "", strike: float | None = None, expiry: str | None = None,
               iv: float | None = None, today: date | None = None, cfg: Config = Config()) -> PaperTrade:
    """Add a position sized by the risk settings. Raises ``ValueError`` when it cannot be opened;
    the message is the English source the screens translate before showing it."""
    if entry <= 0:
        raise ValueError("The entry price is not valid.")
    if not (stop < entry < target):
        raise ValueError("The stop must sit below the entry and the target above it.")
    if sum(1 for t in trades if t.status == OPEN) >= cfg.risk.max_positions:
        raise ValueError(f"You already hold {cfg.risk.max_positions} open positions, the maximum you set.")
    if any(t.status == OPEN and t.ticker == ticker for t in trades):
        raise ValueError(f"You already hold an open position in {ticker}.")
    quantity = size_for(equity, entry, stop, 100 if kind == "call" else 1, cfg)
    if quantity < 1:
        raise ValueError("Your risk per trade does not buy a single unit: the stop is too far away "
                         "or the practice account is small.")
    trade = PaperTrade(id=next_id(trades), opened=str(today or date.today()), ticker=ticker, kind=kind,
                       quantity=quantity, entry=entry, stop=stop, target=target, note=note,
                       strike=strike, expiry=expiry, iv=iv, last=entry)
    trades.append(trade)
    return trade


# --------------------------------------------------------------------------- marking

def option_value(trade: PaperTrade, underlying: float, on: date, cfg: Config = Config()) -> float | None:
    """Modelled worth of the contract today, net of the half-spread that selling costs."""
    from miratrade.options_trades import bs_price

    if trade.strike is None or not trade.expiry or trade.iv is None:
        return None
    years = max((date.fromisoformat(trade.expiry) - on).days, 0) / 365
    price = bs_price(underlying, trade.strike, years, cfg.options.rate, trade.iv)
    return float(price) * (1 - cfg.options.half_spread)


def mark(trades: list[PaperTrade], prices: dict[str, float], on: date | None = None,
         cfg: Config = Config()) -> list[PaperTrade]:
    """Update every open position with the underlying prices given and close the ones that reached
    their stop, their target or their expiry. Returns the positions that closed."""
    on = on or date.today()
    closed = []
    for t in trades:
        if t.status != OPEN:
            continue
        underlying = prices.get(t.ticker)
        if underlying is None or not np.isfinite(underlying):
            continue
        value = underlying if t.kind != "call" else option_value(t, float(underlying), on, cfg)
        if value is None:
            continue
        t.last = float(value)
        # On expiry day the contract is worth whatever it is worth and nothing is held further,
        # so that is the reason it ended, whichever level the value happens to be at.
        expired = t.kind == "call" and t.expiry and date.fromisoformat(t.expiry) <= on
        reason = "expiry" if expired else "stop" if t.last <= t.stop else "target" if t.last >= t.target else None
        if reason:
            close_trade(t, t.last, reason, on)
            closed.append(t)
    return closed


def close_trade(trade: PaperTrade, price: float, reason: str = "manual", on: date | None = None) -> PaperTrade:
    trade.status = CLOSED
    trade.exit_price = float(price)
    trade.exit_reason = reason
    trade.last = float(price)
    trade.closed = str(on or date.today())
    return trade


# --------------------------------------------------------------------------- reading

def summary(trades: list[PaperTrade], start_equity: float) -> dict:
    """What the practice screen shows at the top."""
    open_trades = [t for t in trades if t.status == OPEN]
    done = [t for t in trades if t.status == CLOSED]
    realised = sum(t.profit for t in done)
    unrealised = sum(t.profit for t in open_trades)
    wins = [t for t in done if t.profit > 0]
    return {"open": len(open_trades), "closed": len(done),
            "invested": sum(t.cost for t in open_trades),
            "open_risk": sum(t.risk for t in open_trades),
            "realised": realised, "unrealised": unrealised,
            "equity": start_equity + realised + unrealised,
            "hit_rate": len(wins) / len(done) if done else float("nan"),
            "best": max((t.profit for t in done), default=float("nan")),
            "worst": min((t.profit for t in done), default=float("nan"))}


def equity_curve(trades: list[PaperTrade], start_equity: float) -> tuple[list[str], list[float]]:
    """Closed trades in the order they closed, accumulating their profit."""
    done = sorted((t for t in trades if t.status == CLOSED and t.closed), key=lambda t: t.closed)
    dates, values, running = [], [], start_equity
    for t in done:
        running += t.profit
        dates.append(t.closed)
        values.append(running)
    return dates, values


DEFAULT_EQUITY = 25_000.0


def equity_from_accounts(accounts) -> float | None:
    """Total equity across the broker's accounts, or ``None`` when none of them reports it."""
    values = [a.equity for a in (accounts or []) if getattr(a, "equity", None) is not None]
    return float(sum(values)) if values else None


def account_equity(broker=None, fallback: float = DEFAULT_EQUITY, cfg: Config | None = None
                   ) -> tuple[float, str]:
    """The capital position sizes are worked out from, and where that figure came from.

    By default it is a figure the user typed, **not** their broker balance. Sizing a suggestion to
    somebody's real account turns analysis of a market into advice about that person's money, which
    is a different thing to be doing and a different thing to be responsible for. Reading the real
    balance stays available for the account holder's own use, but it has to be switched on.

    Returning the source as well as the value matters: sizing on a number the user did not expect is
    worse than sizing on one they chose.
    """
    cfg = cfg or Config()
    typed = float(getattr(cfg.risk, "sizing_capital", fallback) or fallback)
    if not getattr(cfg.risk, "size_on_balance", False):
        return typed, "typed"
    if broker is None:
        return typed, "no_broker"
    try:
        equity = equity_from_accounts(broker.accounts())
    except Exception:
        return typed, "unreachable"
    if equity is None or equity <= 0:
        return typed, "unreadable"
    return equity, broker.name
