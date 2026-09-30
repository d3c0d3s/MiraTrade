"""Entry point: ``miratrade-app`` (or ``python -m miratrade.app``)."""
from __future__ import annotations

import sys


def run() -> int:
    from PySide6.QtWidgets import QApplication

    from miratrade.app.brand import app_icon, load_fonts, set_windows_app_id, splash
    from miratrade.app.theme import QSS

    set_windows_app_id()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MiraTrade")
    app.setOrganizationName("Mirandas Group")
    app.setWindowIcon(app_icon())
    load_fonts()
    screen = splash()
    screen.show()
    app.processEvents()

    from miratrade.app import data
    from miratrade.i18n import set_language
    from miratrade.app.window import MainWindow

    set_language(data.read_settings().ui.language)        # before any screen builds its labels
    app.setStyleSheet(QSS)
    window = MainWindow()
    window.show()
    screen.finish(window)
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
