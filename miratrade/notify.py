"""Telling you a new event happened, with enough detail to decide whether to look.

Two channels, doing different jobs. A **push** is short and immediate: three lines saying something
is there. An **email** carries the detail — what was filed, what similar events did, the contract the
profile would buy, whether the quotes make it usable and whether it sits through a results
announcement. Reading a long notification on a lock screen is not a thing anybody does.

What every message says, whatever the channel: that **no rule has been validated out of sample**.
A list of tickers sent to a phone looks like a recommendation unless it is told otherwise, and this
one is not one. The line comes from the latest report rather than the code, so the day something is
validated it changes by itself.

Nothing is sent twice. A notified event is recorded in the store's coverage table, so running this
after every scan — which is the point — announces only what is new.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date
from typing import Callable

import pandas as pd

from miratrade.config import Config

SOURCE = "notified"          # coverage rows: (source, scope=ticker, day=signal_date)
NTFY_URL = "https://ntfy.sh/{topic}"
EMAIL_KEY = "notify.smtp_password"


# --------------------------------------------------------------------------- what to say

def already_sent(db, events: pd.DataFrame) -> pd.DataFrame:
    """Drop the events a message has already gone out about."""
    from miratrade import store

    if events is None or not len(events):
        return events if events is not None else pd.DataFrame()
    keep = []
    for _, row in events.iterrows():
        day = pd.Timestamp(row["signal_date"]).strftime("%Y-%m-%d")
        keep.append(day not in store.covered(db, SOURCE, scope=str(row["ticker"]).upper()))
    return events[pd.Series(keep, index=events.index)]


def mark_sent(db, events: pd.DataFrame) -> None:
    from miratrade import store

    for _, row in events.iterrows():
        store.mark_covered(db, SOURCE, [pd.Timestamp(row["signal_date"]).date()], rows=1,
                           scope=str(row["ticker"]).upper())


def detail(db, row, cfg: Config, reports_dir=None) -> dict:
    """Everything worth saying about one event, each piece missing rather than invented."""
    from miratrade.data.earnings import crosses_earnings
    from miratrade.liquidity import check_stored, underlying_liquidity
    from miratrade.messages import note
    from miratrade.scan import DEFAULT_VARIANT, contract_for, evidence, latest_history_report, load_history

    out = {"ticker": str(row["ticker"]), "date": pd.Timestamp(row["signal_date"]).date(),
           "what": str(row.get("what") or ""), "close": row.get("close"),
           "contract": None, "evidence": None, "liquidity": None, "earnings": None}
    parts = row.get("what_parts")
    if isinstance(parts, str) and parts.strip():
        try:
            out["what"] = note([(t, f) for t, f in json.loads(parts)])
        except (ValueError, TypeError):
            pass

    report = latest_history_report(reports_dir) if reports_dir else None
    if report is not None:
        history, rules = load_history(report)
        out["evidence"] = evidence(row, history, DEFAULT_VARIANT, rules)

    from miratrade import store

    bars = store.prices(db, [out["ticker"]]).get(out["ticker"], pd.DataFrame())
    contract = contract_for(bars, row["signal_date"], DEFAULT_VARIANT, cfg) if len(bars) else None
    out["contract"] = contract
    if contract:
        verdict = check_stored(db, out["ticker"], contract["expiry"], contract["strike"],
                               target_pct=contract.get("target_pct", 0.0), cfg=cfg)
        out["liquidity"] = verdict if verdict.measured else underlying_liquidity(bars, cfg)
        out["earnings"] = crosses_earnings(db, out["ticker"], date.today(),
                                           pd.Timestamp(contract["expiry"]).date())
    return out


def _money(v) -> str:
    return "–" if v is None or not pd.notna(v) else f"${v:,.2f}"


def compose(items: list[dict], honesty: str) -> tuple[str, str, str]:
    """``(title, short, long)`` — the push text and the mail body, from the same facts."""
    title = (f"MiraTrade: {len(items)} new event" + ("s" if len(items) != 1 else ""))
    tickers = ", ".join(i["ticker"] for i in items[:8]) + (" …" if len(items) > 8 else "")
    short = f"{tickers}\n{honesty}"

    lines = [honesty, ""]
    for i in items:
        lines.append(f"{i['ticker']} — {i['date']}")
        if i["what"]:
            lines.append(f"    {i['what']}")
        if i["close"] is not None and pd.notna(i["close"]):
            lines.append(f"    share {_money(i['close'])}")
        if i["evidence"] is not None:
            lines.append(f"    evidence: {i['evidence'].sentence}")
        c = i["contract"]
        if c:
            lines.append(f"    contract: {c['strike']:g} C expiring "
                         f"{pd.Timestamp(c['expiry']):%Y-%m-%d} ({c['dte']} days), "
                         f"premium {_money(c['premium'])}, delta {c['delta']:.2f}")
            lines.append(f"    exits: sell at {_money(c['target'])} "
                         f"(+{c['target_pct'] * 100:.0f}%), stop {_money(c['stop'])} "
                         f"(−{c['stop_pct'] * 100:.0f}%)")
        if i["liquidity"] is not None:
            lines.append(f"    {'tradeable' if i['liquidity'].ok else 'NOT TRADEABLE'}: "
                         f"{i['liquidity'].say()}")
        if i["earnings"] is not None:
            lines.append(f"    REPORTS {i['earnings']}, before this contract expires — the premium "
                         f"usually collapses once the news is out")
        lines.append("")
    lines.append("Contract prices are modelled from the share, not quotes. Analysis, not advice.")
    return title, short, "\n".join(lines)


# --------------------------------------------------------------------------- sending

def send_ntfy(topic: str, title: str, body: str, opener: Callable | None = None) -> bool:
    """A short push. No account and no credential: the topic name is the whole address, which is
    also why it should be long and random — anyone who knows it can read what is sent."""
    if not topic:
        return False
    request = urllib.request.Request(
        NTFY_URL.format(topic=topic.strip()), data=body.encode("utf-8"),
        headers={"Title": title, "Tags": "chart_with_upwards_trend", "Priority": "default",
                 "User-Agent": "MiraTrade"})
    with (opener or urllib.request.urlopen)(request, timeout=30):
        return True


def send_email(cfg: Config, title: str, body: str, password: str | None = None,
               sender: Callable | None = None) -> bool:
    """The detail. Gmail needs an app password, kept in the Windows Credential Manager."""
    import smtplib
    from email.message import EmailMessage

    p = cfg.notify
    if not p.email_to:
        return False
    if password is None and sender is None:        # only SMTP needs one; an injected transport
        from miratrade.brokers.credentials import CredentialStore   # carries its own credentials

        password = CredentialStore().get(EMAIL_KEY)
        if not password:
            raise RuntimeError("No email password: run `miratrade notify setup --email-password "
                               "...`. For Gmail that is an app password, not your account one.")
    message = EmailMessage()
    message["Subject"] = title
    message["From"] = p.email_from or p.email_to
    message["To"] = p.email_to
    message.set_content(body)
    if sender is not None:
        return bool(sender(message, password))
    with smtplib.SMTP(p.smtp_host, p.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(message["From"], password)
        smtp.send_message(message)
    return True


def notify_new(db=None, cfg: Config | None = None, reports_dir=None, days: int = 7,
               log: Callable[[str], None] = print, dry_run: bool = False,
               ntfy_opener: Callable | None = None, email_sender: Callable | None = None) -> dict:
    """Announce the events nothing has been said about yet. Safe to run after every scan."""
    from miratrade import store
    from miratrade.report import honesty_line
    from miratrade.scan import load_events

    cfg = cfg or Config()
    p = cfg.notify
    owned, db = db is None, db if db is not None else store.connect()
    try:
        events = already_sent(db, load_events(db, days=days))
        items = []
        for _, row in events.head(p.max_events * 3).iterrows():
            one = detail(db, row, cfg, reports_dir)
            if p.only_tradeable and one["liquidity"] is not None and not one["liquidity"].ok:
                continue
            items.append(one)
            if len(items) >= p.max_events:
                break
        if not items:
            log("  nothing new to announce")
            return {"sent": 0, "push": False, "email": False}

        title, short, long = compose(items, honesty_line(reports_dir) if reports_dir
                                     else honesty_line())
        if dry_run:
            log(title + "\n" + long)
            return {"sent": len(items), "push": False, "email": False, "body": long}

        push = mail = False
        try:
            push = send_ntfy(p.ntfy_topic, title, short, ntfy_opener)
        except Exception as e:                    # one channel failing must not lose the other
            log(f"  push failed: {e}")
        try:
            mail = send_email(cfg, title, long, sender=email_sender)
        except Exception as e:
            log(f"  email failed: {e}")
        if push or mail:
            mark_sent(db, events.head(len(items)))
        log(f"  {len(items)} events announced"
            + (" by push" if push else "") + (" by email" if mail else ""))
        return {"sent": len(items), "push": push, "email": mail}
    finally:
        if owned:
            db.close()
