"""Entry point: ``miratrade-app`` (or ``python -m miratrade.app``)."""
from __future__ import annotations

import sys


def run() -> int:
    from PySide6.QtWidgets import QApplication

    from miratrade.app.theme import QSS
    from miratrade.app.window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MiraTrade")
    app.setStyleSheet(QSS)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
