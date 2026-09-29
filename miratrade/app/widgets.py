"""Small shared pieces: a read-only table over a DataFrame, cards, background work."""
from __future__ import annotations

import traceback

import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRunnable, Qt, Signal
from PySide6.QtWidgets import QFrame, QHeaderView, QLabel, QTableView, QVBoxLayout, QWidget

from miratrade.app import theme
from miratrade.app.i18n import formats, t


class DataFrameModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame | None = None, headers: dict[str, str] | None = None,
                 right: set[str] | None = None):
        super().__init__()
        self.headers = headers or {}
        # Columns to align right although they hold text. A figure written in the user's own number
        # format is a string by the time it gets here, and a column of right-aligned figures is what
        # makes a table of them readable.
        self.right = set(right or ())
        self.df = pd.DataFrame()
        self.set(df if df is not None else pd.DataFrame())

    def set(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self.df = df.reset_index(drop=True)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.df)

    def columnCount(self, parent=QModelIndex()):
        return len(self.df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        v = self.df.iat[index.row(), index.column()]
        if role == Qt.DisplayRole:
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return "–"
            if isinstance(v, (float, np.floating)):
                return f"{v:,.2f}"
            if isinstance(v, (bool, np.bool_)):
                return t("yes") if v else t("no")
            return str(v)
        if role == Qt.TextAlignmentRole and (str(self.df.columns[index.column()]) in self.right
                                             or (isinstance(v, (int, float, np.number))
                                                 and not isinstance(v, bool))):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and isinstance(v, (float, np.floating)) and self.df.columns[index.column()].endswith("_r"):
            from PySide6.QtGui import QColor
            return QColor(theme.UP if v > 0 else theme.DOWN if v < 0 else theme.TEXT)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            col = str(self.df.columns[section])
            return self.headers.get(col, col)
        return None


def table(df: pd.DataFrame | None = None, headers: dict[str, str] | None = None,
          right: set[str] | None = None, resizable: bool = False) -> QTableView:
    """A read-only table over a DataFrame.

    ``resizable`` gives the columns to the reader: each one starts at the width its contents need
    and can then be dragged, double-clicked to fit, or reordered. A table of filings has one column
    (the insider's name, the asset) that is far wider than the rest, and fixing every width to its
    contents pushes the numbers off the screen — which is exactly the column the reader wants.
    """
    view = QTableView()
    view.setModel(DataFrameModel(df, headers, right))
    view.verticalHeader().hide()
    header = view.horizontalHeader()
    if resizable:
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionsMovable(True)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(48)
        view.setWordWrap(False)
        view.setTextElideMode(Qt.ElideRight)         # a long name is cut, never wrapped over rows
        view.setHorizontalScrollMode(QTableView.ScrollPerPixel)
    else:
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
    view.setSelectionBehavior(QTableView.SelectRows)
    view.setAlternatingRowColors(False)
    return view


def fit_columns(view: QTableView, cap: int = 320) -> None:
    """Start every column at the width its contents need, bounded so one long column cannot push
    the rest off the screen. Called after the data changes, never after the user has dragged."""
    view.resizeColumnsToContents()
    header = view.horizontalHeader()
    for i in range(header.count()):
        header.resizeSection(i, min(max(header.sectionSize(i) + 10, 56), cap))


def card(*widgets, title: str | None = None) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(12)
    if title:
        h = QLabel(title)
        h.setObjectName("h2")
        lay.addWidget(h)
    for w in widgets:
        lay.addWidget(w)
    return frame


def fmt_date(d, year: bool = True) -> str:
    """24 Aug 2026, with the month written in the interface language whatever the system locale is."""
    d = pd.Timestamp(d)
    return f"{d.day} {formats()['months'][d.month - 1]}" + (f" {d.year}" if year else "")


def fmt_num(v: float, decimals: int = 2, sign: bool = False) -> str:
    """1,234.56 in English and 1.234,56 in Spanish, always with a real minus sign; ``sign`` also
    writes the plus."""
    f = formats()
    s = f"{abs(v):,.{decimals}f}".replace(",", "\0").replace(".", f["decimal"]).replace("\0", f["thousands"])
    return ("−" if v < 0 else "+" if sign and v > 0 else "") + s


def fmt_money(v: float) -> str:
    """A short amount for a crowded line: 1.4M$ or 250k$."""
    return f"{fmt_num(v / 1e6, 1)} M$" if abs(v) >= 1e6 else f"{fmt_num(v / 1e3, 0)} k$"


class ShapeIcon(QWidget):
    """The event shape (◆ ● ■) drawn, so it never depends on a font having the glyph."""

    def __init__(self, shape: str, color: str, size: int = 10):
        super().__init__()
        self.shape, self.color = shape, color
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QColor, QPainter, QPolygonF

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.color))
        w, h = self.width(), self.height()
        if self.shape == "●":
            p.drawEllipse(1, 1, w - 2, h - 2)
        elif self.shape == "■":
            p.drawRect(1, 1, w - 2, h - 2)
        else:
            p.drawPolygon(QPolygonF([QPointF(w / 2, 0), QPointF(w, h / 2), QPointF(w / 2, h), QPointF(0, h / 2)]))


def muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    """Runs ``fn`` off the UI thread; connect to ``signals.done`` / ``signals.failed``."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Signals()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:                      # shown to the user, never swallowed
            traceback.print_exc()
            self.signals.failed.emit(f"{type(e).__name__}: {e}")
        else:
            self.signals.done.emit(result)
