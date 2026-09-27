"""Configuración: market data source, Schwab and E*TRADE logins, risk limits and the real-money switch."""
from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtCore import QTime
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
                               QSpinBox, QTimeEdit, QVBoxLayout, QWidget)

from miratrade.app import data
from miratrade.app.i18n import LANGUAGES, t
from miratrade.config import MIN_AUTO_REFRESH_MINUTES
from miratrade.app.widgets import card, muted


class CredentialsDialog(QDialog):
    def __init__(self, callback_url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Credenciales de la app de Schwab")
        self.key = QLineEdit()
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.Password)
        self.callback = QLineEdit(callback_url)
        form = QFormLayout(self)
        form.addRow(muted("developer.schwab.com → Dashboard → tu app. Se guardan en el Administrador de "
                          "credenciales de Windows, nunca en archivos."))
        form.addRow("App Key", self.key)
        form.addRow("Secret", self.secret)
        form.addRow("Callback URL", self.callback)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class EtradeKeysDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Claves de tu cuenta de E*TRADE")
        self.key = QLineEdit()
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.Password)
        self.sandbox = QCheckBox("Son claves de sandbox (pruebas)")
        form = QFormLayout(self)
        form.addRow(muted("E*TRADE → Developer: tu consumer key de uso individual, solo para tus propias cuentas. "
                          "Firma allí el acuerdo de la API y, para cotizaciones en tiempo real, el de datos de "
                          "mercado. Se guardan en el Administrador de credenciales de Windows."))
        form.addRow("Consumer key", self.key)
        form.addRow("Consumer secret", self.secret)
        form.addRow(self.sandbox)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


RESEARCH_WARNING = (
    "Yahoo y Stooq no tienen un acuerdo de licencia con MiraTrade: sus datos sirven solo para tu "
    "investigación personal y no comercial. ¿Usarlos para tus análisis?")

