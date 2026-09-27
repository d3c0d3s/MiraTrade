"""The app's screens are written in English and translated; the app tests assert the Spanish
wording, so they pin that language and put it back afterwards. `test_i18n.py` covers the default."""
import pytest


@pytest.fixture(autouse=True)
def _spanish_interface(request):
    if "test_app.py" not in str(request.node.fspath):
        yield
        return
    from miratrade.app.i18n import language, set_language

    before = language()
    set_language("es")
    yield
    set_language(before)
