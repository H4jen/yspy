"""
yspy Qt GUI — Main Window

Central application window with:
  - Sidebar navigation (left panel)
  - Stacked content area (right panel)
  - Menu bar with all actions
  - Status bar with portfolio summary and last-update time
  - Portfolio loaded from the same data files as the curses app
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QAction, QIcon, QFont, QColor
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QListWidget, QListWidgetItem,
    QLabel, QSplitter, QStatusBar, QMessageBox,
    QMenuBar, QMenu, QFrame
)

from qt_app.theme import Colors, apply_theme, monospace_font
from qt_app.watch_widget import WatchWidget

logger = logging.getLogger(__name__)


# ── Portfolio loader thread ───────────────────────────────────────────────────

class PortfolioLoader(QThread):
    """Loads the Portfolio object in a background thread to keep the UI responsive."""
    loaded = pyqtSignal(object)   # emits Portfolio instance
    failed = pyqtSignal(str)      # emits error message

    def run(self):
        try:
            # Add project root to path so src imports resolve
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            from src.portfolio_manager import Portfolio, HistoricalMode
            from src.app_config import config
            import os as _os

            portfolio_path = config.get_portfolio_path(project_root)
            if not _os.path.isdir(portfolio_path):
                _os.makedirs(portfolio_path, exist_ok=True)

            portfolio = Portfolio(
                path=portfolio_path,
                filename=config.PORTFOLIO_FILENAME,
                historical_mode=HistoricalMode.BACKGROUND,
                verbose=False,
                allow_online_currency_lookup=True,
            )
            self.loaded.emit(portfolio)
        except Exception as e:
            logger.exception("Failed to load portfolio")
            self.failed.emit(str(e))


# ── Sidebar ───────────────────────────────────────────────────────────────────

class SidebarItem:
    def __init__(self, label: str, icon: str, page_index: int, shortcut: str = ""):
        self.label = label
        self.icon = icon
        self.page_index = page_index
        self.shortcut = shortcut


SIDEBAR_ITEMS = [
    SidebarItem("Watch",         "📈", 0, "Ctrl+W"),
    SidebarItem("Portfolio",     "📋", 1, "Ctrl+P"),
    SidebarItem("Shares",        "🗂",  2),
    SidebarItem("Profits",       "💰", 3, "Ctrl+R"),
    SidebarItem("Funds",         "🏦", 4, "Ctrl+F"),
    SidebarItem("Short Selling", "📉", 5),
    SidebarItem("Correlation",   "🔗", 6),
    SidebarItem("AI Assistant",  "🤖", 7, "Ctrl+I"),
]


class Sidebar(QWidget):
    """Left navigation panel."""
    page_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(180)
        self.setObjectName("Sidebar")
        self.setStyleSheet(f"""
            #Sidebar {{
                background-color: {Colors.SIDEBAR_BG};
                border-right: 1px solid {Colors.BORDER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # App title / logo area
        title_frame = QFrame()
        title_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.SIDEBAR_BG};
                border-bottom: 1px solid {Colors.BORDER};
            }}
        """)
        title_layout = QVBoxLayout(title_frame)
        title_layout.setContentsMargins(12, 14, 12, 14)

        app_label = QLabel("yspy")
        app_label.setStyleSheet(f"""
            color: {Colors.ACCENT};
            font-size: 20px;
            font-weight: bold;
            font-family: 'Consolas', monospace;
        """)
        sub_label = QLabel("Portfolio Manager")
        sub_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")

        title_layout.addWidget(app_label)
        title_layout.addWidget(sub_label)
        layout.addWidget(title_frame)

        # Navigation list
        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {Colors.SIDEBAR_BG};
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                color: {Colors.SIDEBAR_TEXT};
                padding: 10px 16px;
                border-bottom: 1px solid rgba(255,255,255,0.04);
                font-size: 13px;
            }}
            QListWidget::item:selected {{
                background-color: {Colors.ACCENT};
                color: white;
                border-radius: 0;
            }}
            QListWidget::item:hover {{
                background-color: {Colors.SIDEBAR_ITEM};
            }}
        """)
        self.nav_list.setSpacing(0)
        self.nav_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        for item in SIDEBAR_ITEMS:
            list_item = QListWidgetItem(f"  {item.icon}  {item.label}")
            list_item.setData(Qt.ItemDataRole.UserRole, item.page_index)
            self.nav_list.addItem(list_item)

        self.nav_list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.nav_list)
        layout.addStretch()

        # Version footer
        ver_label = QLabel("v2.0 (Qt)")
        ver_label.setStyleSheet(f"""
            color: {Colors.TEXT_DIM};
            font-size: 10px;
            padding: 8px 12px;
        """)
        layout.addWidget(ver_label)

    def _on_row_changed(self, row: int):
        if row >= 0:
            page_index = self.nav_list.item(row).data(Qt.ItemDataRole.UserRole)
            self.page_requested.emit(page_index)

    def select_page(self, index: int):
        for i in range(self.nav_list.count()):
            if self.nav_list.item(i).data(Qt.ItemDataRole.UserRole) == index:
                self.nav_list.setCurrentRow(i)
                break


