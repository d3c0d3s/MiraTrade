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
    from miratrade import store

    # a database of its own: a test must never read, or wait on, the user's real market data
    db = store.connect(tmp_path / "market.db")
    w = MainWindow(reports_dir=tmp_path / "reports", settings_path=tmp_path / "settings.json", auth=auth,
                   scan_dir=tmp_path / "scan", etrade_auth=EtradeAuth(CredentialStore(backend=MemoryKeyring())),
                   practice_path=tmp_path / "practice.json", db=db)
    qtbot.addWidget(w)
    return w


def test_window_navigation_and_practice_mode(window):
    from miratrade.app.window import PAGES

    assert window.mode.text() == "● MODO PRÁCTICA"
    for name, page in (("Scanner", window.scanner), ("Practice", window.practice),
                       ("Reports", window.reports), ("Settings", window.settings),
                       ("Signals", window.signals)):
        window.nav.button(PAGES.index(name)).click()       # by name: the order may change again
        assert window.pages.currentWidget() is page, name
    window.nav.button(PAGES.index("Reports")).click()
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
    from miratrade.app.window import PAGES

    s = window.signals
    window.nav.button(PAGES.index("Signals")).click()     # the app now opens on the Scanner
    assert window.pages.currentWidget() is s
    assert s.list.count() == 0 and not s.empty.isHidden() and "Actualizar datos" in s.empty.text()
    assert s.variant.currentData() == "call45_40" and not s.preview_btn.isEnabled()


def _scan_store(tmp_path, result):
    """Save a scan the way a real one is saved: the CSV for the chart prices, and the shared market
    database, which is what the screen filters on. Returns the connection to hand the page."""
    from miratrade import store
    from miratrade.scan import save_scan, store_scan

    save_scan(result, tmp_path / "scan")
    db = store.connect(tmp_path / "market.db")
    store_scan(result, db)
    return db


