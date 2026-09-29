"""Scanner: everything collected, as it was filed, narrowed by filters.

This screen deliberately judges nothing. It shows the rows in the shared market database and lets
them be narrowed, sorted, checked against the original document and exported. Signals turns events
into evidence and a contract; Reports validates rules over five years; the Scanner is where you go to
see what the data actually says before any of that.

Filtering runs in SQL, so changing a dropdown re-queries rather than re-reading a file: with three
quarters of a million price bars stored, that is what keeps the screen answering immediately.
"""
from __future__ import annotations

import webbrowser
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel,
                              QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from miratrade import scanner
from miratrade.app import theme
from miratrade.app.i18n import t
from miratrade.app.widgets import fit_columns, fmt_date, fmt_num, muted, table


def store_path() -> str:
    """Where the data lives, so an error names it instead of leaving it to be guessed."""
    from miratrade.config import DB_PATH

    return str(DB_PATH)

MAX_ROWS = 2000            # a table nobody scrolls to the end of; the count says what was left out


def _combo(choices, on_change, width: int = 0) -> QComboBox:
    box = QComboBox()
    for value, label in choices:
        box.addItem(t(label), value)
    if width:
        box.setMinimumWidth(width)
    box.currentIndexChanged.connect(lambda _: on_change())
    return box


