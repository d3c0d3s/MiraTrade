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

    from miratrade.app.window import MainWindow

    app.setStyleSheet(QSS)
    window = MainWindow()
    window.show()
    screen.finish(window)
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
