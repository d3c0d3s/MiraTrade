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
