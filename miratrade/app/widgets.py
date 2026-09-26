"""Small shared pieces: a read-only table over a DataFrame, cards, background work."""
from __future__ import annotations

import traceback

import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRunnable, Qt, Signal
from PySide6.QtWidgets import QFrame, QHeaderView, QLabel, QTableView, QVBoxLayout

from miratrade.app import theme


class DataFrameModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame | None = None, headers: dict[str, str] | None = None):
        super().__init__()
        self.headers = headers or {}
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
                return "sí" if v else "no"
            return str(v)
        if role == Qt.TextAlignmentRole and isinstance(v, (int, float, np.number)) and not isinstance(v, bool):
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


def table(df: pd.DataFrame | None = None, headers: dict[str, str] | None = None) -> QTableView:
    view = QTableView()
    view.setModel(DataFrameModel(df, headers))
    view.verticalHeader().hide()
    view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    view.horizontalHeader().setStretchLastSection(True)
    view.setSelectionBehavior(QTableView.SelectRows)
    view.setAlternatingRowColors(False)
    return view


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
