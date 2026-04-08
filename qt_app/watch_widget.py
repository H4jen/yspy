"""
yspy Qt GUI — Watch Widget (Phase 2)

Live-updating stock watch screen that replaces the curses watch display.

Features:
  - Two view modes: Stocks view / Shares view (toggle with the View button or 'S' key)
  - Stocks are grouped: Owned → Highlighted/Watchlist → Other → Market Indices
  - Color-coded rows: green = positive, red = negative, yellow = neutral
  - Every column from the original app: Short%, ΔShort, T, Current, High, Low,
    -1d..%1d, -2d..%2d, -3d..%3d, -1w..%1w, -2w..%2w, -1m..%1m, -3m..%3m, -6m..%6m, -1y..%1y
  - Auto-refresh via background PriceWorker thread
  - Portfolio totals footer
  - Status bar showing last-update time and stock count
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, pyqtSlot, QTimer
)
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QBrush
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QFrame, QAbstractItemView, QTabWidget,
    QProgressBar, QSizePolicy
)

from qt_app.theme import Colors, monospace_font, value_color
from qt_app.workers import PriceWorker

logger = logging.getLogger(__name__)

# ── Column definitions ────────────────────────────────────────────────────────

STOCKS_COLUMNS = [
    # (header,      key,         width,  align,      is_numeric)
    ("Name",        "name",       160,  "left",     False),
    ("%Δs",         "_short_pct",  70,  "right",    True),
    ("Δs",          "_short_chg",  65,  "right",    True),
    ("T",           "_trend",      30,  "center",   False),
    ("Current",     "_current",    90,  "right",    True),
    ("High",        "high",        80,  "right",    True),
    ("Low",         "low",         80,  "right",    True),
    ("-1d",         "-1d",         80,  "right",    True),
    ("%1d",         "%1d",         70,  "right",    True),
    ("-2d",         "-2d",         80,  "right",    True),
    ("%2d",         "%2d",         70,  "right",    True),
    ("-3d",         "-3d",         80,  "right",    True),
    ("%3d",         "%3d",         70,  "right",    True),
    ("-1w",         "-1w",         80,  "right",    True),
    ("%1w",         "%1w",         70,  "right",    True),
    ("-2w",         "-2w",         80,  "right",    True),
    ("%2w",         "%2w",         70,  "right",    True),
    ("-1m",         "-1m",         80,  "right",    True),
    ("%1m",         "%1m",         70,  "right",    True),
    ("-3m",         "-3m",         80,  "right",    True),
    ("%3m",         "%3m",         70,  "right",    True),
    ("-6m",         "-6m",         80,  "right",    True),
    ("%6m",         "%6m",         70,  "right",    True),
    ("-1y",         "-1y",         80,  "right",    True),
    ("%1y",         "%1y",         70,  "right",    True),
]

SHARES_COLUMNS = [
    ("Name",        "name",        160,  "left",   False),
    ("Shares",      "_shares",      80,  "right",  True),
    ("Avg Price",   "_avg_price",   90,  "right",  True),
    ("Current",     "_current",     90,  "right",  True),
    ("Total Value", "_total_val",  110,  "right",  True),
    ("P/L",         "_pl",          90,  "right",  True),
    ("P/L %",       "_pl_pct",      80,  "right",  True),
    ("-1d",         "-1d",          80,  "right",  True),
    ("%1d",         "%1d",          70,  "right",  True),
    ("-1w",         "-1w",          80,  "right",  True),
    ("%1w",         "%1w",          70,  "right",  True),
    ("-1m",         "-1m",          80,  "right",  True),
    ("%1m",         "%1m",          70,  "right",  True),
]

# ── Row group colours ─────────────────────────────────────────────────────────

GROUP_BG = {
    "owned":       QColor("#1e2a1e"),   # dark green tint
    "highlighted": QColor("#1e1e2a"),   # dark blue tint
    "other":       QColor(Colors.BACKGROUND),
    "index":       QColor("#2a2a1e"),   # dark yellow tint
    "separator":   QColor("#333333"),
}

# ── Helper: format a float for display ───────────────────────────────────────

def _fmt(value, decimals: int = 2, suffix: str = "", na: str = "N/A") -> str:
    if value is None:
        return na
    try:
        v = float(value)
        return f"{v:,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return na


def _fmt_pct(value, na: str = "N/A") -> str:
    return _fmt(value, 2, "%", na)


# ── Single table row data ─────────────────────────────────────────────────────

def _build_stocks_row(sp: Dict, portfolio, short_data: Dict, short_trend: Dict) -> List[str]:
    """Convert a stock-price dict into the ordered cell strings for STOCKS_COLUMNS."""
    name     = sp.get("name", "")
    currency = sp.get("currency", "SEK")
    is_foreign = currency != "SEK"
    name_display = f"{name} ({currency})" if is_foreign else name

    # Short data
    short_pct = short_data.get(name) if short_data else None
    short_chg = None
    trend_arrow = ""
    if short_trend and name in short_trend:
        ti = short_trend[name]
        trend_arrow = ti.get("arrow", "")
        short_chg   = ti.get("change")

    # Current price — prefer native currency
    current = sp.get("current_native") if sp.get("current_native") is not None else sp.get("current")

    row = [
        name_display,
        _fmt_pct(short_pct),
        _fmt(short_chg, 2, "", "N/A") if short_chg is not None else "N/A",
        trend_arrow or "·",
        _fmt(current),
        _fmt(sp.get("high_native") if sp.get("high_native") is not None else sp.get("high")),
        _fmt(sp.get("low_native") if sp.get("low_native") is not None else sp.get("low")),
        _fmt(sp.get("-1d")),
        _fmt_pct(sp.get("%1d")),
        _fmt(sp.get("-2d")),
        _fmt_pct(sp.get("%2d")),
        _fmt(sp.get("-3d")),
        _fmt_pct(sp.get("%3d")),
        _fmt(sp.get("-1w")),
        _fmt_pct(sp.get("%1w")),
        _fmt(sp.get("-2w")),
        _fmt_pct(sp.get("%2w")),
        _fmt(sp.get("-1m")),
        _fmt_pct(sp.get("%1m")),
        _fmt(sp.get("-3m")),
        _fmt_pct(sp.get("%3m")),
        _fmt(sp.get("-6m")),
        _fmt_pct(sp.get("%6m")),
        _fmt(sp.get("-1y")),
        _fmt_pct(sp.get("%1y")),
    ]
    return row


def _build_shares_row(sp: Dict, portfolio) -> List[str]:
    """Convert a stock-price dict into cell strings for SHARES_COLUMNS (owned stocks only)."""
    name = sp.get("name", "")
    current = sp.get("current_native") if sp.get("current_native") is not None else sp.get("current")

    # Get holdings from portfolio
    shares = 0.0
    avg_price = 0.0
    total_val = 0.0
    pl = 0.0
    pl_pct = 0.0

    stock_obj = getattr(portfolio, "stocks", {}).get(name)
    if stock_obj and hasattr(stock_obj, "holdings") and stock_obj.holdings:
        shares = sum(h.volume for h in stock_obj.holdings)
        costs  = sum(h.volume * h.price for h in stock_obj.holdings)
        avg_price = costs / shares if shares else 0.0
        if current is not None:
            total_val = shares * current
            pl        = total_val - costs
            pl_pct    = (pl / costs * 100) if costs else 0.0

    # Funds
    funds = getattr(portfolio, "funds", {})
    fund_obj = funds.get(name)
    if fund_obj and sp.get("_is_fund"):
        shares    = fund_obj.get_total_units()
        avg_price = fund_obj.get_avg_nav() or 0.0
        cost      = shares * avg_price
        if current is not None:
            total_val = shares * current
            pl        = total_val - cost
            pl_pct    = (pl / cost * 100) if cost else 0.0

    return [
        name,
        _fmt(shares, 4, ""),
        _fmt(avg_price),
        _fmt(current),
        _fmt(total_val),
        _fmt(pl),
        _fmt_pct(pl_pct),
        _fmt(sp.get("-1d")),
        _fmt_pct(sp.get("%1d")),
        _fmt(sp.get("-1w")),
        _fmt_pct(sp.get("%1w")),
        _fmt(sp.get("-1m")),
        _fmt_pct(sp.get("%1m")),
    ]


# ── Cell colour logic ─────────────────────────────────────────────────────────

def _cell_color(col_key: str, raw_value, sp: Dict) -> Optional[QColor]:
    """
    Return a QColor for a cell or None to use the default text colour.
    Percentage columns: green > 0, red < 0, yellow == 0 or None.
    Short % column: red > 10, normal > 5, green <= 2.
    """
    if raw_value is None:
        return None

    # Percentage columns
    pct_keys = {"%1d", "%2d", "%3d", "%1w", "%2w", "%1m", "%3m", "%6m", "%1y", "_pl_pct"}
    if col_key in pct_keys:
        try:
            v = float(raw_value)
            return QColor(Colors.POSITIVE) if v > 0 else (QColor(Colors.NEGATIVE) if v < 0 else QColor(Colors.NEUTRAL))
        except (TypeError, ValueError):
            return None

    # Historical absolute columns — colour relative to current price
    hist_keys = {"-1d", "-2d", "-3d", "-1w", "-2w", "-1m", "-3m", "-6m", "-1y"}
    if col_key in hist_keys:
        cur = sp.get("current_native") if sp.get("current_native") is not None else sp.get("current")
        if cur is None:
            return None
        try:
            h = float(raw_value)
            c = float(cur)
            return QColor(Colors.POSITIVE) if c > h else (QColor(Colors.NEGATIVE) if c < h else QColor(Colors.NEUTRAL))
        except (TypeError, ValueError):
            return None

    # Short percentage
    if col_key == "_short_pct":
        try:
            v = float(raw_value)
            if v > 10:
                return QColor(Colors.NEGATIVE)
            if v <= 2:
                return QColor(Colors.POSITIVE)
        except (TypeError, ValueError):
            pass
        return None

    # Short delta
    if col_key == "_short_chg":
        try:
            v = float(raw_value)
            return QColor(Colors.NEGATIVE) if v > 0 else (QColor(Colors.POSITIVE) if v < 0 else None)
        except (TypeError, ValueError):
            return None

    # P/L absolute
    if col_key == "_pl":
        try:
            v = float(raw_value)
            return QColor(Colors.POSITIVE) if v > 0 else (QColor(Colors.NEGATIVE) if v < 0 else None)
        except (TypeError, ValueError):
            return None

    return None


# ── Watch Table (shared base) ─────────────────────────────────────────────────

class WatchTable(QTableWidget):
    """Base class for the coloured, read-only watch tables."""

    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self._columns = columns
        self._setup()

    def _setup(self):
        self.setColumnCount(len(self._columns))
        self.setHorizontalHeaderLabels([c[0] for c in self._columns])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setMinimumSectionSize(50)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setShowGrid(True)
        self.setFont(monospace_font(12))
        self.horizontalHeader().setFont(monospace_font(12))

        # Set column widths
        for col_idx, (_, _, width, _, _) in enumerate(self._columns):
            self.setColumnWidth(col_idx, width)

        # Stretch last column to fill remaining space
        self.horizontalHeader().setStretchLastSection(True)

    def _make_item(self, text: str, align: str, bg: QColor, fg: Optional[QColor] = None) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        if align == "right":
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        elif align == "center":
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        else:
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        item.setBackground(QBrush(bg))
        item.setForeground(QBrush(fg if fg else QColor(Colors.TEXT)))
        return item

    def _add_separator_row(self, label: str, col_count: int):
        row = self.rowCount()
        self.insertRow(row)
        self.setRowHeight(row, 22)
        item = QTableWidgetItem(f"  {label}")
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setBackground(QBrush(GROUP_BG["separator"]))
        item.setForeground(QBrush(QColor(Colors.TEXT_HEADER)))
        font = QFont(monospace_font(11))
        font.setBold(True)
        item.setFont(font)
        self.setItem(row, 0, item)
        for c in range(1, col_count):
            filler = QTableWidgetItem("")
            filler.setFlags(Qt.ItemFlag.ItemIsEnabled)
            filler.setBackground(QBrush(GROUP_BG["separator"]))
            self.setItem(row, c, filler)

    def _add_blank_row(self, col_count: int):
        row = self.rowCount()
        self.insertRow(row)
        self.setRowHeight(row, 6)
        for c in range(col_count):
            item = QTableWidgetItem("")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setBackground(QBrush(QColor(Colors.BACKGROUND)))
            self.setItem(row, c, item)


# ── Stocks Table ──────────────────────────────────────────────────────────────

class StocksTable(WatchTable):

    def __init__(self, parent=None):
        super().__init__(STOCKS_COLUMNS, parent)

    def populate(self, stock_prices: List[Dict], portfolio, short_data: Dict, short_trend: Dict):
        self.setUpdatesEnabled(False)
        self.setRowCount(0)

        # Group
        owned, highlighted, other, indices = _group(stock_prices, portfolio)

        def _add_group(group: List[Dict], group_key: str):
            bg = GROUP_BG[group_key]
            for sp in group:
                if sp.get("_blank"):
                    continue
                row_idx = self.rowCount()
                self.insertRow(row_idx)
                self.setRowHeight(row_idx, 24)
                cells = _build_stocks_row(sp, portfolio, short_data, short_trend)
                for col_idx, (_, col_key, _, align, is_numeric) in enumerate(STOCKS_COLUMNS):
                    raw = sp.get(col_key)
                    cell_text = cells[col_idx]
                    fg = _cell_color(col_key, raw, sp)
                    self.setItem(row_idx, col_idx, self._make_item(cell_text, align, bg, fg))

        # Owned
        if owned:
            _add_group(owned, "owned")
            if highlighted or other:
                self._add_blank_row(len(STOCKS_COLUMNS))

        # Highlighted / watchlist
        if highlighted:
            _add_group(highlighted, "highlighted")
            if other:
                self._add_blank_row(len(STOCKS_COLUMNS))

        # Others
        if other:
            _add_group(other, "other")

        # Indices
        if indices:
            if owned or highlighted or other:
                self._add_blank_row(len(STOCKS_COLUMNS))
            self._add_separator_row("Market Indices", len(STOCKS_COLUMNS))
            _add_group(indices, "index")

        self.setUpdatesEnabled(True)


# ── Shares Table ──────────────────────────────────────────────────────────────

class SharesTable(WatchTable):

    def __init__(self, parent=None):
        super().__init__(SHARES_COLUMNS, parent)

    def populate(self, stock_prices: List[Dict], portfolio):
        self.setUpdatesEnabled(False)
        self.setRowCount(0)

        owned, highlighted, _, _ = _group(stock_prices, portfolio)
        owned_and_highlighted = owned + highlighted

        if not owned_and_highlighted:
            self.setUpdatesEnabled(True)
            return

        for sp in owned_and_highlighted:
            row_idx = self.rowCount()
            self.insertRow(row_idx)
            self.setRowHeight(row_idx, 24)
            cells = _build_shares_row(sp, portfolio)

            # Colour P/L cell
            bg = GROUP_BG["owned"] if sp in owned else GROUP_BG["highlighted"]

            for col_idx, (_, col_key, _, align, _) in enumerate(SHARES_COLUMNS):
                raw = sp.get(col_key) if col_key not in ("_pl", "_pl_pct", "_shares", "_avg_price", "_total_val") else None
                fg  = _cell_color(col_key, raw, sp)

                # For computed columns, parse from formatted string
                if col_key == "_pl":
                    try:
                        fg = _cell_color("_pl", float(cells[col_idx].replace(",", "").replace("%","").strip()), sp)
                    except Exception:
                        pass
                elif col_key == "_pl_pct":
                    try:
                        fg = _cell_color("_pl_pct", float(cells[col_idx].replace(",", "").replace("%","").strip()), sp)
                    except Exception:
                        pass

                self.setItem(row_idx, col_idx, self._make_item(cells[col_idx], align, bg, fg))

        self.setUpdatesEnabled(True)


# ── Grouping helper ───────────────────────────────────────────────────────────

def _group(stock_prices: List[Dict], portfolio):
    """Replicate StockGrouper.group_stocks() without the curses dependency."""
    owned, highlighted, other, indices = [], [], [], []
    for sp in stock_prices:
        ticker = sp.get("ticker", "")
        name   = sp.get("name", "")

        if ticker.startswith("^"):
            indices.append(sp)
            continue

        # Managed fund
        if sp.get("_is_fund"):
            funds    = getattr(portfolio, "funds", {})
            fund_obj = funds.get(name)
            has_units = fund_obj and fund_obj.get_total_units() > 0
            if has_units:
                owned.append(sp)
            elif portfolio.is_highlighted(name):
                highlighted.append(sp)
            else:
                other.append(sp)
            continue

        stock_obj = getattr(portfolio, "stocks", {}).get(name)
        has_shares = stock_obj and sum(h.volume for h in stock_obj.holdings) > 0

        if has_shares:
            owned.append(sp)
        elif portfolio.is_highlighted(name):
            highlighted.append(sp)
        else:
            other.append(sp)

    return owned, highlighted, other, indices


# ── Totals footer ─────────────────────────────────────────────────────────────

class TotalsBar(QFrame):
    """Compact footer row showing aggregated portfolio totals."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.SURFACE};
                border-top: 1px solid {Colors.BORDER};
            }}
        """)
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(24)

        self._labels: Dict[str, QLabel] = {}
        for key in ("total_value", "total_pl", "total_pl_pct", "daily_pl", "daily_pl_pct"):
            lbl = QLabel("—")
            lbl.setFont(monospace_font(12))
            lbl.setStyleSheet(f"color: {Colors.TEXT_DIM};")
            layout.addWidget(lbl)
            self._labels[key] = lbl
        layout.addStretch()

    def update_totals(self, stock_prices: List[Dict], portfolio):
        total_val = 0.0
        total_cost = 0.0
        daily_pl = 0.0

        for sp in stock_prices:
            name = sp.get("name", "")
            current = sp.get("current_native") if sp.get("current_native") is not None else sp.get("current")
            if current is None:
                continue

            stock_obj = getattr(portfolio, "stocks", {}).get(name)
            if stock_obj and hasattr(stock_obj, "holdings") and stock_obj.holdings:
                shares = sum(h.volume for h in stock_obj.holdings)
                cost   = sum(h.volume * h.price for h in stock_obj.holdings)
                val    = shares * current
                total_val  += val
                total_cost += cost

                day_ago = sp.get("-1d")
                if day_ago and shares:
                    daily_pl += (current - float(day_ago)) * shares

        pl     = total_val - total_cost
        pl_pct = (pl / total_cost * 100) if total_cost else 0.0
        d_pct  = (daily_pl / (total_val - daily_pl) * 100) if (total_val - daily_pl) else 0.0

        def _col(v: float) -> str:
            return Colors.POSITIVE if v > 0 else (Colors.NEGATIVE if v < 0 else Colors.NEUTRAL)

        self._labels["total_value"].setText(f"Total: {total_val:,.0f}")
        self._labels["total_value"].setStyleSheet(f"color: {Colors.TEXT};")

        self._labels["total_pl"].setText(f"P/L: {pl:+,.0f}")
        self._labels["total_pl"].setStyleSheet(f"color: {_col(pl)};")

        self._labels["total_pl_pct"].setText(f"({pl_pct:+.2f}%)")
        self._labels["total_pl_pct"].setStyleSheet(f"color: {_col(pl_pct)};")

        self._labels["daily_pl"].setText(f"Today: {daily_pl:+,.0f}")
        self._labels["daily_pl"].setStyleSheet(f"color: {_col(daily_pl)};")

        self._labels["daily_pl_pct"].setText(f"({d_pct:+.2f}%)")
        self._labels["daily_pl_pct"].setStyleSheet(f"color: {_col(d_pct)};")


# ── Main Watch Widget ─────────────────────────────────────────────────────────

class WatchWidget(QWidget):
    """
    The live watch screen — Phase 2 main deliverable.

    Wired into MainWindow as page index 0.
    Receives a portfolio instance after it has been loaded.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.portfolio      = None
        self._prices: List[Dict] = []
        self._short_data: Dict   = {}
        self._short_trend: Dict  = {}

        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[PriceWorker]    = None

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(500)
        self._refresh_timer.timeout.connect(self._tick_refresh_countdown)
        self._countdown = 0
        self._refresh_interval_s = 15

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ──
        toolbar = QFrame()
        toolbar.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.SURFACE};
                border-bottom: 1px solid {Colors.BORDER};
            }}
        """)
        toolbar.setFixedHeight(44)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(10, 4, 10, 4)
        tb_layout.setSpacing(8)

        # Tab toggle (stocks / shares)
        self.tab_btn_stocks = QPushButton("📈  Stocks")
        self.tab_btn_stocks.setCheckable(True)
        self.tab_btn_stocks.setChecked(True)
        self.tab_btn_stocks.setFixedWidth(110)
        self.tab_btn_stocks.toggled.connect(lambda _: self._show_stocks_view())

        self.tab_btn_shares = QPushButton("🗂  Shares")
        self.tab_btn_shares.setCheckable(True)
        self.tab_btn_shares.setFixedWidth(110)
        self.tab_btn_shares.toggled.connect(lambda _: self._show_shares_view())

        # Refresh controls
        self.refresh_btn = QPushButton("⟳  Refresh")
        self.refresh_btn.setFixedWidth(100)
        self.refresh_btn.clicked.connect(self._manual_refresh)

        self.refresh_label = QLabel("Auto-refresh: —")
        self.refresh_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")

        # Last updated
        self.last_update_label = QLabel("Last update: —")
        self.last_update_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")

        self.stock_count_label = QLabel("")
        self.stock_count_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")

        tb_layout.addWidget(self.tab_btn_stocks)
        tb_layout.addWidget(self.tab_btn_shares)
        tb_layout.addSpacing(12)
        tb_layout.addWidget(self.refresh_btn)
        tb_layout.addWidget(self.refresh_label)
        tb_layout.addStretch()
        tb_layout.addWidget(self.stock_count_label)
        tb_layout.addSpacing(12)
        tb_layout.addWidget(self.last_update_label)

        root.addWidget(toolbar)

        # ── Stacked table area ──
        self.stocks_table = StocksTable()
        self.shares_table = SharesTable()
        self.shares_table.hide()

        # Loading overlay shown before first data arrives
        self.loading_label = QLabel("⟳  Waiting for price data…")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 15px;")

        root.addWidget(self.stocks_table)
        root.addWidget(self.shares_table)
        root.addWidget(self.loading_label)

        self.stocks_table.hide()

        # ── Totals footer ──
        self.totals_bar = TotalsBar()
        root.addWidget(self.totals_bar)

    # ── Portfolio wiring ──────────────────────────────────────────────────────

    def set_portfolio(self, portfolio):
        """Called by MainWindow once the portfolio has finished loading."""
        self.portfolio = portfolio
        self._start_worker()

    def _start_worker(self):
        if self._worker_thread:
            return

        self._worker_thread = QThread()
        self._worker = PriceWorker(self.portfolio, interval_ms=self._refresh_interval_s * 1000)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.start_polling)
        self._worker.prices_ready.connect(self._on_prices)
        self._worker.error.connect(self._on_error)

        self._worker_thread.start()
        self._refresh_timer.start()

    def _stop_worker(self):
        self._refresh_timer.stop()
        if self._worker:
            self._worker.stop_polling()
        if self._worker_thread:
            self._worker_thread.quit()
            # Don't block — let the OS clean up any in-flight network call
            self._worker_thread.wait(300)

    # ── Data updates ──────────────────────────────────────────────────────────

    @pyqtSlot(list)
    def _on_prices(self, prices: List[Dict]):
        self._prices = prices
        self._countdown = self._refresh_interval_s * 2  # half-second ticks
        self._repopulate()
        self.last_update_label.setText(f"Last update: {datetime.now().strftime('%H:%M:%S')}")
        n = sum(1 for p in prices if not p.get("_blank") and not p.get("_separator"))
        self.stock_count_label.setText(f"{n} stocks")

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        self.last_update_label.setText(f"Error: {msg[:60]}")
        self.last_update_label.setStyleSheet(f"color: {Colors.NEGATIVE}; font-size: 11px;")

    def _repopulate(self):
        self.loading_label.hide()

        if self.tab_btn_stocks.isChecked():
            self.stocks_table.show()
            self.shares_table.hide()
            if self.portfolio:
                self.stocks_table.populate(self._prices, self.portfolio, self._short_data, self._short_trend)
        else:
            self.shares_table.show()
            self.stocks_table.hide()
            if self.portfolio:
                self.shares_table.populate(self._prices, self.portfolio)

        if self.portfolio:
            self.totals_bar.update_totals(self._prices, self.portfolio)

    def _tick_refresh_countdown(self):
        if self._countdown > 0:
            self._countdown -= 1
        secs = self._countdown // 2
        self.refresh_label.setText(f"Auto-refresh: {secs}s")

    def _manual_refresh(self):
        """Trigger an immediate price fetch."""
        if self._worker:
            self._worker._fetch()

    # ── View mode toggles ─────────────────────────────────────────────────────

    def _show_stocks_view(self):
        self.tab_btn_stocks.setChecked(True)
        self.tab_btn_shares.setChecked(False)
        self._repopulate()

    def _show_shares_view(self):
        self.tab_btn_shares.setChecked(True)
        self.tab_btn_stocks.setChecked(False)
        self._repopulate()

    # ── Keyboard shortcuts (s = toggle, r = refresh) ─────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key in (Qt.Key.Key_S, Qt.Key.Key_Return):
            if self.tab_btn_stocks.isChecked():
                self._show_shares_view()
            else:
                self._show_stocks_view()
        elif key == Qt.Key.Key_R:
            self._manual_refresh()
        else:
            super().keyPressEvent(event)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._stop_worker()
        event.accept()