# ── Placeholder page ──────────────────────────────────────────────────────────

class PlaceholderPage(QWidget):
    """Temporary placeholder shown for pages not yet implemented."""

    def __init__(self, title: str, description: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_label = QLabel("🚧")
        icon_label.setStyleSheet("font-size: 48px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            color: {Colors.TEXT_HEADER};
            font-size: 22px;
            font-weight: bold;
            font-family: 'Consolas', monospace;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc_label = QLabel(description or "Coming in the next phase.")
        desc_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 13px;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)

        layout.addWidget(icon_label)
        layout.addSpacing(12)
        layout.addWidget(title_label)
        layout.addSpacing(6)
        layout.addWidget(desc_label)


# ── Loading page ──────────────────────────────────────────────────────────────

class LoadingPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.spinner_label = QLabel("⟳")
        self.spinner_label.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 48px;")
        self.spinner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("Loading portfolio…")
        self.status_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 14px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.spinner_label)
        layout.addSpacing(16)
        layout.addWidget(self.status_label)

        # Animate spinner
        self._spin_chars = ["⟳", "↻", "↺", "⟲"]
        self._spin_idx = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._spin)
        self._timer.start(200)

    def _spin(self):
        self._spin_idx = (self._spin_idx + 1) % len(self._spin_chars)
        self.spinner_label.setText(self._spin_chars[self._spin_idx])

    def set_status(self, msg: str):
        self.status_label.setText(msg)


