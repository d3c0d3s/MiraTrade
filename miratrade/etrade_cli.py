"""``miratrade etrade …``: connect your own E*TRADE account (read-only) from the terminal."""
from __future__ import annotations

import getpass
import json
import webbrowser
from datetime import date, timedelta
from pathlib import Path

from miratrade.brokers.etrade import EtradeAuth, EtradeBroker, quote_status
from miratrade.config import APP_DIR


def _money(v) -> str:
    return "–" if v is None else f"${v:,.2f}"


def cmd_setup(a) -> None:
    print("E*TRADE → Customer Service → Developer / API: request your own consumer key (individual use).\n"
          "It is for your own accounts only. Sign the API agreement and, for real-time quotes, the market\n"
          "data agreement in your E*TRADE account.")
    key = input("Consumer key: ").strip()
    secret = getpass.getpass("Consumer secret (hidden): ").strip()
    sandbox = input("Sandbox keys? [y/N]: ").strip().lower().startswith("y")
    EtradeAuth().setup(key, secret, sandbox)
    print("Saved in the Windows Credential Manager (service 'MiraTrade'). Next: miratrade etrade login")


def cmd_login(a) -> None:
    auth = EtradeAuth()
    if not auth.configured():
        raise SystemExit("Run `miratrade etrade setup` first.")
    url = auth.login_url()
    print("1. Sign in to E*TRADE in the browser window that opens (or open this address):\n   " + url)
    webbrowser.open(url)
    print("2. Accept, and copy the verification code E*TRADE shows.")
    auth.complete_login(input("Code: "))
    print(f"Logged in ({auth.env}). The login lasts until midnight US Eastern "
          f"({auth.hours_left():.1f} h from now).")


def cmd_status(a) -> None:
    auth = EtradeAuth()
    print(f"Consumer key: {'saved (' + auth.env + ')' if auth.configured() else 'missing (miratrade etrade setup)'}")
    h = auth.hours_left()
    print("Login: none (miratrade etrade login)" if h is None else
          "Login: expired, run `miratrade etrade login`" if h <= 0 else f"Login: valid for {h:.1f} more hours")


def cmd_accounts(a) -> None:
    for acc in EtradeBroker().accounts():
        print(f"{acc.number_masked}  equity {_money(acc.equity)}  cash {_money(acc.cash)}  "
              f"buying power {_money(acc.buying_power)}")
        for p in acc.positions:
            print(f"   {p.symbol:<24} {p.quantity:>8g}  avg {_money(p.avg_price)}  value {_money(p.market_value)}")


def cmd_quote(a) -> None:
    b = EtradeBroker()
    for s, q in b.quotes([s.upper() for s in a.symbols]).items():
        print(f"{s:<8} bid {q.bid}  ask {q.ask}  last {q.last}  chg {q.change_pct}%  vol {q.volume}")


def cmd_chain(a) -> None:
    dtes = [int(x) for x in a.dte.split(",")]
    today = date.today()
    chain = EtradeBroker().option_chain(a.symbol.upper(), today + timedelta(days=min(dtes) - 10),
                                        today + timedelta(days=max(dtes) + 20), contract_type="CALL")
    if chain.empty:
        raise SystemExit("No contracts returned.")
    for target in dtes:
        exp_dte = chain.loc[(chain["dte"] - target).abs().idxmin(), "dte"]
        c = chain[(chain["dte"] == exp_dte) & chain["delta"].notna()]
        c = c.assign(gap=(c["delta"] - a.delta).abs()).nsmallest(3, "gap")
        print(f"\n~{target} days → expiry {c['expiry'].iat[0].date() if len(c) else '?'} ({exp_dte} days)")
        print(c[["symbol", "strike", "bid", "ask", "delta", "iv", "open_interest", "volume"]].to_string(index=False))


QUOTE_STATUS = {
    "REALTIME": "tiempo real: el acuerdo de datos de mercado está firmado",
    "DELAYED": "con retraso: firma el acuerdo de datos de mercado en tu cuenta para tenerlas en vivo",
    "CLOSING": "cierre de la sesión anterior; el mercado está cerrado, vuelve a comprobarlo en horario "
               "de mercado para saber si tienes tiempo real",
    "EH_REALTIME": "tiempo real fuera de horario",
    "EH_BEFORE_OPEN": "antes de la apertura",
    "EH_CLOSED": "fuera de horario, mercado cerrado",
}


def cmd_diagnose(a) -> None:
    raw = EtradeBroker().diagnose()
    out = Path(a.out or APP_DIR / "etrade_diagnose.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(raw, indent=2, default=str), encoding="utf-8")
    print(f"Saved {out} (account ids masked).")
    for status in raw["quote_status"] or ["?"]:
        print(f"  Cotizaciones: {status} — {QUOTE_STATUS.get(status, 'estado no documentado')}")


def cmd_logout(a) -> None:
    EtradeAuth().logout()
    print("E*TRADE login revoked and deleted.")


def cmd_forget(a) -> None:
    EtradeAuth().forget()
    print("E*TRADE keys and login deleted from the Credential Manager.")


def add_parser(sub) -> None:
    sp = sub.add_parser("etrade", help="your own E*TRADE account (read-only): quotes, option chains, balances")
    s = sp.add_subparsers(dest="etrade_cmd", required=True)
    s.add_parser("setup", help="save your consumer key/secret in the Credential Manager").set_defaults(func=cmd_setup)
    s.add_parser("login", help="sign in to E*TRADE (valid until midnight US Eastern)").set_defaults(func=cmd_login)
    s.add_parser("status", help="key and login state").set_defaults(func=cmd_status)
    s.add_parser("accounts", help="balances and positions").set_defaults(func=cmd_accounts)
    q = s.add_parser("quote", help="quotes (real-time once the market data agreement is signed)")
    q.add_argument("symbols", nargs="+")
    q.set_defaults(func=cmd_quote)
    c = s.add_parser("chain", help="calls near a delta at the given days to expiry")
    c.add_argument("symbol")
    c.add_argument("--dte", default="45,60,90")
    c.add_argument("--delta", type=float, default=0.65)
    c.set_defaults(func=cmd_chain)
    d = s.add_parser("diagnose", help="save raw read-only responses (masked) to check parsing")
    d.add_argument("--out")
    d.set_defaults(func=cmd_diagnose)
    s.add_parser("logout", help="revoke and delete the login").set_defaults(func=cmd_logout)
    s.add_parser("forget", help="delete keys and login").set_defaults(func=cmd_forget)
