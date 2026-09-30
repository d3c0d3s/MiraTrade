"""``miratrade notify`` — announce new events by push and by email."""
from __future__ import annotations

import secrets

from miratrade import store
from miratrade.config import load_user_config
from miratrade.notify import EMAIL_KEY, notify_new


def cmd_setup(a) -> None:
    """Save where to send. The email password goes to the Windows Credential Manager, never a file."""
    cfg = load_user_config()
    if a.ntfy_topic is not None:
        cfg.notify.ntfy_topic = a.ntfy_topic.strip()
    if a.email_to is not None:
        cfg.notify.email_to = a.email_to.strip()
        cfg.notify.email_from = (a.email_from or a.email_to).strip()
    if a.smtp_host:
        cfg.notify.smtp_host = a.smtp_host
    if a.smtp_port:
        cfg.notify.smtp_port = a.smtp_port
    data.write_settings(cfg)
    if a.email_password:
        from miratrade.brokers.credentials import CredentialStore

        CredentialStore().set(EMAIL_KEY, a.email_password)
        print("Email password saved in the Windows Credential Manager.")
    print(f"push topic : {cfg.notify.ntfy_topic or '(off)'}")
    print(f"email to   : {cfg.notify.email_to or '(off)'}")
    if cfg.notify.ntfy_topic:
        print(f"\nSubscribe on your phone: install ntfy (iOS or Android) and add the topic\n"
              f"  {cfg.notify.ntfy_topic}\n"
              f"Anyone who knows that name can read what is sent, so keep it long and private.")


def cmd_topic(a) -> None:
    """Suggest a topic name nobody will guess."""
    print(f"miratrade-{secrets.token_urlsafe(18)}")
    print("\nA topic on the public ntfy server is readable by anyone who knows its name, so a\n"
          "guessable one is a public feed of what you are looking at. Save it with:\n"
          "  miratrade notify setup --ntfy-topic <the name above>")


def cmd_send(a) -> None:
    """Announce what is new. Run it after a scan; it never says the same thing twice."""
    from miratrade.config import REPORTS_DIR

    db = store.connect()
    try:
        out = notify_new(db, load_user_config(), reports_dir=REPORTS_DIR, days=a.days,
                         dry_run=a.dry_run)
        if a.dry_run:
            print("\n(nothing sent: --dry-run)")
        elif out["sent"] and not (out["push"] or out["email"]):
            raise SystemExit("Nothing could be sent. Configure a channel with "
                             "`miratrade notify setup`.")
    finally:
        db.close()


def add_parser(sub) -> None:
    no = sub.add_parser("notify", help="announce new events: a short push, and the detail by email")
    inner = no.add_subparsers(dest="notify_cmd", required=True)

    se = inner.add_parser("setup", help="where to send")
    se.add_argument("--ntfy-topic", default=None, help="the ntfy topic for the short push")
    se.add_argument("--email-to", default=None, help="where the detailed mail goes")
    se.add_argument("--email-from", default=None, help="the account it is sent from (default: --email-to)")
    se.add_argument("--email-password", default=None,
                    help="for Gmail this is an APP password, not your account password")
    se.add_argument("--smtp-host", default=None)
    se.add_argument("--smtp-port", type=int, default=None)
    se.set_defaults(func=cmd_setup)

    tp = inner.add_parser("topic", help="suggest a push topic nobody will guess")
    tp.set_defaults(func=cmd_topic)

    sn = inner.add_parser("send", help="announce the events not announced yet")
    sn.add_argument("--days", type=int, default=7, help="how far back to look (default 7)")
    sn.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
    sn.set_defaults(func=cmd_send)
