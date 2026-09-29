"""Practice: the paper positions opened from Signals, what they are worth and how they ended.

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
from miratrade.app.i18n import t
from miratrade.app.charts import EquityCurve
from miratrade.app.widgets import card, fmt_date, fmt_num, muted
from miratrade.practice import (CLOSED, DEFAULT_EQUITY, OPEN, REASONS, account_equity, load, mark, save,
                                summary)

OPEN_COLUMNS = ["Position", "Opened", "Quantity", "Entry", "Now", "Stop", "Target", "Profit", "Event"]
DONE_COLUMNS = ["Position", "Opened", "Closed", "Quantity", "Entry", "Exit", "Reason", "Profit"]
# Where the capital used for sizing came from. The default is a figure the user typed, because
# sizing a suggestion to somebody's real account is advice about their money, not analysis.
EQUITY_SOURCE = {"typed": "the capital you set under Settings",
                 "default": "the standard practice capital",
                 "no_broker": "no broker connected; using the capital you set",
                 "unreachable": "your account could not be read; using the capital you set",
                 "unreadable": "your account returned no balance; using the capital you set",
                 "schwab": "real balance of your Schwab account",
                 "etrade": "real balance of your E*TRADE account"}


def trade_label(trade) -> str:
    if trade.kind != "call":
        return t("{ticker} · shares", ticker=trade.ticker)
    return t("{ticker} {strike} C · expires {expiry}", ticker=trade.ticker,
             strike=f"{trade.strike:g}", expiry=trade.expiry)


def _money(v: float | None) -> str:
    return "–" if v is None or not pd.notna(v) else f"{fmt_num(v)} $"


def _table(columns: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels([t(c) for c in columns])
    table.verticalHeader().hide()
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    return table


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
        self.equity, self.equity_source = DEFAULT_EQUITY, "default"

        title = QLabel(t("Practice"))
        title.setObjectName("h1")
        self.meta = muted("")
        self.mark_btn = QPushButton(t("Update value"))
        self.mark_btn.setObjectName("primary")
        self.mark_btn.setToolTip(t("Re-values the open positions with the latest saved prices."))
        self.mark_btn.clicked.connect(self.mark_now)
        self.close_btn = QPushButton(t("Close the selected one"))
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
        self.curve.empty_text = t("With two closed trades your running result appears here.")
        self.empty = muted(t("You have not added any trade yet. Go to Signals, pick an event and press "
                             "«Add to practice»."))

        body = QVBoxLayout(self)
        body.setContentsMargins(24, 20, 24, 20)
        body.setSpacing(16)
        body.addLayout(head)
        body.addWidget(card(self.totals, title=t("Summary")))
        body.addWidget(self.empty)
        body.addWidget(QLabel(t("Open")))
        body.addWidget(self.open_table, 2)
        body.addWidget(QLabel(t("Closed")))
        body.addWidget(self.done_table, 2)
        body.addWidget(self.curve, 2)
        self.honesty = muted("")
        body.addWidget(self.honesty)
        body.addWidget(muted(t("No real money. A call's value is modelled from the stock's price, "
                               "not a quote.")))
        self.refresh()

    # ------------------------------------------------------------------ data

    def reload(self) -> None:
        self.trades = load(self.path)
        self.read_equity()
        self.refresh()

    def read_equity(self) -> None:
        """The capital positions are sized from: the figure set under Settings, and the broker's
        real balance only when that has been switched on there."""
        cfg = data.read_settings(self.settings_path)
        broker = data.quote_broker(self.settings_path) if cfg.risk.size_on_balance else None
        self.equity, self.equity_source = account_equity(broker, cfg=cfg)

    def refresh(self) -> None:
        self.honesty.setText(data.honesty_line())
        open_trades = [x for x in self.trades if x.status == OPEN]
        done = [x for x in self.trades if x.status == CLOSED]
        self.empty.setVisible(not self.trades)
        s = summary(self.trades, self.equity)
        hit = "–" if not done else f"{s['hit_rate'] * 100:.0f} %"
        self.totals.setText(
            t("Account {equity} · invested {invested} · open risk {risk}",
              equity=_money(s["equity"]), invested=_money(s["invested"]), risk=_money(s["open_risk"]))
            + "<br>"
            + t("Closed {closed} · winners {hit} · realised {realised} · open {unrealised}",
                closed=s["closed"], hit=hit, realised=_money(s["realised"]),
                unrealised=_money(s["unrealised"]))
            + f"<br><span style='color:{theme.TEXT_2}'>"
            + t("Positions sized on {equity}: {source}.", equity=_money(self.equity),
                source=t(EQUITY_SOURCE.get(self.equity_source, self.equity_source)))
            + "</span>")
        self.meta.setText(t("{open} open · {closed} closed", open=len(open_trades), closed=len(done)))
        self.meta.setToolTip(t("Saved in {path}", path=self.path))
        self.close_btn.setEnabled(bool(open_trades))

        self.open_table.setRowCount(len(open_trades))
        for row, trade in enumerate(open_trades):
            colour = theme.UP if trade.profit >= 0 else theme.DOWN
            profit = f"{_money(trade.profit)}  ({fmt_num(trade.profit_pct * 100, 1, sign=True)} %)"
            cells = [_cell(trade_label(trade)), _cell(fmt_date(trade.opened)),
                     _cell(str(trade.quantity), right=True), _cell(_money(trade.entry), right=True),
                     _cell(_money(trade.last), right=True), _cell(_money(trade.stop), right=True),
                     _cell(_money(trade.target), right=True), _cell(profit, colour, True), _cell(trade.note)]
            for col, item in enumerate(cells):
                item.setData(Qt.UserRole, trade.id)
                self.open_table.setItem(row, col, item)

        self.done_table.setRowCount(len(done))
        for row, trade in enumerate(sorted(done, key=lambda x: x.closed or "", reverse=True)):
            colour = theme.UP if trade.profit >= 0 else theme.DOWN
            profit = f"{_money(trade.profit)}  ({fmt_num(trade.profit_pct * 100, 1, sign=True)} %)"
            cells = [_cell(trade_label(trade)), _cell(fmt_date(trade.opened)),
                     _cell(fmt_date(trade.closed) if trade.closed else "–"),
                     _cell(str(trade.quantity), right=True), _cell(_money(trade.entry), right=True),
                     _cell(_money(trade.exit_price), right=True),
                     _cell(t(REASONS.get(trade.exit_reason or "", "–"))), _cell(profit, colour, True)]
            for col, item in enumerate(cells):
                self.done_table.setItem(row, col, item)

        # the curve accumulates each closed trade's own return, in the order they closed
        in_order = sorted((x for x in done if x.closed), key=lambda x: x.closed)
        self.curve.title = t("Practice account, trade by trade")
        self.curve.set_data([x.closed for x in in_order], [x.profit_pct for x in in_order])
        self.curve.note = t("Sum of each closed trade's result, in the order you closed them.")

    # ------------------------------------------------------------------ actions

    def latest_prices(self) -> dict[str, float]:
        """The last close of every open position's ticker, from the shared market database.

        It holds every bar ever downloaded, not only the ones the last scan happened to fetch, so a
        position opened weeks ago can still be marked instead of reporting a missing price.
        """
        from miratrade import store

        wanted = sorted({x.ticker for x in self.trades if x.status == OPEN})
        if not wanted:
            return {}
        try:
            with store.connect(read_only=True) as db:
                rows = db.execute(
                    f"SELECT ticker, close FROM prices WHERE ticker IN "
                    f"({','.join('?' * len(wanted))}) AND date = "
                    f"(SELECT max(date) FROM prices p WHERE p.ticker = prices.ticker)", wanted)
                return {r["ticker"]: float(r["close"]) for r in rows if r["close"] is not None}
        except Exception:                  # nothing downloaded yet: mark_now says which are missing
            return {}

    def mark_now(self) -> None:
        self.read_equity()
        prices = self.latest_prices()
        missing = sorted({x.ticker for x in self.trades if x.status == OPEN and x.ticker not in prices})
        closed = mark(self.trades, prices)
        save(self.trades, self.path)
        self.refresh()
        notes = []
        if closed:
            names = ", ".join(f"{x.ticker} ({t(REASONS.get(x.exit_reason or '', ''))})" for x in closed)
            notes.append(t("Closed: {list}.", list=names))
        if missing:
            notes.append(t("No saved price for {list}: update the data under Signals.",
                           list=", ".join(missing)))
        if notes:
            QMessageBox.information(self, t("Practice"), "\n\n".join(notes))

    def close_selected(self) -> None:
        row = self.open_table.currentRow()
        if row < 0:
            QMessageBox.information(self, t("Practice"), t("Pick an open position first."))
            return
        trade_id = self.open_table.item(row, 0).data(Qt.UserRole)
        trade = next((x for x in self.trades if x.id == trade_id), None)
        if trade is None:
            return
        price = trade.last if trade.last is not None else trade.entry
        result = _money((price - trade.entry) * trade.quantity * trade.multiplier)
        answer = QMessageBox.question(
            self, t("Close position"),
            t("Close {label} at the last known value ({price})?", label=trade_label(trade),
              price=_money(price)) + "\n\n" + t("Result: {result}", result=result),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        from miratrade.practice import close_trade

        close_trade(trade, price, "manual")
        save(self.trades, self.path)
        self.refresh()