def test_signals_page_shows_events_with_evidence(qtbot, tmp_path):
    from miratrade.app.pages.signals import SignalsPage

    # a saved scan with one insider event and one 13D event
    idx = pd.bdate_range("2026-05-01", periods=120)
    bars = pd.DataFrame({"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1e6}, index=idx)
    events = pd.DataFrame([
        {"ticker": "ACME", "signal_date": idx[-3], "close": 10.2, "event:insider_buy": True, "event:flow": False,
         "event:13dg": False, "ins:exec_buy": True, "trend:up": True, "what": "2 directivos compraron 1,2 M$"},
        {"ticker": "KLTR", "signal_date": idx[-5], "close": 10.2, "event:insider_buy": False, "event:flow": False,
         "event:13dg": True, "own:13d": True, "trend:up": False, "what": "Fondo X presentó un 13D"}])
    db = _scan_store(tmp_path, {"events": events, "prices": {"ACME": bars, "KLTR": bars},
                                "since": idx[-7].date(), "end": idx[-1].date()})
    # a report whose events.csv holds 40 past insider events (half reached the target)
    rep = tmp_path / "reports" / "5y"
    rep.mkdir(parents=True)
    pd.DataFrame({"event:insider_buy": [True] * 40, "event:flow": False, "event:13dg": False,
                  "ins:exec_buy": [True] * 40, "res_call45_40": [1.0, -1.0] * 20,
                  "ret_call45_40": [0.4, -0.25] * 20}).to_csv(rep / "events.csv", index=False)

    (tmp_path / "settings.json").write_text(json.dumps({"data": {"price_source": "research"}}), encoding="utf-8")
    page = SignalsPage(tmp_path / "reports", tmp_path / "scan",
                       settings_path=tmp_path / "settings.json", db=db)
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
    idx = pd.bdate_range("2026-01-01", periods=120)
    # a real price path: a contract can only be modelled when the stock has some volatility
    close = pd.Series(10 * (1.002 ** np.arange(120)) * (1 + 0.02 * np.sin(np.arange(120))), index=idx)
    bars = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)
    events = pd.DataFrame([{"ticker": t, "signal_date": idx[-3], "close": float(close.iloc[-3]),
                            "event:insider_buy": True,
                            "event:flow": False, "event:13dg": False,
                            "what": f"{t}: un directivo compró"} for t in tickers])
    db = _scan_store(tmp_path, {"events": events, "prices": {t: bars for t in tickers},
                                "since": idx[-7].date(), "end": idx[-1].date()})
    (tmp_path / "settings.json").write_text(json.dumps({"data": {"price_source": "research"}}), encoding="utf-8")
    return db


def test_signals_filter_by_ticker(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    from miratrade.app.pages.signals import SignalsPage

    db = _scan_with(tmp_path, ["ACME", "ACOG", "KLTR"])
    page = SignalsPage(tmp_path / "reports", tmp_path / "scan",
                       settings_path=tmp_path / "settings.json", db=db)
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

    db = _scan_with(tmp_path, ["ACME"])
    page = SignalsPage(tmp_path / "reports", tmp_path / "scan",
                       settings_path=tmp_path / "settings.json", db=db)
    qtbot.addWidget(page)
    card = page.contract
    assert card.head.text().startswith("ACME") and card.head.text().endswith("C")
    assert "días" in card.sub.text() and "$" in card.values["premium"].text()
    assert card.values["delta"].text() not in ("", "–") and "%" in card.values["iv"].text()
    assert "Vender en" in card.exits.text() and "stop en" in card.exits.text()
    page.variant.setCurrentIndex(page.variant.findData("stock12m_30"))   # shares: no contract
    assert card.head.text() == "Sin contrato" and "acción" in card.sub.text()
    assert card.values["premium"].text() == "–"


def test_window_and_size_filter_without_searching_again(qtbot, tmp_path):
    """Changing the days or the size must rearrange what is on screen, never start a download."""
    from miratrade.app.pages.signals import SignalsPage

    idx = pd.bdate_range("2026-01-01", periods=120)
    close = pd.Series(10 * (1.002 ** np.arange(120)) * (1 + 0.02 * np.sin(np.arange(120))), index=idx)
    bars = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=idx)
    events = pd.DataFrame([
        {"ticker": "BIG", "signal_date": idx[-2], "close": 10.0, "mkt_cap": 500e9, "what": "hoy, gigante",
         "event:insider_buy": True, "event:flow": False, "event:13dg": False},
        {"ticker": "SML", "signal_date": idx[-2], "close": 10.0, "mkt_cap": 800e6, "what": "hoy, pequeña",
         "event:insider_buy": True, "event:flow": False, "event:13dg": False},
        {"ticker": "OLD", "signal_date": idx[-15], "close": 10.0, "mkt_cap": 500e9, "what": "antigua",
         "event:insider_buy": True, "event:flow": False, "event:13dg": False}])
    db = _scan_store(tmp_path, {"events": events, "prices": {t: bars for t in ("BIG", "SML", "OLD")},
                                "since": idx[-25].date(), "end": idx[-1].date()})
    (tmp_path / "settings.json").write_text(json.dumps({"data": {"price_source": "research"}}), encoding="utf-8")

    page = SignalsPage(tmp_path / "reports", tmp_path / "scan",
                       settings_path=tmp_path / "settings.json", db=db)
    qtbot.addWidget(page)
    started = []
    page.start_scan = lambda: started.append(1)              # nothing here may fetch

    def listed():
        return {page.list.item(i).data(Qt_UserRole)["ticker"] for i in range(page.list.count())}

    from PySide6.QtCore import Qt as _Qt
    Qt_UserRole = _Qt.UserRole
    page.days.setValue(7)                                    # the window is whatever it is set to
    assert listed() == {"BIG", "SML"}                        # OLD is 15 days back
    page.days.setValue(60)
    assert listed() == {"BIG", "SML", "OLD"}                 # wider window, no download
    page.cap.setCurrentIndex(page.cap.findData("mega"))
    assert listed() == {"BIG", "OLD"} and "tamaño" in page.coverage.text().lower()
    page.cap.setCurrentIndex(page.cap.findData("small"))
    assert listed() == {"SML"}
    page.cap.setCurrentIndex(page.cap.findData("all"))
    page.days.setValue(60)
    assert len(listed()) == 3 and started == []              # never searched again


def test_automatic_refresh_respects_the_floor_and_never_overlaps(window, monkeypatch):
    """A timer may repeat the download, but not faster than the floor, not while one is running,
    and not when there is nowhere to get prices from."""
    from PySide6.QtCore import QTime

    from miratrade.config import MIN_AUTO_REFRESH_MINUTES

    s = window.settings
    sig = window.signals
    assert not sig.auto.isActive()                              # off by default

    started = []
    monkeypatch.setattr(sig, "start_scan", lambda: started.append(1))

    s.auto_refresh.setValue(MIN_AUTO_REFRESH_MINUTES - 1)       # below the floor: stays off
    s.save()
    assert not sig.auto.isActive()

    s.auto_refresh.setValue(15)
    s.weekdays_only.setChecked(False)                           # a window that is always open,
    s.window_from.setTime(QTime(0, 0))                          # so this test is about the other
    s.window_to.setTime(QTime(23, 59))                          # rules, not about today's date
    s.save()
    assert sig.auto.isActive() and sig.auto.interval() == 15 * 60_000
    assert "automático cada 15 min" in sig.scan_btn.text()

    sig.scan_btn.setEnabled(True)
    sig._tick()
    assert started == [1]

    sig.proc = object()                                         # a download already running
    sig._tick()
    assert started == [1]
    sig.proc = None

    sig.scan_btn.setEnabled(False)                              # no price source
    sig._tick()
    assert started == [1]

    s.window_from.setTime(QTime(3, 0))                          # a window that excludes now
    s.window_to.setTime(QTime(3, 1))
    s.save()
    assert not sig.in_refresh_window()
    sig.scan_btn.setEnabled(True)
    sig._tick()
    assert started == [1] and "en pausa" in sig.scan_btn.text()

    s.auto_refresh.setValue(0)
    s.save()
    assert not sig.auto.isActive() and sig.scan_btn.text() == "Actualizar datos"


def test_download_window_is_a_setting(window):
    s = window.settings
    s.scan_days.setValue(45)
    s.save()
    assert json.loads(s.settings_path.read_text(encoding="utf-8"))["data"]["scan_days"] == 45


def test_adding_an_event_to_practice_and_seeing_it_there(window, monkeypatch, tmp_path):
    """The two screens are one flow: the contract on Señales becomes a paper position on Práctica."""
    from PySide6.QtWidgets import QMessageBox

    from miratrade.practice import PRACTICE_PATH

    monkeypatch.setattr("miratrade.practice.PRACTICE_PATH", tmp_path / "practice.json")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    sig, prac = window.signals, window.practice
    prac.path = tmp_path / "practice.json"

    sig._contract = None                                        # nothing chosen yet
    sig.add_to_practice()
    assert prac.trades == []

    sig._contract = {"premium": 4.0, "stop": 3.0, "target": 5.6, "strike": 50.0,
                     "expiry": pd.Timestamp("2026-11-20"), "iv": 0.4}
    item = type("Item", (), {"data": staticmethod(lambda role: {"ticker": "ACME", "what": "3 directivos"})})()
    monkeypatch.setattr(sig.list, "currentItem", lambda: item)
    sig.add_to_practice()

    prac.reload()
    assert len(prac.trades) == 1
    t = prac.trades[0]
    assert t.ticker == "ACME" and t.kind == "call" and t.quantity >= 1 and t.note == "3 directivos"
    assert prac.open_table.rowCount() == 1 and prac.done_table.rowCount() == 0
    assert "ACME 50 C" in prac.open_table.item(0, 0).text()      # translated label
    assert prac.empty.isHidden()

    sig.add_to_practice()                                       # the same ticker twice is refused
    prac.reload()
    assert len(prac.trades) == 1


def test_practice_marks_and_closes_from_the_saved_prices(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    from miratrade.practice import open_trade, save

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    prac = window.practice
    prac.path = tmp_path / "practice.json"
    trades = []
    open_trade(trades, ticker="ACME", kind="call", entry=4.0, stop=3.0, target=5.6, equity=25_000.0,
               strike=50.0, expiry="2026-11-20", iv=0.4)
    save(trades, prac.path)
    prac.reload()

    monkeypatch.setattr(prac, "latest_prices", lambda: {"ACME": 80.0})   # deep in the money
    prac.mark_now()
    assert prac.trades[0].status == "closed" and prac.trades[0].exit_reason == "target"
    assert prac.done_table.rowCount() == 1 and prac.open_table.rowCount() == 0
    assert "objetivo" in prac.done_table.item(0, 6).text()       # shown in the chosen language
    assert len(load_practice(prac.path)) == 1                   # and it was written to disk


def load_practice(path):
    from miratrade.practice import load

    return load(path)


def test_practice_says_which_balance_it_sized_on(window, monkeypatch, tmp_path):
    """Sizes come from a figure the user set, not their account, and the screen names which it
    used. Reading the real balance is theirs to switch on: a suggestion sized to somebody's own
    money is advice about that money rather than analysis of a market."""
    from miratrade.brokers.base import Account
    from miratrade.practice import DEFAULT_EQUITY

    prac = window.practice
    prac.path = tmp_path / "practice.json"

    asked = []
    monkeypatch.setattr(data, "quote_broker", lambda path=None: asked.append(1) or None)
    prac.reload()
    assert prac.equity == DEFAULT_EQUITY and prac.equity_source == "typed"
    assert "el capital que fijaste" in prac.totals.text()
    assert asked == []                     # the broker was not consulted at all

    class Broker:
        name = "etrade"

        def accounts(self):
            return [Account(number_masked="…1", account_hash="h", equity=8_000.0, cash=0.0,
                            buying_power=0.0)]

    monkeypatch.setattr(data, "quote_broker", lambda path=None: Broker())
    prac.reload()
    assert prac.equity == DEFAULT_EQUITY          # still not, until it is switched on

    cfg = data.read_settings(prac.settings_path)
    cfg.risk.size_on_balance = True
    data.write_settings(cfg, prac.settings_path)
    prac.reload()
    assert prac.equity == 8_000.0 and prac.equity_source == "etrade"
    assert "E*TRADE" in prac.totals.text() and "8.000,00 $" in prac.totals.text()


# --------------------------------------------------------------------------- Scanner

def _scanner_db(tmp_path):
    from miratrade import store

    db = store.connect(tmp_path / "market.db")
    store.write(db, "insiders", pd.DataFrame([
        {"accession": "0001-26-1", "filing_date": "2026-09-20", "trade_date": "2026-09-19",
         "ticker": "PFE", "owner": "BOURLA ALBERT", "title": "CEO", "code": "P", "shares": 38000.0,
         "price": 26.34, "value": 1_000_920.0, "is_officer": 1, "is_director": 0, "is_ten_pct": 0,
         "plan_10b5_1": 0, "issuer_cik": "0000078003"},
        {"accession": "0001-26-2", "filing_date": "2026-09-21", "trade_date": "2026-09-20",
         "ticker": "ACME", "owner": "DOE JANE", "title": "Director", "code": "S", "shares": 10.0,
         "price": 5.0, "value": 50.0, "is_officer": 0, "is_director": 1, "is_ten_pct": 0,
         "plan_10b5_1": 1, "issuer_cik": "0000001"}]))
    return db


def test_scanner_lists_what_was_collected_and_filters_it_in_the_database(qtbot, tmp_path,
                                                                        monkeypatch):
    """The Scanner shows rows as filed. Changing a filter re-queries: it must not need a rescan."""
    from datetime import date

    from PySide6.QtCore import Qt

    from miratrade.app.pages.scanner import ScannerPage

    page = ScannerPage(db=_scanner_db(tmp_path), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(page)
    monkeypatch.setattr("miratrade.scanner.date", type("D", (), {"today": staticmethod(
        lambda: date(2026, 9, 27))}))
    page.days.setValue(30)

    assert page.table.model().rowCount() == 2
    assert "2" in page.count.text()
    headings = [page.table.model().headerData(i, Qt.Horizontal)
                for i in range(page.table.model().columnCount())]
    assert "Presentado" in headings and "Directivo" in headings      # translated, and no link column
    assert "Documento" not in headings

    page.code.setCurrentIndex(page.code.findData("P"))               # only open-market purchases
    assert page.table.model().rowCount() == 1
    page.ticker.setText("ACME")                                     # …and ACME's row is a sale
    assert page.table.model().rowCount() == 0
    page.ticker.clear()
    page.code.setCurrentIndex(page.code.findData(""))
    assert page.table.model().rowCount() == 2


def test_scanner_shows_only_the_filters_the_chosen_source_understands(qtbot, tmp_path):
    from miratrade.app.pages.scanner import ScannerPage

    page = ScannerPage(db=_scanner_db(tmp_path), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(page)
    page.show()

    assert page.code.isVisible() and page.plan.isVisible()          # insiders have a code and a plan
    assert not page.chamber.isVisible() and not page.stake_kind.isVisible()

    page.source.setCurrentIndex(page.source.findData("congress"))
    assert page.chamber.isVisible() and page.member.isVisible()
    assert not page.code.isVisible() and not page.plan.isVisible()
    assert "45" in page.note.text() or "105" in page.note.text()    # the note explains the lag

    page.source.setCurrentIndex(page.source.findData("prices"))
    assert page.ticker.isVisible() and not page.amount.isVisible()


def test_scanner_explains_an_unreadable_database_instead_of_crashing(qtbot, tmp_path):
    from miratrade.app.pages.scanner import ScannerPage

    page = ScannerPage(db=object(), settings_path=tmp_path / "settings.json")   # not a connection
    qtbot.addWidget(page)
    assert page.table.model().rowCount() == 0
    # the message names the file it could not read: "unable to open database file" on its own tells
    # a person neither what is missing nor where it was looked for
    assert "market.db" in page.count.text() and "No se pudo leer" in page.count.text()
    assert not page.export_btn.isEnabled()


def test_scanner_exports_exactly_the_rows_shown(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from miratrade.app.pages.scanner import ScannerPage

    page = ScannerPage(db=_scanner_db(tmp_path), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(page)
    page.days.setValue(0)                                    # everything collected
    page.code.setCurrentIndex(page.code.findData("P"))
    out = tmp_path / "rows.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    page.export()

    written = pd.read_csv(out)
    assert len(written) == 1 and written.iloc[0]["Ticker"] == "PFE"
    assert "Filing" not in written.columns                   # the link is a button, not a column
    assert str(out) in page.count.text()


def test_scanner_opens_the_original_filing_for_the_selected_row(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from miratrade.app.pages.scanner import ScannerPage

    page = ScannerPage(db=_scanner_db(tmp_path), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(page)
    page.days.setValue(0)
    page.ticker.setText("PFE")
    opened, told = [], []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[-1]))

    page.open_filing()                                       # nothing selected: it says so
    assert opened == [] and len(told) == 1
    page.table.setCurrentIndex(page.table.model().index(0, 0))
    page.open_filing()
    assert len(opened) == 1
    assert opened[0].startswith("https://www.sec.gov/Archives/edgar/data/78003/")


def test_scanner_sorts_on_the_real_values_when_a_heading_is_clicked(qtbot, tmp_path):
    from miratrade.app.pages.scanner import ScannerPage

    page = ScannerPage(db=_scanner_db(tmp_path), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(page)
    page.days.setValue(0)
    value_column = [c.label for c in page.current.columns].index("Value")

    page.sort_column(value_column)                           # biggest first
    assert page.rows.sort_values("Value", ascending=False).iloc[0]["Ticker"] == "PFE"
    assert page.sort_by == "Value" and page.sort_desc is True
    page.sort_column(value_column)                           # clicking again turns it round
    assert page.sort_desc is False
    assert page.selected_row() is None                       # still nothing selected


def test_scanner_writes_figures_in_the_users_number_format(qtbot, tmp_path):
    """The table model formats floats the English way. Money and counts on this screen go through
    the interface's own formatter instead, and are aligned right although they are then text."""
    from PySide6.QtCore import Qt

    from miratrade.app.pages.scanner import ScannerPage

    page = ScannerPage(db=_scanner_db(tmp_path), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(page)
    page.days.setValue(0)
    page.ticker.setText("PFE")
    model = page.table.model()
    shown = {model.headerData(i, Qt.Horizontal): model.data(model.index(0, i))
             for i in range(model.columnCount())}

    assert shown["Acciones"] == "38.000"            # a share count has no cents
    assert shown["Precio"] == "26,34"               # and the decimal comma of the language
    assert shown["Importe"] == "1.000.920,00"
    assert shown["Presentado"] == "20 sep 2026"     # the month in Spanish, not 2026-09-20
    assert shown["10b5-1"] == "no"
    assert page.right_aligned == {"Acciones", "Precio", "Importe"}
    assert model.data(model.index(0, 6), Qt.TextAlignmentRole) == int(
        Qt.AlignRight | Qt.AlignVCenter)

    empty = {model.headerData(i, Qt.Horizontal) for i in range(model.columnCount())}
    assert "Documento" not in empty                 # the filing is a button, not a column


def test_scanner_warns_when_the_daily_flow_capture_skipped_a_session(qtbot, tmp_path,
                                                                    monkeypatch):
    """A missing day is invisible in the rows — it simply is not there — and the volume of a session
    cannot be recovered, so the screen has to say it."""
    from datetime import date

    from miratrade import store
    from miratrade.app.pages.scanner import ScannerPage

    db = store.connect(tmp_path / "market.db")
    store.mark_covered(db, "flow_daily", [date(2026, 9, 21)], rows=1)   # Monday captured
    store.mark_covered(db, "flow_daily", [date(2026, 9, 24)], rows=1)   # Thursday captured
    monkeypatch.setattr("miratrade.data.options.session_date", lambda *a: date(2026, 9, 25))

    page = ScannerPage(db=db, settings_path=tmp_path / "settings.json")
    qtbot.addWidget(page)
    page.source.setCurrentIndex(page.source.findData("flow"))

    note = page.note.text()
    assert "no se puede recuperar" in note                  # Tuesday and Wednesday were lost
    assert "22 sep" in note and "23 sep" in note

    page.source.setCurrentIndex(page.source.findData("insiders"))
    assert "no se puede recuperar" not in page.note.text()  # only where it is relevant
    db.close()


def _report_with(tmp_path, name, validated, wf_confirmed):
    """A report whose rules.csv says how many rules survived validation and walk-forward."""
    folder = tmp_path / "reports" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "edge_report.md").write_text("Window: **2021-01-01 → 2026-01-01**", encoding="utf-8")
    pd.DataFrame({"rule": [f"r{i}" for i in range(max(validated, 1))],
                  "validated": [True] * validated + [False] * (0 if validated else 1),
                  "wf_confirmed": [True] * wf_confirmed
                                  + [False] * (max(validated, 1) - wf_confirmed)}).to_csv(
        folder / "rules.csv", index=False)
    return folder


def test_the_honest_note_is_read_from_the_report_so_it_cannot_go_stale(tmp_path):
    """A disclaimer written into the code drifts from the evidence in both directions — it either
    overstates what is known or hides it. This one is derived from the latest analysis."""
    root = tmp_path / "reports"
    root.mkdir()
    assert "ningún análisis" in data.honesty_line(root)          # nothing run yet

    _report_with(tmp_path, "a", validated=0, wf_confirmed=0)
    said = data.honesty_line(root)
    assert "no validó ninguna regla" in said and "ventaja medida" in said

    _report_with(tmp_path, "b", validated=3, wf_confirmed=0)
    said = data.honesty_line(root)
    assert "validó 3 reglas" in said and "ninguna confirmada" in said

    _report_with(tmp_path, "one", validated=1, wf_confirmed=1)
    assert "validó 1 regla " in data.honesty_line(root)        # not "1 reglas"

    _report_with(tmp_path, "c", validated=4, wf_confirmed=2)
    said = data.honesty_line(root)
    assert "validó 4 reglas" in said and "2 confirmadas" in said


def test_signals_and_practice_both_say_what_was_measured(window, tmp_path):
    """The note belongs wherever numbers are shown as if they meant something."""
    from miratrade.app.i18n import t
    from miratrade.app.pages.signals import DISCLAIMER

    s = window.signals
    # the fixture's report has one validated, walk-forward confirmed rule, and the note says so:
    # it follows the evidence instead of repeating a fixed sentence
    assert "El último análisis validó" in s.honesty.text()
    assert "1 regla " in s.honesty.text() and "1 confirmadas" in s.honesty.text()
    # and the standing disclaimer now says the contract prices are modelled, not quoted
    assert "modelo" in t(DISCLAIMER) and "toda la prima" in t(DISCLAIMER)

    window.practice.refresh()
    assert window.practice.honesty.text() == s.honesty.text() or window.practice.honesty.text()


# --------------------------------------------------------------------------- notification settings

def test_settings_saves_where_notifications_go(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from miratrade.app.pages.settings import SettingsPage

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    path = tmp_path / "settings.json"
    page = SettingsPage(path)
    qtbot.addWidget(page)

    page.ntfy_topic.setText("  miratrade-abc123  ")
    page.email_to.setText(" me@example.com ")
    page.smtp_port.setValue(465)
    page.max_events.setValue(10)
    page.only_tradeable.setChecked(False)
    page.save()

    saved = data.read_settings(path).notify
    assert saved.ntfy_topic == "miratrade-abc123"        # trimmed
    assert saved.email_to == "me@example.com"
    assert saved.email_from == "me@example.com"          # defaults to the same address
    assert saved.smtp_port == 465 and saved.max_events == 10
    assert saved.only_tradeable is False


def test_the_email_password_never_reaches_the_settings_file(qtbot, tmp_path, monkeypatch):
    """It is a secret, so it goes to the Windows Credential Manager and the file never sees it."""
    from PySide6.QtWidgets import QDialog, QMessageBox

    from miratrade.app.pages import settings as settings_page
    from miratrade.app.pages.settings import SettingsPage
    from miratrade.brokers.credentials import CredentialStore

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    path = tmp_path / "settings.json"
    page = SettingsPage(path)
    qtbot.addWidget(page)
    page.email_to.setText("me@example.com")

    kept = {}
    monkeypatch.setattr(CredentialStore, "set", lambda self, name, value: kept.update({name: value}))
    monkeypatch.setattr(CredentialStore, "get", lambda self, name: kept.get(name))

    class Dialog:
        def __init__(self, *a, **k):
            self.password = type("Field", (), {"text": staticmethod(lambda: "an-app-password")})()

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(settings_page, "EmailPasswordDialog", Dialog)
    page.edit_email_password()
    page.save()

    assert kept == {"notify.smtp_password": "an-app-password"}
    assert "an-app-password" not in path.read_text(encoding="utf-8")
    assert "contraseña guardada" in page.notify_state.text()


def test_a_preview_shows_what_would_be_sent_and_sends_nothing(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from miratrade.app.pages.settings import SettingsPage
    from miratrade.notify import notify_new

    # a database of its own: a test must never read, or wait on, the user's real market data
    from miratrade import store

    own = store.connect(tmp_path / "market.db")
    own.close()
    monkeypatch.setattr("miratrade.config.DB_PATH", tmp_path / "market.db")
    monkeypatch.setattr("miratrade.store.db.DB_PATH", tmp_path / "market.db")

    page = SettingsPage(tmp_path / "settings.json")
    qtbot.addWidget(page)
    page.email_to.setText("me@example.com")

    asked = {}
    monkeypatch.setattr(QMessageBox, "exec", lambda self: asked.update(
        {"text": self.text(), "detail": self.detailedText()}) or QMessageBox.Ok)
    sent = []
    monkeypatch.setattr("miratrade.notify.send_ntfy", lambda *a, **k: sent.append(1))
    monkeypatch.setattr("miratrade.notify.send_email", lambda *a, **k: sent.append(1))

    page.preview_notification()
    assert sent == []                                    # a preview sends nothing
    assert "eventos" in asked["text"] and asked["detail"]


def test_a_test_message_is_only_sent_after_the_user_confirms(qtbot, tmp_path, monkeypatch):
    """Sending is the user pressing a button, and the app says where it is going before it does."""
    from PySide6.QtWidgets import QMessageBox

    from miratrade.app.pages import settings as settings_page
    from miratrade.app.pages.settings import SettingsPage

    page = SettingsPage(tmp_path / "settings.json")
    qtbot.addWidget(page)
    page.ntfy_topic.setText("miratrade-abc")

    told, pushed = [], []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[-1]))
    monkeypatch.setattr(settings_page, "QMessageBox", QMessageBox)
    monkeypatch.setattr("miratrade.notify.send_ntfy", lambda *a, **k: pushed.append(a) or True)

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    page.send_test()
    assert pushed == []                                  # said no: nothing left the machine

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    page.send_test()
    assert len(pushed) == 1 and pushed[0][0] == "miratrade-abc"


def test_scanner_recovers_by_itself_from_a_momentary_database_failure(qtbot, tmp_path, monkeypatch):
    """The database is briefly unreadable while something writes to it. Remembering that as broken
    left the screen empty until the app was restarted, with the data readable the whole time."""
    from miratrade import store
    from miratrade.app.pages.scanner import ScannerPage

    path = tmp_path / "market.db"
    seed = store.connect(path)
    store.write(seed, "insiders", pd.DataFrame([
        {"accession": "0001-26-1", "filing_date": "2026-09-20", "ticker": "PFE", "code": "P",
         "value": 1_000_920.0}]))
    seed.close()

    page = ScannerPage(settings_path=tmp_path / "settings.json")
    qtbot.addWidget(page)
    monkeypatch.setattr("miratrade.config.DB_PATH", path)
    monkeypatch.setattr("miratrade.store.db.DB_PATH", path)

    page._db = None
    page.days.setValue(0)
    assert page.table.model().rowCount() == 1              # reads fine

    broken = {"on": True}
    real = store.connect

    def sometimes(*a, **k):
        if broken["on"]:
            raise RuntimeError("database is locked")
        return real(*a, **k)

    monkeypatch.setattr("miratrade.store.connect", sometimes)
    page._db = None
    page.reload()
    assert page.table.model().rowCount() == 0
    assert "bloqueada" in page.count.text() or "locked" in page.count.text()
    assert not page.export_btn.isEnabled()

    broken["on"] = False                                   # whatever was writing has finished
    page.reload()
    assert page.table.model().rowCount() == 1              # back, without restarting the app
    assert page.export_btn.isEnabled()


def test_scanner_says_what_to_press_when_nothing_has_been_downloaded(qtbot, tmp_path, monkeypatch):
    """Nothing downloaded yet is a state to explain, not a SQLite error to show."""
    from miratrade.app.pages.scanner import ScannerPage

    missing = tmp_path / "nothing" / "market.db"
    monkeypatch.setattr("miratrade.config.DB_PATH", missing)
    monkeypatch.setattr("miratrade.store.db.DB_PATH", missing)
    monkeypatch.setattr("miratrade.app.pages.scanner.store_path", lambda: str(missing))

    page = ScannerPage(settings_path=tmp_path / "settings.json")
    qtbot.addWidget(page)
    page._db = None
    page.reload()

    said = page.count.text()
    assert "Actualizar datos" in said and "market.db" in said   # what to press, and where it goes
    assert "NoneType" not in said and "cursor" not in said      # never the raw pandas failure


def test_signals_days_is_the_window_and_the_other_two_only_narrow(qtbot, tmp_path, monkeypatch):
    """One control, one meaning. There used to be two day values — the spinbox filtering the list
    and a hidden setting driving the download — so the header could say 30 while the control said
    15, and nobody could tell which number meant what."""
    import json

    from miratrade import store
    from miratrade.app.pages.signals import SignalsPage

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"data": {"scan_days": 30, "price_source": "research"}}),
                        encoding="utf-8")
    db = store.connect(tmp_path / "market.db")
    page = SignalsPage(tmp_path / "reports", tmp_path / "scan", settings_path=settings, db=db)
    qtbot.addWidget(page)

    assert page.days.value() == 30                     # it starts at the window that was saved

    started = []
    monkeypatch.setattr(page, "start_scan", lambda: started.append(page.days.value()))
    page.days.setValue(12)
    assert started == []                               # changing it downloads nothing
    assert data.read_settings(settings).data.scan_days == 12     # but is remembered

    page.cap.setCurrentIndex(max(0, page.cap.findData("large")))
    page.variant.setCurrentIndex(1 if page.variant.count() > 1 else 0)
    assert started == []                               # neither does the profile or the size

    page.start_scan()
    assert started == [12]                             # the button downloads the window on screen
    db.close()


def test_signals_follows_the_window_when_settings_changes_it(qtbot, tmp_path):
    """The same window appears on two screens; they must not drift apart."""
    import json

    from miratrade import store
    from miratrade.app.pages.signals import SignalsPage

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"data": {"scan_days": 30}}), encoding="utf-8")
    db = store.connect(tmp_path / "market.db")
    page = SignalsPage(tmp_path / "reports", tmp_path / "scan", settings_path=settings, db=db)
    qtbot.addWidget(page)

    cfg = data.read_settings(settings)
    cfg.data.scan_days = 45
    data.write_settings(cfg, settings)
    page.refresh_days()
    assert page.days.value() == 45
    db.close()
