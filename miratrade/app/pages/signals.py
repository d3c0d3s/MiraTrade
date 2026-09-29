"""Signals: the new events of the last days, each with its chart and the evidence of similar
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
from miratrade.app.i18n import t
from miratrade.app.chart import CandleChart
from miratrade.app.widgets import ShapeIcon, fmt_date, fmt_money, fmt_num, muted
from miratrade.config import MIN_AUTO_REFRESH_MINUTES, Config
from miratrade.outcomes import EVENT_TYPES, variants
from miratrade.scan import (CONDITION_LABELS, DEFAULT_VARIANT, EVENT_LABELS, contract_for,
                            empty_events, evidence, latest_history_report, load_events, load_history,
                            load_scan, stored_days, variant_label, within_window)

CONTEXT_LABELS = {"trend:up": "Trending up (above its 20 and 50 averages)",
                  "trend:above_200": "Above its 200-session average",
                  "mom:ret20>0": "Up over the last 20 sessions", "rsi:<40": "Low RSI (under 40)",
                  "rsi:>60": "High RSI (over 60)", "vol:rel>1.5": "Volume 1.5 times the usual",
                  "mkt:spy_above_50d": "Market (SPY) above its 50 average",
                  "short:low": "Little short selling", "short:high": "Heavy short selling",
                  "dark:high": "Unusually high off-exchange volume (dark pool)",
                  "dark:low": "Unusually low off-exchange volume"}
# Said beside every suggestion. The second sentence is read from the latest report at display time
# (see data.honesty_line), so the claim can never drift from what was actually measured.
DISCLAIMER = ("Analysis, not advice. With options you can lose the whole premium, and the contract "
              "prices shown are modelled from the stock, not quotes.")
ITEM_PADDING = 10          # keep in sync with theme.QSS: QListWidget::item padding
SELECTED_BORDER = 1        # …and the border it gains when selected


def event_note(ev) -> str:
    """What was filed, in the user's language. The scan saves the sentence twice: as English prose
    for the console and as its pieces, so a scan downloaded months ago still reads in the language
    chosen today. A scan from before that change only has the prose."""
    import json

    from miratrade.messages import note

    parts = ev.get("what_parts")
    if isinstance(parts, str) and parts.strip():
        try:
            return note([(template, fields) for template, fields in json.loads(parts)], t, fmt_money)
        except (ValueError, TypeError):          # hand-edited or from an older format
            pass
    return str(ev.get("what", ""))


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
    lab = QLabel(t(EVENT_LABELS[kind]))
    lab.setStyleSheet(f"color: {color}; font-size: 12px; border: none;")
    lay.addWidget(lab)
    pill.setAccessibleName(t(EVENT_LABELS[kind]))
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
        lay.addWidget(_label(event_note(ev), "body", wrap=True))
        lay.addWidget(muted(fmt_date(ev["signal_date"])))

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

    FIELDS = (("Premium", "premium"), ("Delta", "delta"), ("Cost of 1 contract", "cost"),
              ("Theta · $/day", "theta"), ("Strike", "strike"), ("Vega", "vega"),
              ("Implied volatility", "iv"), ("Above the strike", "in_the_money"))

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
            name = QLabel(t(caption))
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
        self.earnings = _label("", "body", wrap=True)
        self.earnings.setStyleSheet(f"color: {theme.DOWN}")
        body.addWidget(self.earnings)
        self.liquidity = _label("", "body", wrap=True)
        body.addWidget(self.liquidity)
        body.addWidget(muted(t("Modelled prices, not quotes. With your account connected the real chain "
                               "is used.")))

    def set_contract(self, ticker: str, c: dict | None, reason: str = "", reports=None,
                     tradeable=None) -> None:
        """``reports`` is the earnings date this contract would sit through, if any; ``tradeable`` is
        the liquidity verdict, whose reason is shown whether it passes or not — a contract the quotes
        make unusable must not look the same as one they do not."""
        self.earnings.setText("")
        self.liquidity.setText("")
        if not c:
            self.head.setText(t("No contract"))
            self.sub.setText(reason or t("This profile buys the shares, not an option."))
            self.exits.setText("")
            for label in self.values.values():
                label.setText("–")
            return
        self.head.setText(f"{ticker} {fmt_num(c['strike'])} C")
        self.sub.setText(t("expires {date} · {days} days · stock at {price} $",
                           date=fmt_date(c["expiry"]), days=c["dte"], price=fmt_num(c["spot"])))
        shown = {"premium": f"{fmt_num(c['premium'])} $", "delta": fmt_num(c["delta"]),
                 "cost": f"{fmt_num(c['cost'], 0)} $", "theta": fmt_num(c["theta"], 3),
                 "strike": fmt_num(c["strike"]), "vega": fmt_num(c["vega"], 3),
                 "iv": f"{fmt_num(c['iv'] * 100, 0)} %",
                 "in_the_money": f"{fmt_num(c['in_the_money'] * 100, 1, sign=True)} %"}
        for key, text in shown.items():
            self.values[key].setText(text)
        self.exits.setText(t("Sell at {target} $ (+{up} %) · stop at {stop} $ (−{down} %)",
                             target=fmt_num(c["target"]), up=f"{c['target_pct'] * 100:.0f}",
                             stop=fmt_num(c["stop"]), down=f"{c['stop_pct'] * 100:.0f}"))
        if tradeable is not None:
            self.liquidity.setText(tradeable.say(t, lambda v: fmt_num(v, 0)))
            self.liquidity.setStyleSheet("" if tradeable.ok else f"color: {theme.DOWN}")
        if reports is not None:
            self.earnings.setText(t("Reports on {date}, before this contract expires: the premium "
                                    "usually collapses once the news is out, even when the stock "
                                    "moved the right way, and a gap can open past the stop.",
                                  date=fmt_date(reports)))


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
                 settings_path: Path | None = None, db=None):
        super().__init__()
        self.setObjectName("page")
        self.cfg = cfg
        self.reports_dir = Path(reports_dir or data.REPORTS_DIR)
        self.scan_dir = Path(scan_dir or data.SCAN_DIR)
        self.settings_path = Path(settings_path or data.SETTINGS_PATH)
        self.proc: QProcess | None = None
        self._db = db                        # None: opened read-only on first use
        self._owns_db = db is None
        self.scan: dict | None = None
        self._contract: dict | None = None
        self.auto = QTimer(self)                 # repeats the download on its own; see _tick
        self.auto.timeout.connect(self._tick)
        self.history = self.rules = pd.DataFrame()
        self.report: Path | None = None

        # toolbar
        self.title = _label(t("New signals"), "h1")
        self.meta = _label("", "muted")
        # One control, one meaning: the window you are working in. Pressing «Update data» downloads
        # it, and the list shows it. There used to be two day values — this one filtering the list
        # and a hidden setting driving the download — so the header could say 30 while the control
        # said 15, and nobody could tell which number meant what.
        self.days = QSpinBox()
        self.days.setRange(1, 365)
        self.days.setValue(data.read_settings(self.settings_path).data.scan_days)
        self.days.setSuffix(t(" days"))
        self.days.setAccessibleName(t("The window: days to download and to show"))
        self.days.setToolTip(t("How many days «Update data» downloads, and how many the list shows. "
                               "Changing it alone only re-reads what is already stored."))
        self.days.valueChanged.connect(self._days_changed)
        self.cap = data.cap_combo(data.read_settings(self.settings_path).data.cap_tier, self._cap_changed)
        self.cap.setToolTip(t("Narrows what is on screen by company size. It never downloads."))
        self.variant = QComboBox()
        for v in variants(cfg):
            self.variant.addItem(variant_label(v, cfg, t), v)
        self.variant.setCurrentIndex(max(0, self.variant.findData(DEFAULT_VARIANT)))
        self.variant.setAccessibleName(t("Outcome profile for the evidence"))
        self.variant.setToolTip(t("Which profile the evidence and the contract are shown for. It "
                                  "never downloads."))
        self.variant.currentIndexChanged.connect(lambda _: self._show_selected(self.list.currentItem()))
        self.scan_btn = QPushButton(t("Update data"))
        self.scan_btn.setObjectName("primary")
        self.scan_btn.clicked.connect(self.start_scan)
        self.cancel_btn = QPushButton(t("Cancel"))
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
        for w in (muted(t("Profile")), self.variant, muted(t("Size")), self.cap, self.days,
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
        self.source_btn = QPushButton(t("Open Settings"))
        self.source_btn.clicked.connect(self.open_settings.emit)
        self.research_btn = QPushButton(t("Use public web sources"))
        self.research_btn.setToolTip(t("Yahoo / Stooq, for your personal research only, while you have "
                                       "no broker account connected."))
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
        self.filter.setPlaceholderText(t("Filter by ticker"))
        self.filter.setClearButtonEnabled(True)
        self.filter.setAccessibleName(t("Filter the events by ticker"))
        self.filter.textChanged.connect(self._apply_filter)
        self.count = _label("", "label")
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(self.filter, 1)
        head.addWidget(self.count)
        self.list = QListWidget()
        self.list.setAccessibleName(t("New events"))
        self.list.setUniformItemSizes(False)
        self.list.currentItemChanged.connect(self._show_selected)
        self.empty = muted(t("No search yet. Press «Update data»: the first time it downloads the SEC "
                             "Form 4 filings of those days and can take several minutes. Everything is "
                             "cached."))
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
        b.addWidget(_label(t("Evidence"), "h2"))
        b.addWidget(self.evidence_text)
        b.addWidget(self.outcome)
        b.addWidget(self.legend)
        self.similar = muted("")
        self.rules_text = _label("", "body", wrap=True)
        self.context = muted("")
        self.preview_btn = QPushButton(t("Preview on Schwab"))
        self.preview_btn.setObjectName("primary")
        self.practice_btn = QPushButton(t("Add to practice"))
        self.practice_btn.clicked.connect(self.add_to_practice)
        self.preview_btn.setEnabled(False)
        self.preview_btn.setToolTip(t("Needs an active Schwab session: the preview comes from the broker."))
        for w in (_label(t("REFERENCE TRADE"), "label"), self.profile, self.contract, box, self.similar,
                  _label(t("VALIDATED RULES"), "label"), self.rules_text,
                  _label(t("CONTEXT (DOES NOT TRIGGER SIGNALS)"), "label"), self.context):
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
        self.honesty = muted("")
        outer.addWidget(self.honesty)
        outer.addWidget(muted(t(DISCLAIMER)))

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

    def _days_changed(self, days: int) -> None:
        """Remember the window and re-read the list. It does not download: that is the button."""
        cfg = data.read_settings(self.settings_path)
        if cfg.data.scan_days != days:
            cfg.data.scan_days = days
            data.write_settings(cfg, self.settings_path)
        self.apply_filters()

    def refresh_days(self) -> None:
        """Follow the window when it is changed from the Settings screen instead."""
        window = data.read_settings(self.settings_path).data.scan_days
        if window != self.days.value():
            self.days.blockSignals(True)
            self.days.setValue(window)
            self.days.blockSignals(False)
            self.apply_filters()

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
            ok, why = source_ready(data.read_settings(self.settings_path).data.price_source,
                                   translate=t)
        except Exception as e:
            ok, why = False, t("Could not check the price source: {error}", error=e)
        self.banner.setVisible(not ok)
        d = data.read_settings(self.settings_path).data
        if not self.auto.isActive():
            self.scan_btn.setText(t("Update data"))
        elif self.in_refresh_window():
            self.scan_btn.setText(t("Update data · automatic every {minutes} min",
                                    minutes=d.auto_refresh_minutes))
        else:
            self.scan_btn.setText(t("Update data · automatic paused"))
            self.scan_btn.setToolTip(t("Outside the {start}–{end} New York window. You can still press it.",
                                       start=d.auto_refresh_from, end=d.auto_refresh_to))
        self.source_msg.setText(t("{reason} Without prices the search cannot start.", reason=why))
        self.scan_btn.setEnabled(ok and self.proc is None)
        self.scan_btn.setToolTip("" if ok else why)

    def refresh(self) -> None:
        self.refresh_auto()
        self.honesty.setText(data.honesty_line(self.reports_dir))
        self.report = latest_history_report(self.reports_dir)
        self.history, self.rules = load_history(self.report) if self.report else (pd.DataFrame(), pd.DataFrame())
        self.scan = load_scan(self.scan_dir)
        self.list.clear()
        has = self.stored_events > 0
        self.empty.setVisible(not has)
        self.list.setVisible(has)
        if has or self.scan:
            span = (f"{fmt_date(self.scan['since'], False)} → {fmt_date(self.scan['end'])}"
                    if self.scan and self.scan.get("since") else "")
            src = (t("evidence from {name}", name=self.report.name) if self.report
                   else t("no report with events for the evidence"))
            self.meta.setText(t("Search {span} · {source}", span=span, source=src))
            if not has:
                self.empty.setText(t("No new event in those days. Try more days."))
        else:
            self.meta.setText(t("No search yet"))
        self.filter.setEnabled(has)
        self.apply_filters()

    # ------------------------------------------------------------------ the stored events

    @property
    def db(self):
        """The shared market database, opened read-only and lazily. Signals only reads: the scan
        subprocess is what writes."""
        if self._db is None:
            from miratrade import store

            try:
                self._db = store.connect(read_only=True)
            except Exception:
                # Retried next time rather than remembered as broken. A failure here is usually
                # momentary — the database was being written to, or a scan had not created it yet —
                # and latching on the first one left the screen empty until the app was restarted.
                return None
        return self._db

    @property
    def stored_events(self) -> int:
        db = self.db
        if db is None:
            return 0
        try:
            return int(db.execute("SELECT count(*) AS n FROM events").fetchone()["n"])
        except Exception:
            return 0

    def reports_before(self, ticker: str, contract: dict | None):
        """The earnings date this contract would have to sit through, or ``None``.

        ``None`` also covers "no calendar downloaded", which is not the same as "no report due" — so
        the absence of a warning is not a promise. Running `miratrade earnings update` is what turns
        silence into an answer.
        """
        from datetime import date as _date

        from miratrade.data.earnings import crosses_earnings

        db = self.db
        if db is None or not contract or contract.get("expiry") is None:
            return None
        try:
            return crosses_earnings(db, ticker, _date.today(),
                                   pd.Timestamp(contract["expiry"]).date())
        except Exception:
            return None

    def tradeable(self, ticker: str, contract: dict | None):
        """Whether the quotes make this contract usable, from whatever the chain capture stored.

        With no stored chain it falls back to the share's own liquidity, which is a weaker statement
        and says so. Both are reported even when they pass, because "checked and fine" and "never
        checked" must not look the same on screen.
        """
        from miratrade.liquidity import check_stored, underlying_liquidity

        if not contract or contract.get("expiry") is None:
            return None
        db = self.db
        try:
            if db is not None:
                verdict = check_stored(db, ticker, contract["expiry"], contract["strike"],
                                       target_pct=contract.get("target_pct", 0.0), cfg=self.cfg)
                if verdict.measured:
                    return verdict
            return underlying_liquidity(self.bars(ticker), self.cfg)
        except Exception:
            return None

    def bars(self, ticker: str) -> pd.DataFrame:
        """The daily bars for one ticker, from the store.

        The store holds every bar ever downloaded, not just the ones the last scan happened to fetch,
        so a chart is drawn for a ticker whichever scan first brought it in.
        """
        from miratrade import store

        db = self.db
        if db is None:
            return pd.DataFrame()
        try:
            return store.prices(db, [ticker]).get(ticker, pd.DataFrame())
        except Exception:
            return pd.DataFrame()

    def reopen_db(self) -> None:
        """After a scan the database has new rows; a read-only connection in WAL mode may still be
        looking at the snapshot it opened with, so it is dropped and taken again."""
        if self._db:
            try:
                self._db.close()
            except Exception:
                pass
        self._db = None

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
        """Window, size and ticker are views over what was downloaded, never a reason to fetch.

        They are applied in SQL: with tens of thousands of events stored, narrowing in the database
        is what keeps changing a dropdown instant instead of re-reading and re-filtering a file.
        """
        db = self.db
        if db is None:
            return
        tier = self.cap.currentData() or "all"
        try:
            shown = load_events(db, days=self.days.value(), cap_tier=tier,
                                end=self.scan.get("end") if self.scan else None)
            sized = int(db.execute("SELECT count(*) AS n FROM events "
                                   "WHERE mkt_cap IS NOT NULL").fetchone()["n"])
        except Exception:
            shown, sized = empty_events(), 0
        # Events downloaded before the size filter existed have no market capitalisation, so every
        # tier would empty the list in silence.
        sizeless = tier != "all" and sized == 0
        self._fill_list(shown)
        if sizeless and self.stored_events:
            self.empty.setText(t("This download predates the size filter and did not save the companies' "
                                 "market capitalisation. Press «Update data», or choose «All» under Size."))
            self.empty.setVisible(True)
        have = stored_days(db)
        asking = self.days.value()
        notes = []
        if asking > have:
            notes.append(t("Only {days} days downloaded; press «Update data» to bring more.", days=have))
        if tier != "all" and not sizeless:
            notes.append(t("Filtering by size: {tier}.", tier=self.cap.currentText()))
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
        self.count.setText("" if not total else t("{shown} OF {total}", shown=shown, total=total)
                           if needle else t("{count} EVENTS", count=total))
        if total:
            self.empty.setText(t("No event matching «{text}».", text=self.filter.text().strip()))
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
        self.profile.setText(variant_label(v, self.cfg, t))
        if item is None:
            self._contract = None
            self.practice_btn.setEnabled(False)
            self.contract.set_contract("", None, t("Pick an event."))
            for w in (self.ticker, self.price, self.change, self.evidence_text, self.legend, self.similar,
                      self.rules_text, self.context):
                w.setText("")
            self.outcome.set(0, 0, 0)
            self.chart.set_data(None)
            return
        ev = item.data(Qt.UserRole)
        ticker = ev["ticker"]
        prices = self.bars(ticker)
        self.ticker.setText(ticker)
        if len(prices) >= 2:
            last, prev = prices["close"].iat[-1], prices["close"].iat[-2]
            self.price.setText(f"{fmt_num(last)} $")
            ch = last / prev - 1
            self.change.setText(f"{fmt_num(ch * 100, 1, sign=True)} %")
            self.change.setStyleSheet(f"color: {theme.UP if ch >= 0 else theme.DOWN}")
        contract = contract_for(prices, ev["signal_date"], v, self.cfg) if len(prices) else None
        self._contract = contract
        self.practice_btn.setEnabled(contract is not None)
        self.contract.set_contract(ticker, contract, "" if v.startswith("call") else
                                   t("This profile buys the shares, not an option."),
                                   reports=self.reports_before(ticker, contract),
                                   tradeable=self.tradeable(ticker, contract))
        kind = next((k for k in EVENT_TYPES if ev.get(k)), "event:insider_buy")
        color, shape, _ = theme.EVENT_STYLE[kind]
        self.chart.set_data(prices, ev["signal_date"], color, shape)

        e = evidence(ev, self.history, v, self.rules)
        self.evidence_text.setText(e.say(t, fmt_num) if self.report else
                                   t("There is no report with events: run an analysis under Reports to "
                                     "have evidence."))
        self.outcome.set(e.target, e.stop, e.neither)
        self.legend.setText(t("green: target · coral: stop · grey: neither") if e.n else "")
        narrowed = [t(CONDITION_LABELS[c]) if c in CONDITION_LABELS else c for c in e.similar_to]
        self.similar.setText((t("Similar = same kind of event")
                              + (", " + ", ".join(narrowed) if narrowed else "") + ".") if e.n else "")
        self.rules_text.setText(", ".join(e.rules) if e.rules else
                                t("None yet: the analysis has not confirmed any rule for this profile. "
                                  "Treat the evidence as history, not as a forecast."))
        ctx = [label for c, label in CONTEXT_LABELS.items() if ev.get(c) is True or ev.get(c) == 1]
        self.context.setText("\n".join(f"• {t(c)}" for c in ctx) or t("Nothing remarkable."))

    def add_to_practice(self) -> None:
        """Open the contract on screen as a paper position, sized by the risk settings."""
        from miratrade.practice import PRACTICE_PATH, account_equity, load, open_trade, save

        item = self.list.currentItem()
        contract = self._contract
        if item is None or contract is None:
            QMessageBox.information(self, t("Practice"), t("Pick an event with a contract to add it."))
            return
        ev = item.data(Qt.UserRole)
        trades = load(PRACTICE_PATH)
        cfg = data.read_settings(self.settings_path)
        broker = data.quote_broker(self.settings_path) if cfg.risk.size_on_balance else None
        equity, _source = account_equity(broker, cfg=cfg)
        try:
            trade = open_trade(
                trades, ticker=ev["ticker"], kind="call", entry=contract["premium"],
                stop=contract["stop"], target=contract["target"],
                equity=equity, note=event_note(ev)[:120],
                strike=contract["strike"], expiry=str(contract["expiry"].date()), iv=contract["iv"], cfg=cfg)
        except ValueError as e:
            QMessageBox.warning(self, t("Practice"), t(str(e)))
            return
        save(trades, PRACTICE_PATH)
        self.practice_added.emit()
        from miratrade.app.pages.practice import trade_label

        QMessageBox.information(
            self, t("Practice"),
            t("Added: {quantity} × {label}", quantity=trade.quantity, label=trade_label(trade)) + "\n\n"
            + t("Cost {cost} $ · risk to the stop {risk} $.", cost=f"{trade.cost:,.0f}",
                risk=f"{trade.risk:,.0f}") + "\n"
            + t("No real money; you will see it on the Practice screen."))

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
        window = self.days.value()               # the control on screen is the window, full stop
        self.meta.setText(t("Downloading the last {days} days…", days=window))
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
            if self._owns_db:
                self.reopen_db()             # the scan wrote rows this connection cannot see
            self.refresh()
        else:
            self.meta.setText(t("The search ended with an error (code {code}). Check the log.", code=code))

    def cancel_scan(self) -> None:
        if self.proc is not None:
            self.proc.kill()
            self.meta.setText(t("Cancelled. What was downloaded is kept."))
