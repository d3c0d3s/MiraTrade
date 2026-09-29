"""Everything the screens show, as plain functions (no Qt), so it can be tested directly."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from miratrade.app.i18n import t
from miratrade.config import APP_DIR, REPORTS_DIR, Config, load_user_config

SETTINGS_PATH = APP_DIR / "settings.json"
SCAN_DIR = APP_DIR / "scan"
_WINDOW = re.compile(r"Window: \*\*(\S+) → (\S+)\*\*")


@dataclass
class ReportInfo:
    path: Path
    name: str
    modified: datetime
    start: str | None
    end: str | None
    trades: int
    validated: int
    wf_confirmed: int

    @property
    def label(self) -> str:
        span = f"{self.start} → {self.end}" if self.start else t("no dates")
        return f"{self.name}  ·  {span}"

    @property
    def summary(self) -> str:
        if self.validated == 0:
            return t("{trades} trades · no validated rule", trades=self.trades)
        return t("{trades} trades · {validated} validated rules · {confirmed} with walk-forward",
                 trades=self.trades, validated=self.validated, confirmed=self.wf_confirmed)


def _count_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, encoding="utf-8") as f:
        return max(0, sum(1 for _ in f) - 1)


def report_info(path: Path) -> ReportInfo | None:
    md = path / "edge_report.md"
    if not md.exists():
        return None
    m = _WINDOW.search(md.read_text(encoding="utf-8")[:2000])
    validated = confirmed = 0
    rules = path / "rules.csv"
    if rules.exists() and rules.stat().st_size > 1:
        try:
            r = pd.read_csv(rules, usecols=lambda c: c in ("validated", "wf_confirmed"))
            validated = int(r["validated"].sum()) if "validated" in r else 0
            if "wf_confirmed" in r and "validated" in r:
                confirmed = int((r["validated"] & r["wf_confirmed"]).sum())
        except (pd.errors.EmptyDataError, ValueError):
            pass
    return ReportInfo(path, path.name, datetime.fromtimestamp(md.stat().st_mtime),
                      m.group(1) if m else None, m.group(2) if m else None,
                      _count_rows(path / "trades.csv"), validated, confirmed)


def honesty_line(root: Path = REPORTS_DIR) -> str:
    """What the latest analysis actually found, in one sentence, to be shown beside the suggestions.

    It is read from the report rather than written into the code so it cannot go stale: today it says
    nothing has been validated because nothing has, and the day a rule survives out of sample it will
    say so by itself. A disclaimer that stops matching the evidence is worse than none, in both
    directions — it either overstates what is known or hides it.
    """
    reports = list_reports(root)
    if not reports:
        return t("No analysis has been run yet, so nothing here has been tested against history.")
    best = max(reports, key=lambda r: (r.wf_confirmed, r.validated))
    if best.validated == 0:
        return t("The latest analysis validated no rule out of sample: there is no measured edge "
                 "here yet, only events and what similar ones did.")
    # one rule is not "1 rules", and this line is read by someone deciding whether to risk money
    rules = (t("1 rule") if best.validated == 1
             else t("{count} rules", count=best.validated))
    if best.wf_confirmed == 0:
        return t("The latest analysis validated {rules} out of sample, none confirmed by "
                 "walk-forward.", rules=rules)
    return t("The latest analysis validated {rules} out of sample, {confirmed} confirmed by "
             "walk-forward.", rules=rules, confirmed=best.wf_confirmed)


def list_reports(root: Path = REPORTS_DIR) -> list[ReportInfo]:
    """Every folder holding an ``edge_report.md`` (up to two levels deep), newest first."""
    root = Path(root)
    if not root.exists():
        return []
    folders = {p.parent for p in root.glob("edge_report.md")} | {p.parent for p in root.glob("*/edge_report.md")} \
        | {p.parent for p in root.glob("*/*/edge_report.md")}
    infos = [i for i in (report_info(f) for f in folders) if i is not None]
    return sorted(infos, key=lambda i: i.modified, reverse=True)


def _csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path) if path.exists() and path.stat().st_size > 1 else pd.DataFrame()
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def load_report(path: Path) -> dict:
    path = Path(path)
    rules = _csv(path / "rules.csv")
    if "validated" in rules:
        rules = rules[rules["validated"]]
    return {"markdown": (path / "edge_report.md").read_text(encoding="utf-8"),
            "rules": rules, "walk_forward": _csv(path / "walk_forward.csv"),
            "candidates": _csv(path / "candidates.csv"), "trades": _csv(path / "trades.csv"),
            "events": _csv(path / "events.csv"), "profiles": _csv(path / "profiles.csv")}


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
