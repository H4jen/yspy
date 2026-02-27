#!/usr/bin/env python3
"""
yspy - Fund Manager

FundPrice and Fund classes for tracking Swedish mutual funds (or any
fund with an Avanza orderbook ID) that have no Yahoo Finance ticker.

These classes are deliberately designed to be drop-in compatible with the
existing StockPrice / Stock interface so the Watch, Profit, and correlation
screens work without modification.

Data is persisted in the portfolio directory:
  managedFunds.json         – fund registry  {name: {avanza_id, isin, currency}}
  <name>_fund.json          – per-fund purchase lots

Project: https://github.com/H4jen/yspy
"""

from __future__ import annotations

import datetime
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Synthetic "ticker" prefix so fund rows are distinguishable in the UI
FUND_TICKER_PREFIX = "FUND:"


# ===========================================================================
# FundPrice  (mirrors StockPrice interface)
# ===========================================================================

class FundPrice:
    """
    Price information for a managed fund.

    Provides the same ``get_current_sek()`` / ``get_historical_close()``
    interface as ``StockPrice`` so the existing display and profit code
    works unchanged.
    """

    def __init__(
        self,
        current_nav: Optional[float],
        currency: str,
        history_df: Optional[pd.DataFrame],
        currency_manager=None,        # CurrencyManager – optional SEK conversion
    ):
        self.current  = current_nav   # NAV in native currency
        self.currency = currency
        self._history  = history_df   # DataFrame with DatetimeIndex + 'Close' (native)
        self._cm       = currency_manager

        # Mimic StockPrice attrs used by profit calculations
        self.high    = current_nav
        self.low     = current_nav
        self.opening = current_nav

    # ------------------------------------------------------------------
    # StockPrice-compatible helpers
    # ------------------------------------------------------------------

    def get_current_sek(self) -> Optional[float]:
        """Return latest NAV converted to SEK."""
        if self.current is None:
            return None
        return round(self._to_sek(self.current), 4)

    def get_high_sek(self) -> Optional[float]:
        return self.get_current_sek()

    def get_low_sek(self) -> Optional[float]:
        return self.get_current_sek()

    def get_opening_sek(self) -> Optional[float]:
        return self.get_current_sek()

    def get_historical_close(self, days_ago: int) -> Optional[float]:
        """Return close NAV *days_ago* trading days back, in SEK."""
        if self._history is None or self._history.empty:
            return None
        try:
            idx = -(days_ago + 1)
            if abs(idx) > len(self._history):
                return None
            nav = float(self._history["Close"].iloc[idx])
            import math
            if math.isnan(nav):
                return None
            return round(self._to_sek(nav), 4)
        except Exception:
            return None

    def get_historical_close_native(self, days_ago: int) -> Optional[float]:
        """Return close NAV in the fund's native currency (no conversion)."""
        if self._history is None or self._history.empty:
            return None
        try:
            idx = -(days_ago + 1)
            if abs(idx) > len(self._history):
                return None
            nav = float(self._history["Close"].iloc[idx])
            import math
            return None if math.isnan(nav) else nav
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _to_sek(self, value: float) -> float:
        if self._cm is None or self.currency == "SEK":
            return value
        rate = self._cm.exchange_rates.get(self.currency, 1.0)
        return value * rate


# ===========================================================================
# Holdings
# ===========================================================================

class FundUnitsItem:
    """Represents a single purchase lot of fund units."""

    def __init__(
        self,
        volume: float,          # number of units bought
        price:  float,          # NAV at purchase (native currency)
        date:   str,            # "MM/DD/YYYY"
        uid:    str = "",
    ):
        self.volume = float(volume)
        self.price  = float(price)
        self.date   = date
        self.uid    = uid or str(uuid.uuid4())

    def to_list(self) -> list:
        return [self.volume, self.price, self.date, self.uid]


# ===========================================================================
# Fund
# ===========================================================================

