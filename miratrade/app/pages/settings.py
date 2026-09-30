"""Settings: market data source, Schwab and E*TRADE logins, risk limits and the real-money switch."""
from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtCore import QTime
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
                               QSpinBox, QTimeEdit, QVBoxLayout, QWidget)

from miratrade.app import data
from miratrade.i18n import LANGUAGES, t
from miratrade.config import MIN_AUTO_REFRESH_MINUTES
from miratrade.app.widgets import card, muted


class CredentialsDialog(QDialog):
    def __init__(self, callback_url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Credentials of your Schwab app"))
        self.key = QLineEdit()
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.Password)
        self.callback = QLineEdit(callback_url)
        form = QFormLayout(self)
        form.addRow(muted(t("developer.schwab.com → Dashboard → your app. They are kept in the "
                            "Windows Credential Manager, never in files.")))
        form.addRow("App Key", self.key)
        form.addRow("Secret", self.secret)
        form.addRow("Callback URL", self.callback)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class EmailPasswordDialog(QDialog):
    """Asked for on its own, because it is a secret and goes somewhere else from the settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Email password"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        form = QFormLayout(self)
        form.addRow(muted(t("For Gmail this is an app password from your Google account, not the "
                            "password you sign in with. It is kept in the Windows Credential "
                            "Manager, never in the settings file.")))
        form.addRow(t("App password"), self.password)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class EtradeKeysDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Keys of your E*TRADE account"))
        self.key = QLineEdit()
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.Password)
        self.sandbox = QCheckBox(t("These are sandbox (test) keys"))
        form = QFormLayout(self)
        form.addRow(muted(t("E*TRADE → Developer: your individual consumer key, for your own accounts "
                            "only. Sign the API agreement there and, for real-time quotes, the market "
                            "data one. They are kept in the Windows Credential Manager.")))
        form.addRow("Consumer key", self.key)
        form.addRow("Consumer secret", self.secret)
        form.addRow(self.sandbox)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


RESEARCH_WARNING = ("Yahoo and Stooq have no licence agreement with MiraTrade: their data is only "
                    "for your personal, non-commercial research. Use them for your analyses?")

SOURCE_NOTE = {
    "schwab": "Daily history from your own Schwab account, through your personal developer app.",
    "research": "Yahoo / Stooq with no licence agreement: only for your personal, non-commercial "
                "research. Do not use this data in anything you share or sell.",
}


class SettingsPage(QWidget):
    settings_changed = Signal()

    def __init__(self, settings_path: Path | None = None, auth=None, etrade_auth=None):
        super().__init__()
        self.setObjectName("page")
        self.settings_path = Path(settings_path or data.SETTINGS_PATH)
        self._auth = auth
        self._etrade = etrade_auth
        self.cfg = data.read_settings(self.settings_path)

        # Market data: each user's own broker account
        from miratrade.data.prices import SOURCES
        self.price_source = QComboBox()
        for key, label in SOURCES.items():
            self.price_source.addItem(label, key)
        self.price_source.setCurrentIndex(max(0, self.price_source.findData(self.cfg.data.price_source)))
        self.price_source.setAccessibleName(t("Source of the price history"))
        self.quote_broker = QComboBox()
        self.quote_broker.addItem("Schwab", "schwab")
        self.quote_broker.addItem("E*TRADE", "etrade")
        self.quote_broker.setCurrentIndex(max(0, self.quote_broker.findData(self.cfg.data.quote_broker)))
        self.quote_broker.setAccessibleName(t("Broker for quotes and option chains"))
        self.source_note = muted("")
        self.price_source.currentIndexChanged.connect(self._source_changed)
        self.scan_days = QSpinBox()
        self.scan_days.setRange(1, 365)
        self.scan_days.setSuffix(t(" days"))
        self.scan_days.setValue(self.cfg.data.scan_days)
        self.scan_days.setAccessibleName(t("Days each update downloads"))
        self.auto_refresh = QSpinBox()
        self.auto_refresh.setRange(0, 720)
        self.auto_refresh.setSpecialValueText(t("Only when I ask"))
        self.auto_refresh.setSuffix(" min")
        self.auto_refresh.setValue(self.cfg.data.auto_refresh_minutes)
        self.auto_refresh.setAccessibleName(t("Update automatically every X minutes"))
        src_form = QFormLayout()
        src_form.addRow(t("Price history"), self.price_source)
        src_form.addRow(t("Quotes and options"), self.quote_broker)
        src_form.addRow(t("Each download brings"), self.scan_days)
        src_form.addRow(t("Update on its own"), self.auto_refresh)
        self.window_from = QTimeEdit(QTime.fromString(self.cfg.data.auto_refresh_from, "HH:mm"))
        self.window_to = QTimeEdit(QTime.fromString(self.cfg.data.auto_refresh_to, "HH:mm"))
        for w in (self.window_from, self.window_to):
            w.setDisplayFormat("HH:mm")
        self.window_from.setAccessibleName(t("The window starts at this New York time"))
        self.window_to.setAccessibleName(t("The window ends at this New York time"))
        self.weekdays_only = QCheckBox(t("Monday to Friday only"))
        self.weekdays_only.setChecked(self.cfg.data.auto_refresh_weekdays_only)
        window_row = QHBoxLayout()
        window_row.setContentsMargins(0, 0, 0, 0)
        window_row.addWidget(self.window_from)
        window_row.addWidget(QLabel(t("to")))
        window_row.addWidget(self.window_to)
        window_row.addWidget(self.weekdays_only)
        window_row.addStretch(1)
        window_w = QWidget()
        window_w.setLayout(window_row)
        src_form.addRow(t("Window (New York)"), window_w)
        self.window_note = muted("")
        src_form.addRow("", self.window_note)
        self.language = QComboBox()
        for code, name in LANGUAGES.items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(self.cfg.ui.language)))
        self.language.setAccessibleName(t("Interface language"))
        src_form.addRow(t("Language"), self.language)
        for w in (self.window_from, self.window_to):
            w.timeChanged.connect(self._window_changed)
        self._window_changed()
        src_w = QWidget()
        src_w.setLayout(src_form)
        market = card(src_w, self.source_note,
                      muted(t("Every user connects their own account; MiraTrade shares your data with "
                              "nobody. E*TRADE offers no price history: the history comes from Schwab.")),
                      muted(t("The automatic update only fetches what is new, but it reads today's "
                              "filings again on every pass. Under {minutes} minutes it stays off: you "
                              "would ask the SEC for more than actually changes.",
                              minutes=MIN_AUTO_REFRESH_MINUTES)),
                      title=t("Market data"))
        self._source_changed()

        # E*TRADE (read-only)
        self.etrade_status = QLabel()
        self.etrade_status.setWordWrap(True)
        et_keys = QPushButton(t("Save keys…"))
        et_keys.clicked.connect(self.edit_etrade_keys)
        self.etrade_login_btn = QPushButton(t("Sign in to E*TRADE…"))
        self.etrade_login_btn.clicked.connect(self.etrade_login)
        et_out = QPushButton(t("Sign out"))
        et_out.clicked.connect(self.etrade_logout)
        et_row = QHBoxLayout()
        for b in (et_keys, self.etrade_login_btn, et_out):
            et_row.addWidget(b)
        et_row.addStretch(1)
        et_row_w = QWidget()
        et_row_w.setLayout(et_row)
        etrade = card(self.etrade_status, et_row_w,
                      muted(t("Read-only: balances, quotes and option chains. The session lasts until "
                              "New York midnight. Orders go through Schwab only.")),
                      title=t("E*TRADE account"))

        # Schwab
        self.schwab_status = QLabel()
        self.schwab_status.setWordWrap(True)
        creds = QPushButton(t("Save credentials…"))
        creds.clicked.connect(self.edit_credentials)
        self.login_btn = QPushButton(t("Sign in to Schwab…"))
        self.login_btn.setObjectName("primary")
        self.login_btn.clicked.connect(self.login)
        logout = QPushButton(t("Sign out"))
        logout.clicked.connect(self.logout)
        row = QHBoxLayout()
        for b in (creds, self.login_btn, logout):
            row.addWidget(b)
        row.addStretch(1)
        row_w = QWidget()
        row_w.setLayout(row)
        schwab = card(self.schwab_status, row_w,
                      muted(t("Schwab access lasts 7 days; after that you have to sign in again.")),
                      title=t("Schwab account"))

        # Risk
        r = self.cfg.risk
        self.risk_pct = self._dspin(r.risk_per_trade_pct, 0.1, 5, " %")
        self.risk_ceiling = self._dspin(r.risk_warn_pct, 0.1, 10, " %")
        self.daily_loss = self._dspin(r.daily_loss_limit_pct, 0.5, 20, " %")
        self.max_value = self._dspin(r.max_order_value_pct, 1, 100, " %")
        self.min_price = self._dspin(r.min_price, 0, 100, " $")
        self.max_positions = QSpinBox()
        self.max_positions.setRange(1, 50)
        self.max_positions.setValue(r.max_positions)
        self.capital = QDoubleSpinBox()
        self.capital.setRange(100, 1e9)
        self.capital.setDecimals(0)
        self.capital.setSingleStep(1000)
        self.capital.setGroupSeparatorShown(True)
        self.capital.setPrefix("$ ")
        self.capital.setValue(r.sizing_capital)
        self.capital.setAccessibleName(t("Capital position sizes are worked out from"))
        self.on_balance = QCheckBox(t("Use my broker balance instead"))
        self.on_balance.setChecked(r.size_on_balance)
        self.on_balance.setToolTip(t("Off by default. A suggestion sized to your real account "
                                     "is advice about your money rather than analysis of a "
                                     "market, so it is yours to switch on."))
        grid = QGridLayout()
        fields = [("Capital to size from", self.capital), ("Risk per trade", self.risk_pct),
                  ("Risk ceiling (rejects)", self.risk_ceiling),
                  ("Maximum daily loss", self.daily_loss), ("Maximum order value", self.max_value),
                  ("Minimum share price", self.min_price),
                  ("Maximum open positions", self.max_positions)]
        for i, (label, w) in enumerate(fields):
            lab = QLabel(t(label))
            lab.setBuddy(w)
            grid.addWidget(lab, (i // 2) * 2, i % 2)
            grid.addWidget(w, (i // 2) * 2 + 1, i % 2)
        grid_w = QWidget()
        grid_w.setLayout(grid)
        risk = card(grid_w, self.on_balance,
                    muted(t("Every entry carries a stop and is a limit order. They apply in "
                            "practice and with real money.")),
                    muted(t("Sizes come from the capital above, not from your account, so what "
                            "the screens suggest does not depend on how much money you have.")),
                    title=t("Risk"))

        # Real money
        self.live = QCheckBox(t("Allow real-money orders"))
        self.live.setChecked(self.cfg.broker.live_trading)
        self.live.toggled.connect(self._confirm_live)
        live = card(self.live,
                    muted(t("Off by default. Even when it is on, every order needs a Schwab preview and "
                            "a confirmation you type (for example «BUY 100 ACME»).")),
                    title=t("Real money"))

        # Notifications: a new event announced where you are, rather than only on this screen.
        n = self.cfg.notify
        self.ntfy_topic = QLineEdit(n.ntfy_topic)
        self.ntfy_topic.setPlaceholderText(t("no push"))
        new_topic = QPushButton(t("Make one up"))
        new_topic.setToolTip(t("A topic on the public ntfy server is readable by anyone who knows "
                               "its name, so it should be long and unguessable."))
        new_topic.clicked.connect(self._new_topic)
        topic_row = QHBoxLayout()
        topic_row.setContentsMargins(0, 0, 0, 0)
        topic_row.addWidget(self.ntfy_topic, 1)
        topic_row.addWidget(new_topic)
        topic_w = QWidget()
        topic_w.setLayout(topic_row)

        self.email_to = QLineEdit(n.email_to)
        self.email_to.setPlaceholderText(t("no email"))
        self.email_from = QLineEdit(n.email_from)
        self.email_from.setPlaceholderText(t("the same address"))
        self.smtp_host = QLineEdit(n.smtp_host)
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(n.smtp_port)
        self.smtp_port.setMaximumWidth(90)
        smtp_row = QHBoxLayout()
        smtp_row.setContentsMargins(0, 0, 0, 0)
        smtp_row.addWidget(self.smtp_host, 1)
        smtp_row.addWidget(self.smtp_port)
        smtp_w = QWidget()
        smtp_w.setLayout(smtp_row)

        self.only_tradeable = QCheckBox(t("Only what the quotes make tradeable"))
        self.only_tradeable.setChecked(n.only_tradeable)
        self.max_events = QSpinBox()
        self.max_events.setRange(1, 200)
        self.max_events.setValue(n.max_events)
        self.max_events.setMaximumWidth(90)

        notify_form = QFormLayout()
        notify_form.addRow(t("Push topic"), topic_w)
        notify_form.addRow(t("Email to"), self.email_to)
        notify_form.addRow(t("Sent from"), self.email_from)
        notify_form.addRow(t("Mail server"), smtp_w)
        notify_form.addRow(t("Most events per message"), self.max_events)
        notify_w = QWidget()
        notify_w.setLayout(notify_form)

        email_pw = QPushButton(t("Save the email password…"))
        email_pw.clicked.connect(self.edit_email_password)
        preview = QPushButton(t("Preview…"))
        preview.setToolTip(t("Shows exactly what would be sent, without sending anything."))
        preview.clicked.connect(self.preview_notification)
        test = QPushButton(t("Send a test"))
        test.clicked.connect(self.send_test)
        notify_row = QHBoxLayout()
        for b in (email_pw, preview, test):
            notify_row.addWidget(b)
        notify_row.addStretch(1)
        notify_row_w = QWidget()
        notify_row_w.setLayout(notify_row)
        self.notify_state = muted("")

        notify = card(notify_w, self.only_tradeable, notify_row_w, self.notify_state,
                      muted(t("The push is short and the email carries the detail: what was filed, "
                              "the evidence, the contract, whether the quotes make it usable and "
                              "whether it sits through a results announcement.")),
                      muted(t("Both always say that nothing has been validated out of sample. A "
                              "list of tickers on a phone reads as a recommendation otherwise.")),
                      title=t("Notifications"))
        self._refresh_notify_state()

        save = QPushButton(t("Save changes"))
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        self.saved = muted("")
        foot = QHBoxLayout()
        foot.addWidget(self.saved, 1)
        foot.addWidget(save)

        body = QVBoxLayout()
        body.setSpacing(20)
        title = QLabel(t("Settings"))
        title.setObjectName("h1")
        body.addWidget(title)
        body.addWidget(muted(t("Saved in {path}", path=self.settings_path)))
        for c in (market, schwab, etrade, risk, notify, live):
            body.addWidget(c)
        body.addLayout(foot)
        body.addStretch(1)
        inner = QWidget()
        inner.setObjectName("page")
        inner.setLayout(body)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.addWidget(scroll)
        self.refresh_schwab()
        self.refresh_etrade()

    @staticmethod
    def _dspin(value: float, lo: float, hi: float, suffix: str) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(2)
        s.setSingleStep(0.1)
        s.setSuffix(suffix)
        s.setValue(value)
        return s

    # ------------------------------------------------------------------ Schwab

    @property
    def auth(self):
        if self._auth is None:
            from miratrade.brokers.schwab import SchwabAuth
            self._auth = SchwabAuth()
        return self._auth

    def refresh_schwab(self) -> None:
        from miratrade.brokers.schwab import hours_until_relogin

        try:
            if not self.auth.configured():
                text = t("No credentials yet. Press «Save credentials…».")
            else:
                hours = hours_until_relogin(self.auth)
                if hours is None:
                    text = t("Credentials saved. You still have to sign in.")
                elif hours <= 0:
                    text = t("The session expired. Sign in again.")
                else:
                    text = t("Connected. The session lasts {days} more days.",
                             days=f"{hours / 24:.1f}")
        except Exception as e:                      # Credential Manager unavailable, etc.
            text = t("Could not read the status: {error}", error=e)
        self.schwab_status.setText(text)

    def edit_credentials(self) -> None:
        dlg = CredentialsDialog(self.cfg.broker.callback_url, self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self.auth.setup(dlg.key.text(), dlg.secret.text(), dlg.callback.text())
        except ValueError as e:
            QMessageBox.warning(self, t("Credentials"), str(e))
        self.refresh_schwab()

    def login(self) -> None:
        if not self.auth.configured():
            QMessageBox.information(self, "Schwab", t("Save your app credentials first."))
            return
        url = self.auth.login_url()
        webbrowser.open(url)
        received, ok = QInputDialog.getText(
            self, t("Sign in to Schwab"),
            t("Sign in in the browser window. When you finish, the browser shows an error at\n"
              "https://127.0.0.1… — that is normal. Copy the whole address from the bar and paste "
              "it here:"))
        if not ok or not received.strip():
            return
        try:
            self.auth.complete_login(received)
        except Exception as e:
            QMessageBox.warning(self, "Schwab", t("Could not sign in: {error}", error=e))
        self.refresh_schwab()
        self.settings_changed.emit()

    def logout(self) -> None:
        self.auth.logout()
        self.refresh_schwab()
        self.settings_changed.emit()

    # ------------------------------------------------------------------ market data and E*TRADE

    def _window_changed(self, *_) -> None:
        """Say what the New York window is on this computer's clock, so nobody has to guess."""
        from datetime import datetime

        import pandas as pd

        from miratrade.scan import new_york_time

        now = pd.Timestamp.now(tz="UTC")
        shift = datetime.now().astimezone().utcoffset() - new_york_time(now).utcoffset()

        def here(value: str) -> str:
            return (pd.Timestamp("2000-01-01 " + value) + shift).strftime("%H:%M")

        self.window_note.setText(t("On your clock: from {start} to {end}.",
                                   start=here(self.window_from.time().toString("HH:mm")),
                                   end=here(self.window_to.time().toString("HH:mm"))))

    def _source_changed(self, *_):
        key = self.price_source.currentData()
        self.source_note.setText(t(SOURCE_NOTE[key]) if key in SOURCE_NOTE else "")
        self.source_note.setStyleSheet("color: #FFB4AA;" if key == "research" else "")

    @property
    def etrade(self):
        if self._etrade is None:
            from miratrade.brokers.etrade import EtradeAuth
            self._etrade = EtradeAuth()
        return self._etrade

    def refresh_etrade(self) -> None:
        try:
            if not self.etrade.configured():
                text = t("No keys yet. Press «Save keys…».")
            else:
                h = self.etrade.hours_left()
                env = " (sandbox)" if self.etrade.env == "sandbox" else ""
                text = (t("Keys saved{env}. You still have to sign in.", env=env) if h is None else
                        t("The session ended at midnight. Sign in again.") if h <= 0 else
                        t("Connected{env}. The session lasts {hours} more hours.",
                          env=env, hours=f"{h:.1f}"))
        except Exception as e:
            text = t("Could not read the status: {error}", error=e)
        self.etrade_status.setText(text)

    def edit_etrade_keys(self) -> None:
        dlg = EtradeKeysDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self.etrade.setup(dlg.key.text(), dlg.secret.text(), dlg.sandbox.isChecked())
        except ValueError as e:
            QMessageBox.warning(self, "E*TRADE", str(e))
        self.refresh_etrade()

    def etrade_login(self) -> None:
        if not self.etrade.configured():
            QMessageBox.information(self, "E*TRADE", t("Save your E*TRADE keys first."))
            return
        try:
            webbrowser.open(self.etrade.login_url())
        except Exception as e:
            QMessageBox.warning(self, "E*TRADE",
                                t("Could not start the sign-in: {error}", error=e))
            return
        code, ok = QInputDialog.getText(
            self, t("Sign in to E*TRADE"),
            t("Sign in in the browser window and accept. E*TRADE shows you a verification code:\n"
              "copy it and paste it here:"))
        if not ok or not code.strip():
            return
        try:
            self.etrade.complete_login(code)
        except Exception as e:
            QMessageBox.warning(self, "E*TRADE", t("Could not sign in: {error}", error=e))
        self.refresh_etrade()

    def etrade_logout(self) -> None:
        self.etrade.logout()
        self.refresh_etrade()

    def enable_research_source(self) -> bool:
        """Switch the price history to the public web sources, with the same warning as saving.
        Used by the Signals banner while a broker account is not connected yet."""
        if QMessageBox.warning(self, t("Public websites"), t(RESEARCH_WARNING),
                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return False
        self.price_source.setCurrentIndex(self.price_source.findData("research"))
        self.cfg.data.price_source = "research"
        data.write_settings(self.cfg, self.settings_path)
        self.saved.setText(t("Saved."))
        self.settings_changed.emit()
        return True

    # ------------------------------------------------------------------ settings

    def _confirm_live(self, on: bool) -> None:
        if not on:
            return
        answer = QMessageBox.warning(
            self, t("Real money"),
            t("You are about to let MiraTrade send real orders to Schwab.\n\nEvery order will still "
              "need the preview and your typed confirmation. Are you sure?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            self.live.blockSignals(True)
            self.live.setChecked(False)
            self.live.blockSignals(False)

    def save(self) -> None:
        r = self.cfg.risk
        r.risk_per_trade_pct = self.risk_pct.value()
        r.risk_warn_pct = self.risk_ceiling.value()
        r.daily_loss_limit_pct = self.daily_loss.value()
        r.max_order_value_pct = self.max_value.value()
        r.min_price = self.min_price.value()
        r.max_positions = self.max_positions.value()
        r.sizing_capital = self.capital.value()
        r.size_on_balance = self.on_balance.isChecked()
        n = self.cfg.notify
        n.ntfy_topic = self.ntfy_topic.text().strip()
        n.email_to = self.email_to.text().strip()
        n.email_from = self.email_from.text().strip() or n.email_to
        n.smtp_host = self.smtp_host.text().strip() or n.smtp_host
        n.smtp_port = self.smtp_port.value()
        n.only_tradeable = self.only_tradeable.isChecked()
        n.max_events = self.max_events.value()
        self.cfg.broker.live_trading = self.live.isChecked()
        if self.price_source.currentData() == "research" and self.cfg.data.price_source != "research":
            answer = QMessageBox.warning(self, t("Public websites"), t(RESEARCH_WARNING),
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                self.price_source.setCurrentIndex(self.price_source.findData(self.cfg.data.price_source))
        self.cfg.data.price_source = self.price_source.currentData()
        self.cfg.data.quote_broker = self.quote_broker.currentData()
        self.cfg.data.scan_days = self.scan_days.value()
        self.cfg.data.auto_refresh_minutes = self.auto_refresh.value()
        self.cfg.data.auto_refresh_from = self.window_from.time().toString("HH:mm")
        self.cfg.data.auto_refresh_to = self.window_to.time().toString("HH:mm")
        self.cfg.data.auto_refresh_weekdays_only = self.weekdays_only.isChecked()
        language_changed = self.language.currentData() != self.cfg.ui.language
        self.cfg.ui.language = self.language.currentData()
        if r.risk_per_trade_pct > r.risk_warn_pct:
            QMessageBox.warning(self, t("Risk"),
                                t("The risk per trade cannot be above the ceiling."))
            return
        data.write_settings(self.cfg, self.settings_path)
        self.saved.setText(t("Saved."))
        if language_changed:
            QMessageBox.information(self, t("Language"),
                                    t("Close and open MiraTrade to see it in {name}.",
                                      name=LANGUAGES[self.cfg.ui.language]))
        self.settings_changed.emit()


    # ------------------------------------------------------------------ notifications

    def _new_topic(self) -> None:
        """A name nobody will guess, because the public server has no other protection."""
        import secrets

        self.ntfy_topic.setText(f"miratrade-{secrets.token_urlsafe(18)}")

    def _refresh_notify_state(self) -> None:
        from miratrade.brokers.credentials import CredentialStore
        from miratrade.notify import EMAIL_KEY

        try:
            has_password = bool(CredentialStore().get(EMAIL_KEY))
        except Exception:
            has_password = False
        parts = []
        if self.ntfy_topic.text().strip():
            parts.append(t("push on"))
        if self.email_to.text().strip():
            parts.append(t("email on, password saved") if has_password
                         else t("email address set, password still missing"))
        self.notify_state.setText(" · ".join(parts) or t("Nothing is announced yet."))

    def edit_email_password(self) -> None:
        dlg = EmailPasswordDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.password.text():
            return
        from miratrade.brokers.credentials import CredentialStore
        from miratrade.notify import EMAIL_KEY

        try:
            CredentialStore().set(EMAIL_KEY, dlg.password.text())
        except Exception as e:
            QMessageBox.warning(self, t("Notifications"), t("Could not save: {error}", error=e))
        self._refresh_notify_state()

    def _current_notify_config(self):
        """The settings as they are on screen, so a preview shows what is in front of you rather
        than what was last saved."""
        cfg = data.read_settings(self.settings_path)
        n = cfg.notify
        n.ntfy_topic = self.ntfy_topic.text().strip()
        n.email_to = self.email_to.text().strip()
        n.email_from = self.email_from.text().strip() or n.email_to
        n.smtp_host = self.smtp_host.text().strip() or n.smtp_host
        n.smtp_port = self.smtp_port.value()
        n.only_tradeable = self.only_tradeable.isChecked()
        n.max_events = self.max_events.value()
        return cfg

    def preview_notification(self) -> None:
        """What would be sent, without sending it."""
        from miratrade.notify import notify_new

        try:
            out = notify_new(cfg=self._current_notify_config(), reports_dir=data.REPORTS_DIR,
                             log=lambda _m: None, dry_run=True)
        except Exception as e:
            QMessageBox.warning(self, t("Notifications"), t("Could not read the events: {error}",
                                                            error=e))
            return
        body = out.get("body") or t("Nothing new to announce right now.")
        box = QMessageBox(self)
        box.setWindowTitle(t("This is what would be sent"))
        box.setText(t("{count} events. Nothing has been sent.", count=out["sent"]))
        box.setDetailedText(body)
        box.exec()

    def send_test(self) -> None:
        """Send one for real. It is a button the user presses, and it says so before it does."""
        from miratrade.notify import send_email, send_ntfy

        cfg = self._current_notify_config()
        if not (cfg.notify.ntfy_topic or cfg.notify.email_to):
            QMessageBox.information(self, t("Notifications"),
                                    t("Set a push topic or an email address first."))
            return
        where = ", ".join(x for x in (cfg.notify.ntfy_topic, cfg.notify.email_to) if x)
        if QMessageBox.question(self, t("Send a test"),
                                t("Send a test notification to {where}?", where=where),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        title = t("MiraTrade test")
        body = t("If you are reading this, notifications work. Nothing here has been validated out "
                 "of sample; MiraTrade shows analysis, not advice.")
        done, failed = [], []
        for name, send in ((t("push"), lambda: send_ntfy(cfg.notify.ntfy_topic, title, body)),
                           (t("email"), lambda: send_email(cfg, title, body))):
            try:
                if send():
                    done.append(name)
            except Exception as e:
                failed.append(f"{name}: {e}")
        QMessageBox.information(self, t("Notifications"),
                                (t("Sent by {channels}.", channels=", ".join(done)) if done else "")
                                + ("\n" + "\n".join(failed) if failed else ""))
        self._refresh_notify_state()
