"""
yspy Qt GUI — Dark theme and color palette.

Matches the color scheme of the original curses application:
  - Green  → positive values / gains
  - Red    → negative values / losses
  - Yellow → neutral / warnings / headers
  - White  → default text
  - Dark background throughout
"""

from PyQt6.QtGui import QColor, QPalette, QFont
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


# ── Colours ──────────────────────────────────────────────────────────────────

class Colors:
    BACKGROUND      = "#1a1a1a"
    BACKGROUND_ALT  = "#222222"
    SURFACE         = "#2a2a2a"
    SURFACE_RAISED  = "#333333"
    BORDER          = "#444444"

    TEXT            = "#e0e0e0"
    TEXT_DIM        = "#888888"
    TEXT_HEADER     = "#ffd700"   # yellow — matches curses color_pair(3)

    POSITIVE        = "#00cc66"   # green  — curses color_pair(1)
    NEGATIVE        = "#ff4444"   # red    — curses color_pair(2)
    NEUTRAL         = "#ffd700"   # yellow — curses color_pair(3)
    WHITE           = "#e0e0e0"

    ACCENT          = "#4a9eff"   # blue highlight for selection
    ACCENT_HOVER    = "#5fb0ff"

    # Sidebar
    SIDEBAR_BG      = "#1e1e2e"
    SIDEBAR_ITEM    = "#2a2a3e"
    SIDEBAR_ACTIVE  = "#4a9eff"
    SIDEBAR_TEXT    = "#c0c0d0"


def value_color(value: float) -> str:
    """Return the hex color string for a numeric value (positive/negative/zero)."""
    if value > 0:
        return Colors.POSITIVE
    if value < 0:
        return Colors.NEGATIVE
    return Colors.NEUTRAL


# ── Stylesheet ────────────────────────────────────────────────────────────────

