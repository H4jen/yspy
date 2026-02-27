#!/usr/bin/env python3
"""
yspy - Fund Data Providers

Abstract interface and Avanza implementation for fetching NAV prices
for Swedish mutual funds that lack Yahoo Finance ticker symbols.

Avanza's unofficial public API is used for funds available on their platform.
Other providers (Nordnet, Morningstar, …) can be added by subclassing
FundDataProvider.

Supported providers
-------------------
  AvanzaFundProvider   — uses Avanza orderbook ID to fetch NAV + history

Example::

    provider = AvanzaFundProvider()
    nav = provider.get_current_nav("41567")          # e.g. Swedbank Robur Teknik
    df  = provider.get_historical_nav("41567", 365)  # one year of daily NAV

Project: https://github.com/H4jen/yspy
"""

from __future__ import annotations

import datetime
import logging
import time
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache TTL constants
# ---------------------------------------------------------------------------
_NAV_CACHE_TTL     = 300    # seconds – current NAV refreshed every 5 min
_HISTORY_CACHE_TTL = 3600   # seconds – historical data refreshed every hour

# ---------------------------------------------------------------------------
# HTTP headers to mimic a regular browser visit
# ---------------------------------------------------------------------------
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
    "Referer": "https://www.avanza.se/",
}


# ===========================================================================
# Abstract base class
# ===========================================================================

class FundDataProvider(ABC):
    """
    Interface every fund data provider must implement.

    A provider is an object that knows how to look up a fund by its
    provider-specific *fund_id* and return pricing data.  The rest of yspy
    only calls this interface, so swapping providers is trivial.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of this provider (e.g. 'Avanza')."""

    @abstractmethod
    def get_current_nav(self, fund_id: str) -> Optional[float]:
        """
        Return the latest NAV (Net Asset Value) for the fund.

        Args:
            fund_id: Provider-specific identifier (e.g. Avanza orderbook ID).

        Returns:
            NAV in the fund's native currency, or *None* on failure.
        """

    @abstractmethod
    def get_currency(self, fund_id: str) -> str:
        """
        Return the ISO 4217 currency code for the fund's NAV
        (e.g. 'SEK', 'EUR').  Defaults to 'SEK' if unknown.
        """

    @abstractmethod
    def get_historical_nav(
        self, fund_id: str, days: int = 365
    ) -> Optional[pd.DataFrame]:
        """
        Return historical daily NAV data.

        Args:
            fund_id: Provider-specific identifier.
            days:    Approximate number of calendar days of history to fetch.

        Returns:
            DataFrame with a DatetimeIndex named 'Date' and at least a
            'Close' column with NAV values in the fund's native currency.
            Returns *None* on failure.
        """

    def get_fund_info(self, fund_id: str) -> Dict[str, Any]:
        """
        Return a metadata dict for the fund (name, ISIN, risk rating …).
        Base implementation returns an empty dict; override if the provider
        exposes metadata.
        """
        return {}


# ===========================================================================
# Avanza implementation
# ===========================================================================

# Development-field name → approximate days ago
_AVANZA_DEV_FIELDS: list[tuple[str, int]] = [
    ("developmentOneDay",        1),
    ("developmentOneMonth",     30),
    ("developmentThreeMonths",  91),
    ("developmentSixMonths",   182),
    ("developmentOneYear",     365),
    ("developmentThreeYears", 1095),
]