# ── Main Window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self):
        super().__init__()
        self.portfolio = None
        self._loader: Optional[PortfolioLoader] = None

        self._setup_window()
        self._build_menu_bar()
        self._build_central_widget()
        self._build_status_bar()
        self._start_portfolio_load()

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle("yspy — Stock Portfolio Manager")
        self.resize(1280, 780)
        self.setMinimumSize(900, 600)

    # ── Menu bar ──────────────────────────────────────────────────────────────

    def _build_menu_bar(self):
        mb = self.menuBar()

        # Portfolio menu
        portfolio_menu = mb.addMenu("&Portfolio")
        self._add_action(portfolio_menu, "&Add Stock",      "Ctrl+A", lambda: self._nav(1))
        self._add_action(portfolio_menu, "&Remove Stock",   "Ctrl+D", lambda: self._nav(1))
        portfolio_menu.addSeparator()
        self._add_action(portfolio_menu, "&Buy Shares",     "Ctrl+B", lambda: self._nav(1))
        self._add_action(portfolio_menu, "&Sell Shares",    "Ctrl+S", lambda: self._nav(1))
        portfolio_menu.addSeparator()
        self._add_action(portfolio_menu, "&Quit",           "Ctrl+Q", self.close)

        # View menu
        view_menu = mb.addMenu("&View")
        self._add_action(view_menu, "&Watch Screen",    "Ctrl+W", lambda: self._nav(0))
        self._add_action(view_menu, "&Portfolio List",  "Ctrl+P", lambda: self._nav(1))
        self._add_action(view_menu, "&Shares",          "",       lambda: self._nav(2))
        self._add_action(view_menu, "&Profits",         "Ctrl+R", lambda: self._nav(3))
        view_menu.addSeparator()
        self._add_action(view_menu, "&Funds",           "Ctrl+F", lambda: self._nav(4))
        self._add_action(view_menu, "S&hort Selling",   "",       lambda: self._nav(5))
        self._add_action(view_menu, "&Correlation",     "",       lambda: self._nav(6))
        self._add_action(view_menu, "&AI Assistant",    "Ctrl+I", lambda: self._nav(7))

        # Help menu
        help_menu = mb.addMenu("&Help")
        self._add_action(help_menu, "&About", "", self._show_about)

    def _add_action(self, menu: QMenu, label: str, shortcut: str, slot) -> QAction:
        action = QAction(label, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    # ── Central widget ────────────────────────────────────────────────────────

    def _build_central_widget(self):
        container = QWidget()
        self.setCentralWidget(container)

        h_layout = QHBoxLayout(container)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar.page_requested.connect(self._nav)
        h_layout.addWidget(self.sidebar)

        # Stacked pages
        self.stack = QStackedWidget()
        h_layout.addWidget(self.stack)

        # Page 0: Watch screen (shows loading state until portfolio arrives)
        self.watch_widget = WatchWidget()
        self.stack.addWidget(self.watch_widget)   # index 0

        # Pages 1–7: Placeholders (replaced phase by phase)
        self.stack.addWidget(PlaceholderPage("Portfolio List",   "Phase 3 — coming soon"))   # 1
        self.stack.addWidget(PlaceholderPage("Shares",           "Phase 3 — coming soon"))   # 2
        self.stack.addWidget(PlaceholderPage("Profits",          "Phase 4 — coming soon"))   # 3
        self.stack.addWidget(PlaceholderPage("Managed Funds",    "Phase 5 — coming soon"))   # 4
        self.stack.addWidget(PlaceholderPage("Short Selling",    "Phase 6 — coming soon"))   # 5
        self.stack.addWidget(PlaceholderPage("Correlation",      "Phase 8 — coming soon"))   # 6
        self.stack.addWidget(PlaceholderPage("AI Assistant",     "Phase 7 — coming soon"))   # 7

        # Start on Watch screen
        self.stack.setCurrentIndex(0)
        self.sidebar.select_page(0)

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self):
        sb = self.statusBar()
        sb.setObjectName("StatusBar")

        self.status_portfolio = QLabel("Portfolio: loading…")
        self.status_portfolio.setStyleSheet(f"color: {Colors.TEXT_DIM}; padding-right: 20px;")

        self.status_time = QLabel("")
        self.status_time.setStyleSheet(f"color: {Colors.TEXT_DIM};")

        sb.addWidget(self.status_portfolio)
        sb.addPermanentWidget(self.status_time)

        # Clock update
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        self.status_time.setText(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))

    # ── Portfolio loading ─────────────────────────────────────────────────────

    def _start_portfolio_load(self):
        self._loader = PortfolioLoader()
        self._loader.loaded.connect(self._on_portfolio_loaded)
        self._loader.failed.connect(self._on_portfolio_failed)
        self._loader.start()

    @pyqtSlot(object)
    def _on_portfolio_loaded(self, portfolio):
        self.portfolio = portfolio
        logger.info("Portfolio loaded successfully")

        # Update status bar
        try:
            stocks = portfolio.get_stock_details()
            count = len(stocks)
            self.status_portfolio.setText(f"Portfolio: {count} stocks loaded")
            self.status_portfolio.setStyleSheet(f"color: {Colors.POSITIVE}; padding-right: 20px;")
        except Exception:
            self.status_portfolio.setText("Portfolio: loaded")

        # Hand portfolio to watch widget — it will start polling immediately
        self.watch_widget.set_portfolio(portfolio)
        self.stack.setCurrentIndex(0)
        self.sidebar.select_page(0)

    @pyqtSlot(str)
    def _on_portfolio_failed(self, error_msg: str):
        logger.error(f"Portfolio load failed: {error_msg}")
        self.status_portfolio.setText("Portfolio: load failed")
        self.status_portfolio.setStyleSheet(f"color: {Colors.NEGATIVE}; padding-right: 20px;")

        QMessageBox.critical(
            self,
            "Portfolio Load Error",
            f"Could not load portfolio:\n\n{error_msg}\n\n"
            "Make sure you are running from the project root directory."
        )

    # ── Navigation ────────────────────────────────────────────────────────────

    def _nav(self, page_index: int):
        self.stack.setCurrentIndex(page_index)
        self.sidebar.select_page(page_index)

    # ── About dialog ──────────────────────────────────────────────────────────

    def _show_about(self):
        QMessageBox.about(
            self,
            "About yspy",
            "<b>yspy — Stock Portfolio Manager</b><br>"
            "<br>"
            "PyQt6 GUI (v2.0)<br>"
            "Original curses app: github.com/H4jen/yspy<br>"
            "<br>"
            "All portfolio data is read from the same files<br>"
            "as the original terminal application."
        )

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        # Accept immediately so the window closes at once
        event.accept()
        # Schedule cleanup after the event loop processes the close
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._shutdown)

    def _shutdown(self):
        self.watch_widget._stop_worker()
        if self._loader and self._loader.isRunning():
            self._loader.quit()
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().quit()
