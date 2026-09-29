"""Interface language: English is the source, other languages are lookups over it."""
import pytest

from miratrade.app.i18n import CATALOGS, DEFAULT, LANGUAGES, ES, language, missing, set_language, t


@pytest.fixture(autouse=True)
def _restore():
    before = language()
    yield
    set_language(before)


def test_english_is_the_source_and_needs_no_catalog():
    set_language("en")
    assert language() == "en" == DEFAULT
    assert t("New signals") == "New signals"
    assert t("Profile") == "Profile"


def test_spanish_translates_and_falls_back_to_english():
    set_language("es")
    assert t("New signals") == "Señales nuevas"
    assert t("Stop everything") == "Detener todo"
    assert t("a string nobody translated") == "a string nobody translated"


def test_placeholders_are_filled_in_either_language():
    set_language("en")
    assert t("{count} EVENTS", count=112) == "112 EVENTS"
    set_language("es")
    assert t("{count} EVENTS", count=112) == "112 EVENTOS"
    assert t("{shown} OF {total}", shown=3, total=112) == "3 DE 112"


def test_an_unknown_language_falls_back_instead_of_breaking():
    assert set_language("klingon") == DEFAULT
    assert t("New signals") == "New signals"
    assert set_language("") == DEFAULT


def test_every_catalog_covers_the_english_strings_and_keeps_its_placeholders():
    for code, catalog in CATALOGS.items():
        assert code in LANGUAGES
        assert missing(code) == [], f"{code} is missing translations"
        for english, translated in catalog.items():
            fields = set(_placeholders(english))
            assert set(_placeholders(translated)) == fields, f"{code}: {english!r} lost a placeholder"


def _placeholders(text: str) -> list[str]:
    import string

    return [name for _, name, _, _ in string.Formatter().parse(text) if name]


def test_every_string_the_screens_translate_is_in_the_catalog():
    """The literals the screens hand to ``t()``, read straight out of the source. Without this a
    string converted to English but never translated shows in English inside a Spanish app."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "miratrade" / "app"
    found, missing_here = 0, []
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            first = node.args[0]
            if name != "t" or not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            found += 1
            if first.value not in ES:
                missing_here.append(f"{path.name}: {first.value!r}")
    assert found > 100, "the source scan found almost nothing; the check would pass by accident"
    assert missing_here == []


def test_the_labels_that_reach_the_screens_from_a_dictionary_are_translated():
    """Event kinds, conditions, sizes, price sources and column headings are looked up by key, so
    the source scan above cannot see them. They still have to be in the catalog."""
    from miratrade.app.pages.practice import DONE_COLUMNS, EQUITY_SOURCE, OPEN_COLUMNS
    from miratrade.app.pages.reports import RULE_HEADERS
    from miratrade.app.pages.signals import CONTEXT_LABELS, DISCLAIMER
    from miratrade.config import CAP_TIERS
    from miratrade.data.prices import SOURCES
    from miratrade.practice import REASONS
    from miratrade.scan import CONDITION_LABELS, EVENT_LABELS
    from miratrade import scanner

    # the Scanner's sources, their columns, their notes and every filter choice it offers
    scanner_labels = [s.label for s in scanner.SOURCES]
    scanner_labels += [s.note for s in scanner.SOURCES if s.note]
    scanner_labels += [c.label for s in scanner.SOURCES for c in s.columns]
    for choices in (scanner.CODES, scanner.ROLES, scanner.TRADE_TYPES, scanner.CHAMBERS,
                    scanner.STAKE_KINDS, scanner.OPTION_TYPES):
        scanner_labels += [label for _value, label in choices]

    labels = (scanner_labels + [DISCLAIMER] + OPEN_COLUMNS + DONE_COLUMNS
              + list(EQUITY_SOURCE.values()) + list(RULE_HEADERS.values())
              + list(CONTEXT_LABELS.values()) + list(CONDITION_LABELS.values())
              + list(EVENT_LABELS.values()) + list(REASONS.values()) + list(SOURCES.values())
              + [label for _low, _high, label in CAP_TIERS.values()])
    assert [s for s in labels if s not in ES] == []


def test_a_sentence_composed_in_the_domain_is_translated_when_the_screen_shows_it():
    """The domain writes its sentences as an English template plus values; the console gets the
    English and the screen the translation, from the very same pieces."""
    from miratrade.messages import note
    from miratrade.scan import Evidence, variant_label

    parts = [("{count} insiders bought {amount}", {"count": 3, "amount": 1_400_000.0})]
    assert note(parts) == "3 insiders bought $1.4M"

    set_language("es")
    assert note(parts, t) == "3 directivos compraron $1.4M"
    assert note(parts, t, amount=lambda v: f"{v / 1e6:.1f} M$") == "3 directivos compraron 1.4 M$"
    assert note([], t) == "evento nuevo"

    assert variant_label("call45_40") == "Call 45 days · +40 % / −25 %"
    assert variant_label("call45_40", translate=t) == "Call 45 días · +40 % / −25 %"

    e = Evidence("call45_40", n=40, target=0.5, stop=0.3, neither=0.2, mean_return=0.12)
    assert "similar events" in e.sentence and "eventos parecidos" in e.say(t)


def test_the_app_opens_in_english_and_follows_the_setting(qtbot, tmp_path, monkeypatch):
    """English is what a new install shows; choosing another language is remembered."""
    import json

    from miratrade.app import data
    from miratrade.app.pages.settings import SettingsPage

    set_language("en")
    path = tmp_path / "settings.json"
    page = SettingsPage(path)
    qtbot.addWidget(page)
    assert page.language.currentData() == "en"
    assert page.windowTitle() == "" and t("Signals") == "Signals"

    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    page.language.setCurrentIndex(page.language.findData("es"))
    page.save()
    assert json.loads(path.read_text(encoding="utf-8"))["ui"]["language"] == "es"
    assert data.read_settings(path).ui.language == "es"


def test_a_placeholder_may_be_called_text_or_source():
    """The source string is positional-only, so screens can pass fields with any name."""
    set_language("es")
    assert t("No event matching «{text}».", text="AAPL") == "Ningún evento con «AAPL»."
    assert t("{source} something", source="x") == "x something"
