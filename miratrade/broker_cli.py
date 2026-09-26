"""``miratrade schwab …``: set up, log in, read data and send guarded orders from the terminal.

Every order goes through ``OrderGuard``: risk checks → Schwab preview → (real money only if
``broker.live_trading`` is on in settings.json) typed confirmation → one submission.
"""
from __future__ import annotations

import getpass
import json
import webbrowser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from miratrade.brokers.base import Account, OrderRequest
from miratrade.brokers.guard import OrderGuard, OrderRefused, OrderUncertain, expected_confirmation
from miratrade.brokers.schwab import SchwabAuth, SchwabBroker, hours_until_relogin
from miratrade.config import APP_DIR, load_user_config


def _broker() -> SchwabBroker:
    return SchwabBroker(auth=SchwabAuth())


def _account(broker, last4: str | None) -> Account:
    accounts = broker.accounts()
    if not accounts:
        raise SystemExit("No accounts linked to this login.")
    if last4:
        match = [a for a in accounts if a.number_masked.endswith(last4)]
        if not match:
            raise SystemExit(f"No account ending in {last4}: " + ", ".join(a.number_masked for a in accounts))
        return match[0]
    return accounts[0]


def _money(v) -> str:
    return "–" if v is None else f"${v:,.2f}"


def cmd_setup(a) -> None:
    cfg = load_user_config()
    print("Schwab developer app → Dashboard → your app → App Key / Secret.")
    key = input("App Key: ").strip()
    secret = getpass.getpass("App Secret (hidden): ").strip()
    cb = input(f"Callback URL [{cfg.broker.callback_url}]: ").strip() or cfg.broker.callback_url
    SchwabAuth().setup(key, secret, cb)
    print("Saved in the Windows Credential Manager (service 'MiraTrade'). Next: miratrade schwab login")


def cmd_login(a) -> None:
    auth = SchwabAuth()
    if not auth.configured():
        raise SystemExit("Run `miratrade schwab setup` first.")
    url = auth.login_url()
    print("1. Sign in to Schwab in the browser window that opens (or open this address):\n   " + url)
    webbrowser.open(url)
    print("2. After approving, the browser lands on https://127.0.0.1…/?code=… and shows an error page.\n"
          "   That is expected. Copy the WHOLE address from the address bar and paste it here.")
    received = input("Address: ").strip()
    auth.complete_login(received)
    hours = hours_until_relogin(auth)
    print(f"Logged in. The login lasts {hours / 24:.1f} more days (Schwab limit: 7).")
    for acc in SchwabBroker(auth=auth).accounts():
        print(f"  account {acc.number_masked}: equity {_money(acc.equity)}")


def cmd_status(a) -> None:
    cfg = load_user_config()
    auth = SchwabAuth()
    print(f"App credentials: {'saved' if auth.configured() else 'missing (miratrade schwab setup)'}")
    hours = hours_until_relogin(auth)
    if hours is None:
        print("Login: none (miratrade schwab login)")
    elif hours <= 0:
        print("Login: expired, run `miratrade schwab login`")
    else:
        warn = "  ← log in again soon" if hours <= cfg.broker.token_warn_hours else ""
        print(f"Login: valid for {hours:.0f} more hours{warn}")
    print(f"Live trading: {'ON' if cfg.broker.live_trading else 'off'} "
          f"(settings: {APP_DIR / 'settings.json'})")
    guard = OrderGuard(_broker(), cfg)
    print(f"'Detener todo': {'ACTIVE, new entries blocked' if guard.halted() else 'not active'}")


def cmd_accounts(a) -> None:
    for acc in _broker().accounts():
        print(f"{acc.number_masked}  equity {_money(acc.equity)}  cash {_money(acc.cash)}  "
              f"buying power {_money(acc.buying_power)}  today {_money(acc.day_pl)}")
        for p in acc.positions:
            print(f"   {p.symbol:<24} {p.quantity:>8g}  avg {_money(p.avg_price)}  value {_money(p.market_value)}  "
                  f"today {_money(p.day_pl)}")