MAIN_STYLESHEET = f"""
/* ── Global ── */
QWidget {{
    background-color: {Colors.BACKGROUND};
    color: {Colors.TEXT};
    font-family: "Consolas", "DejaVu Sans Mono", "Courier New", monospace;
    font-size: 13px;
}}

QMainWindow {{
    background-color: {Colors.BACKGROUND};
}}

/* ── Menus & MenuBar ── */
QMenuBar {{
    background-color: {Colors.SURFACE};
    color: {Colors.TEXT};
    border-bottom: 1px solid {Colors.BORDER};
    padding: 2px;
}}
QMenuBar::item:selected {{
    background-color: {Colors.ACCENT};
    color: white;
    border-radius: 3px;
}}
QMenu {{
    background-color: {Colors.SURFACE_RAISED};
    color: {Colors.TEXT};
    border: 1px solid {Colors.BORDER};
}}
QMenu::item:selected {{
    background-color: {Colors.ACCENT};
    color: white;
}}
QMenu::separator {{
    height: 1px;
    background-color: {Colors.BORDER};
    margin: 3px 0;
}}

/* ── Toolbar ── */
QToolBar {{
    background-color: {Colors.SURFACE};
    border-bottom: 1px solid {Colors.BORDER};
    spacing: 4px;
    padding: 3px;
}}

/* ── Status bar ── */
QStatusBar {{
    background-color: {Colors.SURFACE};
    color: {Colors.TEXT_DIM};
    border-top: 1px solid {Colors.BORDER};
    font-size: 11px;
}}

/* ── Tables ── */
QTableWidget, QTableView {{
    background-color: {Colors.BACKGROUND};
    alternate-background-color: {Colors.BACKGROUND_ALT};
    gridline-color: {Colors.BORDER};
    border: 1px solid {Colors.BORDER};
    color: {Colors.TEXT};
    selection-background-color: {Colors.ACCENT};
    selection-color: white;
}}
QHeaderView::section {{
    background-color: {Colors.SURFACE_RAISED};
    color: {Colors.TEXT_HEADER};
    border: 1px solid {Colors.BORDER};
    padding: 4px 8px;
    font-weight: bold;
}}
QTableWidget::item {{
    padding: 3px 6px;
}}
QTableWidget::item:selected {{
    background-color: {Colors.ACCENT};
    color: white;
}}

/* ── Scroll bars ── */
QScrollBar:vertical {{
    background-color: {Colors.BACKGROUND_ALT};
    width: 10px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background-color: {Colors.BORDER};
    min-height: 30px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {Colors.ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background-color: {Colors.BACKGROUND_ALT};
    height: 10px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background-color: {Colors.BORDER};
    min-width: 30px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {Colors.ACCENT};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ── Push buttons ── */
QPushButton {{
    background-color: {Colors.SURFACE_RAISED};
    color: {Colors.TEXT};
    border: 1px solid {Colors.BORDER};
    border-radius: 4px;
    padding: 6px 14px;
    min-width: 70px;
}}
QPushButton:hover {{
    background-color: {Colors.ACCENT};
    color: white;
    border-color: {Colors.ACCENT};
}}
QPushButton:pressed {{
    background-color: {Colors.ACCENT_HOVER};
}}
QPushButton:disabled {{
    color: {Colors.TEXT_DIM};
    background-color: {Colors.SURFACE};
    border-color: {Colors.BORDER};
}}

/* ── Line edits / inputs ── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {Colors.SURFACE};
    color: {Colors.TEXT};
    border: 1px solid {Colors.BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {Colors.ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {Colors.ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {Colors.SURFACE_RAISED};
    color: {Colors.TEXT};
    selection-background-color: {Colors.ACCENT};
}}

/* ── Text areas ── */
QTextEdit, QPlainTextEdit {{
    background-color: {Colors.BACKGROUND_ALT};
    color: {Colors.TEXT};
    border: 1px solid {Colors.BORDER};
    border-radius: 4px;
    padding: 4px;
    selection-background-color: {Colors.ACCENT};
}}

/* ── Labels ── */
QLabel {{
    color: {Colors.TEXT};
    background-color: transparent;
}}
QLabel[role="header"] {{
    color: {Colors.TEXT_HEADER};
    font-weight: bold;
    font-size: 14px;
}}
QLabel[role="dim"] {{
    color: {Colors.TEXT_DIM};
}}
QLabel[role="positive"] {{
    color: {Colors.POSITIVE};
}}
QLabel[role="negative"] {{
    color: {Colors.NEGATIVE};
}}

/* ── Group boxes ── */
QGroupBox {{
    border: 1px solid {Colors.BORDER};
    border-radius: 5px;
    margin-top: 12px;
    padding-top: 6px;
    color: {Colors.TEXT_HEADER};
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 10px;
    top: -1px;
}}

/* ── Splitter ── */
QSplitter::handle {{
    background-color: {Colors.BORDER};
}}
QSplitter::handle:horizontal {{
    width: 3px;
}}
QSplitter::handle:vertical {{
    height: 3px;
}}

/* ── Tabs ── */
QTabWidget::pane {{
    border: 1px solid {Colors.BORDER};
    background-color: {Colors.BACKGROUND};
}}
QTabBar::tab {{
    background-color: {Colors.SURFACE};
    color: {Colors.TEXT_DIM};
    border: 1px solid {Colors.BORDER};
    border-bottom: none;
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{
    background-color: {Colors.BACKGROUND};
    color: {Colors.TEXT};
    border-bottom: 2px solid {Colors.ACCENT};
}}
QTabBar::tab:hover {{
    color: {Colors.TEXT};
    background-color: {Colors.SURFACE_RAISED};
}}

/* ── Dialog ── */
QDialog {{
    background-color: {Colors.SURFACE};
}}

/* ── Dock widgets ── */
QDockWidget {{
    color: {Colors.TEXT};
    titlebar-close-icon: none;
}}
QDockWidget::title {{
    background-color: {Colors.SURFACE_RAISED};
    color: {Colors.TEXT_HEADER};
    padding: 4px 8px;
    border-bottom: 1px solid {Colors.BORDER};
}}

/* ── Tree / List views ── */
QListWidget, QTreeWidget, QListView, QTreeView {{
    background-color: {Colors.BACKGROUND};
    alternate-background-color: {Colors.BACKGROUND_ALT};
    color: {Colors.TEXT};
    border: 1px solid {Colors.BORDER};
    selection-background-color: {Colors.ACCENT};
    selection-color: white;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 3px 4px;
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background-color: {Colors.ACCENT};
    color: white;
}}

/* ── Check boxes ── */
QCheckBox {{
    color: {Colors.TEXT};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {Colors.BORDER};
    border-radius: 3px;
    background-color: {Colors.SURFACE};
}}
QCheckBox::indicator:checked {{
    background-color: {Colors.ACCENT};
    border-color: {Colors.ACCENT};
}}

/* ── Progress bar ── */
QProgressBar {{
    background-color: {Colors.SURFACE};
    border: 1px solid {Colors.BORDER};
    border-radius: 4px;
    text-align: center;
    color: {Colors.TEXT};
}}
QProgressBar::chunk {{
    background-color: {Colors.ACCENT};
    border-radius: 3px;
}}

/* ── Tool tips ── */
QToolTip {{
    background-color: {Colors.SURFACE_RAISED};
    color: {Colors.TEXT};
    border: 1px solid {Colors.BORDER};
    padding: 4px 8px;
    border-radius: 3px;
}}
"""


def apply_theme(app: QApplication) -> None:
    """Apply the yspy dark theme to the QApplication instance."""
    app.setStyleSheet(MAIN_STYLESHEET)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor(Colors.BACKGROUND))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Base,            QColor(Colors.BACKGROUND_ALT))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(Colors.SURFACE))
    palette.setColor(QPalette.ColorRole.Text,            QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Button,          QColor(Colors.SURFACE_RAISED))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor(Colors.ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor(Colors.SURFACE_RAISED))
    palette.setColor(QPalette.ColorRole.ToolTipText,     QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(Colors.TEXT_DIM))
    app.setPalette(palette)


def monospace_font(size: int = 13) -> QFont:
    """Return a monospace font for data-dense widgets."""
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(size)
    return font
