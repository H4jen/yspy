#!/usr/bin/env python3
"""
yspy — PyQt6 GUI Entry Point

Launches the desktop version of the yspy stock portfolio manager.
The original curses app (yspy.py) continues to work unchanged.

Usage:
    ./yspy_qt.py
    python3 yspy_qt.py
"""

import logging
import os
import sys


def _configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("yspy_qt.log", mode="a"),
        ],
    )


def main():
    _configure_logging()
    logger = logging.getLogger("yspy_qt")
    logger.info("Starting yspy Qt GUI")

    # Ensure the project root is always in sys.path, regardless of where
    # the script is invoked from.
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
    except ImportError:
        print(
            "ERROR: PyQt6 is not installed.\n"
            "Install it with:  pip install PyQt6 pyqtgraph\n"
            "Then re-run this script."
        )
        sys.exit(1)

    from qt_app.theme import apply_theme
    from qt_app.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("yspy")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("yspy")

    apply_theme(app)

    window = MainWindow()
    window.show()

    logger.info("Qt event loop starting")
    exit_code = app.exec()
    logger.info(f"Qt event loop exited with code {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
