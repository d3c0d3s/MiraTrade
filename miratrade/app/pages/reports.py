"""Reportes: launch an analysis (as a separate process) and read past reports."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from PySide6.QtCore import QProcess, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QScrollArea, QSpinBox, QTabWidget, QTextBrowser, QVBoxLayout,
                               QWidget)

from miratrade.app import data, theme
from miratrade.scan import variant_label
from miratrade.app.charts import BarChart, EquityCurve, Histogram, event_type_bars, profile_bars, variants_in
from miratrade.app.widgets import muted, table

RULE_HEADERS = {"rule": "Regla", "train_n": "Descubr. n", "train_avg_r": "Descubr. R", "test_n": "Valid. n",
                "test_win_rate": "Valid. acierto", "test_avg_r": "Valid. R", "wf_folds_picked": "WF tramos",
                "wf_oos_n": "WF n", "wf_oos_avg_r": "WF R", "wf_confirmed": "WF confirmada"}


class ReportsPage(QWidget):
    report_finished = Signal(str)

    def __init__(self, reports_dir: Path | None = None, settings_path: Path | None = None):
        super().__init__()
        self.setObjectName("page")
        self.reports_dir = Path(reports_dir or data.REPORTS_DIR)
        self.settings_path = Path(settings_path or data.SETTINGS_PATH)
        self.proc: QProcess | None = None

        # left: new analysis + history
        left = QVBoxLayout()
        title = QLabel("Nuevo análisis")
        title.setObjectName("h2")
        self.days = QSpinBox()
        self.days.setRange(30, 3650)
        self.days.setValue(365)
        self.days.setSuffix(" días")
        self.days.setAccessibleName("Periodo del análisis en días")
        self.cap = data.cap_combo(data.read_settings(self.settings_path).data.cap_tier, self._cap_changed)
        self.run_btn = QPushButton("Ejecutar análisis")
        self.run_btn.setObjectName("primary")
        self.run_btn.clicked.connect(self.start_analysis)
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self.cancel_analysis)
        self.cancel_btn.hide()
        self.status = muted("La primera vez descarga datos de la SEC y FINRA; puede tardar horas. "
                            "Todo queda en caché y puedes seguir usando la app.")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.hide()
        hist = QLabel("Historial")
        hist.setObjectName("h2")
        self.history = QListWidget()
        self.history.setWordWrap(True)
        self.history.setTextElideMode(Qt.ElideNone)
        self.history.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.history.currentItemChanged.connect(self._show_selected)
        for w in (title, self.days, self.cap, self.run_btn, self.cancel_btn, self.status, self.log, hist):
            left.addWidget(w)
        left.addWidget(self.history, 1)
        left_box = QWidget()
        left_box.setLayout(left)
        left_box.setFixedWidth(320)

        # right: the selected report
        self.heading = QLabel("Sin reportes todavía")
        self.heading.setObjectName("h1")
        self.subheading = muted("")
        self.tabs = QTabWidget()
        self.summary = QTextBrowser()
        self.summary.setOpenExternalLinks(False)
        self.rules = table(headers=RULE_HEADERS)
        self.wf = table()
        self.candidates = table()
        self.charts_tab = self._build_charts()
        self.tabs.addTab(self.charts_tab, "Gráficas")
        self.tabs.addTab(self.summary, "Reporte")
        self.tabs.addTab(self.rules, "Reglas validadas")
        self.tabs.addTab(self.wf, "Walk-forward")
        self.tabs.addTab(self.candidates, "Candidatos")
        right = QVBoxLayout()
        right.addWidget(self.heading)
        right.addWidget(self.subheading)
        right.addWidget(self.tabs, 1)

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(24)
        root.addWidget(left_box)
        root.addLayout(right, 1)
        self.refresh()

    def _build_charts(self) -> QWidget:
        """What the tables make hard to see: how the result added up, how it was distributed and
        how the kinds of event compare."""
        self.variant = QComboBox()
        self.variant.setAccessibleName("Perfil de resultado")
        self.variant.currentIndexChanged.connect(lambda _: self._draw_charts())
        head = QHBoxLayout()
        head.addWidget(muted("Perfil"))
        head.addWidget(self.variant)
        head.addStretch(1)
        self.equity = EquityCurve()
        self.hist = Histogram()
        self.by_event = BarChart("Resultado medio por tipo de evento")
        self.by_profile = BarChart("Resultado medio por perfil")
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 12, 0)
        body.setSpacing(14)
        body.addLayout(head)
        for c in (self.equity, self.hist, self.by_event, self.by_profile):
            c.setMinimumHeight(250)
            body.addWidget(c)
        self.charts_note = muted("")
        body.addWidget(self.charts_note)
        inner = QWidget()
        inner.setObjectName("page")
        inner.setLayout(body)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        return scroll

    def _draw_charts(self) -> None:
        events = getattr(self, "_events", None)
        variant = self.variant.currentData()
        if events is None or events.empty or not variant:
            for c in (self.equity, self.hist, self.by_event, self.by_profile):
                c.set_data([], []) if isinstance(c, (EquityCurve, BarChart)) else c.set_data([])
            self.charts_note.setText("Este reporte no guardó los resultados por evento (events.csv).")
            return
        column = f"ret_{variant}"
        rows = (events.dropna(subset=[column])                       # events.csv keeps dates as text
                .assign(signal_date=lambda d: pd.to_datetime(d["signal_date"], errors="coerce"))
                .dropna(subset=["signal_date"]).sort_values("signal_date"))
        split = rows["signal_date"].quantile(0.6) if len(rows) else None
        self.equity.set_data(rows["signal_date"], rows[column], split)
        target, stop = self._targets(variant)
        self.hist.set_data(rows[column], [(target, f"objetivo +{target * 100:.0f} %", theme.UP),
                                          (-stop, f"stop −{stop * 100:.0f} %", theme.DOWN)])
        self.by_event.set_data(*event_type_bars(events, variant),
                               note="Solo cuenta el tipo de evento, no las reglas.")
        self.by_profile.set_data(*profile_bars(getattr(self, "_profiles", None)),
                                 note="Cada perfil es una combinación de instrumento, objetivo y stop.")
        self.charts_note.setText(f"{len(rows)} eventos con resultado en el perfil {variant}. "
                                 "Los precios de las calls son de modelo, no cotizaciones.")

    @staticmethod
    def _targets(variant: str) -> tuple[float, float]:
        from miratrade.config import Config

        pct = int(variant.rsplit("_", 1)[-1])
        stops = {int(round(t * 100)): s for t, s in Config().outcomes.targets}
        return pct / 100, stops.get(pct, 0.25)

    # ------------------------------------------------------------------ history

    def refresh(self, select: str | None = None) -> None:
        self.history.clear()
        for info in data.list_reports(self.reports_dir):
            item = QListWidgetItem(f"{info.name}\n{info.summary}")
            item.setData(Qt.UserRole, str(info.path))
            item.setToolTip(info.label)
            self.history.addItem(item)
            if select and str(info.path) == select:
                self.history.setCurrentItem(item)
        if self.history.currentItem() is None and self.history.count():
            self.history.setCurrentRow(0)

    def _show_selected(self, item: QListWidgetItem | None, _prev=None) -> None:
        if item is None:
            return
        path = Path(item.data(Qt.UserRole))
        info = data.report_info(path)
        rep = data.load_report(path)
        self.heading.setText(f"Reporte · {info.start} → {info.end}" if info and info.start else path.name)
        self.subheading.setText(info.summary if info else "")
        self.summary.setMarkdown(rep["markdown"])
        cols = [c for c in RULE_HEADERS if c in rep["rules"].columns]
        self.rules.model().set(rep["rules"][cols] if cols else rep["rules"])
        self.wf.model().set(rep["walk_forward"])
        self.candidates.model().set(rep["candidates"])
        self._events, self._profiles = rep.get("events"), rep.get("profiles")
        current = self.variant.currentData()
        self.variant.blockSignals(True)
        self.variant.clear()
        for v in variants_in(self._events):
            self.variant.addItem(variant_label(v), v)
        self.variant.setCurrentIndex(max(0, self.variant.findData(current or "call45_40")))
        self.variant.blockSignals(False)
        self._draw_charts()

    # ------------------------------------------------------------------ running an analysis

    def start_analysis(self) -> None:
        if self.proc is not None:
            return
        out = self.reports_dir / f"{datetime.now():%Y%m%d-%H%M}-{self.days.value()}d"
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read_output)
        self.proc.finished.connect(lambda code, _status, out=out: self._finished(code, out))
        self.log.clear()
        self.log.show()
        self.run_btn.setEnabled(False)
        self.cancel_btn.show()
        self.status.setText(f"Analizando {self.days.value()} días…")
        self.proc.start(sys.executable, data.analyze_command(self.days.value(), out, self.cap.currentData()))

    def _cap_changed(self, tier: str) -> None:
        data.set_cap_tier(tier, self.settings_path)

    def refresh_cap(self) -> None:
        tier = data.read_settings(self.settings_path).data.cap_tier
        if tier != self.cap.currentData():
            self.cap.blockSignals(True)
            self.cap.setCurrentIndex(max(0, self.cap.findData(tier)))
            self.cap.blockSignals(False)

    def _read_output(self) -> None:
        text = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in text.splitlines():
            if line.strip() and not line.startswith(("|", "#")):   # skip the report echoed at the end
                self.log.appendPlainText(line)

    def _finished(self, code: int, out: Path) -> None:
        self.proc = None
        self.run_btn.setEnabled(True)
        self.cancel_btn.hide()
        if code == 0:
            self.status.setText("Análisis terminado.")
            self.refresh(select=str(out))
            self.report_finished.emit(str(out))
        else:
            self.status.setText(f"El análisis terminó con error (código {code}). Revisa el registro.")

    def cancel_analysis(self) -> None:
        if self.proc is not None:
            self.proc.kill()
            self.status.setText("Cancelado. Lo descargado queda en caché.")
