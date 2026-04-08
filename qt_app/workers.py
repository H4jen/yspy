"""
yspy Qt GUI — Background worker threads.

PriceWorker: fetches fresh stock prices on a timer without blocking the UI.
"""

import logging
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QObject

logger = logging.getLogger(__name__)


class PriceWorker(QObject):
    """
    Runs in a background QThread and periodically calls
    portfolio.get_stock_prices() to fetch current prices.

    Signals
    -------
    prices_ready  : emits the list of stock-price dicts
    error         : emits an error message string
    """

    prices_ready = pyqtSignal(list)
    error        = pyqtSignal(str)

    def __init__(self, portfolio, interval_ms: int = 15_000, parent=None):
        super().__init__(parent)
        self.portfolio    = portfolio
        self.interval_ms  = interval_ms
        self._timer: Optional[QTimer] = None
        self._running     = False

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start_polling(self):
        """Call this from the worker thread (via QObject.moveToThread)."""
        self._running = True
        self._timer = QTimer()
        self._timer.setInterval(self.interval_ms)
        self._timer.timeout.connect(self._fetch)
        self._timer.start()
        # Fire immediately so the UI doesn't wait interval_ms for first data
        self._fetch()

    def stop_polling(self):
        self._running = False
        if self._timer:
            self._timer.stop()

    # ── fetch ────────────────────────────────────────────────────────────────

    def _fetch(self):
        if not self._running:
            return
        try:
            prices = self.portfolio.get_stock_prices(
                include_zero_shares=True,
                compute_history=True,
            )
            self.prices_ready.emit(prices)
        except Exception as e:
            logger.exception("PriceWorker fetch error")
            self.error.emit(str(e))
