"""Charts for the Reportes screen, drawn the same way as the candlestick chart: flat colours, a
faint horizontal grid, figures in mono, and every colour paired with a label so nothing depends on
telling green from coral.

Three views answer the questions the tables make hard: how the result added up over time, how the
individual results were distributed, and how the event types compare.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from miratrade.app import theme
from miratrade.app.widgets import es_date, es_num

PAD = 16
AXIS_W = 62
AXIS_H = 26


class Chart(QWidget):
    """Shared frame: rounded panel, title, axes and an empty state."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.title = title
        self.empty_text = "Sin datos para este reporte."
        self.note = ""
        self.setMinimumHeight(230)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName(title)

    # -- helpers ---------------------------------------------------------
    def _frame(self, p: QPainter) -> QRectF:
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.fillPath(path, QColor(theme.PANEL))
        p.setPen(QColor(theme.BORDER))
        p.drawPath(path)
        if self.title:
            f = QFont(theme.FONT.split(",")[0].strip("' "))
            f.setPixelSize(14)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(QColor(theme.TEXT))
            p.drawText(QRectF(r.left() + PAD, r.top() + 10, r.width() - 2 * PAD, 20), Qt.AlignLeft, self.title)
        if self.note:
            f = QFont(theme.FONT.split(",")[0].strip("' "))
            f.setPixelSize(11)
            p.setFont(f)
            p.setPen(QColor(theme.TEXT_2))
            p.drawText(QRectF(r.left() + PAD, r.bottom() - 20, r.width() - 2 * PAD, 16), Qt.AlignLeft, self.note)
        return r

    def _plot_rect(self, r: QRectF) -> QRectF:
        top = r.top() + (34 if self.title else PAD)
        bottom = r.bottom() - AXIS_H - (18 if self.note else 0)
        return QRectF(r.left() + PAD, top, r.width() - AXIS_W - PAD, max(20.0, bottom - top))

    def _mono(self, p: QPainter, size: int = 11) -> None:
        f = QFont(theme.MONO.split(",")[0].strip("' "))
        f.setPixelSize(size)
        p.setFont(f)

    def _y_axis(self, p: QPainter, plot: QRectF, low: float, high: float, fmt=lambda v: es_num(v, 1)) -> None:
        self._mono(p)
        for k in range(5):
            value = low + (high - low) * k / 4
            y = plot.bottom() - (value - low) / (high - low or 1) * plot.height()
            p.setPen(QPen(QColor(theme.GRID), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(theme.TEXT_2))
            p.drawText(QRectF(plot.right() + 8, y - 8, AXIS_W - 10, 16), Qt.AlignLeft | Qt.AlignVCenter, fmt(value))

    def _no_data(self, p: QPainter, r: QRectF) -> bool:
        p.setPen(QColor(theme.TEXT_2))
        p.drawText(r, Qt.AlignCenter, self.empty_text)
        return True


class EquityCurve(Chart):
    """Cumulative result of taking every event with the same stake, in date order."""

    def __init__(self, parent=None):
        super().__init__("Resultado acumulado, evento a evento", parent)
        self.dates: list = []
        self.values: np.ndarray = np.array([])
        self.split: pd.Timestamp | None = None

    def set_data(self, dates, returns, split=None) -> None:
        returns = np.asarray(returns, dtype=float)
        ok = np.isfinite(returns)
        self.dates = list(pd.to_datetime(pd.Series(dates)[ok]))
        self.values = np.cumsum(returns[ok]) * 100
        self.split = pd.Timestamp(split) if split is not None else None
        self.note = ("Suma de los resultados de cada evento, en el orden en que ocurrieron. "
                     "La línea vertical separa el periodo de descubrimiento del de confirmación.")
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._frame(p)
        if len(self.values) < 2:
            return self._no_data(p, r)
        plot = self._plot_rect(r)
        low, high = float(self.values.min()), float(self.values.max())
        pad = (high - low) * 0.08 or 1.0
        low, high = min(low - pad, 0.0), high + pad
        self._y_axis(p, plot, low, high, lambda v: f"{es_num(v, 0)} %")

        n = len(self.values)
        x = lambda i: plot.left() + i / (n - 1) * plot.width()            # noqa: E731
        y = lambda v: plot.bottom() - (v - low) / (high - low) * plot.height()   # noqa: E731
        zero = y(0.0)
        p.setPen(QPen(QColor(theme.BORDER_2), 1, Qt.DashLine))
        p.drawLine(QPointF(plot.left(), zero), QPointF(plot.right(), zero))

        if self.split is not None and self.dates:
            after = [i for i, d in enumerate(self.dates) if d >= self.split]
            if after:
                sx = x(after[0])
                p.fillRect(QRectF(sx, plot.top(), plot.right() - sx, plot.height()), QColor(255, 255, 255, 8))
                p.setPen(QPen(QColor(theme.TEXT_2), 1, Qt.DashLine))
                p.drawLine(QPointF(sx, plot.top()), QPointF(sx, plot.bottom()))
                self._mono(p, 10)
                p.setPen(QColor(theme.TEXT_2))
                p.drawText(QRectF(sx + 6, plot.top() + 2, 120, 14), Qt.AlignLeft, "confirmación →")

        line = QPolygonF([QPointF(x(i), y(v)) for i, v in enumerate(self.values)])
        p.setPen(QPen(QColor(theme.UP if self.values[-1] >= 0 else theme.DOWN), 2))
        p.drawPolyline(line)
        self._mono(p, 10)
        p.setPen(QColor(theme.TEXT_2))
        p.drawText(QRectF(plot.left(), plot.bottom() + 6, 150, 14), Qt.AlignLeft, es_date(self.dates[0]))
        p.drawText(QRectF(plot.right() - 150, plot.bottom() + 6, 150, 14), Qt.AlignRight, es_date(self.dates[-1]))


class Histogram(Chart):
    """How the individual results were distributed, with the target and the stop marked."""

    def __init__(self, parent=None):
        super().__init__("Distribución de los resultados", parent)
        self.counts: np.ndarray = np.array([])
        self.edges: np.ndarray = np.array([])
        self.markers: list[tuple[float, str, str]] = []

    def set_data(self, returns, markers=()) -> None:
        values = np.asarray(returns, dtype=float)
        values = values[np.isfinite(values)] * 100
        if len(values):
            lo, hi = float(np.percentile(values, 1)), float(np.percentile(values, 99))
            lo, hi = min(lo, -5.0), max(hi, 5.0)
            self.counts, self.edges = np.histogram(np.clip(values, lo, hi), bins=28, range=(lo, hi))
        else:
            self.counts, self.edges = np.array([]), np.array([])
        self.markers = list(markers)
        self.note = "Cada barra cuenta eventos. Los extremos incluyen los resultados más raros."
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._frame(p)
        if not len(self.counts) or self.counts.max() == 0:
            return self._no_data(p, r)
        plot = self._plot_rect(r)
        self._y_axis(p, plot, 0, float(self.counts.max()), lambda v: es_num(v, 0))
        lo, hi = float(self.edges[0]), float(self.edges[-1])
        x = lambda v: plot.left() + (v - lo) / (hi - lo or 1) * plot.width()   # noqa: E731
        width = plot.width() / len(self.counts)
        for i, count in enumerate(self.counts):
            centre = (self.edges[i] + self.edges[i + 1]) / 2
            h = count / self.counts.max() * plot.height()
            colour = QColor(theme.UP if centre >= 0 else theme.DOWN)
            p.fillRect(QRectF(x(self.edges[i]) + 1, plot.bottom() - h, max(1.0, width - 2), h), colour)
        for value, label, colour in self.markers:
            if lo <= value * 100 <= hi:
                mx = x(value * 100)
                p.setPen(QPen(QColor(colour), 1, Qt.DashLine))
                p.drawLine(QPointF(mx, plot.top()), QPointF(mx, plot.bottom()))
                self._mono(p, 10)
                p.setPen(QColor(colour))
                p.drawText(QRectF(mx + 4, plot.top() + 2, 90, 14), Qt.AlignLeft, label)
        self._mono(p, 10)
        p.setPen(QColor(theme.TEXT_2))
        p.drawText(QRectF(plot.left(), plot.bottom() + 6, 120, 14), Qt.AlignLeft, f"{es_num(lo, 0)} %")
        p.drawText(QRectF(plot.right() - 120, plot.bottom() + 6, 120, 14), Qt.AlignRight, f"{es_num(hi, 0)} %")


class BarChart(Chart):
    """One labelled bar per group; values may be negative."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(title, parent)
        self.labels: list[str] = []
        self.values: list[float] = []
        self.counts: list[int] = []
        self.suffix = " %"

    def set_data(self, labels, values, counts=None, note: str = "") -> None:
        pairs = [(str(l), float(v)) for l, v in zip(labels, values) if v is not None and np.isfinite(v)]
        self.labels = [l for l, _ in pairs]
        self.values = [v for _, v in pairs]
        self.counts = list(counts or [])
        self.note = note
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._frame(p)
        if not self.values:
            return self._no_data(p, r)
        plot = self._plot_rect(r)
        low, high = min(0.0, min(self.values)), max(0.0, max(self.values))
        pad = (high - low) * 0.15 or 1.0
        low, high = low - pad, high + pad
        self._y_axis(p, plot, low, high, lambda v: f"{es_num(v, 0)}{self.suffix}")
        y = lambda v: plot.bottom() - (v - low) / (high - low) * plot.height()   # noqa: E731
        zero = y(0.0)
        p.setPen(QPen(QColor(theme.BORDER_2), 1))
        p.drawLine(QPointF(plot.left(), zero), QPointF(plot.right(), zero))
        step = plot.width() / len(self.values)
        for i, value in enumerate(self.values):
            cx = plot.left() + (i + 0.5) * step
            top, bottom = min(zero, y(value)), max(zero, y(value))
            colour = QColor(theme.UP if value >= 0 else theme.DOWN)
            p.fillRect(QRectF(cx - step * 0.3, top, step * 0.6, max(1.0, bottom - top)), colour)
            self._mono(p, 10)
            p.setPen(QColor(theme.TEXT))
            above = value >= 0
            p.drawText(QRectF(cx - step / 2, (top - 16) if above else (bottom + 2), step, 14),
                       Qt.AlignHCenter, f"{es_num(value, 1)}{self.suffix}")
            f = QFont(theme.FONT.split(",")[0].strip("' "))
            f.setPixelSize(11)
            p.setFont(f)
            p.setPen(QColor(theme.TEXT_2))
            caption = self.labels[i] + (f" · n={self.counts[i]}" if i < len(self.counts) else "")
            p.drawText(QRectF(cx - step / 2, plot.bottom() + 5, step, 30), Qt.AlignHCenter | Qt.TextWordWrap, caption)


def profile_bars(profiles: pd.DataFrame) -> tuple[list[str], list[float], list[int]]:
    """Mean return per outcome profile, from ``profiles.csv``."""
    if profiles is None or profiles.empty or "variant" not in profiles:
        return [], [], []
    d = profiles.sort_values("variant")
    return list(d["variant"]), [v * 100 for v in d["mean_return"]], [int(n) for n in d["events"]]


def event_type_bars(events: pd.DataFrame, variant: str) -> tuple[list[str], list[float], list[int]]:
    """Mean return per kind of event for one profile, from ``events.csv``."""
    column = f"ret_{variant}"
    if events is None or events.empty or column not in events:
        return [], [], []
    labels, values, counts = [], [], []
    for key, label in (("event:insider_buy", "Directivos"), ("event:flow", "Opciones"), ("event:13dg", "13D / 13G")):
        if key not in events:
            continue
        rows = events[events[key].astype(bool)][column].dropna()
        if len(rows):
            labels.append(label)
            values.append(float(rows.mean()) * 100)
            counts.append(len(rows))
    return labels, values, counts


def variants_in(events: pd.DataFrame) -> list[str]:
    return sorted({c[4:] for c in (events.columns if events is not None else []) if str(c).startswith("ret_")},
                  key=lambda v: (not v.startswith("call"), v))