def cmd_quote(a) -> None:
    for s, q in _broker().quotes([s.upper() for s in a.symbols]).items():
        print(f"{s:<8} bid {q.bid}  ask {q.ask}  last {q.last}  chg {q.change_pct}%  vol {q.volume}")


def cmd_chain(a) -> None:
    """Calls nearest the target delta at each requested days-to-expiry."""
    dtes = [int(x) for x in a.dte.split(",")]
    today = date.today()
    chain = _broker().option_chain(a.symbol.upper(), today + timedelta(days=min(dtes) - 10),
                                   today + timedelta(days=max(dtes) + 20), contract_type="CALL")
    if chain.empty:
        raise SystemExit("No contracts returned.")
    for target in dtes:
        exp_dte = chain.loc[(chain["dte"] - target).abs().idxmin(), "dte"]
        c = chain[chain["dte"] == exp_dte].assign(gap=lambda d: (d["delta"] - a.delta).abs()).nsmallest(3, "gap")
        print(f"\n~{target} days → expiry {c['expiry'].iat[0].date()} ({exp_dte} days)")
        print(c[["symbol", "strike", "bid", "ask", "delta", "iv", "open_interest", "volume"]].to_string(index=False))


def cmd_orders(a) -> None:
    b = _broker()
    acc = _account(b, a.account)
    since = datetime.now(timezone.utc) - timedelta(days=a.days)
    for o in b.orders(acc.account_hash, since):
        print(f"{o.entered:%Y-%m-%d %H:%M}  {o.order_id:>12}  {o.status:<12} {o.side:<12} {o.quantity:g} "
              f"{o.symbol}  filled {o.filled:g}  @ {o.price}")


def cmd_transactions(a) -> None:
    b = _broker()
    acc = _account(b, a.account)
    t = b.transactions(acc.account_hash, date.today() - timedelta(days=a.days), date.today())
    print(t.to_string(index=False) if len(t) else "No transactions.")


def cmd_buy(a) -> None:
    cfg = load_user_config()
    b = _broker()
    guard = OrderGuard(b, cfg)
    acc = _account(b, a.account)
    asset = "OPTION" if a.option else "EQUITY"
    symbol = a.option or a.symbol.upper()
    mult = 100 if a.option else 1
    qty = a.qty or guard.suggest_quantity(acc, a.limit, a.stop, mult)
    if qty < 1:
        raise SystemExit("The stop is too close/far for a whole unit at your risk per trade; set --qty.")
    req = OrderRequest(symbol=symbol, quantity=qty, limit_price=a.limit, asset_type=asset,
                       stop_price=a.stop, target_price=a.target, underlying=a.symbol.upper(), note=a.note or "")
    try:
        preview, check = guard.preview(acc, req)
    except OrderRefused as e:
        raise SystemExit(f"REFUSED: {e}")
    print(f"\nPREVIEW  {req.describe()}   account {acc.number_masked}")
    print(f"  cost ~{_money(preview.est_cost)}  commission {_money(preview.est_commission)}  "
          f"risk {_money(check.risk_usd)} ({check.risk_pct or 0:.2f}% of {_money(acc.equity)})")
    for m in preview.messages:
        print("  " + m)
    if not preview.accepted:
        raise SystemExit("Schwab would reject this order; nothing was sent.")
    if a.preview_only:
        return
    if not cfg.broker.live_trading:
        raise SystemExit("\nLive trading is off, so nothing was sent. To enable it, set "
                         '{"broker": {"live_trading": true}} in ' + str(APP_DIR / "settings.json"))
    phrase = expected_confirmation(req)
    typed = input(f"\nREAL MONEY. Type '{phrase}' to send, anything else cancels: ")
    try:
        order_id = guard.place(acc, req, typed)
    except OrderRefused as e:
        raise SystemExit(f"Not sent: {e}")
    except OrderUncertain as e:
        raise SystemExit(f"UNCERTAIN: {e}")
    print(f"Sent. Schwab order id {order_id}. Check it with `miratrade schwab orders`.")


