"""The look: Elgin City's black and white, with green, grey and red for
wins, draws and defeats."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QStyleFactory

BLACK = "#111111"
INK = "#1d1d1f"
MUTED = "#6e6e73"
LINE = "#d9d9de"
PAPER = "#ffffff"
SHADE = "#f4f4f6"
ACCENT = "#c8102e"  # the red of the away kit, sparingly
WIN_COLOUR = "#1e8e3e"
DRAW_COLOUR = "#8a8a8e"
LOSS_COLOUR = "#c62828"
RESULT_COLOURS = {"W": WIN_COLOUR, "D": DRAW_COLOUR, "L": LOSS_COLOUR}

STYLE = f"""
QWidget {{ color: {INK}; font-size: 10.5pt; }}
QMainWindow, QTabWidget::pane, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {SHADE}; }}
QTabWidget::pane {{ border: none; }}
QTabBar {{ background: {BLACK}; }}
QTabBar::tab {{ background: {BLACK}; color: #bdbdc2; padding: 10px 22px; border: none; font-weight: 600; }}
QTabBar::tab:selected {{ color: white; border-bottom: 3px solid white; }}
QTabBar::tab:hover {{ color: white; }}
QFrame#card {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 10px; }}
QLabel#cardTitle {{ font-size: 9pt; font-weight: 700; color: {MUTED}; letter-spacing: 1px; }}
QLabel#big {{ font-size: 22pt; font-weight: 700; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#banner {{ background: {BLACK}; color: white; }}
QLineEdit, QComboBox {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 6px; padding: 5px 8px; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {BLACK}; }}
QPushButton {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 6px; padding: 5px 12px; }}
QPushButton:hover {{ border-color: {BLACK}; }}
QTableView, QListWidget, QTreeWidget {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 8px;
    gridline-color: {SHADE}; selection-background-color: {BLACK}; selection-color: white; }}
QHeaderView::section {{ background: {PAPER}; border: none; border-bottom: 1px solid {LINE};
    padding: 6px; font-weight: 700; color: {MUTED}; }}
QStatusBar {{ background: {PAPER}; color: {MUTED}; }}
"""


def apply(app: QApplication) -> None:
    """A light look whatever the desktop's theme: the club's colours
    are black on white."""
    app.setStyle(QStyleFactory.create("Fusion"))
    palette = QPalette()
    for role, colour in ((QPalette.Window, SHADE), (QPalette.Base, PAPER), (QPalette.AlternateBase, SHADE),
                         (QPalette.Text, INK), (QPalette.WindowText, INK), (QPalette.Button, PAPER),
                         (QPalette.ButtonText, INK), (QPalette.Highlight, BLACK), (QPalette.HighlightedText, "#ffffff"),
                         (QPalette.ToolTipBase, PAPER), (QPalette.ToolTipText, INK), (QPalette.PlaceholderText, MUTED)):
        palette.setColor(role, QColor(colour))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


def result_chip(result: str) -> str:
    """A coloured W/D/L letter, as rich text."""
    colour = RESULT_COLOURS.get(result, MUTED)
    return (f"<span style='background:{colour}; color:white; font-weight:700; "
            f"padding:1px 5px; border-radius:3px;'>&nbsp;{result or '–'}&nbsp;</span>")


def title(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("cardTitle")
    return label
