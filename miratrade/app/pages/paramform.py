"""The settings dialog a screen opens to change what it looks for — the shape of a TradingView
indicator's settings.

What the fields are and what they mean is :mod:`miratrade.params`; this is only how they are drawn.
The three things worth knowing about the drawing:

* **A field that differs from the default is marked**, and says what the default was. Looking at a
  form and not knowing which of nineteen numbers somebody moved is how a result becomes impossible
  to reproduce.
* **Nothing is saved until Save**, and Cancel really is a cancel. A form that writes as you type
  turns a stray scroll wheel over a spin box into a change to the rules.
* **The attempt count is on the form, not hidden in a report.** It is shown at the moment a person
  is about to try another configuration, because that is the moment it means something. See
  :mod:`miratrade.attempts` for why.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from miratrade import params, prefs
from miratrade.app import theme
from miratrade.i18n import t
from miratrade.app.widgets import muted


def _editor(field: params.Field, value: Any) -> QWidget:
    """One control for one setting, of the type the setting actually is."""
    if field.kind == "bool":
        box = QCheckBox()
        box.setChecked(bool(value))
        return box
    if field.kind == "choice":
        box = QComboBox()
        for key, label in field.choices:
            box.addItem(t(label), key)
        box.setCurrentIndex(max(0, box.findData(value)))
        return box
    if field.kind == "text":
        line = QLineEdit(str(value or ""))
        return line
    if field.kind == "integer":
        box = QSpinBox()
        box.setRange(int(field.low), int(min(field.high, 2_147_483_647)))
        box.setSingleStep(max(1, int(field.step)))
        box.setValue(int(value))
        box.setSuffix(t(field.suffix) if field.suffix else "")
        return box
    box = QDoubleSpinBox()
    box.setRange(float(field.low), float(field.high))
    box.setDecimals(field.decimals)
    box.setSingleStep(float(field.step))
    # Money reads better grouped, and the numbers here run to eight figures.
    box.setGroupSeparatorShown(field.kind == "money")
    box.setValue(float(value))
    box.setSuffix(t(field.suffix) if field.suffix else (" $" if field.kind == "money" else ""))
    return box


def _value(field: params.Field, widget: QWidget) -> Any:
    if field.kind == "bool":
        return widget.isChecked()
    if field.kind == "choice":
        return widget.currentData()
    if field.kind == "text":
        return widget.text().strip()
    if field.kind == "integer":
        return int(widget.value())
    return float(widget.value())


class ParamForm(QDialog):
    """Change the settings of one group of screens. Nothing is written until Save is pressed."""

    saved = Signal()

    def __init__(self, groups, db, title: str = "Settings", kind: str = "search", parent=None):
        super().__init__(parent)
        self.setWindowTitle(t(title))
        self.setObjectName("page")
        self.setMinimumSize(620, 620)
        self.groups = tuple(groups)
        self.db = db
        self.kind = kind
        self.editors: dict[tuple[str, str], QWidget] = {}
        self.marks: dict[tuple[str, str], QLabel] = {}

        cfg, _unknown = prefs.read(db)
        touched = prefs.changed(db)

        inner = QVBoxLayout()
        inner.setSpacing(14)
        for group in self.groups:
            box = QGroupBox(t(group.title))
            layout = QVBoxLayout(box)
            layout.setSpacing(8)
            note = muted(t(group.note))
            note.setWordWrap(True)
            layout.addWidget(note)
            form = QFormLayout()
            form.setSpacing(8)
            form.setLabelAlignment(Qt.AlignLeft)
            form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
            for field in group.fields:
                pair = (field.section, field.key)
                widget = _editor(field, getattr(getattr(cfg, field.section), field.key))
                widget.setToolTip(t(field.help))
                self.editors[pair] = widget
                mark = QLabel("")
                mark.setObjectName("muted")
                self.marks[pair] = mark
                self._mark(field, pair in touched)
                line = QHBoxLayout()
                line.setSpacing(8)
                line.addWidget(widget)
                line.addWidget(mark)
                line.addStretch(1)
                holder = QWidget()
                holder.setLayout(line)
                label = QLabel(t(field.label))
                label.setToolTip(t(field.help))
                form.addRow(label, holder)
                explain = muted(t(field.help))
                explain.setWordWrap(True)
                form.addRow("", explain)
            layout.addLayout(form)
            inner.addWidget(box)
        inner.addStretch(1)
        page = QWidget()
        page.setLayout(inner)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)

        # The count of how many different configurations a result has been chosen from. On the form
        # rather than in a report, because this is the moment it changes what someone does.
        self.attempts_line = QLabel("")
        self.attempts_line.setWordWrap(True)
        self.forget_btn = QPushButton(t("Start the count again"))
        self.forget_btn.setToolTip(t("Use it when you genuinely begin a new line of research. It "
                                     "is a deliberate act with a date on it, not a way to make the "
                                     "warning go away."))
        self.forget_btn.clicked.connect(self._forget)
        self.refresh_attempts()

        self.reset_btn = QPushButton(t("Back to defaults"))
        self.reset_btn.clicked.connect(self._reset)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(t("Save"))
        buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.Cancel).setText(t("Cancel"))
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        buttons.addButton(self.reset_btn, QDialogButtonBox.ResetRole)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)
        root.addWidget(scroll, 1)
        foot = QHBoxLayout()
        foot.addWidget(self.attempts_line, 1)
        foot.addWidget(self.forget_btn)
        root.addLayout(foot)
        root.addWidget(buttons)

    # ------------------------------------------------------------------ the attempt count

    def refresh_attempts(self) -> None:
        from miratrade import attempts

        n = attempts.count(self.db, self.kind)
        self.attempts_line.setText(attempts.say(n, t))
        self.attempts_line.setStyleSheet(f"color: {theme.DOWN}" if n > 5 else "")
        self.forget_btn.setEnabled(n > 0)

    def _forget(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from miratrade import attempts

        if QMessageBox.question(
                self, t("Start the count again"),
                t("This forgets the {count} configurations tried so far. Do it when you are "
                  "genuinely starting a new line of research — not to make a result look better "
                  "than it is.", count=attempts.count(self.db, self.kind))) != QMessageBox.Yes:
            return
        attempts.forget(self.db, self.kind)
        self.refresh_attempts()

    # ------------------------------------------------------------------ marks and saving

    def _mark(self, field: params.Field, changed: bool) -> None:
        label = self.marks[(field.section, field.key)]
        if changed:
            label.setText(t("changed · default {value}", value=_pretty(field.default())))
            label.setStyleSheet(f"color: {theme.ACCENT}")
        else:
            label.setText("")

    def values(self) -> dict[tuple[str, str], Any]:
        return {pair: _value(_field_of(self.groups, pair), widget)
                for pair, widget in self.editors.items()}

    def save(self) -> None:
        """Write only what actually changed, one row each."""
        cfg, _unknown = prefs.read(self.db)
        written = 0
        for pair, value in self.values().items():
            section, key = pair
            if getattr(getattr(cfg, section), key) != value:
                prefs.put(self.db, section, key, value)
                written += 1
        if written:
            prefs.save_json(prefs.load(db=self.db))      # keep the readable mirror in step
        self.saved.emit()
        self.accept()

    def _reset(self) -> None:
        for pair, widget in self.editors.items():
            field = _field_of(self.groups, pair)
            widget.blockSignals(True)
            if field.kind == "bool":
                widget.setChecked(bool(field.default()))
            elif field.kind == "choice":
                widget.setCurrentIndex(max(0, widget.findData(field.default())))
            elif field.kind == "text":
                widget.setText(str(field.default()))
            elif field.kind == "integer":
                widget.setValue(int(field.default()))
            else:
                widget.setValue(float(field.default()))
            widget.blockSignals(False)
            self._mark(field, False)
        # The stored rows go too, so a default that changes in a later version is followed rather
        # than frozen at today's value.
        for section in {s for s, _k in self.editors}:
            prefs.reset(self.db, section)


def _field_of(groups, pair) -> params.Field:
    for group in groups:
        for field in group.fields:
            if (field.section, field.key) == pair:
                return field
    raise KeyError(pair)


def _pretty(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value:,}" if isinstance(value, (int, float)) else str(value)