def cmd_stop_all(a) -> None:
    b = _broker()
    guard = OrderGuard(b, load_user_config())
    acc = _account(b, a.account)
    cancelled = guard.stop_all(acc)
    print(f"Stopped. Cancelled {len(cancelled)} pending entries; stops on open positions were kept. "
          "New entries are blocked until `miratrade schwab resume`.")


def cmd_resume(a) -> None:
    OrderGuard(_broker(), load_user_config()).resume()
    print("Resumed: new entries allowed again.")


def cmd_diagnose(a) -> None:
    out = Path(a.out)
    out.write_text(json.dumps(_broker().diagnose(), indent=1, default=str), encoding="utf-8")
    print(f"Saved read-only responses (account numbers masked) to {out}")


def cmd_logout(a) -> None:
    auth = SchwabAuth()
    if a.forget_app:
        auth.forget()
        print("Removed the token and the app key/secret from the Credential Manager.")
    else:
        auth.logout()
        print("Removed the Schwab token. App key/secret kept.")


def add_parser(sub) -> None:
    sp = sub.add_parser("schwab", help="Schwab account: login, data and guarded orders")
    s = sp.add_subparsers(dest="schwab_cmd", required=True)
    s.add_parser("setup", help="save app key/secret/callback in the Credential Manager").set_defaults(func=cmd_setup)
    s.add_parser("login", help="sign in to Schwab (valid 7 days)").set_defaults(func=cmd_login)
    s.add_parser("status", help="login expiry, live-trading switch, stop state").set_defaults(func=cmd_status)
    s.add_parser("accounts", help="balances and positions").set_defaults(func=cmd_accounts)
    q = s.add_parser("quote", help="real-time quotes")
    q.add_argument("symbols", nargs="+")
    q.set_defaults(func=cmd_quote)
    c = s.add_parser("chain", help="calls near a delta at 30/45/60 days")
    c.add_argument("symbol")
    c.add_argument("--dte", default="30,45,60")
    c.add_argument("--delta", type=float, default=0.65)
    c.set_defaults(func=cmd_chain)
    for name, fn, days in (("orders", cmd_orders, 7), ("transactions", cmd_transactions, 30)):
        p = s.add_parser(name)
        p.add_argument("--days", type=int, default=days)
        p.add_argument("--account", help="last 4 digits")
        p.set_defaults(func=fn)
    b = s.add_parser("buy", help="preview (and, with live trading on, send) a bracket entry")
    b.add_argument("symbol", help="stock ticker (the underlying, for options)")
    b.add_argument("--limit", type=float, required=True, help="entry limit price")
    b.add_argument("--stop", type=float, required=True, help="stop price (stock, or option premium)")
    b.add_argument("--target", type=float, help="target price (stock, or option premium)")
    b.add_argument("--qty", type=int, help="default: size to your risk per trade")
    b.add_argument("--option", help='Schwab option symbol, e.g. "ACME  261120C00045000"')
    b.add_argument("--account", help="last 4 digits")
    b.add_argument("--note", help="why (saved in the order journal)")
    b.add_argument("--preview-only", action="store_true")
    b.set_defaults(func=cmd_buy)
    for name, fn in (("stop-all", cmd_stop_all),):
        p = s.add_parser(name, help="cancel pending entries and block new ones")
        p.add_argument("--account", help="last 4 digits")
        p.set_defaults(func=fn)
    s.add_parser("resume", help="allow new entries after stop-all").set_defaults(func=cmd_resume)
    d = s.add_parser("diagnose", help="save raw read-only responses (masked) to check parsing")
    d.add_argument("--out", default=str(APP_DIR / "schwab_diagnose.json"),
                   help="kept outside the repo: it holds your positions")
    d.set_defaults(func=cmd_diagnose)
    lo = s.add_parser("logout", help="delete the saved token")
    lo.add_argument("--forget-app", action="store_true", help="also delete app key/secret")
    lo.set_defaults(func=cmd_logout)
