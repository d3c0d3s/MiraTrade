"""Desktop app: pure data functions and the screens (offscreen, no real settings or credentials)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import numpy as np
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
    from miratrade.brokers.etrade import EtradeAuth

    auth = SchwabAuth(CredentialStore(backend=MemoryKeyring()))
    w = MainWindow(reports_dir=tmp_path / "reports", settings_path=tmp_path / "settings.json", auth=auth,
                   scan_dir=tmp_path / "scan", etrade_auth=EtradeAuth(CredentialStore(backend=MemoryKeyring())))
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


def test_signals_page_empty_state(window):
    s = window.signals
    assert window.pages.currentWidget() is s
    assert s.list.count() == 0 and not s.empty.isHidden() and "Buscar eventos" in s.empty.text()
    assert s.variant.currentData() == "call45_40" and not s.preview_btn.isEnabled()


def test_signals_page_shows_events_with_evidence(qtbot, tmp_path):
    from miratrade.app.pages.signals import SignalsPage
    from miratrade.scan import save_scan

    # a saved scan with one insider event and one 13D event
    idx = pd.bdate_range("2026-05-01", periods=120)
    bars = pd.DataFrame({"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1e6}, index=idx)
    events = pd.DataFrame([
        {"ticker": "ACME", "signal_date": idx[-3], "close": 10.2, "event:insider_buy": True, "event:flow": False,
         "event:13dg": False, "ins:exec_buy": True, "trend:up": True, "what": "2 directivos compraron 1,2 M$"},
        {"ticker": "KLTR", "signal_date": idx[-5], "close": 10.2, "event:insider_buy": False, "event:flow": False,
         "event:13dg": True, "own:13d": True, "trend:up": False, "what": "Fondo X presentó un 13D"}])
    save_scan({"events": events, "prices": {"ACME": bars, "KLTR": bars}, "since": idx[-7].date(),
               "end": idx[-1].date()}, tmp_path / "scan")
    # a report whose events.csv holds 40 past insider events (half reached the target)
    rep = tmp_path / "reports" / "5y"
    rep.mkdir(parents=True)
    pd.DataFrame({"event:insider_buy": [True] * 40, "event:flow": False, "event:13dg": False,
                  "ins:exec_buy": [True] * 40, "res_call45_40": [1.0, -1.0] * 20,
                  "ret_call45_40": [0.4, -0.25] * 20}).to_csv(rep / "events.csv", index=False)

    page = SignalsPage(tmp_path / "reports", tmp_path / "scan")
    qtbot.addWidget(page)
    assert page.list.count() == 2 and page.empty.isHidden()
    assert page.ticker.text() == "ACME" and page.price.text() == "10,20 $"
    assert "40 eventos parecidos: 50 %" in page.evidence_text.text()
    assert "Ninguna todavía" in page.rules_text.text()
    assert "Tendencia al alza" in page.context.text()
    assert page.chart.event_date == idx[-3] and len(page.chart.df) == 120
    page.list.setCurrentRow(1)                                  # 13D: no such events in the report
    assert page.ticker.text() == "KLTR" and "Sin eventos parecidos" in page.evidence_text.text()
    assert page.chart.event_shape == "■"
    page.variant.setCurrentIndex(page.variant.findData("stock12m_30"))
    assert page.profile.text().startswith("Acción 12 meses")


def test_brand_assets_load(qtbot):
    from miratrade.app import brand

    families = brand.load_fonts()
    assert "IBM Plex Sans" in families and "IBM Plex Mono" in families
    assert not brand.app_icon().isNull()
    w = brand.nav_brand()
    qtbot.addWidget(w)
    s = brand.splash()
    assert not s.pixmap().isNull()
    s.close()


def test_scan_command_arguments(tmp_path):
    args = data.scan_command(7, "call45_40", tmp_path / "scan", tmp_path / "rep", "mid")
    assert args[args.index("scan") + 1:] == ["--days", "7", "--variant", "call45_40", "--save",
                                             str(tmp_path / "scan"), "--cap", "mid",
                                             "--report", str(tmp_path / "rep")]
    assert data.analyze_command(90, tmp_path / "out", "mega")[-2:] == ["--cap", "mega"]


def test_market_data_settings_need_consent_for_research_sources(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    s = window.settings
    assert s.price_source.currentData() == "schwab" and "Sin claves" in s.etrade_status.text()
    s.price_source.setCurrentIndex(s.price_source.findData("research"))
    assert "investigación personal" in s.source_note.text()
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.No)
    s.save()
    saved = json.loads(s.settings_path.read_text(encoding="utf-8"))
    assert saved["data"]["price_source"] == "schwab"                # declined: stays on the licensed source
    s.price_source.setCurrentIndex(s.price_source.findData("research"))
    s.quote_broker.setCurrentIndex(s.quote_broker.findData("etrade"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Yes)
    s.save()
    saved = json.loads(s.settings_path.read_text(encoding="utf-8"))
    assert saved["data"]["price_source"] == "research" and saved["data"]["quote_broker"] == "etrade"


def test_data_folders_do_not_depend_on_the_launch_directory(tmp_path, monkeypatch):
    """A desktop shortcut starts the app in .venv/Scripts: the cache and the reports must still
    be the ones in the checkout, or every analysis re-downloads everything."""
    import subprocess
    import sys

    code = ("from miratrade.config import CACHE_DIR, REPORTS_DIR, base_dir;"
            "print(CACHE_DIR.is_absolute(), REPORTS_DIR.is_absolute(), CACHE_DIR.parent == base_dir())")
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["True", "True", "True"]

    monkeypatch.setenv("MIRATRADE_REPORTS", str(tmp_path / "otros"))
    code = "from miratrade.config import data_dir; print(data_dir('MIRATRADE_REPORTS', 'reports'))"
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == str(tmp_path / "otros")            # the variable still wins


def test_signals_banner_offers_a_way_out_when_no_broker_is_connected(window, monkeypatch):
    """Schwab not approved yet: say so before any download and let one click switch sources."""
    from PySide6.QtWidgets import QMessageBox

    s = window.signals
    assert not s.banner.isHidden() and not s.scan_btn.isEnabled()
    assert "Schwab" in s.source_msg.text()
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.No)
    s.research_btn.click()
    assert not s.scan_btn.isEnabled()                       # declined: still blocked
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Yes)
    s.research_btn.click()
    assert s.banner.isHidden() and s.scan_btn.isEnabled()   # now a scan can run
    assert json.loads(window.settings.settings_path.read_text(encoding="utf-8"))["data"]["price_source"] == "research"


def _scan_with(tmp_path, tickers):
    from miratrade.scan import save_scan

    idx = pd.bdate_range("2026-01-01", periods=120)
    # a real price path: a contract can only be modelled when the stock has some volatility
    close = pd.Series(10 * (1.002 ** np.arange(120)) * (1 + 0.02 * np.sin(np.arange(120))), index=idx)
    bars = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)
    events = pd.DataFrame([{"ticker": t, "signal_date": idx[-3], "close": float(close.iloc[-3]),
                            "event:insider_buy": True,
                            "event:flow": False, "event:13dg": False,
                            "what": f"{t}: un directivo compró"} for t in tickers])
    save_scan({"events": events, "prices": {t: bars for t in tickers}, "since": idx[-7].date(),
               "end": idx[-1].date()}, tmp_path / "scan")
    (tmp_path / "settings.json").write_text(json.dumps({"data": {"price_source": "research"}}), encoding="utf-8")


def test_signals_filter_by_ticker(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    from miratrade.app.pages.signals import SignalsPage

    _scan_with(tmp_path, ["ACME", "ACOG", "KLTR"])
    page = SignalsPage(tmp_path / "reports", tmp_path / "scan", settings_path=tmp_path / "settings.json")
    qtbot.addWidget(page)

    def visible():
        return [page.list.item(i).data(Qt.UserRole)["ticker"] for i in range(page.list.count())
                if not page.list.item(i).isHidden()]

    assert page.count.text() == "3 EVENTOS" and page.filter.isEnabled() and page.empty.isHidden()
    page.filter.setText("ac")                                   # case-insensitive, partial
    assert visible() == ["ACME", "ACOG"] and page.count.text() == "2 DE 3"
    assert page.ticker.text() == "ACME"                         # still visible: selection kept
    page.filter.setText("kl")
    assert visible() == ["KLTR"] and page.ticker.text() == "KLTR"   # moved to the visible one
    page.filter.setText("zzz")
    assert visible() == [] and page.count.text() == "0 DE 3"
    assert not page.empty.isHidden() and "zzz" in page.empty.text() and page.ticker.text() == ""
    page.filter.clear()
    assert len(visible()) == 3 and page.count.text() == "3 EVENTOS" and page.empty.isHidden()


def test_event_card_height_follows_the_wrapped_text(qtbot):
    """Long filer names wrap: the row must grow, or the date below them gets cut off."""
    from miratrade.app.pages.signals import EventCard

    base = {"ticker": "ACME", "signal_date": pd.Timestamp("2026-09-25"), "event:insider_buy": True,
            "event:flow": False, "event:13dg": False}
    short = EventCard({**base, "what": "1 directivo compró 43 k$"})
    long = EventCard({**base, "what": "Frazier Life Sciences Public Fund, L.P. presentó un 13G en la empresa"})
    for c in (short, long):
        qtbot.addWidget(c)
    assert long.fit(284) > short.fit(284)
    assert short.fit(284) == short.fit(284)             # stable when measured twice
    assert long.fit(600) < long.fit(284)                # wider card, fewer lines


def test_company_size_filter_is_shared_by_both_screens(window):
    """One setting, two screens: choosing a size in Señales must reach Reportes and the commands."""
    s, r = window.signals, window.reports
    assert s.cap.currentData() == "all" and r.cap.currentData() == "all"
    s.cap.setCurrentIndex(s.cap.findData("mid"))
    assert json.loads(s.settings_path.read_text(encoding="utf-8"))["data"]["cap_tier"] == "mid"
    r.refresh_cap()
    assert r.cap.currentData() == "mid"
    assert "--cap" in data.scan_command(7, "call45_40", s.scan_dir, None, s.cap.currentData())
    r.cap.setCurrentIndex(r.cap.findData("mega"))                # and the other way round
    s.refresh_cap()
    assert s.cap.currentData() == "mega"


def test_contract_card_shows_the_modelled_call(qtbot, tmp_path):
    from miratrade.app.pages.signals import SignalsPage

    _scan_with(tmp_path, ["ACME"])
    page = SignalsPage(tmp_path / "reports", tmp_path / "scan", settings_path=tmp_path / "settings.json")
    qtbot.addWidget(page)
    card = page.contract
    assert card.head.text().startswith("ACME") and card.head.text().endswith("C")
    assert "días" in card.sub.text() and "$" in card.values["premium"].text()
    assert card.values["delta"].text() not in ("", "–") and "%" in card.values["iv"].text()
    assert "Vender en" in card.exits.text() and "stop en" in card.exits.text()
    page.variant.setCurrentIndex(page.variant.findData("stock12m_30"))   # shares: no contract
    assert card.head.text() == "Sin contrato" and "acción" in card.sub.text()
    assert card.values["premium"].text() == "–"
