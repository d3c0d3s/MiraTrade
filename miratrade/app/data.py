"""Everything the screens show, as plain functions (no Qt), so it can be tested directly."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

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
        span = f"{self.start} → {self.end}" if self.start else "sin fechas"
        return f"{self.name}  ·  {span}"

    @property
    def summary(self) -> str:
        if self.validated == 0:
            return f"{self.trades} operaciones · sin reglas validadas"
        return f"{self.trades} operaciones · {self.validated} reglas validadas · {self.wf_confirmed} con walk-forward"


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

def read_settings(path: Path = SETTINGS_PATH) -> Config:
    return load_user_config(path)


def write_settings(cfg: Config, path: Path = SETTINGS_PATH) -> None:
    """Save the user-editable sections; re-read to make sure the file is valid."""
    from dataclasses import asdict

    data = {"risk": asdict(cfg.risk), "broker": asdict(cfg.broker), "data": asdict(cfg.data),
            "ui": asdict(cfg.ui)}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    load_user_config(tmp)                   # raises if something is off; the old file stays
    tmp.replace(path)


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
    """A size selector shared by Señales and Reportes."""
    from PySide6.QtWidgets import QComboBox

    from miratrade.config import CAP_TIERS

    box = QComboBox()
    for key, (_low, _high, label) in CAP_TIERS.items():
        box.addItem(label, key)
    box.setCurrentIndex(max(0, box.findData(current)))
    box.setAccessibleName("Tamaño de empresa")
    box.setToolTip("Reduce las empresas a descargar y simular. Ahorra tiempo; en el análisis de 5 años "
                   "ningún tramo de tamaño mostró ventaja por sí solo.")
    box.currentIndexChanged.connect(lambda _: on_change(box.currentData()))
    return box
