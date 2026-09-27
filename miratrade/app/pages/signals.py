"""Señales: the new events of the last days, each with its chart and the evidence of similar
past events (from the newest report with ``events.csv``). The scan runs as a separate process."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QProcess, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMessageBox,
                               QListWidgetItem,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from miratrade.app import data, theme
from miratrade.app.chart import CandleChart
from miratrade.app.widgets import ShapeIcon, es_date, es_num, muted
from miratrade.config import MIN_AUTO_REFRESH_MINUTES, Config
from miratrade.outcomes import EVENT_TYPES, variants
from miratrade.scan import (CONDITION_LABELS, DEFAULT_VARIANT, EVENT_LABELS, contract_for, covered_days,
                            evidence, filter_events, latest_history_report, load_history, load_scan,
                            variant_label, within_window)

CONTEXT_LABELS = {"trend:up": "Tendencia al alza (sobre sus medias de 20 y 50)",
                  "trend:above_200": "Por encima de su media de 200 sesiones",
                  "mom:ret20>0": "Sube en las últimas 20 sesiones", "rsi:<40": "RSI bajo (menos de 40)",
                  "rsi:>60": "RSI alto (más de 60)", "vol:rel>1.5": "Volumen 1,5 veces el normal",
                  "mkt:spy_above_50d": "Mercado (SPY) sobre su media de 50", "short:low": "Poca venta en corto",
                  "short:high": "Mucha venta en corto",
                  "dark:high": "Volumen fuera de bolsa inusualmente alto (dark pool)",
                  "dark:low": "Volumen fuera de bolsa inusualmente bajo"}
DISCLAIMER = "Análisis, no asesoramiento. Con opciones puedes perder la prima entera."
ITEM_PADDING = 10          # keep in sync with theme.QSS: QListWidget::item padding
SELECTED_BORDER = 1        # …and the border it gains when selected


def _label(text: str, name: str, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def _pill(kind: str) -> QFrame:
    color, shape, border = theme.EVENT_STYLE[kind]
    pill = QFrame()
    pill.setObjectName("eventPill")
    pill.setFixedHeight(22)
    pill.setStyleSheet(f"QFrame#eventPill {{ border: 1px solid {border}; border-radius: 11px; }}")
    lay = QHBoxLayout(pill)
    lay.setContentsMargins(8, 0, 9, 0)
    lay.setSpacing(5)
    lay.addWidget(ShapeIcon(shape, color, 9))
    lab = QLabel(EVENT_LABELS[kind])
    lab.setStyleSheet(f"color: {color}; font-size: 12px; border: none;")
    lay.addWidget(lab)
    pill.setAccessibleName(EVENT_LABELS[kind])
    return pill


class EventCard(QWidget):
    def __init__(self, ev: dict):
        super().__init__()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(_label(ev["ticker"], "ticker"))
        top.addStretch(1)
        for k in EVENT_TYPES:
            if ev.get(k):
                top.addWidget(_pill(k))
        lay.addLayout(top)
        lay.addWidget(_label(str(ev.get("what", "")), "body", wrap=True))
        lay.addWidget(muted(es_date(ev["signal_date"])))

    def fit(self, width: int) -> int:
        """Lay the card out for ``width`` and return the height it really needs. Qt guesses the
        height of a wrapped label from a fixed aspect ratio, which claims two lines for texts that
        take one, so each wrapped label is measured at the width it will actually get."""
        self.setFixedWidth(width)
        margins = self.layout().contentsMargins()
        inner = width - margins.left() - margins.right()
        for label in self.findChildren(QLabel):
            if label.wordWrap():
                label.setFixedHeight(label.heightForWidth(inner))
        self.adjustSize()
        return self.height()


class ContractCard(QFrame):
    """The contract the chosen profile would buy, with its cost and greeks. Every number is
    modelled from the stock's realised volatility, which the footer says plainly."""

    FIELDS = (("Prima", "premium"), ("Delta", "delta"), ("Coste 1 contrato", "cost"), ("Theta · $/día", "theta"),
              ("Strike", "strike"), ("Vega", "vega"), ("Vol. implícita", "iv"), ("Sobre el strike", "in_the_money"))

    def __init__(self):
        super().__init__()
        self.setObjectName("evidence")
        self.head = _label("", "h2", wrap=True)
        self.sub = muted("")
        self.exits = _label("", "body", wrap=True)
        self.values: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        for i, (caption, key) in enumerate(self.FIELDS):
            box = QVBoxLayout()
            box.setSpacing(1)
            name = QLabel(caption)
            name.setObjectName("label")
            value = QLabel("–")
            value.setObjectName("price")
            self.values[key] = value
            box.addWidget(name)
            box.addWidget(value)
            holder = QWidget()
            holder.setLayout(box)
            grid.addWidget(holder, i // 2, i % 2)
        body = QVBoxLayout(self)
        body.setContentsMargins(14, 12, 14, 12)
        body.setSpacing(8)
        body.addWidget(self.head)
        body.addWidget(self.sub)
        body.addLayout(grid)
        body.addWidget(self.exits)
        body.addWidget(muted("Precios de modelo, no cotizaciones. Con tu cuenta conectada se usará la cadena real."))

    def set_contract(self, ticker: str, c: dict | None, reason: str = "") -> None:
        if not c:
            self.head.setText("Sin contrato")
            self.sub.setText(reason or "Este perfil compra la acción, no una opción.")
            self.exits.setText("")
            for label in self.values.values():
                label.setText("–")
            return
        self.head.setText(f"{ticker} {es_num(c['strike'])} C")
        self.sub.setText(f"vence el {es_date(c['expiry'])} · {c['dte']} días · acción a {es_num(c['spot'])} $")
        shown = {"premium": f"{es_num(c['premium'])} $", "delta": es_num(c["delta"]),
                 "cost": f"{es_num(c['cost'], 0)} $", "theta": es_num(c["theta"], 3),
                 "strike": es_num(c["strike"]), "vega": es_num(c["vega"], 3),
                 "iv": f"{es_num(c['iv'] * 100, 0)} %",
                 "in_the_money": f"{es_num(c['in_the_money'] * 100, 1, sign=True)} %"}
        for key, text in shown.items():
            self.values[key].setText(text)
        self.exits.setText(f"Vender en {es_num(c['target'])} $ (+{c['target_pct'] * 100:.0f} %) · "
                           f"stop en {es_num(c['stop'])} $ (−{c['stop_pct'] * 100:.0f} %)")


class OutcomeBar(QWidget):
    """Target / stop / neither as one stacked bar; the labels say the numbers (never colour alone)."""

    def __init__(self):
        super().__init__()
        self.parts = (0.0, 0.0, 0.0)
        self.setFixedHeight(10)

    def set(self, target: float, stop: float, neither: float) -> None:
        self.parts = tuple(0.0 if pd.isna(v) else float(v) for v in (target, stop, neither))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.GRID))
        p.drawRoundedRect(0, 0, w, h, 5, 5)
        x = 0.0
        for v, c in zip(self.parts, (theme.UP, theme.DOWN, theme.TEXT_2)):
            p.setBrush(QColor(c))
            p.drawRect(int(x), 0, int(round(w * v)), h)
            x += w * v