class AvanzaFundProvider(FundDataProvider):
    """
    Fetch fund NAV data from Avanza's public REST API.

    Endpoints used (no authentication required):

    1. ``/_api/fund-guide/guide/{avanza_id}``
       Returns fund metadata (name, ISIN, currency) and the current NAV plus
       period-based development percentages (1-day, 1-month, … 3-years).
       These are back-calculated into sparse historical data points.

    2. ``/_api/search/filtered-search`` (POST)
       Full-text / ISIN search returning ``hits[].orderBookId`` — used to
       resolve an ISIN string to an Avanza orderbook ID.

    The avanza_id is Avanza's internal *orderbook ID*, visible in the fund
    URL on avanza.se, e.g.
    ``https://www.avanza.se/fonder/om-fonden.html/1515259/...``  →  id = 1515259.
    """

    _BASE           = "https://www.avanza.se"
    _FUND_GUIDE_URL = _BASE + "/_api/fund-guide/guide/{avanza_id}"
    _SEARCH_URL     = _BASE + "/_api/search/filtered-search"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(_BROWSER_HEADERS)
        self._lock = threading.Lock()

        # In-memory caches: {fund_id: (fetched_at_unix, value)}
        self._nav_cache:     Dict[str, tuple] = {}
        self._history_cache: Dict[str, tuple] = {}
        self._info_cache:    Dict[str, tuple] = {}

    # ------------------------------------------------------------------
    # FundDataProvider interface
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "Avanza"

    def get_current_nav(self, fund_id: str) -> Optional[float]:
        """Return latest NAV in the fund's native currency (usually SEK)."""
        with self._lock:
            hit = self._nav_cache.get(fund_id)
            if hit and (time.time() - hit[0]) < _NAV_CACHE_TTL:
                return hit[1]

        info = self._fetch_fund_guide(fund_id)
        nav: Optional[float] = None
        if info:
            raw = info.get("nav")
            if raw is not None:
                nav = float(raw)

        if nav is not None:
            with self._lock:
                self._nav_cache[fund_id] = (time.time(), nav)

        return nav

    def get_currency(self, fund_id: str) -> str:
        """Return ISO 4217 currency code (defaults to 'SEK')."""
        info = self.get_fund_info(fund_id)
        return info.get("currency", "SEK")

    def get_historical_nav(
        self, fund_id: str, days: int = 365
    ) -> Optional[pd.DataFrame]:
        """
        Return sparse historical NAV as a DataFrame with a 'Close' column.

        Because Avanza's chart endpoint is not publicly accessible, history is
        back-calculated from the period development percentages returned by the
        fund-guide endpoint (1-day, 1-month, 3-months, 6-months, 1-year,
        3-years).  This gives 6-7 data points — enough for -1d / -1m display.
        """
        cache_key = f"{fund_id}_{days}"
        with self._lock:
            hit = self._history_cache.get(cache_key)
            if hit and (time.time() - hit[0]) < _HISTORY_CACHE_TTL:
                return hit[1]

        df = self._build_history_from_guide(fund_id, days)

        if df is not None:
            with self._lock:
                self._history_cache[cache_key] = (time.time(), df)

        return df

    def get_fund_info(self, fund_id: str) -> Dict[str, Any]:
        """Return metadata from the fund-guide endpoint (name, ISIN, currency …)."""
        with self._lock:
            hit = self._info_cache.get(fund_id)
            if hit and (time.time() - hit[0]) < _HISTORY_CACHE_TTL:
                return hit[1]

        info = self._fetch_fund_guide(fund_id) or {}
        with self._lock:
            self._info_cache[fund_id] = (time.time(), info)
        return info

    def resolve_isin(self, isin: str) -> Optional[str]:
        """
        Look up an ISIN and return the Avanza orderbook ID string, or None.

        Uses ``/_api/search/filtered-search`` (POST, no auth required).
        """
        payload = {
            "query": isin,
            "instrumentTypes": ["FUND"],
            "pagination": {"from": 0, "size": 5},
        }
        try:
            resp = self._session.post(
                self._SEARCH_URL, json=payload, timeout=self.timeout
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            # Prefer exact ISIN match, fall back to first hit
            for hit in hits:
                if hit.get("isin", "").upper() == isin.upper():
                    return str(hit["orderBookId"])
            if hits:
                return str(hits[0]["orderBookId"])
        except Exception as exc:
            logger.debug("AvanzaFundProvider.resolve_isin(%s): %s", isin, exc)
        return None

    # ------------------------------------------------------------------
    # Private HTTP helpers
    # ------------------------------------------------------------------

    def _fetch_fund_guide(self, avanza_id: str) -> Optional[Dict[str, Any]]:
        """
        GET /_api/fund-guide/guide/{id}

        Returns the raw JSON dict from Avanza, or None on any error.
        Key fields: name, isin, currency, nav, navDate,
                    developmentOneDay, developmentOneMonth, …
        """
        url = self._FUND_GUIDE_URL.format(avanza_id=avanza_id)
        try:
            resp = self._session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.debug("AvanzaFundProvider._fetch_fund_guide(%s): %s", avanza_id, exc)
            return None

    def _build_history_from_guide(
        self, avanza_id: str, days: int
    ) -> Optional[pd.DataFrame]:
        """
        Build a sparse historical DataFrame from the development percentages
        returned by the fund-guide endpoint.

        Each ``developmentXxx`` field holds the cumulative percentage change
        since that period started.  Back-calculating::

            price_n_days_ago = current_nav / (1 + dev_pct / 100)

        Only data points within the requested *days* window are included.
        """
        info = self._fetch_fund_guide(avanza_id)
        if not info:
            return None

        nav = info.get("nav")
        if nav is None:
            return None
        nav = float(nav)

        today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        dates:  list[datetime.datetime] = [today]
        prices: list[float]             = [nav]

        for field, days_ago in _AVANZA_DEV_FIELDS:
            if days_ago > days:
                continue
            dev_pct = info.get(field)
            if dev_pct is None:
                continue
            try:
                past_nav = nav / (1.0 + float(dev_pct) / 100.0)
                dates.append(today - datetime.timedelta(days=days_ago))
                prices.append(past_nav)
            except (ZeroDivisionError, TypeError, ValueError):
                continue

        if len(dates) < 2:
            return None

        df = pd.DataFrame(
            {"Close": prices},
            index=pd.DatetimeIndex(dates),
        )
        df.index.names = ["Date"]
        df.sort_index(inplace=True)
        return df


# ===========================================================================
# Provider registry – easy lookup by name
# ===========================================================================

_REGISTRY: Dict[str, type] = {
    "avanza": AvanzaFundProvider,
}


def get_provider(name: str = "avanza", **kwargs) -> FundDataProvider:
    """
    Return an instantiated FundDataProvider by registry name.

    Args:
        name:    Provider name (case-insensitive).  Currently: 'avanza'.
        **kwargs: Passed to the provider constructor.

    Raises:
        ValueError: If the provider name is not registered.
    """
    key = name.strip().lower()
    cls = _REGISTRY.get(key)
    if cls is None:
        raise ValueError(
            f"Unknown fund provider '{name}'. "
            f"Registered providers: {list(_REGISTRY)}"
        )
    return cls(**kwargs)