class ScannerPage(QWidget):
    def __init__(self, db=None, settings_path: Path | None = None):
        super().__init__()
        self.setObjectName("page")
        self._db = db
        self._owns_db = db is None
        self.rows = pd.DataFrame()
        self.trouble = ""                    # why the database could not be read, if it could not
        self._widths_touched = False         # once a column is dragged, the widths are the reader's
        self.right_aligned: set[str] = set()
        self.sort_by: str | None = None
        self.sort_desc = True

        title = QLabel(t("Scanner"))
        title.setObjectName("h1")
        self.subtitle = muted(t("Everything collected, as it was filed. No strategy applied here."))
        self.stored = muted("")
        self.stored.setToolTip(t("Rows in the shared market database, and the days they cover."))

        # ---------------------------------------------------------------- filters
        self.source = _combo([(s.key, s.label) for s in scanner.SOURCES], self.source_changed, 190)
        self.days = QSpinBox()
        self.days.setRange(0, 3650)
        self.days.setValue(30)
        self.days.setSuffix(t(" days"))
        self.days.setSpecialValueText(t("all history"))
        self.days.setAccessibleName(t("How far back to look"))
        self.days.valueChanged.connect(self.reload)
        self.ticker = QLineEdit()
        self.ticker.setPlaceholderText(t("Ticker, or several: PFE, AAPL"))
        self.ticker.setMaximumWidth(190)
        self.ticker.textChanged.connect(self.reload)
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0, 1e9)
        self.amount.setSingleStep(50_000)
        self.amount.setDecimals(0)
        self.amount.setPrefix("≥ $")
        self.amount.setGroupSeparatorShown(True)
        self.amount.setSpecialValueText(t("any amount"))
        self.amount.setAccessibleName(t("Smallest amount to show"))
        self.amount.valueChanged.connect(self.reload)

        self.code = _combo(scanner.CODES, self.reload)
        self.role = _combo(scanner.ROLES, self.reload)
        self.plan = QCheckBox(t("Exclude 10b5-1 plans"))
        self.plan.setToolTip(t("A purchase set up months earlier by a plan is not a decision made "
                               "this week."))
        self.plan.toggled.connect(self.reload)
        self.trade_type = _combo(scanner.TRADE_TYPES, self.reload)
        self.chamber = _combo(scanner.CHAMBERS, self.reload)
        self.member = QLineEdit()
        self.member.setPlaceholderText(t("Member"))
        self.member.setMaximumWidth(170)
        self.member.textChanged.connect(self.reload)
        self.stake_kind = _combo(scanner.STAKE_KINDS, self.reload)
        self.passive = QCheckBox(t("Active stakes only"))
        self.passive.setToolTip(t("Leaves out the 13G filings index funds make mechanically."))
        self.passive.toggled.connect(self.reload)
        self.option_type = _combo(scanner.OPTION_TYPES, self.reload)
        self.text = QLineEdit()
        self.text.setPlaceholderText(t("Search a name: insider, filer, member, asset"))
        self.text.setMinimumWidth(240)
        self.text.textChanged.connect(self.reload)
        self.new_position = QCheckBox(t("New positions only"))
        self.new_position.setToolTip(t("Bought into a holding they did not have, rather than adding "
                                       "to one."))
        self.new_position.toggled.connect(self.reload)
        self.amendments = QCheckBox(t("Exclude amendments"))
        self.amendments.setToolTip(t("An /A restates an earlier filing rather than reporting "
                                     "something new."))
        self.amendments.toggled.connect(self.reload)
        self.min_volume = QSpinBox()
        self.min_volume.setRange(0, 10_000_000)
        self.min_volume.setSingleStep(100)
        self.min_volume.setGroupSeparatorShown(True)
        self.min_volume.setPrefix(t("vol ≥ "))
        self.min_volume.setSpecialValueText(t("any volume"))
        self.min_volume.valueChanged.connect(self.reload)
        self.min_oi = QSpinBox()
        self.min_oi.setRange(0, 10_000_000)
        self.min_oi.setSingleStep(100)
        self.min_oi.setGroupSeparatorShown(True)
        self.min_oi.setPrefix(t("OI ≥ "))
        self.min_oi.setSpecialValueText(t("any open interest"))
        self.min_oi.valueChanged.connect(self.reload)

        # every filter widget, by the name of the filter that owns it, so a source shows only its own
        self.widgets = {"dates": [self.days], "ticker": [self.ticker], "amount": [self.amount],
                        "code": [self.code], "role": [self.role], "plan": [self.plan],
                        "trade_type": [self.trade_type], "chamber": [self.chamber],
                        "member": [self.member], "stake_kind": [self.stake_kind],
                        "passive": [self.passive], "option_type": [self.option_type],
                        "text": [self.text], "new_position": [self.new_position],
                        "amendments": [self.amendments],
                        "contract_volume": [self.min_volume, self.min_oi]}

        # Two rows: what to look at on top, how to narrow it underneath. One row of a dozen controls
        # pushes the last of them off the screen at any window a person actually uses.
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.source)
        for w in (self.days, self.ticker, self.text):
            top.addWidget(w)
        top.addStretch(1)
        self.reset_btn = QPushButton(t("Clear filters"))
        self.reset_btn.clicked.connect(self.reset_filters)
        self.fit_btn = QPushButton(t("Fit columns"))
        self.fit_btn.setToolTip(t("Back to widths that fit the contents. Drag a heading to set your "
                                  "own; they are kept until you change source."))
        self.fit_btn.clicked.connect(self.fit_columns_now)
        top.addWidget(self.reset_btn)
        top.addWidget(self.fit_btn)

        narrow = QHBoxLayout()
        narrow.setSpacing(8)
        for name, group in self.widgets.items():
            if name in ("dates", "ticker", "text"):
                continue                      # already on the top row
            for w in group:
                narrow.addWidget(w)
        narrow.addStretch(1)
        rows = QVBoxLayout()
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(8)
        for layout in (top, narrow):
            holder = QWidget()
            holder.setLayout(layout)
            rows.addWidget(holder)
        bar_w = QWidget()
        bar_w.setLayout(rows)

        # ---------------------------------------------------------------- table and footer
        self.note = muted("")
        self.table = table(resizable=True)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().sectionClicked.connect(self.sort_column)
        self.table.horizontalHeader().sectionResized.connect(self._width_changed)
        self.table.doubleClicked.connect(lambda _: self.open_filing())

        self.count = QLabel()
        self.count.setObjectName("mono")
        self.filing_btn = QPushButton(t("Open the original filing"))
        self.filing_btn.setToolTip(t("Opens the document this row came from, at the SEC or the "
                                     "House of Representatives."))
        self.filing_btn.clicked.connect(self.open_filing)
        self.export_btn = QPushButton(t("Export…"))
        self.export_btn.setToolTip(t("Saves exactly the rows shown, with the filters applied."))
        self.export_btn.clicked.connect(self.export)
        foot = QHBoxLayout()
        foot.addWidget(self.count, 1)
        foot.addWidget(self.filing_btn)
        foot.addWidget(self.export_btn)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(title)
        titles.addWidget(self.subtitle)
        head.addLayout(titles)
        head.addStretch(1)
        head.addWidget(self.stored)

        body = QVBoxLayout(self)
        body.setContentsMargins(24, 20, 24, 20)
        body.setSpacing(12)
        body.addLayout(head)
        body.addWidget(bar_w)
        body.addWidget(self.note)
        body.addWidget(self.table, 1)
        body.addLayout(foot)

        self.source_changed()

    # ------------------------------------------------------------------ data

    @property
    def db(self):
        """The market database, opened read-only and lazily; ``None`` when there is nothing to read.

        It is retried on every access rather than remembered as broken. A failure here is usually
        momentary — the database was being written to, or a download had not created it yet — and
        latching on the first one left the screen empty until the app was restarted, with the data
        sitting there perfectly readable the whole time.
        """
        if self._db is None:
            from miratrade import store

            try:
                self._db = store.connect(read_only=True)
                self.trouble = ""
            except store.NoDatabase:
                self.trouble = ""            # nothing downloaded yet is a state, not a failure:
                return None                  # the screen says what to press, in the user's language
            except Exception as e:                   # locked, mid-checkpoint, unreadable: say so,
                self.trouble = str(e)                # and try again the next time round
                return None
        return self._db

    @property
    def current(self) -> scanner.Source:
        return scanner.BY_KEY[self.source.currentData()]

    def filters(self) -> scanner.Filters:
        return scanner.Filters(
            days=self.days.value(), ticker=self.ticker.text(), code=self.code.currentData(),
            role=self.role.currentData(), exclude_plan=self.plan.isChecked(),
            trade_type=self.trade_type.currentData(), chamber=self.chamber.currentData(),
            member=self.member.text(), stake_kind=self.stake_kind.currentData(),
            exclude_passive=self.passive.isChecked(), option_type=self.option_type.currentData(),
            min_amount=self.amount.value(), text=self.text.text(),
            new_position=self.new_position.isChecked(),
            exclude_amendments=self.amendments.isChecked(),
            min_volume=self.min_volume.value(), min_open_interest=self.min_oi.value())

    def source_changed(self) -> None:
        """Show the filters this source understands and hide the rest, so nothing on screen is a
        control that would do nothing."""
        understands = set(self.current.filters)
        for name, group in self.widgets.items():
            for w in group:
                w.setVisible(name in understands)
        self._widths_touched = False          # a different source is a different table
        self.note.setText(t(self.current.note) if self.current.note else "")
        if self.current.key == "flow":
            self.note.setText(self.note.text() + self.flow_gaps())
        self.sort_by = None
        self.reload()

    def flow_gaps(self) -> str:
        """A warning when the daily capture skipped a session.

        It belongs on this screen because the loss is invisible in the rows themselves — a missing day
        simply is not there. Open interest catches up on its own; the volume of a session is only
        readable while that session is the last one, so a gap is permanent and worth saying out loud.
        """
        from miratrade.data.options import session_date
        from miratrade.flow import missed_sessions

        db = self.db
        if db is None:
            return ""
        try:
            missed = missed_sessions(db, session_date())
        except Exception:
            return ""
        if not missed:
            return ""
        return "\n" + t("No capture for {days} — that volume cannot be recovered. Run "
                        "«miratrade flow status».",
                        days=", ".join(fmt_date(d) for d in missed[:6]))

    def reload(self) -> None:
        source = self.current
        db = self.db
        if db is None:                               # nothing to read: checked before it is used,
            self.nothing_to_show(                    # or pandas reports it as a NoneType error
                t("Nothing downloaded yet. Press «Update data» under Signals, or run "
                  "`miratrade scan`. It is stored in {path}.", path=store_path())
                if not self.trouble else
                t("Could not read {path}: {error}", path=store_path(), error=self.trouble))
            return
        try:
            f = self.filters()
            self.rows = scanner.run(db, source, f, MAX_ROWS)
            stored = scanner.total(db, source, f)
        except Exception as e:                       # a database this app cannot read
            self.nothing_to_show(t("Could not read {path}: {error}", path=store_path(), error=e))
            return
        self.apply_sort()
        if not len(self.rows):
            self.count.setText(t("Nothing collected for these filters yet. The Reports screen "
                                 "downloads Form 4 filings and prices; `miratrade congress trades` "
                                 "brings congressional disclosures."))
        elif stored > len(self.rows):
            self.count.setText(t("{shown} of {total} rows — narrow the filters to see the rest",
                                 shown=fmt_num(len(self.rows), 0), total=fmt_num(stored, 0)))
        else:
            self.count.setText(t("{total} rows", total=fmt_num(stored, 0)))
        self.filing_btn.setEnabled(bool(len(self.rows)) and self._link_column() is not None)
        self.export_btn.setEnabled(bool(len(self.rows)))
        self.stored.setText(" · ".join(t("{label}: {count}", label=t(label), count=fmt_num(n, 0))
                                       for label, n, _a, _b in scanner.summary(self.db) if n))

    def nothing_to_show(self, why: str) -> None:
        """Empty the table and say why in one place, so no branch can forget half of it."""
        self.rows = pd.DataFrame()
        self.table.model().set(self.rows)
        self.count.setText(why)
        self.filing_btn.setEnabled(False)
        self.export_btn.setEnabled(False)

    def apply_sort(self) -> None:
        rows = self.rows
        if self.sort_by and self.sort_by in rows.columns:
            rows = rows.sort_values(self.sort_by, ascending=not self.sort_desc, kind="stable")
        shown = self._for_display(rows)
        self.table.model().right = self.right_aligned
        self.table.model().set(shown)
        if not self._widths_touched:
            fit_columns(self.table)

    def reset_filters(self) -> None:
        """Back to showing everything this source has, without changing source."""
        for w in (self.ticker, self.text):
            w.blockSignals(True)
            w.clear()
            w.blockSignals(False)
        for spin in (self.amount, self.min_volume, self.min_oi):
            spin.blockSignals(True)
            spin.setValue(0)
            spin.blockSignals(False)
        for box in (self.code, self.role, self.trade_type, self.chamber, self.stake_kind,
                    self.option_type):
            box.blockSignals(True)
            box.setCurrentIndex(0)
            box.blockSignals(False)
        for check in (self.plan, self.passive, self.new_position, self.amendments):
            check.blockSignals(True)
            check.setChecked(False)
            check.blockSignals(False)
        self.member.blockSignals(True)
        self.member.clear()
        self.member.blockSignals(False)
        self.days.setValue(30)                # the only one that fires the reload
        self.reload()

    def _width_changed(self, _index: int, _old: int, _new: int) -> None:
        """Once a column has been dragged the widths belong to the reader, and reloading the rows
        must not snatch them back."""
        if self.table.horizontalHeader().isVisible():
            self._widths_touched = True

    def fit_columns_now(self) -> None:
        """Give the automatic widths back, for when the reader wants to start over."""
        self._widths_touched = False
        fit_columns(self.table)

    def sort_column(self, index: int) -> None:
        """Clicking a heading sorts on the real values, not on the text shown."""
        if index >= len(self.current.columns):
            return
        label = self.current.columns[index].label
        self.sort_desc = not self.sort_desc if self.sort_by == label else True
        self.sort_by = label
        self.apply_sort()

    def _for_display(self, rows: pd.DataFrame) -> pd.DataFrame:
        """The table as it is shown: headings in the user's language, dates and flags written the way
        the interface writes them, and no link column — the button opens that.

        ``self.rows`` keeps the English headings, because sorting, exporting and finding the link
        column all work off the source's own labels.
        """
        out = pd.DataFrame(index=rows.index)
        self.right_aligned = set()
        for column in self.current.columns:
            if column.label not in rows.columns or column.kind == "link":
                continue
            values, heading = rows[column.label], t(column.label)
            if column.kind == "date":
                out[heading] = [fmt_date(v) if pd.notna(v) else "–" for v in values]
            elif column.kind in ("money", "number"):
                # in the user's own number format, which the table model knows nothing about;
                # a share count or a volume is a whole number, an amount has its cents
                places = 2 if column.kind == "money" else 0
                out[heading] = [fmt_num(v, places) if pd.notna(v) else "–" for v in values]
                self.right_aligned.add(heading)
            elif len(values.dropna()) and set(values.dropna().unique()) <= {0, 1}:
                out[heading] = [t("yes") if v else t("no") for v in values]
            else:
                out[heading] = values.fillna("–").replace("", "–")
        return out

    # ------------------------------------------------------------------ actions

    def _link_column(self) -> str | None:
        return next((c.label for c in self.current.columns if c.kind == "link"), None)

    def selected_row(self) -> pd.Series | None:
        index = self.table.currentIndex()
        if not index.isValid() or not len(self.rows):
            return None
        rows = self.rows
        if self.sort_by and self.sort_by in rows.columns:
            rows = rows.sort_values(self.sort_by, ascending=not self.sort_desc, kind="stable")
        return rows.iloc[index.row()] if index.row() < len(rows) else None

    def open_filing(self) -> None:
        """Open the document a row came from. Nothing about a filing has to be taken on trust."""
        column = self._link_column()
        row = self.selected_row()
        if column is None or row is None:
            QMessageBox.information(self, t("Scanner"), t("Pick a row first."))
            return
        url = scanner.filing_link(self.current, row.get(column))
        if not url:
            QMessageBox.information(self, t("Scanner"),
                                    t("This row does not say which document it came from."))
            return
        webbrowser.open(url)

    def export(self) -> None:
        """Save what is on screen, filters and all, for a spreadsheet or another program."""
        if not len(self.rows):
            return
        suggested = f"miratrade-{self.current.key}-{pd.Timestamp.now():%Y%m%d-%H%M}.csv"
        path, _chosen = QFileDialog.getSaveFileName(
            self, t("Export the rows shown"), suggested,
            t("Comma-separated values (*.csv);;JSON (*.json)"))
        if not path:
            return
        rows = self.rows.drop(columns=[c for c in (self._link_column(),) if c in self.rows.columns])
        try:
            if path.lower().endswith(".json"):
                rows.to_json(path, orient="records", date_format="iso", indent=1)
            else:
                rows.to_csv(path, index=False, encoding="utf-8-sig")   # Excel reads the accents
        except OSError as e:
            QMessageBox.warning(self, t("Scanner"), t("Could not save: {error}", error=e))
            return
        self.count.setText(t("{total} rows · saved to {path}",
                             total=fmt_num(len(rows), 0), path=path))

    def closeEvent(self, event):
        if self._owns_db and self._db is not None:
            self._db.close()
            self._db = None
        super().closeEvent(event)
