"""The app's screens are written in English and translated; the app tests assert the Spanish
wording, so they pin that language and put it back afterwards. `test_i18n.py` covers the default."""
import pytest


@pytest.fixture(autouse=True)
def _spanish_interface(request):
    if "test_app.py" not in str(request.node.fspath):
        yield
        return
    from miratrade.i18n import language, set_language

    before = language()
    set_language("es")
    yield
    set_language(before)


@pytest.fixture(autouse=True)
def _never_the_real_database(tmp_path, monkeypatch):
    """Every test gets its own market database, whether it asks for one or not.

    Four separate bugs this session came from a test reaching the real store: it hung waiting on a
    lock, it failed for reasons unrelated to the test, and once it masked genuine corruption as a
    hanging test. A test that forgets to pass ``db=`` would also *write* to the user's own data.
    Making it impossible is worth more than remembering every time.
    """
    import miratrade.backup
    import miratrade.config
    import miratrade.prefs
    import miratrade.store.db

    path = tmp_path / "test-market.db"
    for module in (miratrade.config, miratrade.store.db, miratrade.backup):
        if hasattr(module, "DB_PATH"):
            monkeypatch.setattr(module, "DB_PATH", path)
    for module in (miratrade.config, miratrade.backup):
        if hasattr(module, "DATA_HOME"):
            monkeypatch.setattr(module, "DATA_HOME", tmp_path / "data-home")
    # Settings live in the database now, seeded once from this file. Left unpatched, a test would
    # read the real user's settings.json into its own store and then assert on whatever that person
    # happens to have configured — which passes on one machine and fails on the next.
    monkeypatch.setattr(miratrade.prefs, "JSON_PATH", tmp_path / "settings.json")

    # …and the same protection for anything that starts a SUBPROCESS. Patching module attributes
    # stops at the process boundary, so a test that starts a job walks straight past everything
    # above and opens the real store. That is not hypothetical: a jobs test ran a real reprocess
    # and rewrote a window of the user's events table. The environment variables cross the
    # boundary; the monkeypatched attributes do not.
    monkeypatch.setenv("MIRATRADE_DB", str(path))
    monkeypatch.setenv("MIRANDAS_DATA", str(tmp_path / "data-home"))
    monkeypatch.setenv("MIRATRADE_HOME", str(tmp_path / "app-home"))
    monkeypatch.setenv("MIRATRADE_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("MIRATRADE_REPORTS", str(tmp_path / "reports"))
    yield path
