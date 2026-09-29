"""Main window: navigation, a header that always shows the trading mode, and the pages."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from miratrade import __version__
from miratrade.app import data
from miratrade.app.i18n import t
from miratrade.app.brand import app_icon, nav_brand
from miratrade.app.pages.practice import PracticePage
from miratrade.app.pages.signals import SignalsPage
from miratrade.app.pages.reports import ReportsPage
from miratrade.app.pages.scanner import ScannerPage
from miratrade.app.pages.settings import SettingsPage
from miratrade.app.widgets import Worker

PAGES = ("Scanner", "Signals", "Reports", "Practice", "Settings")


class MainWindow(QMainWindow):
    def __init__(self, reports_dir: Path | None = None, settings_path: Path | None = None, auth=None,
                 scan_dir: Path | None = None, etrade_auth=None, practice_path: Path | None = None,
                 db=None):
        super().__init__()
        self.setWindowTitle(f"MiraTrade {__version__}")
        self.resize(1440, 900)
        self.setWindowIcon(app_icon())
        self.settings_path = Path(settings_path or data.SETTINGS_PATH)
        self.pool = QThreadPool.globalInstance()

        self.pages = QStackedWidget()
        self.signals = SignalsPage(reports_dir, scan_dir, settings_path=self.settings_path, db=db)
        self.scanner = ScannerPage(db=db, settings_path=self.settings_path, scan_dir=scan_dir)
        self.practice = PracticePage(practice_path, scan_dir, self.settings_path)
        self.reports = ReportsPage(reports_dir, self.settings_path)
        self.settings = SettingsPage(self.settings_path, auth, etrade_auth)
        for w in (self.scanner, self.signals, self.reports, self.practice, self.settings):
            self.pages.addWidget(w)
        self.settings.settings_changed.connect(self.refresh_header)
        self.settings.settings_changed.connect(self.scanner.refresh_auto)     # source or timer changed
        self.settings.settings_changed.connect(self.signals.refresh_days)     # the window changed
        self.scanner.open_settings.connect(lambda: self.nav.button(PAGES.index("Settings")).click())
        self.scanner.use_research.connect(self.settings.enable_research_source)
        # Downloading happens on one screen; every screen that reads is told when it has finished,
        # so nothing keeps showing data that was replaced while it was on another tab.
        self.scanner.downloaded.connect(self.signals.reopen_db)
        self.scanner.downloaded.connect(self.signals.refresh)
        self.scanner.downloaded.connect(self.reports.refresh_freshness)
        self.scanner.downloaded.connect(self.practice.reload)
        for page in (self.signals, self.reports):     # "the data is old" → the one screen that fetches
            page.go_to_scanner.connect(lambda: self.nav.button(PAGES.index("Scanner")).click())
        self.signals.practice_added.connect(self.practice.reload)      # keep the journal in step
        self.reports.report_finished.connect(lambda _path: self.signals.refresh())   # fresher evidence
        self.reports.report_finished.connect(lambda _path: self.scanner.reload())

        # navigation
        nav = QWidget()
        nav.setObjectName("nav")
        nav.setFixedWidth(220)
        nav_lay = QVBoxLayout(nav)
        nav_lay.setContentsMargins(12, 20, 12, 20)
        nav_lay.setSpacing(4)
        nav_lay.addWidget(nav_brand())
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        for i, name in enumerate(PAGES):
            b = QPushButton(t(name))
            b.setObjectName("navButton")
            b.setCheckable(True)
            b.setAccessibleName(t("Go to {name}", name=t(name)))
            self.nav.addButton(b, i)
            nav_lay.addWidget(b)
        self.nav.idClicked.connect(self.pages.setCurrentIndex)
        self.nav.idClicked.connect(self._sync_pages)
        self.nav.button(0).setChecked(True)
        nav_lay.addStretch(1)
        version = QLabel(f"v{__version__}")
        version.setObjectName("muted")
        nav_lay.addWidget(version)

        # header
        header = QWidget()
        header.setObjectName("header")
        header.setFixedHeight(64)
        h = QHBoxLayout(header)
        h.setContentsMargins(24, 0, 24, 0)
        h.setSpacing(16)
        self.mode = QLabel()
        self.mode.setObjectName("pill")
        self.mode.setFixedHeight(26)
        self.broker_state = QLabel()
        self.broker_state.setObjectName("muted")
        self.stop_btn = QPushButton(t("Stop everything"))
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setToolTip(t("Cancels pending entries and blocks new ones. The stops on open "
                                   "positions stay."))
        self.stop_btn.clicked.connect(self.stop_all)
        h.addWidget(self.mode)
        h.addWidget(self.broker_state)
        h.addStretch(1)
        h.addWidget(self.stop_btn)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(header)
        right.addWidget(self.pages, 1)
        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(nav)
        root.addLayout(right, 1)
        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)
        self.refresh_header()

    def _sync_pages(self, _index: int = 0) -> None:
        """The size filter is one setting shared by both screens."""
        self.signals.refresh_cap()
        self.reports.refresh_cap()
        self.practice.reload()
        self.scanner.reload()                  # rows may have arrived since it was last shown

    def refresh_header(self) -> None:
        cfg = data.read_settings(self.settings_path)
        live = cfg.broker.live_trading
        self.mode.setText(t("● REAL MONEY ALLOWED") if live else t("● PRACTICE MODE"))
        self.mode.setProperty("live", "true" if live else "false")
        self.mode.style().unpolish(self.mode)
        self.mode.style().polish(self.mode)
        self.broker_state.setText(self.settings.schwab_status.text())
        from miratrade.brokers.schwab import hours_until_relogin
        try:
            hours = hours_until_relogin(self.settings.auth)
        except Exception:
            hours = None
        self.stop_btn.setEnabled(bool(hours and hours > 0))

    def stop_all(self) -> None:
        answer = QMessageBox.warning(
            self, t("Stop everything"),
            t("Pending entry orders at Schwab will be cancelled and new entries blocked.\n"
              "The stops and targets on open positions stay.\n\nContinue?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self.stop_btn.setEnabled(False)
        worker = Worker(self._stop_all_job)
        worker.signals.done.connect(self._stopped)
        worker.signals.failed.connect(self._stop_failed)
        self.pool.start(worker)

    def _stop_all_job(self) -> list[str]:
        from miratrade.brokers.guard import OrderGuard
        from miratrade.brokers.schwab import SchwabBroker

        broker = SchwabBroker(auth=self.settings.auth)
        guard = OrderGuard(broker, data.read_settings(self.settings_path))
        cancelled = []
        for account in broker.accounts():
            cancelled += guard.stop_all(account)
        return cancelled

    def _stopped(self, cancelled: list[str]) -> None:
        self.stop_btn.setEnabled(True)
        QMessageBox.information(self, t("Stop everything"),
                                t("Done. Entries cancelled: {count}. New entries stay blocked until you "
                                  "resume them.", count=len(cancelled)))

    def _stop_failed(self, error: str) -> None:
        self.stop_btn.setEnabled(True)
        QMessageBox.critical(self, t("Stop everything"),
                             t("Could not finish: {error}\n\nCheck the orders at Schwab directly.",
                               error=error))
