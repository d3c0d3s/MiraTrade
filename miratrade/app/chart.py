"""Candlestick chart with the event day marked (manual, page 10): green up / coral down candles,
faint horizontal grid only, prices in mono on the right, the event as a dashed line + its shape."""
from __future__ import annotations

import pandas as pd
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from miratrade.app import theme
from miratrade.app.widgets import es_date, es_num

AXIS_W = 64          # right-hand price axis
PAD = 14


class CandleChart(QWidget):
    def __init__(self, bars: int = 120, parent=None):
        super().__init__(parent)
        self.bars = bars
        self.df = pd.DataFrame()
        self.event_date: pd.Timestamp | None = None
        self.event_color = theme.INSIDER
        self.event_shape = "◆"
        self.empty_text = "Elige un evento para ver su gráfico."
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName("Gráfico de velas")

    def set_data(self, df: pd.DataFrame | None, event_date=None, color: str = theme.INSIDER, shape: str = "◆") -> None:
        df = pd.DataFrame() if df is None else df
        if len(df):
            if event_date is not None:
                # keep the event visible: end the window a few weeks after it at most
                pos = int(df.index.searchsorted(pd.Timestamp(event_date)))
                df = df.iloc[: min(len(df), max(pos + 30, self.bars))]
            df = df.tail(self.bars)
        self.df, self.event_date = df, (pd.Timestamp(event_date) if event_date is not None else None)
        self.event_color, self.event_shape = color, shape
        self.update()

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.fillPath(path, QColor(theme.PANEL))
        p.setPen(QColor(theme.BORDER))
        p.drawPath(path)
        if self.df.empty:
            p.setPen(QColor(theme.TEXT_2))
            p.drawText(r, Qt.AlignCenter, self.empty_text)
            return
        plot = QRectF(PAD, PAD + 18, r.width() - AXIS_W - PAD, r.height() - 2 * PAD - 18)
        lo, hi = float(self.df["low"].min()), float(self.df["high"].max())
        span = (hi - lo) or 1.0
        lo, hi = lo - span * 0.04, hi + span * 0.04
        y = lambda v: plot.top() + (hi - v) / (hi - lo) * plot.height()  # noqa: E731

        mono = QFont(theme.MONO.split(",")[0].strip("' "))
        mono.setPixelSize(11)
        p.setFont(mono)
        for k in range(5):
            v = lo + (hi - lo) * k / 4
            yy = y(v)
            p.setPen(QPen(QColor(theme.GRID), 1))
            p.drawLine(QPointF(plot.left(), yy), QPointF(plot.right(), yy))
            p.setPen(QColor(theme.TEXT_2))
            p.drawText(QRectF(plot.right() + 8, yy - 8, AXIS_W - 10, 16), Qt.AlignLeft | Qt.AlignVCenter, es_num(v))

        n = len(self.df)
        step = plot.width() / n
        body_w = max(1.5, step * 0.62)
        event_x = None
        for i, (d, row) in enumerate(self.df.iterrows()):
            cx = plot.left() + (i + 0.5) * step
            up = row["close"] >= row["open"]
            c = QColor(theme.UP if up else theme.DOWN)
            p.setPen(QPen(c, 1))
            p.drawLine(QPointF(cx, y(row["high"])), QPointF(cx, y(row["low"])))
            top, bot = y(max(row["open"], row["close"])), y(min(row["open"], row["close"]))
            p.fillRect(QRectF(cx - body_w / 2, top, body_w, max(1.2, bot - top)), c)
            if self.event_date is not None and event_x is None and d >= self.event_date:
                event_x, event_low = cx, y(row["low"])

        # date labels: first and last bar
        p.setPen(QColor(theme.TEXT_2))
        p.drawText(QRectF(plot.left(), r.bottom() - PAD - 2, 120, 14), Qt.AlignLeft, es_date(self.df.index[0]))
        p.drawText(QRectF(plot.right() - 120, r.bottom() - PAD - 2, 120, 14), Qt.AlignRight, es_date(self.df.index[-1]))

        if event_x is not None:
            col = QColor(self.event_color)
            pen = QPen(col, 1, Qt.DashLine)
            col.setAlphaF(0.7)
            pen.setColor(col)
            p.setPen(pen)
            p.drawLine(QPointF(event_x, plot.top()), QPointF(event_x, plot.bottom()))
            self._shape(p, QPointF(event_x, min(event_low + 14, plot.bottom() - 6)), QColor(self.event_color))
            self._shape(p, QPointF(plot.left() + 5, PAD + 6), QColor(self.event_color), 4.0)
            p.setPen(QColor(theme.TEXT_BODY))
            p.drawText(QRectF(plot.left() + 16, PAD - 2, plot.width(), 16), Qt.AlignLeft,
                       f"evento del {es_date(self.event_date)}")

    def _shape(self, p: QPainter, c: QPointF, color: QColor, s: float = 6.5) -> None:
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        if self.event_shape == "●":
            p.drawEllipse(c, s, s)
        elif self.event_shape == "■":
            p.drawRect(QRectF(c.x() - s, c.y() - s, 2 * s, 2 * s))
        else:
            p.drawPolygon(QPolygonF([QPointF(c.x(), c.y() - s * 1.3), QPointF(c.x() + s * 1.3, c.y()),
                                     QPointF(c.x(), c.y() + s * 1.3), QPointF(c.x() - s * 1.3, c.y())]))
