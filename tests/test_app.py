"""Desktop app: pure data functions and the screens (offscreen, no real settings or credentials)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import pandas as pd
import pytest

pytest.importorskip("PySide6")

from miratrade.app import data
from miratrade.brokers.credentials import CredentialStore
from miratrade.brokers.schwab import SchwabAuth


class MemoryKeyring:
    def __init__(self):
        self.data = {}

    def set_password(self, s, k, v):
        self.data[(s, k)] = v

    def get_password(self, s, k):
        return self.data.get((s, k))

    def delete_password(self, s, k):
        self.data.pop((s, k))


def _report(root, name, validated=1):
    d = root / name
    d.mkdir(parents=True)
    (d / "edge_report.md").write_text("# MiraTrade edge report\n\nWindow: **2025-09-25 → 2026-09-25** · x\n",
                                      encoding="utf-8")
    pd.DataFrame({"ticker": ["A", "B", "C"]}).to_csv(d / "trades.csv", index=False)
    pd.DataFrame({"rule": ["ins:any_buy", "flow:bullish"], "validated": [True, validated > 1],
                  "wf_confirmed": [True, False], "test_avg_r": [0.9, 0.1]}).to_csv(d / "rules.csv", index=False)
    pd.DataFrame({"fold": [1], "picked_n": [3]}).to_csv(d / "walk_forward.csv", index=False)
    return d


def test_report_listing_and_loading(tmp_path):
    _report(tmp_path, "old")
    new = _report(tmp_path, "sub/new", validated=2)
    os.utime(new / "edge_report.md", (2e9, 2e9))
    infos = data.list_reports(tmp_path)
    assert [i.name for i in infos] == ["new", "old"]
    assert infos[0].start == "2025-09-25" and infos[0].trades == 3 and infos[0].validated == 2
    assert infos[1].wf_confirmed == 1 and "1 con walk-forward" in infos[1].summary
    rep = data.load_report(new)
    assert list(rep["rules"]["rule"]) == ["ins:any_buy", "flow:bullish"] and rep["candidates"].empty


def test_settings_round_trip_rejects_bad_values(tmp_path):
    path = tmp_path / "settings.json"
    cfg = data.read_settings(path)
    cfg.risk.max_positions = 3
    cfg.broker.live_trading = True
    data.write_settings(cfg, path)
    again = data.read_settings(path)
    assert again.risk.max_positions == 3 and again.broker.live_trading
    path.write_text(json.dumps({"risk": {"max_postions": 9}}), encoding="utf-8")   # typo
    with pytest.raises(ValueError, match="unknown setting"):
        data.read_settings(path)


@pytest.fixture
def window(qtbot, tmp_path):
    from miratrade.app.theme import QSS
    from miratrade.app.window import MainWindow
    from PySide6.QtWidgets import QApplication

    QApplication.instance().setStyleSheet(QSS)
    _report(tmp_path / "reports", "r1")
    auth = SchwabAuth(CredentialStore(backend=MemoryKeyring()))
    w = MainWindow(reports_dir=tmp_path / "reports", settings_path=tmp_path / "settings.json", auth=auth)
    qtbot.addWidget(w)
    return w


def test_window_navigation_and_practice_mode(window):
    assert window.mode.text() == "● MODO PRÁCTICA"
    window.nav.button(2).click()
    assert window.pages.currentWidget() is window.reports
    assert window.reports.history.count() == 1
    assert window.reports.rules.model().rowCount() == 1        # only the validated rule
    assert "2025-09-25" in window.reports.heading.text()


def test_settings_page_saves_and_header_follows(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    s = window.settings
    assert "Sin credenciales" in s.schwab_status.text()
    s.max_positions.setValue(4)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.No)
    s.live.setChecked(True)                                     # declined in the dialog
    assert not s.live.isChecked()
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Yes)
    s.live.setChecked(True)
    s.save()
    saved = json.loads(s.settings_path.read_text(encoding="utf-8"))
    assert saved["risk"]["max_positions"] == 4 and saved["broker"]["live_trading"] is True
    assert window.mode.text() == "● DINERO REAL PERMITIDO"


def test_risk_above_ceiling_is_not_saved(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]) or QMessageBox.Ok)
    s = window.settings
    s.risk_ceiling.setValue(1.0)
    s.risk_pct.setValue(1.5)
    s.save()
    assert warned and not s.settings_path.exists()


def test_stop_all_asks_first(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    started = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.No)
    monkeypatch.setattr(window.pool, "start", lambda w: started.append(w))
    window.stop_all()
    assert started == []                                        # declined: nothing sent
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Yes)
    window.stop_all()
    assert len(started) == 1 and not window.stop_btn.isEnabled()
