"""Brand assets inside the app: IBM Plex fonts, the window icon, the nav symbol and the splash.

The files in ``assets/`` are exported from ``brand/fuente-diseno/export_brand.py``; the nav symbol
is drawn for the nav background (the arrow's knockout edge takes the colour it sits on).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSplashScreen, QWidget

from miratrade.app import theme

ASSETS = Path(__file__).with_name("assets")
APP_ID = "MirandasGroup.MiraTrade"


def load_fonts() -> list[str]:
    """Register the bundled IBM Plex files; returns the family names Qt now knows."""
    families: set[str] = set()
    for ttf in sorted((ASSETS / "fonts").glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(ttf))
        if fid != -1:
            families.update(QFontDatabase.applicationFontFamilies(fid))
    return sorted(families)


def app_icon() -> QIcon:
    return QIcon(str(ASSETS / "miratrade.ico"))


def set_windows_app_id() -> None:
    """Group the app under its own taskbar icon instead of python.exe's (Windows only)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except (AttributeError, OSError):
            pass


def svg_pixmap(name: str, size: QSize, background: str | None = None, ratio: float = 1.0) -> QPixmap:
    pm = QPixmap(size * ratio)
    pm.setDevicePixelRatio(ratio)
    pm.fill(QColor(background) if background else Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray((ASSETS / name).read_bytes())).render(p, QRectF(0, 0, size.width(), size.height()))
    p.end()
    return pm


def nav_brand() -> QWidget:
    """Symbol + "Mira" bold / "Trade" light blue, as in the lockup."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(10, 2, 10, 18)
    lay.setSpacing(10)
    mark = QLabel()
    mark.setPixmap(svg_pixmap("simbolo-nav.svg", QSize(30, 30), ratio=2.0))
    mark.setAccessibleName("MiraTrade")
    name = QLabel(f'<span style="font-weight:700">Mira</span>'
                  f'<span style="font-weight:300; color:{theme.ACCENT}">Trade</span>')
    name.setObjectName("brand")
    lay.addWidget(mark)
    lay.addWidget(name)
    lay.addStretch(1)
    return w


def splash() -> QSplashScreen:
    """Firma with the group endorsement on the app background, shown while the window loads."""
    w, h = 560, 300
    pm = QPixmap(QSize(w, h) * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(QColor(theme.BG))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor(theme.BORDER_2))
    p.drawRect(QRectF(0.5, 0.5, w - 1, h - 1))
    QSvgRenderer(QByteArray((ASSETS / "firma-arranque.svg").read_bytes())).render(p, QRectF(40, 87, 468, 113.4))
    p.end()
    s = QSplashScreen(pm)
    s.showMessage("Cargando…", Qt.AlignBottom | Qt.AlignHCenter, QColor(theme.TEXT_2))
    return s
