"""Reportes: launch an analysis (as a separate process) and read past reports."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                               QSpinBox, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from miratrade.app import data
from miratrade.app.widgets import muted, table

RULE_HEADERS = {"rule": "Regla", "train_n": "Descubr. n", "train_avg_r": "Descubr. R", "test_n": "Valid. n",
                "test_win_rate": "Valid. acierto", "test_avg_r": "Valid. R", "wf_folds_picked": "WF tramos",
                "wf_oos_n": "WF n", "wf_oos_avg_r": "WF R", "wf_confirmed": "WF confirmada"}


class ReportsPage(QWidget):
    report_finished = Signal(str)

    def __init__(self, reports_dir: Path | None = None):
        super().__init__()
        self.setObjectName("page")
        self.reports_dir = Path(reports_dir or data.REPORTS_DIR)
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
        for w in (title, self.days, self.run_btn, self.cancel_btn, self.status, self.log, hist):
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
        self.proc.start(sys.executable, data.analyze_command(self.days.value(), out))

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
