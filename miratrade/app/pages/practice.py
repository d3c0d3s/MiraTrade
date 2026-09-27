"""Práctica: the paper positions you opened from Señales, what they are worth and how they ended.

No money and no broker: an option's value is modelled from the underlying's price the same way
the analysis prices contracts, and the screen says so. Marking uses whatever price source is
configured, so it works the same whether that is a broker or the research sources.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from miratrade.app import data, theme
from miratrade.app.charts import EquityCurve
from miratrade.app.widgets import card, es_date, es_num, muted
from miratrade.practice import CLOSED, OPEN, REASONS, load, mark, save, summary

OPEN_COLUMNS = ["Posición", "Abierta", "Cantidad", "Entrada", "Ahora", "Stop", "Objetivo", "Ganancia", "Evento"]
DONE_COLUMNS = ["Posición", "Abierta", "Cerrada", "Cantidad", "Entrada", "Salida", "Motivo", "Ganancia"]
START_EQUITY = 25_000.0


def _money(v: float | None) -> str:
    return "–" if v is None or not pd.notna(v) else f"{es_num(v)} $"


def _table(columns: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(columns))
    t.setHorizontalHeaderLabels(columns)
    t.verticalHeader().hide()
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def _cell(text: str, colour: str | None = None, right: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if colour:
        from PySide6.QtGui import QColor
        item.setForeground(QColor(colour))
    if right:
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return item


class PracticePage(QWidget):
    def __init__(self, practice_path: Path | None = None, scan_dir: Path | None = None,
                 settings_path: Path | None = None):
        super().__init__()
        self.setObjectName("page")
        from miratrade.practice import PRACTICE_PATH

        self.path = Path(practice_path or PRACTICE_PATH)
        self.scan_dir = Path(scan_dir or data.SCAN_DIR)
        self.settings_path = Path(settings_path or data.SETTINGS_PATH)
        self.trades = load(self.path)

        title = QLabel("Práctica")
        title.setObjectName("h1")
        self.meta = muted("")
        self.mark_btn = QPushButton("Actualizar valor")
        self.mark_btn.setObjectName("primary")
        self.mark_btn.setToolTip("Vuelve a valorar las posiciones abiertas con los últimos precios guardados.")
        self.mark_btn.clicked.connect(self.mark_now)
        self.close_btn = QPushButton("Cerrar la seleccionada")
        self.close_btn.clicked.connect(self.close_selected)
        head = QHBoxLayout()
        head.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(title)
        titles.addWidget(self.meta)
        head.addLayout(titles)
        head.addStretch(1)
        head.addWidget(self.mark_btn)
        head.addWidget(self.close_btn)

        self.totals = QLabel()
        self.totals.setObjectName("body")
        self.totals.setWordWrap(True)
        self.open_table = _table(OPEN_COLUMNS)
        self.done_table = _table(DONE_COLUMNS)
        self.curve = EquityCurve()
        self.curve.empty_text = "Con dos operaciones cerradas aparecerá aquí tu resultado acumulado."
        self.empty = muted("Todavía no has añadido ninguna operación. Ve a Señales, elige un evento y pulsa "
                           "«Añadir a práctica».")

        body = QVBoxLayout(self)
        body.setContentsMargins(24, 20, 24, 20)
        body.setSpacing(16)
        body.addLayout(head)
        body.addWidget(card(self.totals, title="Resumen"))
        body.addWidget(self.empty)
        body.addWidget(QLabel("Abiertas"))
        body.addWidget(self.open_table, 2)
        body.addWidget(QLabel("Cerradas"))
        body.addWidget(self.done_table, 2)
        body.addWidget(self.curve, 2)
        body.addWidget(muted("Sin dinero real. El valor de una call es de modelo, calculado desde el precio de "
                             "la acción, no una cotización."))
        self.refresh()

    # ------------------------------------------------------------------ data

    def reload(self) -> None:
        self.trades = load(self.path)
        self.refresh()

    def refresh(self) -> None:
        open_trades = [t for t in self.trades if t.status == OPEN]
        done = [t for t in self.trades if t.status == CLOSED]
        self.empty.setVisible(not self.trades)
        s = summary(self.trades, START_EQUITY)
        hit = "–" if not done else f"{s['acierto'] * 100:.0f} %"
        self.totals.setText(
            f"Cuenta de práctica {_money(s['equity'])} · invertido {_money(s['invertido'])} · "
            f"riesgo abierto {_money(s['riesgo_abierto'])}<br>"
            f"Cerradas {s['cerradas']} · aciertos {hit} · realizado {_money(s['ganancia_realizada'])} · "
            f"abierto {_money(s['ganancia_abierta'])}")
        self.meta.setText(f"{len(open_trades)} abiertas · {len(done)} cerradas")
        self.meta.setToolTip(f"Se guarda en {self.path}")
        self.close_btn.setEnabled(bool(open_trades))

        self.open_table.setRowCount(len(open_trades))
        for row, t in enumerate(open_trades):
            colour = theme.UP if t.profit >= 0 else theme.DOWN
            cells = [_cell(t.label()), _cell(es_date(t.opened)), _cell(str(t.quantity), right=True),
                     _cell(_money(t.entry), right=True), _cell(_money(t.last), right=True),
                     _cell(_money(t.stop), right=True), _cell(_money(t.target), right=True),
                     _cell(f"{_money(t.profit)}  ({es_num(t.profit_pct * 100, 1, sign=True)} %)", colour, True),
                     _cell(t.note)]
            for col, item in enumerate(cells):
                item.setData(Qt.UserRole, t.id)
                self.open_table.setItem(row, col, item)

        self.done_table.setRowCount(len(done))
        for row, t in enumerate(sorted(done, key=lambda x: x.closed or "", reverse=True)):
            colour = theme.UP if t.profit >= 0 else theme.DOWN
            cells = [_cell(t.label()), _cell(es_date(t.opened)), _cell(es_date(t.closed) if t.closed else "–"),
                     _cell(str(t.quantity), right=True), _cell(_money(t.entry), right=True),
                     _cell(_money(t.exit_price), right=True), _cell(REASONS.get(t.exit_reason or "", "–")),
                     _cell(f"{_money(t.profit)}  ({es_num(t.profit_pct * 100, 1, sign=True)} %)", colour, True)]
            for col, item in enumerate(cells):
                self.done_table.setItem(row, col, item)

        # the curve accumulates each closed trade's own return, in the order they closed
        in_order = sorted((x for x in done if x.closed), key=lambda x: x.closed)
        self.curve.title = "Cuenta de práctica, operación a operación"
        self.curve.set_data([t.closed for t in in_order], [t.profit_pct for t in in_order])
        self.curve.note = "Suma del resultado de cada operación cerrada, en el orden en que las cerraste."

    # ------------------------------------------------------------------ actions

    def latest_prices(self) -> dict[str, float]:
        """Last close per ticker from the saved scan: the same prices the Señales charts show."""
        from miratrade.scan import load_scan

        scan = load_scan(self.scan_dir)
        prices = {}
        for ticker, bars in (scan or {}).get("prices", {}).items():
            if len(bars):
                prices[ticker] = float(bars["close"].iloc[-1])
        return prices

    def mark_now(self) -> None:
        prices = self.latest_prices()
        missing = sorted({t.ticker for t in self.trades if t.status == OPEN and t.ticker not in prices})
        closed = mark(self.trades, prices)
        save(self.trades, self.path)
        self.refresh()
        notes = []
        if closed:
            notes.append("Se cerraron: " + ", ".join(f"{t.ticker} ({REASONS.get(t.exit_reason or '', '')})"
                                                     for t in closed) + ".")
        if missing:
            notes.append("Sin precio guardado para " + ", ".join(missing) +
                         ": actualiza los datos en Señales.")
        if notes:
            QMessageBox.information(self, "Práctica", "\n\n".join(notes))

    def close_selected(self) -> None:
        row = self.open_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Práctica", "Elige primero una posición abierta.")
            return
        trade_id = self.open_table.item(row, 0).data(Qt.UserRole)
        trade = next((t for t in self.trades if t.id == trade_id), None)
        if trade is None:
            return
        price = trade.last if trade.last is not None else trade.entry
        answer = QMessageBox.question(
            self, "Cerrar posición",
            f"Cerrar {trade.label()} al último valor conocido ({_money(price)})?\n\n"
            f"Resultado: {_money((price - trade.entry) * trade.quantity * trade.multiplier)}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        from miratrade.practice import close_trade

        close_trade(trade, price, "manual")
        save(self.trades, self.path)
        self.refresh()
