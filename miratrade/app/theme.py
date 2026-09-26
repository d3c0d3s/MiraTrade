"""Approved visual system (see the mockup): dark theme, one meaning per colour."""
from __future__ import annotations

BG = "#0B0E13"
PANEL = "#0F131A"
PANEL_2 = "#12161D"
BORDER = "#1E242E"
BORDER_2 = "#2A3240"
TEXT = "#E6EAF2"
TEXT_2 = "#9AA4B2"
ACCENT = "#6E9BFF"
PRIMARY = "#3562D1"
UP = "#00D26A"
DOWN = "#FF8A7A"
INSIDER = "#F4B740"
OPTIONS = "#B79CFF"
OWNERSHIP = "#F472B6"                   # 13D / 13G
TEXT_BODY = "#C4CCD8"
SELECTED = "#141C2E"
GRID = "#1A2029"
# Each event type: colour, shape (never colour alone) and the pill's border.
EVENT_STYLE = {"event:insider_buy": (INSIDER, "◆", "#6B5320"),
               "event:flow": (OPTIONS, "●", "#4F4470"),
               "event:13dg": (OWNERSHIP, "■", "#6B2E52")}
DANGER_BG = "#3A1614"
DANGER_BORDER = "#8C3A33"

FONT = "'IBM Plex Sans', 'Segoe UI', sans-serif"
MONO = "'IBM Plex Mono', Consolas, monospace"

QSS = f"""
* {{ font-family: {FONT}; font-size: 14px; color: {TEXT}; }}
QMainWindow, QWidget#page, QStackedWidget {{ background: {BG}; }}
QWidget#nav {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
QWidget#header {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QLabel#brand {{ font-size: 20px; letter-spacing: -0.5px; }}
QLabel#ticker {{ font-family: {MONO}; font-size: 22px; font-weight: 600; }}
QLabel#price {{ font-family: {MONO}; font-size: 18px; }}
QLabel#label {{ color: {TEXT_2}; font-size: 12px; font-weight: 600; letter-spacing: 0.5px; }}
QLabel#body {{ color: {TEXT_BODY}; font-size: 14px; }}
QFrame#evidence {{ background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 10px; }}
QWidget#side {{ background: {PANEL}; border-left: 1px solid {BORDER}; }}
QLabel#h1 {{ font-size: 20px; font-weight: 600; }}
QLabel#h2 {{ font-size: 16px; font-weight: 600; }}
QLabel#muted, QLabel.muted {{ color: {TEXT_2}; font-size: 13px; }}
QLabel#mono {{ font-family: {MONO}; }}
QLabel#pill {{ border: 1px solid {ACCENT}; color: #BFD0FF; border-radius: 11px; padding: 2px 10px;
               font-weight: 600; font-size: 12px; }}
QLabel#pill[live="true"] {{ border-color: {DOWN}; color: #FFD2CC; background: {DANGER_BG}; }}
QPushButton {{ min-height: 40px; padding: 0 16px; border-radius: 8px; border: 1px solid {BORDER_2};
               background: {PANEL_2}; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:focus {{ border: 2px solid {ACCENT}; }}
QPushButton:disabled {{ color: #6F7A89; border-color: {BORDER}; }}
QPushButton#primary {{ background: {PRIMARY}; border-color: {PRIMARY}; color: white; }}
QPushButton#primary:disabled {{ background: #1C2A45; border-color: #1C2A45; color: #7F8BA0; }}
QPushButton#danger {{ background: {DANGER_BG}; border-color: {DANGER_BORDER}; color: #FFB4AA; font-weight: 600; }}
QPushButton#navButton {{ text-align: left; min-height: 44px; border: none; background: transparent;
                         color: {TEXT_2}; font-size: 15px; font-weight: 500; padding-left: 14px; }}
QPushButton#navButton:hover {{ background: #161B24; color: {TEXT}; }}
QPushButton#navButton:checked {{ background: #18213A; color: {TEXT}; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ min-height: 40px; padding: 0 10px; border-radius: 8px;
    border: 1px solid {BORDER_2}; background: {BG}; font-family: {MONO}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
QCheckBox {{ spacing: 10px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 0; border: none; }}
QListWidget, QTableView, QTextBrowser, QPlainTextEdit {{ background: {PANEL}; border: 1px solid {BORDER};
    border-radius: 10px; }}
QListWidget::item {{ padding: 10px; border-radius: 8px; }}
QListWidget::item:selected {{ background: #141C2E; border: 1px solid {ACCENT}; }}
QHeaderView::section {{ background: {PANEL}; color: {TEXT_2}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px; font-size: 12px; font-weight: 600; }}
QTableView {{ gridline-color: #161B24; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ min-height: 40px; padding: 0 16px; background: transparent; color: {TEXT_2};
    border-bottom: 2px solid transparent; font-size: 15px; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom-color: {ACCENT}; }}
QPlainTextEdit {{ font-family: {MONO}; font-size: 12px; }}
QScrollArea {{ border: none; background: {BG}; }}
QScrollBar:vertical {{ background: {PANEL}; width: 10px; margin: 0; border: none; }}
QScrollBar::handle:vertical {{ background: {BORDER_2}; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: {PANEL}; height: 10px; margin: 0; border: none; }}
QScrollBar::handle:horizontal {{ background: {BORDER_2}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
"""
