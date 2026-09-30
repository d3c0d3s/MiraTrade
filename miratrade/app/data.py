"""Everything the screens show, as plain functions (no Qt), so it can be tested directly.

Mostly thin: the work lives in the core (`miratrade.report`, `miratrade.prefs`) and this layer only
hands it the interface's translator and the app's own paths. That way one function serves a screen,
the console and the server, and the core never has to know which of the three is asking.
"""
from __future__ import annotations

import json
from pathlib import Path

from miratrade import report
from miratrade.app.i18n import t
from miratrade.config import APP_DIR, REPORTS_DIR, Config, load_user_config

SETTINGS_PATH = APP_DIR / "settings.json"
SCAN_DIR = APP_DIR / "scan"


# The reading of finished reports lives in `miratrade.report`, in the core, because the notifier
# needs it too and the notifier runs on a server with no Qt. Here they are only given the interface's
# translator, so a screen keeps calling one function with no language argument.

def report_info(path: Path) -> report.ReportInfo | None:
    return report.report_info(path, translate=t)


def list_reports(root: Path = REPORTS_DIR) -> list[report.ReportInfo]:
    return report.list_reports(root, translate=t)


def load_report(path: Path) -> dict:
    return report.load_report(path)


def honesty_line(root: Path = REPORTS_DIR) -> str:
    return report.honesty_line(root, translate=t)


# --------------------------------------------------------------------------- settings

def read_settings(path: Path = SETTINGS_PATH, db=None) -> Config:
    """The settings in force. They live in the market database (see :mod:`miratrade.prefs`); the
    file is where they came from the first time, and the fallback when the store cannot be read."""
    from miratrade import prefs

    return prefs.load(db=db, json_path=path)


def write_settings(cfg: Config, path: Path = SETTINGS_PATH, db=None) -> None:
    """Save every user-editable section to the store, and mirror it to the file.

    Which sections those are is :data:`miratrade.prefs.USER_SECTIONS`, in one place: a section
    listed in one saver and not the other is silently forgotten, however carefully a screen filled
    it in — which is what used to happen to ``notify``.
    """
    from miratrade import prefs

    prefs.save(cfg, db=db, json_path=path)


def analyze_command(days: int, out: Path, cap: str = "all", extra: list[str] | None = None) -> list[str]:
    """Arguments for running an analysis as a separate process (the app never blocks on it)."""
    return ["-X", "utf8", "-W", "ignore", "-m", "miratrade.cli", "analyze", "--days", str(days),
            "--out", str(out), "--cap", cap, *(extra or [])]


def scan_command(days: int, variant: str, save: Path, report: Path | None = None,
                 cap: str = "all") -> list[str]:
    """Arguments for ``miratrade scan`` as a separate process; it saves its result in ``save``."""
    return ["-X", "utf8", "-W", "ignore", "-m", "miratrade.cli", "scan", "--days", str(days),
            "--variant", variant, "--save", str(save), "--cap", cap,
            *(["--report", str(report)] if report else [])]


def search_command(days: int, cap: str = "all", extra: list[str] | None = None) -> list[str]:
    """Arguments for re-deriving the events from stored data. This one never downloads.

    ``cap`` is "all" and the screen does not pass its own: size narrows what is *shown*, and
    filtering here as well would mean the stored events only ever hold the tier that was selected
    when they were last built.
    """
    return ["-X", "utf8", "-W", "ignore", "-m", "miratrade.cli", "reprocess", "--days", str(days),
            "--cap", cap, *(extra or [])]


def offline_analysis_command(days: int, out: Path, cap: str = "all") -> list[str]:
    """Arguments for a backtest over stored data: the same analysis without the download."""
    return ["-X", "utf8", "-W", "ignore", "-m", "miratrade.cli", "analyze", "--offline",
            "--days", str(days), "--out", str(out), "--cap", cap]


def quote_broker(path: Path = SETTINGS_PATH):
    """The broker the settings point at, or ``None`` when it cannot be reached. Read-only use:
    balances and positions, never orders."""
    name = read_settings(path).data.quote_broker
    try:
        if name == "etrade":
            from miratrade.brokers.etrade import EtradeBroker

            return EtradeBroker()
        from miratrade.brokers.schwab import SchwabBroker, hours_until_relogin

        auth_ok = SchwabBroker().auth
        return SchwabBroker() if (hours_until_relogin(auth_ok) or 0) > 0 else None
    except Exception:                     # not configured, not logged in, extra not installed
        return None


def set_cap_tier(tier: str, path: Path = SETTINGS_PATH) -> None:
    """Remember the company-size filter, so both screens and the CLI agree on it."""
    cfg = read_settings(path)
    cfg.data.cap_tier = tier
    write_settings(cfg, path)


def cap_combo(current: str, on_change) -> "object":
    """A size selector shared by the Signals and Reports screens."""
    from PySide6.QtWidgets import QComboBox

    from miratrade.config import CAP_TIERS

    box = QComboBox()
    for key, (_low, _high, label) in CAP_TIERS.items():
        box.addItem(t(label), key)
    box.setCurrentIndex(max(0, box.findData(current)))
    box.setAccessibleName(t("Company size"))
    box.setToolTip(t("Narrows the companies to download and simulate. It saves time; over the "
                     "5-year analysis no size band showed an edge on its own."))
    box.currentIndexChanged.connect(lambda _: on_change(box.currentData()))
    return box