class Fund:
    """
    A managed mutual fund tracked without a Yahoo Finance ticker.

    Attributes:
        name       – human-readable name (portfolio key)
        avanza_id  – Avanza orderbook ID string, e.g. "41567"
        isin       – ISIN code for reference, e.g. "SE0000677916"
        currency   – ISO 4217 currency of the fund's NAV (usually 'SEK')
        ticker     – Synthetic identifier used in UI dicts: "FUND:<avanza_id>"
        holdings   – list of FundUnitsItem (purchase lots)
    """

    def __init__(
        self,
        name:       str,
        avanza_id:  str,
        isin:       str,
        currency:   str,
        data_manager,       # src.portfolio_manager.DataManager
        provider,           # src.fund_provider.FundDataProvider
        currency_manager=None,   # src.portfolio_manager.CurrencyManager
    ):
        self.name            = name
        self.avanza_id       = avanza_id
        self.isin            = isin
        self.currency        = currency
        self.data_manager    = data_manager
        self.provider        = provider
        self.currency_manager = currency_manager

        # Synthetic ticker used in all price-dict rows (keeps UI key compatibility)
        self.ticker = f"{FUND_TICKER_PREFIX}{avanza_id}"

        # Holdings file
        safe_name = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        self._holdings_file = os.path.join(
            data_manager.base_path,
            f"{safe_name}_fund.json",
        )
        # Profit file – same naming convention as stocks
        self._profit_file = os.path.join(
            data_manager.base_path,
            f"{safe_name}_profit.json",
        )
        # Transaction ledger – append-only, never modified, full buy/sell history
        self._transactions_file = os.path.join(
            data_manager.base_path,
            f"{safe_name}_transactions.json",
        )

        # Holdings
        self.holdings: List[FundUnitsItem] = []
        self._load_holdings()

        # Price cache
        self._price_cache: Optional[FundPrice] = None
        self._price_cache_ts: float = 0.0
        self._price_cache_ttl: float = 300.0  # 5 minutes

    # ------------------------------------------------------------------
    # Price info  (same interface as Stock.get_price_info)
    # ------------------------------------------------------------------

    def get_price_info(self) -> Optional[FundPrice]:
        """Return a FundPrice object (cached for up to 5 minutes)."""
        now = time.time()
        if (
            self._price_cache is not None
            and (now - self._price_cache_ts) < self._price_cache_ttl
        ):
            return self._price_cache

        try:
            nav     = self.provider.get_current_nav(self.avanza_id)
            history = self.provider.get_historical_nav(self.avanza_id, days=375)
            self._price_cache    = FundPrice(nav, self.currency, history, self.currency_manager)
            self._price_cache_ts = now
        except Exception as exc:
            logger.warning("Fund.get_price_info(%s): %s", self.name, exc)
            # Serve stale cache rather than None to avoid display crashes
            if self._price_cache is None:
                self._price_cache = FundPrice(None, self.currency, None, self.currency_manager)

        return self._price_cache

    def invalidate_price_cache(self):
        """Force a fresh fetch on the next get_price_info() call."""
        self._price_cache_ts = 0.0

    # ------------------------------------------------------------------
    # Holdings persistence
    # ------------------------------------------------------------------

    def _load_holdings(self):
        data = self.data_manager.load_json(self._holdings_file)
        if data and isinstance(data, list):
            for item in data:
                if len(item) >= 4:
                    volume, price, date, uid = item[:4]
                    self.holdings.append(FundUnitsItem(float(volume), float(price), date, uid))

    def save_holdings(self) -> bool:
        save_data = [lot.to_list() for lot in self.holdings]
        return self.data_manager.save_json(self._holdings_file, save_data)

    # ------------------------------------------------------------------
    # Holdings mutations  (same interface as Stock)
    # ------------------------------------------------------------------

    def add_units(self, volume: float, price: float, fee: float = 0.0) -> bool:
        """Record a purchase of *volume* units at *price* NAV (native currency)."""
        if volume <= 0:
            logger.error("Fund.add_units: volume must be > 0")
            return False
        today = datetime.date.today().strftime("%m/%d/%Y")
        lot = FundUnitsItem(volume, price, today)
        self.holdings.append(lot)
        if not self.save_holdings():
            return False
        self._append_transaction({
            "type":         "buy",
            "date":         datetime.date.today().strftime("%Y-%m-%d"),
            "date_display": today,
            "uid":          lot.uid,
            "volume":       volume,
            "price":        price,
            "amount":       round(volume * price, 6),
            "fee":          fee,
            "currency":     self.currency,
        })
        return True

    def remove_units_fifo(self, volume: float) -> bool:
        """
        Remove *volume* units using FIFO order (oldest lots first).
        Returns False if there are not enough units to sell.
        """
        available = self.get_total_units()
        if volume > available:
            logger.error(
                "Fund.remove_units_fifo: requested %.4f > available %.4f",
                volume, available,
            )
            return False

        remaining = volume
        new_holdings: List[FundUnitsItem] = []
        for lot in self.holdings:
            if remaining <= 0:
                new_holdings.append(lot)
            elif lot.volume <= remaining:
                remaining -= lot.volume          # fully consume this lot
            else:
                lot.volume -= remaining          # partially consume
                remaining = 0
                new_holdings.append(lot)

        self.holdings = new_holdings
        return self.save_holdings()

    def sell_units(self, volume: float, sell_price: float, fee: float = 0.0) -> bool:
        """
        FIFO sell *volume* units at *sell_price* (native currency).

        Writes a profit record to *_profit_file* in the same JSON format
        as the stock sell flow so that menu 8 and menu 9 pick it up.

        Returns True on success.
        """
        available = self.get_total_units()
        if volume > available:
            logger.error(
                "Fund.sell_units: requested %.4f > available %.4f",
                volume, available,
            )
            return False

        today = datetime.date.today().strftime("%m/%d/%Y")

        profit_records: List[Dict[str, Any]] = []
        remaining = volume
        new_holdings: List[FundUnitsItem] = []

        for lot in self.holdings:
            if remaining <= 0:
                new_holdings.append(lot)
                continue

            if lot.volume <= remaining:
                # Fully consume this lot
                sell_vol = lot.volume
                remaining -= lot.volume
            else:
                # Partially consume
                sell_vol = remaining
                lot.volume -= remaining
                remaining = 0
                new_holdings.append(lot)

            profit = (sell_price - lot.price) * sell_vol
            profit_records.append({
                "stockName": self.name,
                "uid":       lot.uid,
                "buy_price": lot.price,
                "sell_price": sell_price,
                "volume":    sell_vol,
                "profit":    profit,
                "buy_date":  lot.date,
                "sell_date": today,
            })

        self.holdings = new_holdings
        if not self.save_holdings():
            return False

        # Append profit records to _profit_file
        try:
            existing: List[Dict[str, Any]] = self.data_manager.load_json(self._profit_file) or []
            existing.extend(profit_records)
            self.data_manager.save_json(self._profit_file, existing)
        except Exception as exc:
            logger.error("Fund.sell_units: failed to write profit records: %s", exc)

        # Append one sell entry per consumed lot to the transaction ledger
        today_display = datetime.date.today().strftime("%m/%d/%Y")
        today_iso     = datetime.date.today().strftime("%Y-%m-%d")
        for rec in profit_records:
            self._append_transaction({
                "type":         "sell",
                "date":         today_iso,
                "date_display": today_display,
                "uid":          rec["uid"],
                "volume":       rec["volume"],
                "price":        rec["sell_price"],
                "amount":       round(rec["volume"] * rec["sell_price"], 6),
                "fee":          fee,
                "currency":     self.currency,
                "buy_price":    rec["buy_price"],
                "buy_date":     rec["buy_date"],
                "profit":       rec["profit"],
            })

        return True

    # ------------------------------------------------------------------
    # Transaction ledger
    # ------------------------------------------------------------------

    def _append_transaction(self, entry: Dict[str, Any]) -> None:
        """
        Append one entry to the append-only transaction log.
        Failures are logged but never raise — the holdings file is authoritative.
        """
        try:
            records: List[Dict[str, Any]] = (
                self.data_manager.load_json(self._transactions_file) or []
            )
            records.append(entry)
            self.data_manager.save_json(self._transactions_file, records)
        except Exception as exc:
            logger.error("Fund._append_transaction(%s): %s", self.name, exc)

    def get_transactions(self) -> List[Dict[str, Any]]:
        """
        Return all transactions sorted by date (oldest first).

        Each entry has at minimum:
          type, date (YYYY-MM-DD), date_display (MM/DD/YYYY),
          uid, volume, price, amount, fee, currency

        Sell entries additionally carry:
          buy_price, buy_date, profit
        """
        records = self.data_manager.load_json(self._transactions_file) or []
        try:
            records.sort(key=lambda r: r.get("date", ""))
        except Exception:
            pass
        return records

    # Alias matching the 'add_shares' / 'remove_shares' vocabulary used elsewhere
    def add_shares(self, volume: float, price: float, fee: float = 0.0) -> bool:
        return self.add_units(volume, price, fee)

    # ------------------------------------------------------------------
    # Aggregates  (same interface as Stock)
    # ------------------------------------------------------------------

    def get_total_units(self) -> float:
        """Total number of fund units held."""
        return sum(lot.volume for lot in self.holdings)

    # Alias used by existing UI code that calls get_total_shares()
    def get_total_shares(self) -> float:
        return self.get_total_units()

    def get_average_price(self) -> float:
        """Weighted-average purchase NAV (native currency)."""
        total_units = self.get_total_units()
        if total_units == 0:
            return 0.0
        total_cost = sum(lot.volume * lot.price for lot in self.holdings)
        return total_cost / total_units

    def to_dict(self) -> Dict[str, Any]:
        """Serialise fund metadata (does not include holdings)."""
        return {
            "avanza_id": self.avanza_id,
            "isin":      self.isin,
            "currency":  self.currency,
        }

    def __repr__(self) -> str:
        return (
            f"Fund(name={self.name!r}, avanza_id={self.avanza_id!r}, "
            f"isin={self.isin!r}, units={self.get_total_units():.4f})"
        )