class SignalsPage(QWidget):
    open_settings = Signal()
    use_research = Signal()
    practice_added = Signal()

    def __init__(self, reports_dir: Path | None = None, scan_dir: Path | None = None, cfg: Config = Config(),
                 settings_path: Path | None = None):
        super().__init__()
        self.setObjectName("page")
        self.cfg = cfg
        self.reports_dir = Path(reports_dir or data.REPORTS_DIR)
        self.scan_dir = Path(scan_dir or data.SCAN_DIR)
        self.settings_path = Path(settings_path or data.SETTINGS_PATH)
        self.proc: QProcess | None = None
        self.scan: dict | None = None
        self._contract: dict | None = None
        self.auto = QTimer(self)                 # repeats the download on its own; see _tick
        self.auto.timeout.connect(self._tick)
        self.history = self.rules = pd.DataFrame()
        self.report: Path | None = None

        # toolbar
        self.title = _label("Señales nuevas", "h1")
        self.meta = _label("", "muted")
        self.days = QSpinBox()
        self.days.setRange(1, 60)
        self.days.setValue(7)
        self.days.setSuffix(" días")
        self.days.setAccessibleName("Mostrar los eventos de los últimos días")
        self.days.setToolTip("Filtra lo ya descargado. No vuelve a buscar.")
        self.days.valueChanged.connect(lambda _: self.apply_filters())
        self.cap = data.cap_combo(data.read_settings(self.settings_path).data.cap_tier, self._cap_changed)
        self.cap.setToolTip("Filtra lo ya descargado por tamaño de empresa. No vuelve a buscar.")
        self.variant = QComboBox()
        for v in variants(cfg):
            self.variant.addItem(variant_label(v, cfg), v)
        self.variant.setCurrentIndex(max(0, self.variant.findData(DEFAULT_VARIANT)))
        self.variant.setAccessibleName("Perfil de resultado para la evidencia")
        self.variant.currentIndexChanged.connect(lambda _: self._show_selected(self.list.currentItem()))
        self.scan_btn = QPushButton("Actualizar datos")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.clicked.connect(self.start_scan)
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self.cancel_scan)
        self.cancel_btn.hide()
        bar = QHBoxLayout()
        bar.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(self.title)
        titles.addWidget(self.meta)
        bar.addLayout(titles)
        bar.addStretch(1)
        for w in (muted("Perfil"), self.variant, muted("Tamaño"), self.cap, self.days,
                  self.scan_btn, self.cancel_btn):
            bar.addWidget(w)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        self.log.hide()

        # Data-source banner: says up front whether a scan can even get prices.
        self.coverage = muted("")
        self.coverage.hide()
        self.source_msg = _label("", "body", wrap=True)
        self.source_btn = QPushButton("Abrir Configuración")
        self.source_btn.clicked.connect(self.open_settings.emit)
        self.research_btn = QPushButton("Usar webs públicas")
        self.research_btn.setToolTip("Yahoo / Stooq, solo para tu investigación personal, mientras no tengas "
                                     "conectada una cuenta de bróker.")
        self.research_btn.clicked.connect(self.use_research.emit)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        b = QHBoxLayout(self.banner)
        b.setContentsMargins(14, 10, 14, 10)
        b.setSpacing(12)
        b.addWidget(self.source_msg, 1)
        b.addWidget(self.research_btn)
        b.addWidget(self.source_btn)
        self.banner.hide()

        # left: filter + events
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtrar por ticker")
        self.filter.setClearButtonEnabled(True)
        self.filter.setAccessibleName("Filtrar los eventos por ticker")
        self.filter.textChanged.connect(self._apply_filter)
        self.count = _label("", "label")
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(self.filter, 1)
        head.addWidget(self.count)
        self.list = QListWidget()
        self.list.setAccessibleName("Eventos nuevos")
        self.list.setUniformItemSizes(False)
        self.list.currentItemChanged.connect(self._show_selected)
        self.empty = muted("Aún no hay búsqueda. Pulsa «Buscar eventos»: la primera vez descarga los Form 4 "
                           "de la SEC de esos días y puede tardar varios minutos. Todo queda en caché.")
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addLayout(head)
        left.addWidget(self.empty)
        left.addWidget(self.list, 1)
        left_box = QWidget()
        left_box.setLayout(left)
        left_box.setFixedWidth(340)

        # centre: chart
        self.ticker = _label("", "ticker")
        self.price = _label("", "price")
        self.change = _label("", "price")
        head = QHBoxLayout()
        head.setSpacing(14)
        for w in (self.ticker, self.price, self.change):
            head.addWidget(w, 0, Qt.AlignBaseline)
        head.addStretch(1)
        self.chart = CandleChart()
        centre = QVBoxLayout()
        centre.setSpacing(12)
        centre.addLayout(head)
        centre.addWidget(self.chart, 1)

        # right: evidence and the proposed profile
        side = QWidget()
        side.setObjectName("side")
        side.setFixedWidth(356)
        outer = QVBoxLayout(side)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(12)
        s = QVBoxLayout()                       # the detail scrolls; the actions stay in sight
        s.setContentsMargins(0, 0, 10, 0)
        s.setSpacing(12)
        self.profile = _label("", "h2", wrap=True)
        self.contract = ContractCard()
        self.evidence_text = _label("", "body", wrap=True)
        self.outcome = OutcomeBar()
        self.legend = muted("")
        box = QFrame()
        box.setObjectName("evidence")
        b = QVBoxLayout(box)
        b.setContentsMargins(14, 12, 14, 12)
        b.setSpacing(8)
        b.addWidget(_label("Evidencia", "h2"))
        b.addWidget(self.evidence_text)
        b.addWidget(self.outcome)
        b.addWidget(self.legend)
        self.similar = muted("")
        self.rules_text = _label("", "body", wrap=True)
        self.context = muted("")
        self.preview_btn = QPushButton("Vista previa en Schwab")
        self.preview_btn.setObjectName("primary")
        self.practice_btn = QPushButton("Añadir a práctica")
        self.practice_btn.clicked.connect(self.add_to_practice)
        self.preview_btn.setEnabled(False)
        self.preview_btn.setToolTip("Necesita una sesión de Schwab activa: la vista previa la da el bróker.")
        for w in (_label("OPERACIÓN DE REFERENCIA", "label"), self.profile, self.contract, box, self.similar,
                  _label("REGLAS VALIDADAS", "label"), self.rules_text, _label("CONTEXTO (NO DISPARA SEÑALES)", "label"),
                  self.context):
            s.addWidget(w)
        s.addStretch(1)
        detail = QWidget()
        detail.setObjectName("page")
        detail.setLayout(s)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(detail)
        outer.addWidget(scroll, 1)
        outer.addWidget(self.preview_btn)
        outer.addWidget(self.practice_btn)
        outer.addWidget(muted(DISCLAIMER))

        body = QHBoxLayout()
        body.setSpacing(24)
        body.addWidget(left_box)
        body.addLayout(centre, 1)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 0, 0)
        root.setSpacing(16)
        top = QVBoxLayout()
        top.setContentsMargins(0, 0, 24, 0)
        top.addLayout(bar)
        top.addWidget(self.coverage)
        top.addWidget(self.banner)
        top.addWidget(self.log)
        root.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(24)
        inner = QVBoxLayout()
        inner.setContentsMargins(0, 0, 0, 20)
        inner.addLayout(body)
        row.addLayout(inner, 1)
        row.addWidget(side)
        root.addLayout(row, 1)
        side.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.refresh()

    # ------------------------------------------------------------------ data

    def _cap_changed(self, tier: str) -> None:
        data.set_cap_tier(tier, self.settings_path)
        self.apply_filters()

    def refresh_cap(self) -> None:
        """Pick up a size chosen on the other screen."""
        tier = data.read_settings(self.settings_path).data.cap_tier
        if tier != self.cap.currentData():
            self.cap.blockSignals(True)
            self.cap.setCurrentIndex(max(0, self.cap.findData(tier)))
            self.cap.blockSignals(False)

    def in_refresh_window(self) -> bool:
        """Whether the clock is inside the New York window where filings actually arrive."""
        d = data.read_settings(self.settings_path).data
        return within_window(pd.Timestamp.now(tz="UTC"), d.auto_refresh_from, d.auto_refresh_to,
                             d.auto_refresh_weekdays_only)

    def _tick(self) -> None:
        """One turn of the automatic refresh. It starts a download only when the last one has
        finished, there is somewhere to get prices from, and New York is still filing — outside
        that there is nothing new to find."""
        if self.proc is None and self.scan_btn.isEnabled() and self.in_refresh_window():
            self.start_scan()

    def refresh_auto(self) -> None:
        """Start, restart or stop the automatic refresh from the saved settings."""
        minutes = data.read_settings(self.settings_path).data.auto_refresh_minutes
        if minutes and minutes >= MIN_AUTO_REFRESH_MINUTES:
            self.auto.start(int(minutes) * 60_000)
        else:
            self.auto.stop()
        self.refresh_source()

    def refresh_source(self) -> None:
        """Whether a scan could get prices right now (checked without downloading anything)."""
        from miratrade.data.prices import source_ready

        try:
            # the source this app is configured with, not whatever the default settings file says
            ok, why = source_ready(data.read_settings(self.settings_path).data.price_source)
        except Exception as e:
            ok, why = False, f"No se pudo comprobar la fuente de precios: {e}"
        self.banner.setVisible(not ok)
        d = data.read_settings(self.settings_path).data
        if not self.auto.isActive():
            self.scan_btn.setText("Actualizar datos")
        elif self.in_refresh_window():
            self.scan_btn.setText(f"Actualizar datos · automático cada {d.auto_refresh_minutes} min")
        else:
            self.scan_btn.setText("Actualizar datos · automático en pausa")
            self.scan_btn.setToolTip(f"Fuera de la franja {d.auto_refresh_from}–{d.auto_refresh_to} de "
                                     "Nueva York. Puedes pulsarlo igualmente.")
        self.source_msg.setText(why + " Sin precios, la búsqueda no puede empezar.")
        self.scan_btn.setEnabled(ok and self.proc is None)
        self.scan_btn.setToolTip("" if ok else why)

    def refresh(self) -> None:
        self.refresh_auto()
        self.report = latest_history_report(self.reports_dir)
        self.history, self.rules = load_history(self.report) if self.report else (pd.DataFrame(), pd.DataFrame())
        self.scan = load_scan(self.scan_dir)
        self.list.clear()
        events = self.scan["events"] if self.scan else pd.DataFrame()
        has = len(events) > 0
        self.empty.setVisible(not has)
        self.list.setVisible(has)
        if self.scan:
            span = f"{es_date(self.scan['since'], False)} → {es_date(self.scan['end'])}" if self.scan["since"] else ""
            src = f"evidencia de {self.report.name}" if self.report else "sin reporte con eventos para la evidencia"
            self.meta.setText(f"Búsqueda {span} · {src}")
            if not has:
                self.empty.setText("Ningún evento nuevo en esos días. Prueba con más días.")
        else:
            self.meta.setText("Sin búsqueda todavía")
        self.filter.setEnabled(has)
        self.apply_filters()

    def _fill_list(self, events: pd.DataFrame) -> None:
        self.list.clear()
        for ev in events.to_dict("records"):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, ev)
            item.setData(Qt.AccessibleTextRole, f"{ev['ticker']}: {ev.get('what', '')}")
            card = EventCard(ev)
            item.setSizeHint(card.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, card)
        self._resize_cards()
        self._apply_filter()
        if not len(events):
            self._show_selected(None)

    # ------------------------------------------------------------------ list layout and filter

    def _resize_cards(self) -> None:
        """Each card's height depends on how its description wraps, which is only known once the
        list has a real width; without this, long filer names are cut off. The row must also
        leave room for the padding and selection border the stylesheet draws around it."""
        row = self.list.viewport().width() - 4
        if row < 80:                                    # not laid out yet: showEvent runs this again
            return
        pad = ITEM_PADDING + SELECTED_BORDER
        for i in range(self.list.count()):
            item = self.list.item(i)
            card = self.list.itemWidget(item)
            if card is not None:
                item.setSizeHint(QSize(row, card.fit(row - 2 * pad) + 2 * pad))

    def apply_filters(self) -> None:
        """Window, size and ticker are views over the download: rebuild the list, never fetch."""
        if self.scan is None:
            return
        events = self.scan["events"]
        tier = self.cap.currentData() or "all"
        sizes = pd.to_numeric(events["mkt_cap"], errors="coerce") if "mkt_cap" in events else None
        # An older download has no company sizes, so every tier would empty the list in silence.
        sizeless = tier != "all" and (sizes is None or not sizes.notna().any())
        shown = filter_events(events, days=self.days.value(), cap_tier=tier, end=self.scan.get("end"))
        self._fill_list(shown)
        if sizeless and len(events):
            self.empty.setText("Esta descarga es anterior al filtro de tamaño y no guardó la capitalización "
                               "de las empresas. Pulsa «Actualizar datos», o elige «Todas» en Tamaño.")
            self.empty.setVisible(True)
        have = covered_days(self.scan)
        asking = self.days.value()
        notes = []
        if asking > have:
            notes.append(f"Solo hay {have} días descargados; pulsa «Actualizar datos» para traer más.")
        if tier != "all" and not sizeless:
            notes.append(f"Filtrando por tamaño: {self.cap.currentText()}.")
        self.coverage.setText("  ".join(notes))
        self.coverage.setVisible(bool(notes))

    def _apply_filter(self, _text: str = "") -> None:
        needle = self.filter.text().strip().upper()
        total = self.list.count()
        first = None
        shown = 0
        for i in range(total):
            item = self.list.item(i)
            ticker = str((item.data(Qt.UserRole) or {}).get("ticker", "")).upper()
            match = not needle or needle in ticker
            item.setHidden(not match)
            if match:
                shown += 1
                first = first or item
        self.count.setText("" if not total else f"{shown} DE {total}" if needle else f"{total} EVENTOS")
        if total:
            self.empty.setText(f"Ningún evento con «{self.filter.text().strip()}».")
            self.empty.setVisible(shown == 0)
        current = self.list.currentItem()
        if first is not None and (current is None or current.isHidden()):
            self.list.setCurrentItem(first)
        elif first is None:
            self._show_selected(None)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_cards()

    def showEvent(self, event):
        super().showEvent(event)
        self._resize_cards()

    def _show_selected(self, item: QListWidgetItem | None, _prev=None) -> None:
        v = self.variant.currentData()
        self.profile.setText(variant_label(v, self.cfg))
        if item is None:
            self._contract = None
            self.practice_btn.setEnabled(False)
            self.contract.set_contract("", None, "Elige un evento.")
            for w in (self.ticker, self.price, self.change, self.evidence_text, self.legend, self.similar,
                      self.rules_text, self.context):
                w.setText("")
            self.outcome.set(0, 0, 0)
            self.chart.set_data(None)
            return
        ev = item.data(Qt.UserRole)
        t = ev["ticker"]
        prices = (self.scan or {}).get("prices", {}).get(t, pd.DataFrame())
        self.ticker.setText(t)
        if len(prices) >= 2:
            last, prev = prices["close"].iat[-1], prices["close"].iat[-2]
            self.price.setText(f"{es_num(last)} $")
            ch = last / prev - 1
            self.change.setText(f"{es_num(ch * 100, 1, sign=True)} %")
            self.change.setStyleSheet(f"color: {theme.UP if ch >= 0 else theme.DOWN}")
        contract = contract_for(prices, ev["signal_date"], v, self.cfg) if len(prices) else None
        self._contract = contract
        self.practice_btn.setEnabled(contract is not None)
        self.contract.set_contract(t, contract, "" if v.startswith("call") else
                                   "Este perfil compra la acción, no una opción.")
        kind = next((k for k in EVENT_TYPES if ev.get(k)), "event:insider_buy")
        color, shape, _ = theme.EVENT_STYLE[kind]
        self.chart.set_data(prices, ev["signal_date"], color, shape)

        e = evidence(ev, self.history, v, self.rules)
        self.evidence_text.setText(e.sentence if self.report else "No hay un reporte con eventos: ejecuta un "
                                   "análisis en Reportes para tener evidencia.")
        self.outcome.set(e.target, e.stop, e.neither)
        self.legend.setText("verde: objetivo · coral: stop · gris: ninguno" if e.n else "")
        narrowed = [CONDITION_LABELS.get(c, c) for c in e.similar_to]
        self.similar.setText(("Parecidos = mismo tipo de evento" + (", " + ", ".join(narrowed) if narrowed else "")
                              + ".") if e.n else "")
        self.rules_text.setText(", ".join(e.rules) if e.rules else
                                "Ninguna todavía: el análisis no ha confirmado ninguna regla para este perfil. "
                                "Trata la evidencia como historial, no como predicción.")
        ctx = [label for c, label in CONTEXT_LABELS.items() if ev.get(c) is True or ev.get(c) == 1]
        self.context.setText("\n".join(f"• {c}" for c in ctx) or "Nada destacable.")

    def add_to_practice(self) -> None:
        """Open the contract on screen as a paper position, sized by the risk settings."""
        from miratrade.practice import PRACTICE_PATH, load, open_trade, save
        from miratrade.app.pages.practice import START_EQUITY

        item = self.list.currentItem()
        contract = self._contract
        if item is None or contract is None:
            QMessageBox.information(self, "Práctica", "Elige un evento con contrato para añadirlo.")
            return
        ev = item.data(Qt.UserRole)
        trades = load(PRACTICE_PATH)
        cfg = data.read_settings(self.settings_path)
        try:
            trade = open_trade(
                trades, ticker=ev["ticker"], kind="call", entry=contract["premium"],
                stop=contract["stop"], target=contract["target"],
                equity=START_EQUITY, note=str(ev.get("what", ""))[:120],
                strike=contract["strike"], expiry=str(contract["expiry"].date()), iv=contract["iv"], cfg=cfg)
        except ValueError as e:
            QMessageBox.warning(self, "Práctica", str(e))
            return
        save(trades, PRACTICE_PATH)
        self.practice_added.emit()
        QMessageBox.information(
            self, "Práctica",
            f"Añadida: {trade.quantity} × {trade.label()}\n\n"
            f"Coste {trade.cost:,.0f} $ · riesgo hasta el stop {trade.risk:,.0f} $.\n"
            "Sin dinero real; la verás en la pantalla Práctica.")

    # ------------------------------------------------------------------ running a scan

    def start_scan(self) -> None:
        if self.proc is not None:
            return
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read_output)
        self.proc.finished.connect(lambda code, _status: self._finished(code))
        self.log.clear()
        self.log.show()
        self.scan_btn.setEnabled(False)
        self.cancel_btn.show()
        window = data.read_settings(self.settings_path).data.scan_days
        self.meta.setText(f"Descargando los últimos {window} días…")
        self.proc.start(sys.executable, data.scan_command(window, self.variant.currentData(),
                                                          self.scan_dir, self.report, "all"))

    def _read_output(self) -> None:
        text = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in text.splitlines():
            if line.strip():
                self.log.appendPlainText(line)

    def _finished(self, code: int) -> None:
        self.proc = None
        self.scan_btn.setEnabled(True)
        self.refresh_source()
        self.cancel_btn.hide()
        if code == 0:
            self.log.hide()
            self.refresh()
        else:
            self.meta.setText(f"La búsqueda terminó con error (código {code}). Revisa el registro.")

    def cancel_scan(self) -> None:
        if self.proc is not None:
            self.proc.kill()
            self.meta.setText("Cancelada. Lo descargado queda en caché.")
