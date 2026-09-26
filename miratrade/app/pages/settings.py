"""Configuración: Schwab login, risk limits and the real-money switch."""
from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
                               QSpinBox, QVBoxLayout, QWidget)

from miratrade.app import data
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


class SettingsPage(QWidget):
    settings_changed = Signal()

    def __init__(self, settings_path: Path | None = None, auth=None):
        super().__init__()
        self.setObjectName("page")
        self.settings_path = Path(settings_path or data.SETTINGS_PATH)
        self._auth = auth
        self.cfg = data.read_settings(self.settings_path)

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
        for c in (schwab, risk, live):
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
        if r.risk_per_trade_pct > r.risk_warn_pct:
            QMessageBox.warning(self, "Riesgo", "El riesgo por operación no puede superar el techo.")
            return
        data.write_settings(self.cfg, self.settings_path)
        self.saved.setText("Guardado.")
        self.settings_changed.emit()