SOURCE_NOTE = {
    "schwab": "Historial diario desde tu propia cuenta de Schwab, con tu app de desarrollador personal.",
    "research": "Yahoo / Stooq sin acuerdo de licencia: solo para tu investigación personal y no comercial. "
                "No uses estos datos en nada que compartas o vendas.",
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
        self.price_source.setAccessibleName("Fuente del historial de precios")
        self.quote_broker = QComboBox()
        self.quote_broker.addItem("Schwab", "schwab")
        self.quote_broker.addItem("E*TRADE", "etrade")
        self.quote_broker.setCurrentIndex(max(0, self.quote_broker.findData(self.cfg.data.quote_broker)))
        self.quote_broker.setAccessibleName("Bróker para cotizaciones y cadenas de opciones")
        self.source_note = muted("")
        self.price_source.currentIndexChanged.connect(self._source_changed)
        self.scan_days = QSpinBox()
        self.scan_days.setRange(1, 365)
        self.scan_days.setSuffix(" días")
        self.scan_days.setValue(self.cfg.data.scan_days)
        self.scan_days.setAccessibleName("Días que descarga cada actualización")
        self.auto_refresh = QSpinBox()
        self.auto_refresh.setRange(0, 720)
        self.auto_refresh.setSpecialValueText("Solo cuando yo lo pida")
        self.auto_refresh.setSuffix(" min")
        self.auto_refresh.setValue(self.cfg.data.auto_refresh_minutes)
        self.auto_refresh.setAccessibleName("Actualizar automáticamente cada X minutos")
        src_form = QFormLayout()
        src_form.addRow("Historial de precios", self.price_source)
        src_form.addRow("Cotizaciones y opciones", self.quote_broker)
        src_form.addRow("Cada descarga trae", self.scan_days)
        src_form.addRow("Actualizar solo", self.auto_refresh)
        self.window_from = QTimeEdit(QTime.fromString(self.cfg.data.auto_refresh_from, "HH:mm"))
        self.window_to = QTimeEdit(QTime.fromString(self.cfg.data.auto_refresh_to, "HH:mm"))
        for w in (self.window_from, self.window_to):
            w.setDisplayFormat("HH:mm")
        self.window_from.setAccessibleName("La franja empieza a esta hora de Nueva York")
        self.window_to.setAccessibleName("La franja termina a esta hora de Nueva York")
        self.weekdays_only = QCheckBox("Solo de lunes a viernes")
        self.weekdays_only.setChecked(self.cfg.data.auto_refresh_weekdays_only)
        window_row = QHBoxLayout()
        window_row.setContentsMargins(0, 0, 0, 0)
        window_row.addWidget(self.window_from)
        window_row.addWidget(QLabel("a"))
        window_row.addWidget(self.window_to)
        window_row.addWidget(self.weekdays_only)
        window_row.addStretch(1)
        window_w = QWidget()
        window_w.setLayout(window_row)
        src_form.addRow("Franja (Nueva York)", window_w)
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
                      muted("Cada usuario conecta su propia cuenta; MiraTrade no comparte tus datos con nadie. "
                            "E*TRADE no ofrece historial de precios: el historial viene de Schwab."),
                      muted(f"La actualización automática solo baja lo nuevo, pero vuelve a leer los formularios "
                            f"de hoy en cada pasada. Por debajo de {MIN_AUTO_REFRESH_MINUTES} minutos se queda "
                            "apagada: pedirías a la SEC más de lo que cambia."),
                      title="Datos de mercado")
        self._source_changed()

        # E*TRADE (read-only)
        self.etrade_status = QLabel()
        self.etrade_status.setWordWrap(True)
        et_keys = QPushButton("Guardar claves…")
        et_keys.clicked.connect(self.edit_etrade_keys)
        self.etrade_login_btn = QPushButton("Iniciar sesión en E*TRADE…")
        self.etrade_login_btn.clicked.connect(self.etrade_login)
        et_out = QPushButton("Cerrar sesión")
        et_out.clicked.connect(self.etrade_logout)
        et_row = QHBoxLayout()
        for b in (et_keys, self.etrade_login_btn, et_out):
            et_row.addWidget(b)
        et_row.addStretch(1)
        et_row_w = QWidget()
        et_row_w.setLayout(et_row)
        etrade = card(self.etrade_status, et_row_w,
                      muted("Solo lectura: saldos, cotizaciones y cadenas de opciones. La sesión dura hasta la "
                            "medianoche de Nueva York. Las órdenes se envían solo por Schwab."),
                      title="Cuenta de E*TRADE")

        # Schwab
        self.schwab_status = QLabel()
        self.schwab_status.setWordWrap(True)
        creds = QPushButton("Guardar credenciales…")
        creds.clicked.connect(self.edit_credentials)
        self.login_btn = QPushButton("Iniciar sesión en Schwab…")
        self.login_btn.setObjectName("primary")
        self.login_btn.clicked.connect(self.login)
        logout = QPushButton("Cerrar sesión")
        logout.clicked.connect(self.logout)
        row = QHBoxLayout()
        for b in (creds, self.login_btn, logout):
            row.addWidget(b)
        row.addStretch(1)
        row_w = QWidget()
        row_w.setLayout(row)
        schwab = card(self.schwab_status, row_w, muted("El acceso de Schwab dura 7 días; después hay que "
                                                       "iniciar sesión otra vez."), title="Cuenta de Schwab")

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
        grid = QGridLayout()
        fields = [("Riesgo por operación", self.risk_pct), ("Techo de riesgo (rechaza)", self.risk_ceiling),
                  ("Pérdida diaria máxima", self.daily_loss), ("Valor máx. de una orden", self.max_value),
                  ("Precio mínimo por acción", self.min_price), ("Posiciones abiertas máx.", self.max_positions)]
        for i, (label, w) in enumerate(fields):
            lab = QLabel(label)
            lab.setBuddy(w)
            grid.addWidget(lab, (i // 2) * 2, i % 2)
            grid.addWidget(w, (i // 2) * 2 + 1, i % 2)
        grid_w = QWidget()
        grid_w.setLayout(grid)
        risk = card(grid_w, muted("Toda entrada lleva stop y es una orden limitada. Se aplican en práctica y con "
                                  "dinero real."), title="Riesgo")

        # Real money
        self.live = QCheckBox("Permitir órdenes con dinero real")
        self.live.setChecked(self.cfg.broker.live_trading)
        self.live.toggled.connect(self._confirm_live)
        live = card(self.live, muted("Apagado por defecto. Aun activado, cada orden necesita una vista previa de "
                                     "Schwab y que escribas la confirmación (p. ej. «BUY 100 ACME»)."),
                    title="Dinero real")

        save = QPushButton("Guardar cambios")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        self.saved = muted("")
        foot = QHBoxLayout()
        foot.addWidget(self.saved, 1)
        foot.addWidget(save)

        body = QVBoxLayout()
        body.setSpacing(20)
        title = QLabel("Configuración")
        title.setObjectName("h1")
        body.addWidget(title)
        body.addWidget(muted(f"Se guarda en {self.settings_path}"))
        for c in (market, schwab, etrade, risk, live):
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
                text = "Sin credenciales. Pulsa «Guardar credenciales…»."
            else:
                hours = hours_until_relogin(self.auth)
                if hours is None:
                    text = "Credenciales guardadas. Falta iniciar sesión."
                elif hours <= 0:
                    text = "La sesión caducó. Inicia sesión otra vez."
                else:
                    text = f"Conectado. La sesión dura {hours / 24:.1f} días más."
        except Exception as e:                      # Credential Manager unavailable, etc.
            text = f"No se pudo leer el estado: {e}"
        self.schwab_status.setText(text)

    def edit_credentials(self) -> None:
        dlg = CredentialsDialog(self.cfg.broker.callback_url, self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self.auth.setup(dlg.key.text(), dlg.secret.text(), dlg.callback.text())
        except ValueError as e:
            QMessageBox.warning(self, "Credenciales", str(e))
        self.refresh_schwab()

    def login(self) -> None:
        if not self.auth.configured():
            QMessageBox.information(self, "Schwab", "Guarda primero las credenciales de tu app.")
            return
        url = self.auth.login_url()
        webbrowser.open(url)
        received, ok = QInputDialog.getText(
            self, "Iniciar sesión en Schwab",
            "Inicia sesión en la ventana del navegador. Al terminar, el navegador muestra un error en\n"
            "https://127.0.0.1… — es normal. Copia la dirección completa de la barra y pégala aquí:")
        if not ok or not received.strip():
            return
        try:
            self.auth.complete_login(received)
        except Exception as e:
            QMessageBox.warning(self, "Schwab", f"No se pudo iniciar sesión: {e}")
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

        self.window_note.setText(f"En tu reloj: de {here(self.window_from.time().toString('HH:mm'))} "
                                 f"a {here(self.window_to.time().toString('HH:mm'))}.")

    def _source_changed(self, *_):
        key = self.price_source.currentData()
        self.source_note.setText(SOURCE_NOTE.get(key, ""))
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
                text = "Sin claves. Pulsa «Guardar claves…»."
            else:
                h = self.etrade.hours_left()
                env = " (sandbox)" if self.etrade.env == "sandbox" else ""
                text = (f"Claves guardadas{env}. Falta iniciar sesión." if h is None else
                        "La sesión terminó a medianoche. Inicia sesión otra vez." if h <= 0 else
                        f"Conectado{env}. La sesión dura {h:.1f} horas más.")
        except Exception as e:
            text = f"No se pudo leer el estado: {e}"
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
            QMessageBox.information(self, "E*TRADE", "Guarda primero tus claves de E*TRADE.")
            return
        try:
            webbrowser.open(self.etrade.login_url())
        except Exception as e:
            QMessageBox.warning(self, "E*TRADE", f"No se pudo empezar el inicio de sesión: {e}")
            return
        code, ok = QInputDialog.getText(self, "Iniciar sesión en E*TRADE",
                                        "Inicia sesión en la ventana del navegador y acepta. E*TRADE te muestra\n"
                                        "un código de verificación: cópialo y pégalo aquí:")
        if not ok or not code.strip():
            return
        try:
            self.etrade.complete_login(code)
        except Exception as e:
            QMessageBox.warning(self, "E*TRADE", f"No se pudo iniciar sesión: {e}")
        self.refresh_etrade()

    def etrade_logout(self) -> None:
        self.etrade.logout()
        self.refresh_etrade()

    def enable_research_source(self) -> bool:
        """Switch the price history to the public web sources, with the same warning as saving.
        Used by the Señales banner while a broker account is not connected yet."""
        if QMessageBox.warning(self, "Webs públicas", RESEARCH_WARNING,
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
            self, "Dinero real",
            "Vas a permitir que MiraTrade envíe órdenes reales a Schwab.\n\nCada orden seguirá necesitando "
            "la vista previa y tu confirmación escrita. ¿Seguro?",
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
        self.cfg.broker.live_trading = self.live.isChecked()
        if self.price_source.currentData() == "research" and self.cfg.data.price_source != "research":
            answer = QMessageBox.warning(self, "Webs públicas", RESEARCH_WARNING,
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
            QMessageBox.warning(self, "Riesgo", "El riesgo por operación no puede superar el techo.")
            return
        data.write_settings(self.cfg, self.settings_path)
        self.saved.setText(t("Saved."))
        if language_changed:
            QMessageBox.information(self, t("Language"),
                                    t("Close and open MiraTrade to see it in {name}.",
                                      name=LANGUAGES[self.cfg.ui.language]))
        self.settings_changed.emit()
