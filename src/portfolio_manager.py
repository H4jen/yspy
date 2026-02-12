"""
yspy - Portfolio Management Engine

This module provides classes for managing stock portfolios, real-time price tracking,
fully automated historical data management, and currency conversion.

Project: https://github.com/H4jen/yspy

Key Features:
- Real-time stock price monitoring with configurable update intervals
- Fully automated background historical data updates (no manual intervention needed)
- Automatic detection and updating of stale historical data
- Currency conversion with cached exchange rates
- Comprehensive error handling and logging
- Thread-safe operations for concurrent access

Example usage:
    ```python
    from portfolio_lib_refactored import Portfolio, HistoricalMode, Config
    
    # Create portfolio with custom configuration
    config = Config()
    config.DEFAULT_TICK_SECONDS = 10.0  # Update every 10 seconds
    config.HISTORICAL_UPDATE_INTERVAL = 300.0  # Update historical data every 5 minutes
    
    portfolio = Portfolio(
        path="/path/to/portfolio",
        filename="my_portfolio.json",
        historical_mode=HistoricalMode.BACKGROUND,
        verbose=True,
        config=config
    )
    
    # Add a stock (historical data will be loaded and automatically updated)
    portfolio.add_stock("Apple", "AAPL")
    
    # Add shares
    portfolio.add_shares("Apple", 100, 150.0)
    
    # Get stock details (includes up-to-date historical data)
    details = portfolio.get_stock_details()
    print(f"Portfolio value: {sum(d['market_value'] for d in details):.2f} SEK")
    
    # Check update statistics
    stats = portfolio.get_update_stats()
    print(f"Continuous updates running: {stats['historical_updates']['continuous_updates_running']}")
    
    # Historical data is always kept up-to-date automatically
    ```

Classes:
    Config: Configuration settings including historical update intervals
    HistoricalMode: Historical data loading strategies
    CurrencyManager: Currency conversion and exchange rates
    DataManager: File I/O operations
    StockPrice: Real-time and historical price data
    TickerValidator: Ticker symbol validation
    HistoricalDataManager: Automated historical data fetching, caching, and staleness detection
    RealTimeDataManager: Real-time price monitoring
    Stock: Individual stock with holdings
    Portfolio: Main portfolio management class with fully automated updates

Exceptions:
    StockError: Base exception for stock-related errors
    InvalidTickerError: Invalid ticker symbol
    CurrencyError: Currency conversion failures
"""

import yfinance as yf
import os
import json
import pathlib
from json import JSONDecodeError
import datetime
import contextlib
import uuid
import time
import threading
import requests
from typing import Dict, List, Optional, Tuple, Any, Union, Set
import pandas as pd
import re
import logging
from dataclasses import dataclass
from enum import Enum


# Configuration and logging setup
logger = logging.getLogger(__name__)

# Set up file-only logging to prevent console interference with ncurses
# But don't interfere with the main logging system or input handling
if not logger.handlers:
    file_handler = logging.FileHandler('yspy.log')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)


@dataclass
class Config:
    """
    Configuration settings for the portfolio system.
    
    Attributes:
        DEFAULT_TICK_SECONDS: Default interval for real-time updates (seconds)
        DEFAULT_HISTORICAL_PERIOD: Default period for historical data
        DEFAULT_HISTORICAL_INTERVAL: Default interval for historical data
        BULK_HISTORY_DAYS: Days of historical data to fetch in bulk
        API_TIMEOUT: Timeout for API requests (seconds)
        EXCHANGE_RATE_API_URLS: List of exchange rate API URLs
        CACHE_DIR: Directory name for cache files
        HISTORICAL_DIR: Directory name for historical data files
        HISTORICAL_UPDATE_INTERVAL: Interval for automatic historical data updates (seconds)
        HISTORICAL_STALE_THRESHOLD: Threshold for considering historical data stale (seconds)
        PRICE_SCALE_FACTORS: Mapping of ticker symbols to price scaling factors
    """
    DEFAULT_TICK_SECONDS: float = 10.0
    DEFAULT_HISTORICAL_PERIOD: str = "2y"  # Use 2 years to ensure enough data for 1-year lookback
    DEFAULT_HISTORICAL_INTERVAL: str = "1d"
    BULK_HISTORY_DAYS: int = 130
    API_TIMEOUT: int = 10
    EXCHANGE_RATE_API_URLS: List[str] = None
    CACHE_DIR: str = "portfolio"
    HISTORICAL_DIR: str = "historical"
    HISTORICAL_UPDATE_INTERVAL: float = 300.0  # Update historical data every 5 minutes
    HISTORICAL_STALE_THRESHOLD: float = 3600.0  # Consider data stale after 1 hour
    PRICE_SCALE_FACTORS: Dict[str, float] = None  # Ticker -> scale factor (e.g., HG=F: 2204.62 for USD/lb to USD/ton)
    
    def __post_init__(self):
        if self.EXCHANGE_RATE_API_URLS is None:
            self.EXCHANGE_RATE_API_URLS = [
                "https://api.exchangerate-api.com/v4/latest/SEK",
                "https://api.fixer.io/latest?base=SEK"
            ]
        if self.PRICE_SCALE_FACTORS is None:
            self.PRICE_SCALE_FACTORS = {
                "HG=F": 2204.62  # Copper: convert USD/lb to USD/metric ton
            }


class HistoricalMode(Enum):
    """
    Historical data loading strategies.
    
    Values:
        EAGER: Load all historical data immediately on startup (slower startup)
        BACKGROUND: Load historical data in background thread (faster startup)
        SKIP: Don't load historical data automatically (fastest startup)
    
    Note: Regardless of the loading strategy, historical data is now continuously
    updated in the background once the portfolio is initialized.
    """
    EAGER = "eager"
    BACKGROUND = "background"
    SKIP = "skip"


class StockError(Exception):
    """Base exception for stock-related errors."""
    pass


class InvalidTickerError(StockError):
    """Raised when a ticker symbol is invalid."""
    pass


class CurrencyError(StockError):
    """Raised when currency conversion fails."""
    pass


class CurrencyManager:
    """Manages currency exchange rates and conversions."""
    
    def __init__(self, portfolio_path: str = "", allow_online_lookup: bool = True, config: Config = None):
        self.config = config or Config()
        self.portfolio_path = portfolio_path
        self.allow_online_lookup = allow_online_lookup
        self.exchange_rates = {"SEK": 1.0}
        self.currency_cache_file = os.path.join(portfolio_path, "exchange_rates.json") if portfolio_path else "exchange_rates.json"
        self._lock = threading.Lock()
        
        # Currency mapping based on ticker suffixes
        # Note: .L (London) excluded - can be GBP, USD, or EUR depending on security
        self.suffix_currency_map = {
            'ST': 'SEK',  # Nasdaq Stockholm
            'HE': 'EUR',  # Helsinki
            'CO': 'DKK',  # Copenhagen
            'OL': 'NOK',  # Oslo
            'DE': 'EUR',  # Germany
            'FI': 'EUR',
            'DK': 'DKK',
            'NO': 'NOK',
            'AS': 'EUR',  # Amsterdam (Euronext)
            'PA': 'EUR',  # Paris (Euronext)
            'MI': 'EUR',  # Milan
            'SW': 'CHF',  # Swiss Exchange
        }
        
        # Static currency mapping for known tickers
        # This takes priority over suffix-based mapping for reliability
        self.static_currency_map = {
            # US stocks
            'AAPL': 'USD', 'GOOGL': 'USD', 'MSFT': 'USD', 'TSLA': 'USD', 'AMZN': 'USD',
            'META': 'USD', 'NFLX': 'USD', 'NVDA': 'USD',
            # European stocks
            'ASML': 'EUR', 'SAP': 'EUR',
            'NESN': 'CHF', 'NOVN': 'CHF', 
            'EQNR': 'NOK', 'DNB': 'NOK', 'MOWI': 'NOK',
            'NOVO-B': 'DKK', 'MAERSK-B': 'DKK', 'CARL-B': 'DKK',
            # London-listed ETCs/ETFs (often USD-denominated despite .L suffix)
            'SSLV.L': 'USD',   # Invesco Physical Silver
            'PHPT.L': 'USD',   # WisdomTree Physical Platinum
            'PHAG.L': 'USD',   # WisdomTree Physical Silver (London)
            'PHAU.L': 'USD',   # WisdomTree Physical Gold
            'PHPM.L': 'USD',   # WisdomTree Physical Precious Metals
            'SLVR.L': 'USD',   # iShares Physical Silver
            # Amsterdam-listed (EUR)
            'PHAG.AS': 'EUR',  # WisdomTree Physical Silver (Amsterdam)
        }
        
        # Default exchange rates (fallback)
        self.default_rates = {
            "SEK": 1.0,
            "USD": 10.75, "EUR": 11.76, "GBP": 13.70, "NOK": 0.98,
            "DKK": 1.59, "CHF": 12.05, "JPY": 0.073, "CAD": 7.95, "AUD": 7.12,
        }
        
        self._load_exchange_rates()
    
    def get_currency(self, ticker: str) -> str:
        """Get currency for a ticker symbol using multiple strategies."""
        ticker = ticker.upper()
        
        # Check static mapping first (full ticker with suffix)
        # This ensures known tickers like SSLV.L get correct currency
        if ticker in self.static_currency_map:
            return self.static_currency_map[ticker]
        
        # Check static mapping with base ticker (without suffix)
        base_ticker = ticker.split('.')[0]
        if base_ticker in self.static_currency_map:
            return self.static_currency_map[base_ticker]
        
        # Check suffix-based mapping
        suffix_match = re.search(r"\.([A-Z]{2,3})$", ticker)
        if suffix_match:
            suffix = suffix_match.group(1)
            if suffix in self.suffix_currency_map:
                return self.suffix_currency_map[suffix]
        
        # Optional online lookup
        if self.allow_online_lookup:
            try:
                info = yf.Ticker(ticker).info
                currency = info.get('currency')
                if currency:
                    return currency
            except Exception as e:
                logger.debug(f"Failed to get currency for {ticker} from yfinance: {e}")
        
        # Fallback to SEK
        logger.warning(f"Could not determine currency for {ticker}, defaulting to SEK")
        return 'SEK'
    
    def _load_exchange_rates(self):
        """Load cached exchange rates or download fresh ones."""
        today = datetime.date.today().strftime("%Y-%m-%d")
        
        # Try to load cached rates
        if os.path.exists(self.currency_cache_file):
            try:
                with open(self.currency_cache_file, 'r') as f:
                    cached_data = json.load(f)
                    if cached_data.get('date') == today:
                        self.exchange_rates = cached_data.get('rates', {"SEK": 1.0})
                        logger.info(f"Loaded cached exchange rates for {len(self.exchange_rates)} currencies")
                        return
            except Exception as e:
                logger.warning(f"Failed to load cached exchange rates: {e}")
        
        # Download fresh rates
        self._download_exchange_rates()
    
    def _download_exchange_rates(self):
        """Download current exchange rates to SEK."""
        today = datetime.date.today().strftime("%Y-%m-%d")
        
        for api_url in self.config.EXCHANGE_RATE_API_URLS:
            try:
                response = requests.get(api_url, timeout=self.config.API_TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    rates = {"SEK": 1.0}
                    
                    # Convert rates to "foreign currency to SEK"
                    for currency, rate in data['rates'].items():
                        if rate != 0:
                            rates[currency] = 1.0 / rate
                    
                    self.exchange_rates = rates
                    self._cache_exchange_rates(today, rates)
                    logger.info(f"Successfully fetched exchange rates for {len(rates)} currencies")
                    return
                    
            except Exception as e:
                logger.warning(f"Failed to fetch from {api_url}: {e}")
                continue
        
        # If all APIs fail, use default rates
        logger.warning("All exchange rate APIs failed, using default rates")
        self.exchange_rates = self.default_rates.copy()
        self._cache_exchange_rates(today, self.exchange_rates)
    
    def _cache_exchange_rates(self, date: str, rates: Dict[str, float]):
        """Cache exchange rates to file."""
        cache_data = {'date': date, 'rates': rates}
        try:
            with open(self.currency_cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to cache exchange rates: {e}")
    
    def convert_to_sek(self, amount: float, ticker: str) -> Optional[float]:
        """Convert an amount to SEK based on the ticker's currency."""
        if amount is None:
            return None
        
        currency = self.get_currency(ticker)
        if currency == "SEK":
            return amount
        
        with self._lock:
            rate = self.exchange_rates.get(currency)
            
        if rate is None:
            logger.warning(f"No exchange rate found for {currency}, refreshing rates")
            self._download_exchange_rates()
            with self._lock:
                rate = self.exchange_rates.get(currency, 1.0)
        
        return amount * rate


class DataManager:
    """Manages file I/O operations for portfolio data."""
    
    def __init__(self, base_path: str, config: Config = None):
        self.config = config or Config()
        self.base_path = base_path
        self.historical_dir = os.path.join(base_path, self.config.HISTORICAL_DIR)
        os.makedirs(self.historical_dir, exist_ok=True)
    
    def save_json(self, filepath: str, data: Any) -> bool:
        """Save data to JSON file."""
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save JSON to {filepath}: {e}")
            return False
    
    def load_json(self, filepath: str) -> Optional[Any]:
        """Load data from JSON file."""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except JSONDecodeError:
            logger.warning(f"Invalid JSON in {filepath}")
            return None
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Failed to load JSON from {filepath}: {e}")
            return None
    
    def save_csv(self, df: pd.DataFrame, filepath: str) -> bool:
        """Save DataFrame to CSV file."""
        try:
            df.to_csv(filepath)
            return True
        except Exception as e:
            logger.error(f"Failed to save CSV to {filepath}: {e}")
            return False
    
    def load_csv(self, filepath: str, **kwargs) -> Optional[pd.DataFrame]:
        """Load DataFrame from CSV file."""
        try:
            return pd.read_csv(filepath, **kwargs)
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Failed to load CSV from {filepath}: {e}")
            return None
    
    def get_historical_filepath(self, ticker: str, period: str, interval: str, 
                               convert_to_sek: bool = True) -> str:
        """Get filepath for historical data CSV."""
        suffix = "_SEK" if convert_to_sek else ""
        filename = f"{ticker}_{period}_{interval}{suffix}.csv"
        return os.path.join(self.historical_dir, filename)
    
    def ensure_file_exists(self, filepath: str):
        """Ensure file exists, create if it doesn't."""
        if not os.path.exists(filepath):
            pathlib.Path(filepath).touch()


class StockSharesItem:
    """Represents a stock purchase (shares, price, date)."""
    
    def __init__(self, volume: int, price: float, date: str, uid: str = None):
        self.volume = volume
        self.price = price
        self.date = date
        self.uid = uid or str(uuid.uuid4())

    def __hash__(self):
        return hash((self.volume, self.price, self.date, self.uid))

    def __eq__(self, other):
        if not isinstance(other, StockSharesItem):
            return False
        return (self.volume, self.price, self.date, self.uid) == (other.volume, other.price, other.date, other.uid)


class StockPrice:
    """Manages real-time and historical price data for a single stock."""
    
    def __init__(self, ticker: str, currency_manager: CurrencyManager, data_manager: 'DataManager' = None, 
                 historical_data_manager: 'HistoricalDataManager' = None, verbose: bool = False, config: Config = None):
        self.ticker = ticker
        self.currency_manager = currency_manager
        self.currency = currency_manager.get_currency(ticker)
        self.data_manager = data_manager  # DataManager for file paths
        self.historical_data_manager = historical_data_manager  # HistoricalDataManager for bulk operations
        self.verbose = verbose
        self.config = config or Config()
        
        # Price scaling factor for commodities
        self.price_scale = self.config.PRICE_SCALE_FACTORS.get(ticker, 1.0)
        
        # Current price data (in original currency)
        self.latest_data = None
        self.current = self.high = self.low = self.opening = None
        
        # Historical data cache
        self._historical_cache = {}
        self._bulk_hist_df = None
        self._bulk_hist_fetch_date = None
    
    def update_from_yfinance_data(self, data):
        """Update price attributes from yfinance data."""
        self.latest_data = data
        if data is not None and len(data.values) > 0:
            # Find the last row with non-NaN Close price
            # This handles cases where different stocks have data on different dates
            # (e.g., USA stocks from yesterday, Swedish stocks from today)
            import math
            values = None
            for i in range(len(data.values) - 1, -1, -1):
                row = data.values[i]
                if len(row) > 0 and not math.isnan(row[0]):  # Check Close price
                    values = row
                    break
            
            if values is not None:
                self.current = round(values[0] * self.price_scale, 2) if len(values) > 0 else None
                self.high = round(values[1] * self.price_scale, 2) if len(values) > 1 else None
                self.low = round(values[2] * self.price_scale, 2) if len(values) > 2 else None
                self.opening = round(values[3] * self.price_scale, 2) if len(values) > 3 else None
            else:
                self.current = self.high = self.low = self.opening = None
        else:
            self.current = self.high = self.low = self.opening = None
    
    def get_current_sek(self) -> Optional[float]:
        """Get current price in SEK."""
        if self.current is None:
            return None
        return self.currency_manager.convert_to_sek(self.current, self.ticker)
    
    def get_high_sek(self) -> Optional[float]:
        """Get high price in SEK."""
        if self.high is None:
            return None
        return self.currency_manager.convert_to_sek(self.high, self.ticker)
    
    def get_low_sek(self) -> Optional[float]:
        """Get low price in SEK."""
        if self.low is None:
            return None
        return self.currency_manager.convert_to_sek(self.low, self.ticker)
    
    def get_opening_sek(self) -> Optional[float]:
        """Get opening price in SEK."""
        if self.opening is None:
            return None
        return self.currency_manager.convert_to_sek(self.opening, self.ticker)
    
    def get_historical_close(self, days_ago: int) -> Optional[float]:
        """Get historical close price in SEK for N days ago."""
        cache_key = f"{days_ago}_{self.currency}"
        if cache_key in self._historical_cache:
            return self._historical_cache[cache_key]
        
        close = self._fetch_historical_close(days_ago)
        if close is not None:
            # close is already in SEK from _fetch_historical_close
            # (it reads from *_SEK.csv files which are already converted)
            self._historical_cache[cache_key] = close
            return close
        
        self._historical_cache[cache_key] = None
        return None
    
    def get_historical_close_native(self, days_ago: int) -> Optional[float]:
        """Get historical close price in native currency for N days ago."""
        close_sek = self.get_historical_close(days_ago)
        if close_sek is None:
            return None
        
        # Convert back to native currency
        if self.currency == 'SEK':
            return close_sek
        
        # Divide by exchange rate to get native currency
        rate = self.currency_manager.exchange_rates.get(self.currency, 1.0)
        if rate == 0:
            return close_sek
        return close_sek / rate
    
    def _fetch_historical_close(self, days_ago: int) -> Optional[float]:
        """Fetch historical close price from cached files, bulk data, or yfinance."""
        today = datetime.date.today()
        
        # First try to load from cached CSV files
        try:
            filepath = self.data_manager.get_historical_filepath(
                self.ticker, 
                "2y",  # Use 2y period to ensure we have data for 1y lookback
                "1d",  # Daily interval
                convert_to_sek=True
            )
            
            if os.path.exists(filepath):
                # Check if file is not stale (within threshold)
                file_mtime = os.path.getmtime(filepath)
                current_time = time.time()
                age_seconds = current_time - file_mtime
                
                # Use cached file if it's fresh (not older than threshold)
                if age_seconds <= 3600.0:  # 1 hour threshold
                    df = self.data_manager.load_csv(filepath, index_col=0, parse_dates=True)
                    if df is not None and not df.empty:
                        # Check if recent trading days are missing from CSV
                        import datetime as dt
                        today_date = dt.datetime.now().date()
                        
                        # For 1-day lookups, check if yesterday (last trading day) is missing
                        if days_ago == 1:
                            yesterday = today_date - dt.timedelta(days=1)
                            while yesterday.weekday() >= 5:  # Skip weekends
                                yesterday -= dt.timedelta(days=1)
                            
                            yesterday_exists = any(d.date() == yesterday for d in df.index)
                            if not yesterday_exists:
                                logger.warning(f"CSV missing recent trading day {yesterday}, trying hourly reconstruction")
                                hourly_result = self._try_hourly_reconstruction(days_ago)
                                if hourly_result is not None:
                                    return hourly_result
                        
                        # Use CSV data if we have enough
                        if len(df) >= days_ago + 1:
                            close_price = float(df['Close'].iloc[-(days_ago + 1)])
                            # Check for NaN values from pandas
                            import math
                            if math.isnan(close_price):
                                if self.verbose:
                                    logger.debug(f"Cached data returned NaN for {self.ticker} ({days_ago} days ago)")
                                # Try intraday reconstruction for recent dates with NaN values
                                if days_ago <= 7:
                                    logger.info(f"CSV has NaN for recent date ({days_ago} days ago), trying intraday fallback")
                                    hourly_result = self._try_hourly_reconstruction(days_ago)
                                    if hourly_result is not None:
                                        return hourly_result
                                return None
                            if self.verbose:
                                logger.debug(f"Used cached historical data for {self.ticker} ({days_ago} days ago)")
                            return close_price
                        
        except Exception as e:
            logger.debug(f"Error loading cached historical data for {self.ticker}: {e}")
        
        # Use bulk historical data if available and fresh
        if (self._bulk_hist_df is not None and 
            self._bulk_hist_fetch_date == today and
            not self._bulk_hist_df.empty):
            try:
                import math
                if len(self._bulk_hist_df) >= days_ago + 1:
                    close_price = float(self._bulk_hist_df['Close'].iloc[-(days_ago + 1)])
                    # Check for NaN values from pandas
                    if math.isnan(close_price):
                        if self.verbose:
                            logger.debug(f"Bulk data returned NaN for {self.ticker} ({days_ago} days ago)")
                        return None
                    return close_price
                elif len(self._bulk_hist_df) > 0:
                    close_price = float(self._bulk_hist_df['Close'].iloc[0])
                    # Check for NaN values from pandas
                    if math.isnan(close_price):
                        if self.verbose:
                            logger.debug(f"Bulk data returned NaN for {self.ticker} (oldest available)")
                        return None
                    return close_price
            except Exception as e:
                logger.debug(f"Error accessing bulk historical data for {self.ticker}: {e}")
        
        # Fallback to individual fetch
        try:
            if self.verbose:
                logger.debug(f"Fetching individual historical data for {self.ticker} (fallback)")
            hist = yf.Ticker(self.ticker).history(period="2y")  # Get 2 years to support 1y lookback
            if not hist.empty:
                # Check if recent daily data is missing (enhanced detection)
                import datetime as dt
                today_date = dt.datetime.now().date()
                
                # Look for missing recent trading days (skip weekends)
                recent_missing = False
                missing_date = None
                
                for days_back in range(1, 6):  # Check last 5 business days
                    check_date = today_date - dt.timedelta(days=days_back)
                    
                    # Skip weekends
                    if check_date.weekday() >= 5:  # Saturday=5, Sunday=6
                        continue
                    
                    # Check if this date exists in the daily data
                    date_exists = any(d.date() == check_date for d in hist.index)
                    if not date_exists:
                        logger.warning(f"Missing recent trading day {check_date} ({check_date.strftime('%A')}) for {self.ticker}")
                        recent_missing = True
                        missing_date = check_date
                        
                        # Special handling for 1-day lookups when yesterday is missing
                        if days_ago == 1 and days_back == 1:
                            logger.info(f"1-day lookup but yesterday ({check_date}) is missing - checking hourly data")
                            break
                        break
                
                # If recent data is missing, force hourly reconstruction
                if recent_missing:
                    logger.info(f"Recent trading data missing for {self.ticker}, trying hourly reconstruction")
                    hourly_result = self._try_hourly_reconstruction(days_ago)
                    if hourly_result is not None:
                        return hourly_result
                
                # Use the regular daily data if no issues detected
                self._bulk_hist_df = hist
                self._bulk_hist_fetch_date = today
                
                import math
                if len(hist) >= days_ago + 1:
                    close_price = float(hist['Close'].iloc[-(days_ago + 1)])
                    # Check for NaN values from pandas
                    if math.isnan(close_price):
                        if self.verbose:
                            logger.debug(f"Individual fetch returned NaN for {self.ticker} ({days_ago} days ago)")
                        return None
                    return close_price
                elif len(hist) > 0:
                    close_price = float(hist['Close'].iloc[0])
                    # Check for NaN values from pandas
                    if math.isnan(close_price):
                        if self.verbose:
                            logger.debug(f"Individual fetch returned NaN for {self.ticker} (oldest available)")
                        return None
                    return close_price
        except Exception as e:
            logger.error(f"Failed to fetch historical data for {self.ticker}: {e}")
        
        # Final fallback: Try hourly reconstruction
        return self._try_hourly_reconstruction(days_ago)
    
    def _try_hourly_reconstruction(self, days_ago: int) -> Optional[float]:
        """Try to reconstruct daily close from intraday data (1-minute for recent dates)."""
        try:
            import datetime as dt
            target_date = dt.date.today() - dt.timedelta(days=days_ago)
            
            # Skip weekends when calculating target date
            while target_date.weekday() >= 5:  # Skip Saturday/Sunday
                target_date -= dt.timedelta(days=1)
                days_ago += 1
            
            logger.info(f"Attempting intraday data reconstruction for {self.ticker} on {target_date}")
            
            # For recent dates (within 7 days), use 1-minute data for highest accuracy
            # This is especially important for Stockholm Exchange and other markets
            days_from_today = (dt.date.today() - target_date).days
            
            if days_from_today <= 7:
                # Use 1-minute interval for recent dates - gets last data point of the day
                logger.debug(f"Using 1-minute interval for recent date ({days_from_today} days ago)")
                hist_intraday = yf.Ticker(self.ticker).history(period="7d", interval="1m")
            else:
                # Use hourly for older dates
                logger.debug(f"Using hourly interval for older date ({days_from_today} days ago)")
                hist_intraday = yf.Ticker(self.ticker).history(period="14d", interval="1h")
            
            if hist_intraday is not None and not hist_intraday.empty:
                logger.debug(f"Retrieved {len(hist_intraday)} data points for {self.ticker}")
                
                # Group by date and get the LAST data point for each day (closing price)
                daily_data = hist_intraday.groupby(hist_intraday.index.date).agg({
                    'Close': 'last',  # Last price of the day = closing price
                    'Volume': 'sum',
                    'High': 'max',
                    'Low': 'min'
                })
                
                # Log available trading days
                available_dates = list(daily_data.index)
                logger.info(f"Intraday data shows trading on: {available_dates[-5:]}")
                
                if target_date in available_dates:
                    target_close = daily_data.loc[target_date, 'Close']
                    target_volume = daily_data.loc[target_date, 'Volume']
                    
                    logger.info(f"✅ Found {target_date} in intraday data: Close={target_close:.2f}, Volume={target_volume}")
                    
                    # Verify this was actual trading (not just stale data)
                    if target_volume > 0:
                        logger.info(f"Confirmed trading activity on {target_date} (Volume: {target_volume})")
                        return float(target_close)
                    else:
                        logger.warning(f"No trading volume on {target_date}, may be holiday")
                else:
                    logger.warning(f"❌ Target date {target_date} not found in intraday data")
                    
                    # Show what dates we do have around that time
                    nearby_dates = [d for d in available_dates if abs((d - target_date).days) <= 3]
                    logger.info(f"Nearby dates in intraday data: {nearby_dates}")
                
                # Fallback: use the most recent available data
                if len(daily_data) >= days_ago + 1:
                    fallback_close = daily_data['Close'].iloc[-(days_ago + 1)]
                    fallback_date = daily_data.index[-(days_ago + 1)]
                    logger.info(f"Fallback: Using {fallback_date} close: {fallback_close:.2f}")
                    return float(fallback_close)
                    
        except Exception as e:
            logger.debug(f"Intraday data reconstruction failed for {self.ticker}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        return None
    
    def clear_cache(self):
        """Clear all cached data."""
        self._historical_cache.clear()
        self._bulk_hist_df = None
        self._bulk_hist_fetch_date = None


class TickerValidator:
    """Validates ticker symbols using yfinance."""
    
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()
        self._yf_lock = threading.Lock()  # Lock for yfinance API calls
    
    def is_valid(self, ticker: str, use_cache: bool = True) -> bool:
        """Check if a ticker is valid."""
        if not ticker or not isinstance(ticker, str):
            return False
        
        ticker = ticker.strip().upper()
        
        if use_cache:
            with self._lock:
                cached = self._cache.get(ticker)
                if cached is not None:
                    return cached
        
        valid = self._validate_ticker(ticker)
        
        if use_cache:
            with self._lock:
                self._cache[ticker] = valid
        
        return valid
    
    def _validate_ticker(self, ticker: str) -> bool:
        """Validate ticker using yfinance."""
        try:
            # Try downloading 1 day of data with thread safety
            with self._yf_lock:
                df = yf.download(ticker, period="1d", progress=False, auto_adjust=True)
            if df is not None and not df.empty:
                return True
            
            # Fallback to ticker info
            info = yf.Ticker(ticker).info
            return bool(info and ("regularMarketPrice" in info or "symbol" in info))
            
        except Exception as e:
            logger.debug(f"Ticker validation failed for {ticker}: {e}")
            return False


class HistoricalDataManager:
    """Manages historical stock data fetching and caching."""
    
    def __init__(self, data_manager: DataManager, currency_manager: CurrencyManager, config: Config = None):
        self.data_manager = data_manager
        self.currency_manager = currency_manager
        self.config = config or Config()
        self._cache = {}
        self._yf_call_count = 0
        self._yf_last_call_time = None
        self._lock = threading.Lock()
        # Separate lock for yfinance API calls to prevent threading issues
        self._yf_lock = threading.Lock()
    
    def _record_yf_call(self):
        """Record a yfinance API call for statistics."""
        with self._lock:
            self._yf_call_count += 1
            self._yf_last_call_time = datetime.datetime.now()
    
    def get_call_stats(self) -> Tuple[int, Optional[datetime.datetime]]:
        """Get yfinance call statistics."""
        with self._lock:
            return self._yf_call_count, self._yf_last_call_time
    
    def load_historical_data(self, ticker: str, period: str = "1y", interval: str = "1d",
                           convert_to_sek: bool = True) -> Optional[pd.DataFrame]:
        """Load historical data for a ticker (automatic staleness detection with fallback)."""
        cache_key = f"{ticker}|{period}|{interval}|{'SEK' if convert_to_sek else 'RAW'}"
        today_iso = datetime.date.today().isoformat()
        
        # Always check cache first
        cached = self._cache.get(cache_key)
        cached_data = cached.get('data') if cached and cached.get('date') == today_iso else None
        
        # If no cache data, try to load from file as backup
        if cached_data is None:
            cached_data = self._load_from_file_fallback(ticker, period, interval, convert_to_sek)
            if cached_data is not None:
                # Cache the file data
                self._cache[cache_key] = {"date": today_iso, "data": cached_data}
        
        # If data is not stale, return cached data
        if not self.is_historical_data_stale(ticker, period, interval) and cached_data is not None:
            return cached_data
        
        # Data is stale or missing, try to fetch fresh data
        logger.info(f"Fetching fresh historical data for {ticker} (stale or missing)")
        df = self._fetch_from_yfinance(ticker, period, interval)
        
        if df is not None and not df.empty:
            # Fresh data fetch succeeded
            # Convert to SEK if requested
            if convert_to_sek:
                df = self._convert_dataframe_to_sek(df, ticker)
            
            # Cache the fresh result
            self._cache[cache_key] = {"date": today_iso, "data": df}
            logger.info(f"Successfully refreshed historical data for {ticker}")
            return df
        else:
            # Fresh data fetch failed - fall back to cached data if available
            if cached_data is not None:
                logger.warning(f"Failed to fetch fresh data for {ticker}, using stale cached data as fallback")
                return cached_data
            else:
                # No cached data and fetch failed
                logger.error(f"No historical data available for {ticker} (fetch failed and no cached data)")
                return None
    
    def _load_from_file_fallback(self, ticker: str, period: str, interval: str, convert_to_sek: bool) -> Optional[pd.DataFrame]:
        """Load historical data from file as fallback when cache is empty."""
        try:
            filepath = self.data_manager.get_historical_filepath(ticker, period, interval, convert_to_sek)
            if os.path.exists(filepath):
                # Suppress FutureWarning about mixed timezones
                import warnings
                with warnings.catch_warnings():
                    warnings.filterwarnings('ignore', category=FutureWarning)
                    df = pd.read_csv(filepath, index_col=0, parse_dates=True)
                if not df.empty:
                    logger.debug(f"Loaded fallback data from file for {ticker}: {filepath}")
                    return df
        except Exception as e:
            logger.debug(f"Failed to load fallback data from file for {ticker}: {e}")
        
        return None
    
    def _fetch_from_yfinance(self, ticker: str, period: str, interval: str) -> Optional[pd.DataFrame]:
        """Fetch data from yfinance with retries."""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                self._record_yf_call()
                df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
                
                if self._is_valid_price_data(df):
                    return df
                    
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {ticker}: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(0.5)
        
        logger.error(f"Failed to fetch historical data for {ticker} after {max_attempts} attempts")
        return None
    
    def _is_valid_price_data(self, df: pd.DataFrame) -> bool:
        """Validate that DataFrame contains valid price data."""
        if df is None or df.empty:
            return False
        
        price_cols = [c for c in ["Open", "High", "Low", "Close", "Adj Close"] if c in df.columns]
        if not price_cols:
            return False
        
        for col in price_cols:
            try:
                converted = pd.to_numeric(df[col], errors='coerce')
                if converted.isna().mean() >= 0.95:  # More than 95% NaN
                    return False
            except Exception:
                return False
        
        return True
    
    def _convert_dataframe_to_sek(self, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """Convert price columns in DataFrame to SEK and apply price scaling."""
        # Apply price scaling first (e.g., for commodities like copper)
        price_scale = self.config.PRICE_SCALE_FACTORS.get(ticker, 1.0)
        
        currency = self.currency_manager.get_currency(ticker)
        if currency == "SEK":
            df_copy = df.copy()
            # Still apply price scaling even for SEK
            if price_scale != 1.0:
                for col in ["Open", "High", "Low", "Close", "Adj Close"]:
                    if col in df_copy.columns:
                        df_copy[col] = df_copy[col].astype(float) * price_scale
            return df_copy
        
        rate = self.currency_manager.exchange_rates.get(currency)
        if rate is None or rate == 1.0:
            return df
        
        df_copy = df.copy()
        for col in ["Open", "High", "Low", "Close", "Adj Close"]:
            if col in df_copy.columns:
                # Apply both price scaling and currency conversion
                df_copy[col] = df_copy[col].astype(float) * price_scale * rate
        
        return df_copy
    
    def bulk_fetch_historical(self, tickers: List[str], period: str = "130d", 
                            interval: str = "1d") -> Dict[str, pd.DataFrame]:
        """Fetch historical data for multiple tickers in one call."""
        if not tickers:
            return {}

        ticker_string = " ".join(tickers)

        try:
            # Synchronize yfinance calls to prevent threading issues
            with self._yf_lock:
                self._record_yf_call()
                bulk_data = yf.download(ticker_string, period=period, interval=interval, 
                                      auto_adjust=True, progress=False, group_by='ticker')

            if bulk_data is None or bulk_data.empty:
                return {}

            results = {}
            multi_index = isinstance(bulk_data.columns, pd.MultiIndex)

            for ticker in tickers:
                try:
                    if multi_index:
                        # With group_by='ticker', tickers are in level 0
                        levels0 = bulk_data.columns.get_level_values(0)
                        if ticker in levels0:
                            ticker_data = bulk_data.xs(ticker, level=0, axis=1)
                            if not ticker_data.empty:
                                results[ticker] = ticker_data
                        else:
                            logger.warning(f"Ticker {ticker} not found in level 0: {list(set(levels0))}")
                    else:
                        # Non-MultiIndex case (should not happen with group_by='ticker')
                        if len(tickers) == 1:
                            results[ticker] = bulk_data
                        else:
                            logger.warning(f"Unexpected non-MultiIndex data for multiple tickers")

                except Exception as e:
                    logger.warning(f"Failed to extract data for {ticker}: {e}")

            return results

        except Exception as e:
            logger.error(f"Bulk fetch failed for tickers {tickers}: {e}")
            return {}

    def _validate_historical_data_quality(self, ticker: str, df: pd.DataFrame) -> List[str]:
        """Validate historical data quality and return list of issues found."""
        issues = []
        
        if df is None or df.empty:
            issues.append("empty_data")
            return issues
        
        try:
            # Check for required columns
            required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                issues.append(f"missing_columns_{missing_columns}")
            
            # Check for insufficient data (less than 30 days for 1y period)
            if len(df) < 30:
                issues.append(f"insufficient_data_{len(df)}_rows")
            
            # Check for flat/unchanging data (all Close prices identical)
            if 'Close' in df.columns and len(df) > 1:
                close_values = df['Close'].dropna()
                if len(close_values) > 5:  # Only check if we have enough data
                    unique_values = close_values.nunique()
                    if unique_values <= 1:
                        issues.append("flat_close_data")
                    elif unique_values < len(close_values) * 0.1:  # Less than 10% unique values
                        issues.append("suspicious_low_variance")
            
            # Check for excessive NaN values
            if 'Close' in df.columns:
                close_nan_pct = df['Close'].isna().sum() / len(df)
                if close_nan_pct > 0.15:  # More than 15% NaN (was 30%)
                    issues.append(f"excessive_nan_{close_nan_pct:.1%}")
                
                # Check for NaN values in recent data (last 30 days) - critical for percentage calculations
                if len(df) >= 30:
                    recent_close = df['Close'].tail(30)
                    recent_nan_count = recent_close.isna().sum()
                    if recent_nan_count > 0:
                        issues.append(f"recent_nan_{recent_nan_count}_in_last_30_days")
            
            # Check for unrealistic price changes (more than 500% in one day)
            if 'Close' in df.columns and len(df) > 1:
                close_values = df['Close'].dropna()
                if len(close_values) > 1:
                    price_changes = close_values.pct_change().abs()
                    extreme_changes = price_changes > 5.0  # 500%
                    if extreme_changes.any():
                        issues.append("extreme_price_changes")
            
            # Check for zero or negative prices
            if 'Close' in df.columns:
                invalid_prices = (df['Close'] <= 0).sum()
                if invalid_prices > 0:
                    issues.append(f"invalid_prices_{invalid_prices}")
                    
        except Exception as e:
            issues.append(f"validation_error_{str(e)[:50]}")
        
        return issues

    def get_problematic_tickers(self, tickers: List[str]) -> List[str]:
        """Get list of tickers with problematic historical data that need refresh.
        
        This method only checks cached files and does NOT make API calls.
        """
        problematic_tickers = []
        
        for ticker in tickers:
            try:
                # Check if cached file exists
                filepath = self.data_manager.get_historical_filepath(
                    ticker, 
                    self.config.DEFAULT_HISTORICAL_PERIOD,
                    self.config.DEFAULT_HISTORICAL_INTERVAL,
                    convert_to_sek=True
                )
                
                # If no file exists, mark as problematic
                if not os.path.exists(filepath):
                    problematic_tickers.append(ticker)
                    logger.debug(f"Ticker {ticker} has no cached historical data file")
                    continue
                
                # Load from file only (no API call)
                df = self._load_from_file_fallback(ticker, 
                                                   self.config.DEFAULT_HISTORICAL_PERIOD,
                                                   self.config.DEFAULT_HISTORICAL_INTERVAL,
                                                   convert_to_sek=True)
                
                if df is None or df.empty:
                    problematic_tickers.append(ticker)
                    logger.debug(f"Ticker {ticker} has empty cached data")
                    continue
                
                # Validate data quality
                issues = self._validate_historical_data_quality(ticker, df)
                
                if issues:
                    problematic_tickers.append(ticker)
                    logger.debug(f"Ticker {ticker} has data quality issues: {issues}")
                    
            except Exception as e:
                # If we can't even load the data, it's definitely problematic
                problematic_tickers.append(ticker)
                logger.debug(f"Failed to validate data for {ticker}: {e}")
        
        return problematic_tickers

    def force_refresh_ticker(self, ticker: str):
        """Force refresh of historical data for a ticker with safe fallback preservation."""
        cache_backup = {}
        
        try:
            # Preserve current cache data as backup before clearing
            cache_keys_to_remove = [key for key in self._cache.keys() if key.startswith(f"{ticker}|")]
            
            for key in cache_keys_to_remove:
                cache_backup[key] = self._cache[key].copy()  # Keep backup
            
            logger.info(f"Preserved {len(cache_backup)} cache entries as backup for {ticker}")
            
            # Remove from memory cache to force refresh
            for key in cache_keys_to_remove:
                del self._cache[key]
            
            # Try to fetch fresh data immediately
            fresh_data_success = False
            periods = ["1y"]  # Focus on main period first
            intervals = ["1d"]
            
            for period in periods:
                for interval in intervals:
                    try:
                        df = self._fetch_from_yfinance(ticker, period, interval)
                        if df is not None and not df.empty:
                            # Fresh data fetch succeeded, we can safely remove old files
                            fresh_data_success = True
                            break
                    except Exception as fetch_error:
                        logger.warning(f"Failed to fetch fresh data for {ticker} during force refresh: {fetch_error}")
                
                if fresh_data_success:
                    break
            
            if fresh_data_success:
                # Safe to remove old files since we have fresh data
                self._remove_historical_files(ticker)
                logger.info(f"Successfully force refreshed {ticker} with fresh data")
            else:
                # Restore cache backup since fresh fetch failed
                logger.warning(f"Fresh data fetch failed for {ticker}, restoring cache backup")
                for key, backup_data in cache_backup.items():
                    self._cache[key] = backup_data
                
                logger.warning(f"Force refresh failed for {ticker}, kept existing data as fallback")
            
        except Exception as main_error:
            # Restore backup on any error
            logger.error(f"Failed to force refresh ticker {ticker}: {main_error}")
            if cache_backup:
                logger.info(f"Restoring cache backup due to error")
                for key, backup_data in cache_backup.items():
                    self._cache[key] = backup_data
    
    def _remove_historical_files(self, ticker: str):
        """Remove historical data files for a ticker."""
        import os
        periods = ["1y", "6mo", "3mo", "1mo"]
        intervals = ["1d"]
        
        for period in periods:
            for interval in intervals:
                filepath = self.data_manager.get_historical_filepath(ticker, period, interval, convert_to_sek=True)
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                        logger.debug(f"Removed historical data file: {filepath}")
                    except Exception as e:
                        logger.warning(f"Failed to remove file {filepath}: {e}")

    def is_historical_data_stale(self, ticker: str, period: str = None, interval: str = None) -> bool:
        """Check if historical data for a ticker is stale and needs updating."""
        period = period or self.config.DEFAULT_HISTORICAL_PERIOD
        interval = interval or self.config.DEFAULT_HISTORICAL_INTERVAL
        
        # Check if we have cached data
        cache_key = f"{ticker}|{period}|{interval}|SEK"
        cached = self._cache.get(cache_key)
        
        if not cached:
            return True  # No cached data means it's stale
        
        # Check file modification time
        filepath = self.data_manager.get_historical_filepath(ticker, period, interval, convert_to_sek=True)
        if not os.path.exists(filepath):
            return True  # No file means it's stale
        
        try:
            file_mtime = os.path.getmtime(filepath)
            current_time = time.time()
            age_seconds = current_time - file_mtime
            
            return age_seconds > self.config.HISTORICAL_STALE_THRESHOLD
        except Exception as e:
            logger.warning(f"Could not check file modification time for {ticker}: {e}")
            return True  # If we can't check, assume it's stale

    def get_stale_tickers(self, tickers: List[str]) -> List[str]:
        """Get list of tickers that have stale historical data."""
        stale_tickers = []
        for ticker in tickers:
            if self.is_historical_data_stale(ticker):
                stale_tickers.append(ticker)
        return stale_tickers
class RealTimeDataManager:
    """Manages real-time stock price updates."""
    
    def __init__(self, currency_manager: CurrencyManager, 
                 data_manager: DataManager,
                 historical_manager: HistoricalDataManager, config: Config = None):
        self.currency_manager = currency_manager
        self.data_manager = data_manager
        self.historical_manager = historical_manager
        self.config = config or Config()
        
        self.stocks: Dict[str, StockPrice] = {}
        self.tick_seconds = self.config.DEFAULT_TICK_SECONDS
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # Statistics
        self._bulk_update_count = 0
        self._last_bulk_update_time = None
    
    def add_stock(self, ticker: str) -> bool:
        """Add a stock for real-time monitoring."""
        with self._lock:
            if ticker in self.stocks:
                return False
            
            self.stocks[ticker] = StockPrice(ticker, self.currency_manager, self.data_manager, self.historical_manager, verbose=True, config=self.config)
            return True
    
    def remove_stock(self, ticker: str) -> bool:
        """Remove a stock from monitoring."""
        with self._lock:
            if ticker in self.stocks:
                del self.stocks[ticker]
                return True
            return False
    
    def get_stock_price(self, ticker: str) -> Optional[StockPrice]:
        """Get current stock price data."""
        with self._lock:
            return self.stocks.get(ticker)
    
    def get_all_stock_prices(self) -> Dict[str, StockPrice]:
        """Get all monitored stock prices."""
        with self._lock:
            return self.stocks.copy()
    
    def set_tick_interval(self, seconds: float):
        """Set the update interval in seconds."""
        with self._lock:
            self.tick_seconds = seconds
    
    def start_monitoring(self):
        """Start real-time price monitoring."""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._update_loop, daemon=True)
            self._thread.start()
            logger.info("Started real-time price monitoring")
    
    def stop_monitoring(self):
        """Stop real-time price monitoring."""
        self._running = False
        if self._thread:
            self._thread.join()
            self._thread = None
            logger.info("Stopped real-time price monitoring")
    
    def _update_loop(self):
        """Background thread loop for price updates."""
        while self._running:
            try:
                start_time = time.time()
                self._bulk_update()
                
                # Calculate remaining time to maintain consistent interval
                elapsed = time.time() - start_time
                sleep_time = max(0, self.tick_seconds - elapsed)
                time.sleep(sleep_time)
            except Exception as e:
                logger.error(f"Error in update loop: {e}")
                time.sleep(self.tick_seconds)
    
    def _bulk_update(self):
        """Update all stock prices in a single yfinance call."""
        with self._lock:
            if not self.stocks:
                return
            
            tickers = list(self.stocks.keys())
            self._bulk_update_count += 1
            self._last_bulk_update_time = datetime.datetime.now()
        
        ticker_string = " ".join(tickers)
        
        try:
            # Synchronize yfinance calls to prevent threading issues
            with self.historical_manager._yf_lock:
                self.historical_manager._record_yf_call()
                bulk_data = yf.download(ticker_string, period="1d", auto_adjust=True, progress=False)
            
            # Update each stock with its data
            for ticker in tickers:
                stock_price = self.stocks.get(ticker)
                if not stock_price:
                    continue
                
                try:
                    if len(tickers) == 1:
                        # Single ticker - data is not nested
                        stock_price.update_from_yfinance_data(bulk_data)
                    else:
                        # Multiple tickers - extract data for this ticker
                        if not bulk_data.empty and ticker in bulk_data.columns.get_level_values(1):
                            ticker_data = bulk_data.xs(ticker, level=1, axis=1)
                            stock_price.update_from_yfinance_data(ticker_data)
                        else:
                            stock_price.update_from_yfinance_data(None)
                
                except Exception as e:
                    logger.warning(f"Failed to update {ticker}: {e}")
                    stock_price.update_from_yfinance_data(None)
                    
        except Exception as e:
            logger.error(f"Bulk update failed: {e}")
    
    def force_immediate_update(self):
        """Force an immediate price update, bypassing the normal sleep cycle."""
        self._bulk_update()
    
    def get_update_stats(self) -> Tuple[int, Optional[datetime.datetime]]:
        """Get update statistics."""
        with self._lock:
            return self._bulk_update_count, self._last_bulk_update_time
    
    def ensure_bulk_history(self):
        """Ensure bulk historical data is available for all tickers."""
        with self._lock:
            tickers = list(self.stocks.keys())
        
        if not tickers:
            return
        
        today = datetime.date.today()
        
        # Check if any stock needs fresh bulk history
        needs_update = False
        for ticker in tickers:
            stock_price = self.stocks.get(ticker)
            if (not stock_price or 
                stock_price._bulk_hist_fetch_date != today or 
                stock_price._bulk_hist_df is None):
                needs_update = True
                break
        
        if not needs_update:
            return
        
        # Fetch bulk historical data
        bulk_historical = self.historical_manager.bulk_fetch_historical(
            tickers, period=f"{self.config.BULK_HISTORY_DAYS}d"
        )
        
        # Update each stock's bulk historical data
        for ticker, df in bulk_historical.items():
            stock_price = self.stocks.get(ticker)
            if stock_price:
                stock_price._bulk_hist_df = df
                stock_price._bulk_hist_fetch_date = today


class Stock:
    """Represents a stock with holdings and price information."""
    
    def __init__(self, ticker: str, data_manager: DataManager, real_time_manager: RealTimeDataManager):
        self.ticker = ticker
        self.data_manager = data_manager
        self.real_time_manager = real_time_manager
        
        # File management
        self.file_name = ticker.replace(".", "_") + ".json"
        self.file_path = os.path.join(data_manager.base_path, self.file_name)
        self.data_manager.ensure_file_exists(self.file_path)
        
        # Holdings
        self.holdings: List[StockSharesItem] = []
        self._load_holdings()
    
    def _load_holdings(self):
        """Load holdings from file."""
        data = self.data_manager.load_json(self.file_path)
        if data:
            for item in data:
                if len(item) >= 4:
                    volume, price, date, uid = item[:4]
                    self.holdings.append(StockSharesItem(volume, price, date, uid))
    
    def get_price_info(self) -> Optional[StockPrice]:
        """Get current price information."""
        return self.real_time_manager.get_stock_price(self.ticker)
    
    def add_shares(self, volume: int, price: float) -> bool:
        """Add shares to holdings."""
        if volume <= 0:
            logger.error("Volume must be greater than 0")
            return False
        
        today = datetime.date.today().strftime("%m/%d/%Y")
        self.holdings.append(StockSharesItem(volume, price, today))
        return self.save_holdings()
    
    def save_holdings(self) -> bool:
        """Save holdings to file."""
        save_data = []
        for item in self.holdings:
            save_data.append([item.volume, item.price, item.date, item.uid])
        
        return self.data_manager.save_json(self.file_path, save_data)
    
    def get_total_shares(self) -> int:
        """Get total number of shares held."""
        return sum(holding.volume for holding in self.holdings)
    
    def get_average_price(self) -> float:
        """Get average purchase price of all holdings."""
        if not self.holdings:
            return 0.0
        
        total_cost = sum(holding.volume * holding.price for holding in self.holdings)
        total_shares = sum(holding.volume for holding in self.holdings)
        
        return total_cost / total_shares if total_shares > 0 else 0.0
    
    def sort_holdings_by_price(self, reverse: bool = False):
        """Sort holdings by price."""
        self.holdings.sort(key=lambda x: x.price, reverse=reverse)


class CapitalTracker:
    """Tracks capital flow in/out of portfolio and calculates time-weighted returns."""
    
    def __init__(self, data_manager: DataManager, currency_manager: CurrencyManager = None):
        self.data_manager = data_manager
        self.currency_manager = currency_manager
        self.events = []
        self.cash_balance = 0.0
        self.summary = {}
        self._capital_file = "portfolio_capital.json"
        self.load()
    
    def load(self):
        """Load capital tracking data from file."""
        filepath = os.path.join(self.data_manager.base_path, self._capital_file)
        
        if not os.path.exists(filepath):
            # Initialize empty structure
            self.events = []
            self.cash_balance = 0.0
            self.summary = {}
            return
        
        try:
            data = self.data_manager.load_json(filepath)
            if data:
                self.events = data.get('capital_events', [])
                cash_info = data.get('cash_balance', {})
                self.cash_balance = cash_info.get('current', 0.0)
                self.summary = data.get('summary', {})
                
                # If cash_balance is 0 but we have events, recalculate from events
                if self.cash_balance == 0.0 and len(self.events) > 0:
                    deposits = sum(e['amount'] for e in self.events if e['type'] in ['deposit', 'initial_deposit'])
                    withdrawals = sum(abs(e['amount']) for e in self.events if e['type'] == 'withdrawal')
                    buys = sum(e['amount'] for e in self.events if e['type'] == 'buy')
                    sells = sum(e['amount'] for e in self.events if e['type'] == 'sell')
                    self.cash_balance = deposits - withdrawals - buys + sells
                    logger.info(f"Recalculated cash balance from events: {self.cash_balance:.2f} SEK")
                
                # Update days_invested for all events
                self._update_days_invested()
                
                logger.info(f"Loaded {len(self.events)} capital events")
        except Exception as e:
            logger.error(f"Failed to load capital tracking data: {e}")
            self.events = []
            self.cash_balance = 0.0
            self.summary = {}
    
    def save(self):
        """Save capital tracking data to file."""
        filepath = os.path.join(self.data_manager.base_path, self._capital_file)
        
        # Update summary before saving
        self._update_summary()
        
        data = {
            'capital_events': self.events,
            'cash_balance': {
                'current': self.cash_balance,
                'last_updated': datetime.date.today().strftime("%Y-%m-%d")
            },
            'summary': self.summary
        }
        
        try:
            self.data_manager.save_json(filepath, data)
            logger.info(f"Saved capital tracking data with {len(self.events)} events")
        except Exception as e:
            logger.error(f"Failed to save capital tracking data: {e}")
    
    def is_initialized(self) -> bool:
        """Check if capital tracking has been initialized."""
        return len(self.events) > 0
    
    def initialize_manual(self, historical_deposits: list):
        """One-time initialization with historical deposits.
        
        Args:
            historical_deposits: List of tuples (date_str, amount, description)
                date_str format: "YYYY-MM-DD"
        """
        logger.info(f"Initializing capital tracking with {len(historical_deposits)} historical deposits")
        
        for date_str, amount, description in historical_deposits:
            event_id = str(uuid.uuid4())
            self.events.append({
                'id': event_id,
                'date': date_str,
                'type': 'deposit',
                'amount': float(amount),
                'description': description,
                'days_invested': self._calculate_days_invested(date_str)
            })
        
        # Set initial cash balance to sum of all deposits
        self.cash_balance = sum(e['amount'] for e in self.events)
        self._update_summary()
        self.save()
        
        logger.info(f"Capital tracking initialized: {len(self.events)} deposits, {self.cash_balance:.2f} SEK")
    
    def initialize_from_current_portfolio(self, portfolio_value: float):
        """Quick initialization using current portfolio value."""
        today = datetime.date.today().strftime("%Y-%m-%d")
        event_id = str(uuid.uuid4())
        
        self.events.append({
            'id': event_id,
            'date': today,
            'type': 'initial_deposit',
            'amount': float(portfolio_value),
            'description': 'Initial capital (estimated from current portfolio)',
            'days_invested': 0
        })
        
        self.cash_balance = 0.0  # Assume all is invested
        self._update_summary()
        self.save()
        
        logger.info(f"Capital tracking initialized with current portfolio value: {portfolio_value:.2f} SEK")
    
    def record_deposit(self, amount: float, date_str: str = None, description: str = ""):
        """Record money transferred TO broker.
        
        Args:
            amount: Amount in SEK
            date_str: Date in "YYYY-MM-DD" format (defaults to today)
            description: Optional description
        """
        if date_str is None:
            date_str = datetime.date.today().strftime("%Y-%m-%d")
        
        event_id = str(uuid.uuid4())
        self.events.append({
            'id': event_id,
            'date': date_str,
            'type': 'deposit',
            'amount': float(amount),
            'description': description or f"Deposit of {amount:.2f} SEK",
            'days_invested': self._calculate_days_invested(date_str)
        })
        
        self.cash_balance += amount
        self._update_summary()
        
        logger.info(f"Recorded deposit: {amount:.2f} SEK on {date_str}")
    
    def record_withdrawal(self, amount: float, date_str: str = None, description: str = ""):
        """Record money transferred FROM broker.
        
        Args:
            amount: Amount in SEK (positive number)
            date_str: Date in "YYYY-MM-DD" format (defaults to today)
            description: Optional description
        """
        if date_str is None:
            date_str = datetime.date.today().strftime("%Y-%m-%d")
        
        event_id = str(uuid.uuid4())
        self.events.append({
            'id': event_id,
            'date': date_str,
            'type': 'withdrawal',
            'amount': -float(amount),  # Negative for withdrawal
            'description': description or f"Withdrawal of {amount:.2f} SEK"
        })
        
        self.cash_balance -= amount
        self._update_summary()
        
        logger.info(f"Recorded withdrawal: {amount:.2f} SEK on {date_str}")
    
    def record_buy(self, stock_name: str, volume: int, price: float, date_str: str = None, fee: float = 0.0):
        """Record stock purchase (moves cash to invested).
        
        Args:
            stock_name: Stock ticker
            volume: Number of shares
            price: Price per share in SEK
            date_str: Date in "YYYY-MM-DD" format (defaults to today)
            fee: Broker fee/commission in SEK (optional)
        """
        if date_str is None:
            date_str = datetime.date.today().strftime("%Y-%m-%d")
        
        amount = volume * price
        event_id = str(uuid.uuid4())
        
        event_data = {
            'id': event_id,
            'date': date_str,
            'type': 'buy',
            'stock': stock_name,
            'amount': amount,
            'volume': volume,
            'price': price,
            'description': f"Bought {volume} shares of {stock_name} at {price:.2f} SEK"
        }
        
        if fee > 0:
            event_data['fee'] = fee
            event_data['description'] += f" (fee: {fee:.2f} SEK)"
        
        self.events.append(event_data)
        
        self.cash_balance -= (amount + fee)  # Deduct both stock cost and fee from cash
        self._update_summary()
        
        logger.debug(f"Recorded buy: {volume} shares of {stock_name} at {price:.2f} SEK (fee: {fee:.2f})")
    
    def record_sell(self, stock_name: str, volume: int, price: float, realized_profit: float, date_str: str = None, fee: float = 0.0):
        """Record stock sale (moves value back to cash).
        
        Args:
            stock_name: Stock ticker
            volume: Number of shares
            price: Sell price per share in SEK
            realized_profit: Profit/loss from the sale
            date_str: Date in "YYYY-MM-DD" format (defaults to today)
            fee: Broker fee/commission in SEK (optional)
        """
        if date_str is None:
            date_str = datetime.date.today().strftime("%Y-%m-%d")
        
        amount = volume * price
        event_id = str(uuid.uuid4())
        
        event_data = {
            'id': event_id,
            'date': date_str,
            'type': 'sell',
            'stock': stock_name,
            'amount': amount,
            'volume': volume,
            'price': price,
            'realized_profit': realized_profit,
            'description': f"Sold {volume} shares of {stock_name} at {price:.2f} SEK (P/L: {realized_profit:+.2f} SEK)"
        }
        
        if fee > 0:
            event_data['fee'] = fee
            event_data['description'] += f" (fee: {fee:.2f} SEK)"
        
        self.events.append(event_data)
        
        self.cash_balance += (amount - fee)  # Add proceeds but subtract fee
        self._update_summary()
        
        logger.debug(f"Recorded sell: {volume} shares of {stock_name} at {price:.2f} SEK (fee: {fee:.2f})")
    
    def _calculate_days_invested(self, event_date_str: str) -> int:
        """Calculate days from event_date to today."""
        try:
            event_date = datetime.datetime.strptime(event_date_str, "%Y-%m-%d").date()
            today = datetime.date.today()
            return (today - event_date).days
        except Exception as e:
            logger.warning(f"Failed to calculate days invested for {event_date_str}: {e}")
            return 0
    
    def _update_days_invested(self):
        """Update days_invested for all deposit events."""
        for event in self.events:
            if event['type'] in ['deposit', 'initial_deposit']:
                event['days_invested'] = self._calculate_days_invested(event['date'])
    
    def _update_summary(self):
        """Update summary statistics."""
        # Calculate totals
        total_deposits = sum(e['amount'] for e in self.events if e['type'] in ['deposit', 'initial_deposit'])
        total_withdrawals = abs(sum(e['amount'] for e in self.events if e['type'] == 'withdrawal'))
        total_buys = sum(e['amount'] for e in self.events if e['type'] == 'buy')
        total_sells = sum(e['amount'] for e in self.events if e['type'] == 'sell')
        total_fees = sum(e.get('fee', 0.0) for e in self.events if e['type'] in ['buy', 'sell'])
        realized_profit = sum(e.get('realized_profit', 0.0) for e in self.events if e['type'] == 'sell')
        
        net_capital_input = total_deposits - total_withdrawals
        current_invested = total_buys - total_sells
        
        self.summary = {
            'total_deposits': total_deposits,
            'total_withdrawals': total_withdrawals,
            'net_capital_input': net_capital_input,
            'current_invested': current_invested,
            'current_cash': self.cash_balance,
            'total_capital_in_system': current_invested + self.cash_balance,
            'total_fees': total_fees,
            'realized_profit_total': realized_profit,
            'last_updated': datetime.date.today().strftime("%Y-%m-%d")
        }
    
    def get_net_capital(self) -> float:
        """Get net capital currently in system."""
        return self.summary.get('net_capital_input', 0.0)
    
    def get_total_deposits(self) -> float:
        """Get total amount deposited."""
        return self.summary.get('total_deposits', 0.0)
    
    def get_total_withdrawals(self) -> float:
        """Get total amount withdrawn."""
        return self.summary.get('total_withdrawals', 0.0)
    
    def get_current_cash(self) -> float:
        """Get current cash balance."""
        return self.cash_balance
    
    def get_realized_profit(self) -> float:
        """Get total realized profit from all sells."""
        return self.summary.get('realized_profit_total', 0.0)
    
    def get_fifo_cost_basis(self) -> dict:
        """Calculate current holdings cost basis using FIFO method.
        
        Returns:
            Dictionary with:
                - 'total_cost_basis': Total cost basis of all current holdings
                - 'holdings': Dict of stock -> list of (volume, price) lots
        """
        from collections import defaultdict
        holdings = defaultdict(list)
        
        # Replay all buy/sell events in order
        for event in sorted(self.events, key=lambda e: e['date']):
            if event['type'] == 'buy':
                stock = event['stock']
                volume = event['volume']
                price = event['price']
                holdings[stock].append({'volume': volume, 'price': price})
                
            elif event['type'] == 'sell':
                stock = event['stock']
                volume_to_sell = event['volume']
                
                # FIFO: Remove from oldest lots first
                while volume_to_sell > 0 and holdings[stock]:
                    lot = holdings[stock][0]
                    if lot['volume'] <= volume_to_sell:
                        volume_to_sell -= lot['volume']
                        holdings[stock].pop(0)
                    else:
                        lot['volume'] -= volume_to_sell
                        volume_to_sell = 0
        
        # Calculate total cost basis
        total_cost_basis = 0.0
        for stock, lots in holdings.items():
            for lot in lots:
                total_cost_basis += lot['volume'] * lot['price']
        
        return {
            'total_cost_basis': total_cost_basis,
            'holdings': dict(holdings)
        }
    
    def calculate_simple_return(self, current_portfolio_value: float) -> dict:
        """Calculate simple return percentage.
        
        Args:
            current_portfolio_value: Current total value of portfolio (stocks + cash)
        
        Returns:
            Dictionary with return metrics
        """
        net_capital = self.get_net_capital()
        
        if net_capital == 0:
            return {
                'simple_return_sek': 0.0,
                'simple_return_percent': 0.0,
                'portfolio_value': current_portfolio_value,
                'net_capital': net_capital
            }
        
        simple_return_sek = current_portfolio_value - net_capital
        simple_return_percent = (simple_return_sek / net_capital) * 100
        
        return {
            'simple_return_sek': simple_return_sek,
            'simple_return_percent': simple_return_percent,
            'portfolio_value': current_portfolio_value,
            'net_capital': net_capital
        }
    
    def calculate_time_weighted_return(self, current_portfolio_value: float, portfolio_instance=None) -> dict:
        """Calculate true time-weighted return percentage.
        
        This measures portfolio performance independent of cash flows by:
        1. Splitting timeline into sub-periods at each cash flow event
        2. Calculating return for each sub-period
        3. Geometrically linking the returns
        
        Args:
            current_portfolio_value: Current total value of portfolio (stocks + cash)
            portfolio_instance: Portfolio instance to access historical data (optional)
        
        Returns:
            Dictionary with time-weighted return metrics
        """
        # Get all cash flow events (deposits, withdrawals) sorted by date
        cash_flow_events = [e for e in self.events if e['type'] in ['deposit', 'initial_deposit', 'withdrawal']]
        
        if not cash_flow_events:
            return {
                'time_weighted_return_percent': 0.0,
                'annualized_return_percent': 0.0,
                'total_days': 0,
                'calculation_method': 'none'
            }
        
        # Sort by date
        cash_flow_events = sorted(cash_flow_events, key=lambda e: e['date'])
        
        # If we can't calculate TWR (no portfolio instance for historical data),
        # fall back to simple return with a note
        if portfolio_instance is None:
            net_capital = self.get_net_capital()
            if net_capital == 0:
                return {
                    'time_weighted_return_percent': 0.0,
                    'annualized_return_percent': 0.0,
                    'total_days': 0,
                    'calculation_method': 'insufficient_data'
                }
            
            # Calculate simple return
            total_return = current_portfolio_value - net_capital
            simple_return_percent = (total_return / net_capital) * 100
            
            # Calculate total days
            first_date = datetime.datetime.strptime(cash_flow_events[0]['date'], "%Y-%m-%d").date()
            last_date = datetime.date.today()
            total_days = (last_date - first_date).days
            
            # Annualize
            if total_days > 0:
                years = total_days / 365.0
                annualized = (pow(current_portfolio_value / net_capital, 1 / years) - 1) * 100
            else:
                annualized = 0.0
            
            return {
                'time_weighted_return_percent': simple_return_percent,
                'annualized_return_percent': annualized,
                'total_days': total_days,
                'calculation_method': 'simple_return_fallback'
            }
        
        # TRUE TIME-WEIGHTED RETURN CALCULATION
        # For each period between cash flows, calculate the holding period return
        try:
            periods = []
            cumulative_return = 1.0  # Start with 1 (100%)
            
            # Initial portfolio value (first deposit)
            portfolio_value = cash_flow_events[0]['amount']
            first_date = datetime.datetime.strptime(cash_flow_events[0]['date'], "%Y-%m-%d").date()
            
            # Process each subsequent cash flow
            for i in range(1, len(cash_flow_events) + 1):
                if i < len(cash_flow_events):
                    next_event = cash_flow_events[i]
                    next_date = datetime.datetime.strptime(next_event['date'], "%Y-%m-%d").date()
                    
                    # Calculate portfolio value just before this cash flow
                    # Exclude the cash flow event itself to get the value BEFORE the flow
                    value_before_flow = self._estimate_portfolio_value_at_date(
                        next_date, portfolio_instance, exclude_event_ids=[next_event.get('id')]
                    )
                    
                    if value_before_flow is not None and portfolio_value > 0:
                        # Calculate return for this period
                        period_return = value_before_flow / portfolio_value
                        cumulative_return *= period_return
                        
                        periods.append({
                            'start_value': portfolio_value,
                            'end_value': value_before_flow,
                            'return': period_return,
                            'days': (next_date - first_date).days
                        })
                        
                        # Update portfolio value after cash flow
                        cash_flow = next_event['amount']  # Positive for deposit, negative for withdrawal
                        portfolio_value = value_before_flow + cash_flow
                        first_date = next_date
                else:
                    # Final period to today
                    # Portfolio value is the current value
                    if portfolio_value > 0:
                        period_return = current_portfolio_value / portfolio_value
                        cumulative_return *= period_return
                        
                        today = datetime.date.today()
                        periods.append({
                            'start_value': portfolio_value,
                            'end_value': current_portfolio_value,
                            'return': period_return,
                            'days': (today - first_date).days
                        })
            
            # Convert to percentage
            twr_percent = (cumulative_return - 1.0) * 100
            
            # Calculate total days and annualize
            first_date = datetime.datetime.strptime(cash_flow_events[0]['date'], "%Y-%m-%d").date()
            total_days = (datetime.date.today() - first_date).days
            
            if total_days > 0:
                years = total_days / 365.0
                annualized = (pow(cumulative_return, 1 / years) - 1) * 100
            else:
                annualized = twr_percent
            
            return {
                'time_weighted_return_percent': twr_percent,
                'annualized_return_percent': annualized,
                'total_days': total_days,
                'num_periods': len(periods),
                'calculation_method': 'true_twr'
            }
            
        except Exception as e:
            logger.warning(f"Failed to calculate true TWR, falling back to simple return: {e}")
            # Fall back to simple return
            net_capital = self.get_net_capital()
            if net_capital == 0:
                return {
                    'time_weighted_return_percent': 0.0,
                    'annualized_return_percent': 0.0,
                    'total_days': 0,
                    'calculation_method': 'error_fallback'
                }
            
            total_return = current_portfolio_value - net_capital
            simple_return_percent = (total_return / net_capital) * 100
            
            first_date = datetime.datetime.strptime(cash_flow_events[0]['date'], "%Y-%m-%d").date()
            total_days = (datetime.date.today() - first_date).days
            
            if total_days > 0:
                years = total_days / 365.0
                annualized = (pow(current_portfolio_value / net_capital, 1 / years) - 1) * 100
            else:
                annualized = 0.0
            
            return {
                'time_weighted_return_percent': simple_return_percent,
                'annualized_return_percent': annualized,
                'total_days': total_days,
                'calculation_method': 'error_fallback'
            }
    
    def _estimate_portfolio_value_at_date(self, target_date: datetime.date, portfolio_instance, exclude_event_ids: list = None) -> Optional[float]:
        """Estimate total portfolio value at a specific historical date.
        
        Args:
            target_date: Date to estimate value for
            portfolio_instance: Portfolio instance to access stocks and historical data
            exclude_event_ids: List of event IDs to exclude from calculation (e.g. the cash flow event itself)
            
        Returns:
            Estimated portfolio value in SEK, or None if cannot estimate
        """
        try:
            exclude_ids = set(exclude_event_ids) if exclude_event_ids else set()
            
            # Calculate cash balance at that date by replaying events
            cash_at_date = 0.0
            for event in sorted(self.events, key=lambda e: e['date']):
                if event.get('id') in exclude_ids:
                    continue
                    
                event_date = datetime.datetime.strptime(event['date'], "%Y-%m-%d").date()
                if event_date > target_date:
                    break
                
                if event['type'] in ['deposit', 'initial_deposit']:
                    cash_at_date += event['amount']
                elif event['type'] == 'withdrawal':
                    cash_at_date += event['amount']  # Already negative
                elif event['type'] == 'buy':
                    cash_at_date -= event['amount']
                elif event['type'] == 'sell':
                    cash_at_date += event['amount']
            
            # Calculate stock value at that date
            # Reconstruct holdings at target_date from buy/sell events
            stock_value_at_date = 0.0
            days_ago = (datetime.date.today() - target_date).days
            
            # Track holdings at target_date by looking at buy/sell events
            holdings_at_date = {}  # {stock_name: [(volume, buy_price, buy_date), ...]}
            
            for event in sorted(self.events, key=lambda e: e['date']):
                if event.get('id') in exclude_ids:
                    continue
                    
                event_date = datetime.datetime.strptime(event['date'], "%Y-%m-%d").date()
                if event_date > target_date:
                    break
                
                if event['type'] == 'buy':
                    stock_name = event['stock']
                    volume = event['volume']
                    price = event['price']
                    
                    if stock_name not in holdings_at_date:
                        holdings_at_date[stock_name] = []
                    holdings_at_date[stock_name].append({
                        'volume': volume,
                        'buy_price': price,
                        'buy_date': event_date
                    })
                    
                elif event['type'] == 'sell':
                    stock_name = event['stock']
                    volume = event['volume']
                    
                    # Remove sold shares (FIFO - first in, first out)
                    if stock_name in holdings_at_date:
                        remaining_to_sell = volume
                        for holding in holdings_at_date[stock_name]:
                            if remaining_to_sell <= 0:
                                break
                            if holding['volume'] <= remaining_to_sell:
                                remaining_to_sell -= holding['volume']
                                holding['volume'] = 0
                            else:
                                holding['volume'] -= remaining_to_sell
                                remaining_to_sell = 0
                        
                        # Remove empty holdings
                        holdings_at_date[stock_name] = [h for h in holdings_at_date[stock_name] if h['volume'] > 0]
            
            # Now value the holdings at target_date using historical prices
            for stock_name, holdings_list in holdings_at_date.items():
                for holding in holdings_list:
                    volume = holding['volume']
                    if volume <= 0:
                        continue
                    
                    # Get historical price
                    stock_price_obj = portfolio_instance.real_time_manager.get_stock_price(stock_name)
                    if stock_price_obj:
                        historical_price_native = stock_price_obj.get_historical_close_native(days_ago)
                        if historical_price_native:
                            # Convert to SEK
                            native_currency = stock_price_obj.currency
                            if native_currency and native_currency != 'SEK':
                                sek_price = self.currency_manager.convert(
                                    historical_price_native,
                                    native_currency,
                                    'SEK'
                                )
                            else:
                                sek_price = historical_price_native
                            
                            stock_value_at_date += volume * sek_price
                        else:
                            # No historical data, use buy price as estimate
                            stock_value_at_date += volume * holding['buy_price']
                    else:
                        # Use buy price as fallback
                        stock_value_at_date += volume * holding['buy_price']
            
            return cash_at_date + stock_value_at_date
            
        except Exception as e:
            logger.warning(f"Failed to estimate portfolio value at {target_date}: {e}")
            return None
    
    def get_capital_summary(self, current_portfolio_value: float, current_stock_value: float, stock_cost_basis: float = None, portfolio_instance=None) -> dict:
        """Get comprehensive capital summary with all metrics.
        
        Args:
            current_portfolio_value: Total value including cash
            current_stock_value: Current value of stock holdings only
            stock_cost_basis: Cost basis of current holdings (what you paid for them)
            portfolio_instance: Portfolio instance for historical data (for true TWR)
        
        Returns:
            Complete summary dictionary
        """
        simple_return = self.calculate_simple_return(current_portfolio_value)
        time_weighted_return = self.calculate_time_weighted_return(current_portfolio_value, portfolio_instance)
        
        # Use provided cost basis if available, otherwise fall back to net buys-sells
        actual_cost_basis = stock_cost_basis if stock_cost_basis is not None else self.summary.get('current_invested', 0.0)
        
        unrealized_gain = current_stock_value - actual_cost_basis
        realized_gain = self.get_realized_profit()
        total_gain = unrealized_gain + realized_gain
        
        return {
            # Capital flow
            'total_deposits': self.get_total_deposits(),
            'total_withdrawals': self.get_total_withdrawals(),
            'net_capital_input': self.get_net_capital(),
            
            # Current position
            'cash_balance': self.cash_balance,
            'stock_value_at_cost': actual_cost_basis,
            'stock_value_current': current_stock_value,
            'portfolio_value_total': current_portfolio_value,
            
            # Returns
            'unrealized_gain': unrealized_gain,
            'realized_gain': realized_gain,
            'total_gain': total_gain,
            
            # Simple return
            'simple_return_sek': simple_return['simple_return_sek'],
            'simple_return_percent': simple_return['simple_return_percent'],
            
            # Time-weighted return
            'time_weighted_return_percent': time_weighted_return['time_weighted_return_percent'],
            'annualized_return_percent': time_weighted_return['annualized_return_percent'],
            'average_days_invested': time_weighted_return.get('total_days', 0),
            'average_years_invested': time_weighted_return.get('total_days', 0) / 365.0,
            
            # Metadata
            'last_updated': datetime.date.today().strftime("%Y-%m-%d"),
            'num_events': len(self.events)
        }


class Portfolio:
    """Main portfolio management class with improved architecture."""
    
    def __init__(self, path: str, filename: str, 
                 historical_mode: HistoricalMode = HistoricalMode.BACKGROUND,
                 verbose: bool = False, allow_online_currency_lookup: bool = False,
                 config: Config = None):
        """
        Initialize portfolio with configurable historical data loading strategy.
        
        Args:
            path: Portfolio directory path
            filename: Portfolio JSON filename
            historical_mode: How to handle historical data loading
            verbose: Enable verbose logging
            allow_online_currency_lookup: Allow online currency lookups
            config: Configuration object
        """
        self.config = config or Config()
        self.path = path
        self.filename = filename
        self.filepath = os.path.join(path, filename)
        self.verbose = verbose
        
        # Ensure directory exists
        if not os.path.isdir(path):
            raise ValueError(f"Directory does not exist: {path}")
        
        # Initialize managers
        self.currency_manager = CurrencyManager(path, allow_online_currency_lookup, self.config)
        self.data_manager = DataManager(path, self.config)
        self.historical_manager = HistoricalDataManager(self.data_manager, self.currency_manager, self.config)
        self.real_time_manager = RealTimeDataManager(self.currency_manager, self.data_manager, self.historical_manager, self.config)
        self.ticker_validator = TickerValidator()
        self.capital_tracker = CapitalTracker(self.data_manager, self.currency_manager)  # NEW: Capital tracking
        
        # Portfolio data
        self.stocks: Dict[str, Stock] = {}
        self._portfolio_data = {}
        self.highlighted_stocks: Set[str] = set()  # Stock names that are highlighted
        self._highlighted_filepath = os.path.join(path, "highlighted_stocks.json")
        
        # Historical data handling
        self._historical_mode = historical_mode
        self._historical_thread = None
        self._historical_pending = []
        self._historical_done = set()
        self._historical_lock = threading.Lock()
        
        # Continuous historical update thread
        self._historical_update_thread = None
        self._historical_update_running = False
        self._historical_update_lock = threading.Lock()
        
        # Cache for computed stock prices with historical data
        self._stock_prices_cache = None
        self._stock_prices_cache_time = 0
        self._stock_prices_cache_lock = threading.Lock()
        
        # Debug: Track portfolio instance
        import random
        self._instance_id = random.randint(1000, 9999)
        logger.info(f"Portfolio instance created with ID: {self._instance_id}")
        
        # Initialize
        start_time = time.perf_counter()
        self._load_portfolio()
        self._setup_historical_loading()
        self.real_time_manager.start_monitoring()
        self._start_continuous_historical_updates()
        
        # Perform initial data quality check if we have stocks
        if self.stocks and self._historical_mode != HistoricalMode.SKIP:
            self._perform_initial_data_quality_check()
        
        if verbose:
            elapsed = time.perf_counter() - start_time
            logger.info(f"Portfolio initialized in {elapsed:.2f}s with {len(self.stocks)} stocks")
    
    def _load_portfolio(self):
        """Load portfolio data from file."""
        # Ensure portfolio file exists
        self.data_manager.ensure_file_exists(self.filepath)
        
        # Load portfolio data
        self._portfolio_data = self.data_manager.load_json(self.filepath) or {}
        
        # Load highlighted stocks
        highlighted_data = self.data_manager.load_json(self._highlighted_filepath)
        if highlighted_data and isinstance(highlighted_data, list):
            self.highlighted_stocks = set(highlighted_data)
        
        # Load stocks
        for stock_name, ticker in self._portfolio_data.items():
            try:
                stock = Stock(ticker, self.data_manager, self.real_time_manager)
                self.stocks[stock_name] = stock
                self.real_time_manager.add_stock(ticker)
                self._historical_pending.append(ticker)
                
                if self.verbose:
                    logger.info(f"Loaded stock {stock_name} ({ticker})")
                    
            except Exception as e:
                logger.error(f"Failed to load stock {stock_name} ({ticker}): {e}")
    
    def _setup_historical_loading(self):
        """Setup historical data loading based on mode."""
        if self._historical_mode == HistoricalMode.EAGER:
            self._load_all_historical_eager()
        elif self._historical_mode == HistoricalMode.BACKGROUND:
            self._start_historical_background_thread()
        # SKIP mode does nothing
    
    def _load_all_historical_eager(self):
        """Load all historical data synchronously."""
        for ticker in list(self._historical_pending):
            self._load_historical_for_ticker(ticker)
            self._historical_done.add(ticker)
        self._historical_pending.clear()
    
    def _start_historical_background_thread(self):
        """Start background thread for historical data loading."""
        if self._historical_thread and self._historical_thread.is_alive():
            return
            
        def worker():
            successful_loads = []
            failed_loads = []
            
            with self._historical_lock:
                tickers = list(self._historical_pending)
                total_tickers = len(tickers)
            
            if not tickers:
                return
            
            logger.info(f"Starting background historical data loading for {total_tickers} tickers (bulk fetch)")
            
            try:
                # Use bulk fetch to get all historical data in ONE API call
                bulk_data = self.historical_manager.bulk_fetch_historical(
                    tickers,
                    period=self.config.DEFAULT_HISTORICAL_PERIOD,
                    interval=self.config.DEFAULT_HISTORICAL_INTERVAL
                )
                
                # Process each ticker's data
                for ticker in tickers:
                    try:
                        df = bulk_data.get(ticker)
                        
                        if df is None or df.empty:
                            logger.warning(f"No historical data available for {ticker}")
                            failed_loads.append(ticker)
                            continue
                        
                        # Convert to SEK
                        df = self.historical_manager._convert_dataframe_to_sek(df, ticker)
                        
                        # Validate data quality
                        validation_issues = self.historical_manager._validate_historical_data_quality(ticker, df)
                        
                        if validation_issues:
                            logger.warning(f"Data quality issues for {ticker}: {', '.join(validation_issues[:3])}")
                            # Still save the data as it's better than nothing
                        
                        # Save to CSV
                        filepath = self.data_manager.get_historical_filepath(
                            ticker, 
                            self.config.DEFAULT_HISTORICAL_PERIOD,
                            self.config.DEFAULT_HISTORICAL_INTERVAL,
                            convert_to_sek=True
                        )
                        
                        self.data_manager.save_csv(df, filepath)
                        successful_loads.append(ticker)
                        
                    except Exception as e:
                        logger.error(f"Exception processing historical data for {ticker}: {e}")
                        failed_loads.append(ticker)
                    finally:
                        with self._historical_lock:
                            self._historical_done.add(ticker)
                
            except Exception as e:
                logger.error(f"Bulk historical fetch failed: {e}")
                # Mark all as failed
                failed_loads.extend(tickers)
                with self._historical_lock:
                    for ticker in tickers:
                        self._historical_done.add(ticker)
            
            # Clear pending list
            with self._historical_lock:
                self._historical_pending.clear()
            
            # Report summary
            success_count = len(successful_loads)
            failed_count = len(failed_loads)
            
            if self.verbose or failed_count > 0:
                logger.info(f"Background historical loading completed: {success_count}/{total_tickers} successful (1 bulk API call)")
                
                if failed_loads:
                    logger.warning(f"Failed to load historical data for: {failed_loads}")
                else:
                    logger.info("All historical data loaded successfully")
        
        self._historical_thread = threading.Thread(target=worker, daemon=True)
        self._historical_thread.start()
    
    def _load_historical_for_ticker(self, ticker: str):
        """Load historical data for a specific ticker with detailed validation."""
        try:
            logger.info(f"Loading historical data for {ticker}")
            
            # Load and store default historical data
            df = self.historical_manager.load_historical_data(
                ticker,
                period=self.config.DEFAULT_HISTORICAL_PERIOD,
                interval=self.config.DEFAULT_HISTORICAL_INTERVAL,
                convert_to_sek=True
            )
            
            if df is None or df.empty:
                logger.warning(f"No historical data available for {ticker}")
                return False
            
            # Validate data quality
            validation_issues = self.historical_manager._validate_historical_data_quality(ticker, df)
            
            if validation_issues:
                logger.warning(f"Data quality issues for {ticker}: {', '.join(validation_issues[:3])}")
                # Still save the data as it's better than nothing
            
            # Save to CSV
            filepath = self.data_manager.get_historical_filepath(
                ticker, 
                self.config.DEFAULT_HISTORICAL_PERIOD,
                self.config.DEFAULT_HISTORICAL_INTERVAL,
                convert_to_sek=True
            )
            
            success = self.data_manager.save_csv(df, filepath)
            
            if success:
                # Check freshness
                is_stale = self.historical_manager.is_historical_data_stale(
                    ticker, 
                    self.config.DEFAULT_HISTORICAL_PERIOD,
                    self.config.DEFAULT_HISTORICAL_INTERVAL
                )
                
                data_status = "stale" if is_stale else "fresh"
                quality_status = "with issues" if validation_issues else "good quality"
                
                logger.info(f"✓ {ticker}: Loaded {len(df)} rows, {data_status} data, {quality_status}")
                return True
            else:
                logger.error(f"✗ {ticker}: Failed to save data to {filepath}")
                return False
                
        except Exception as e:
            logger.error(f"✗ {ticker}: Failed to load historical data - {e}")
            return False
    
    def _start_continuous_historical_updates(self):
        """Start continuous background updates for historical data."""
        if self._historical_update_running:
            return
            
        self._historical_update_running = True
        
        def continuous_update_worker():
            """Background worker that continuously updates historical data."""
            error_check_cycle = 0  # Track cycles for periodic error checking
            
            while self._historical_update_running:
                try:
                    # Get all tickers from the portfolio
                    tickers = [stock.ticker for stock in self.stocks.values()]
                    
                    if tickers:
                        # Normal staleness check (every cycle)
                        stale_tickers = self.historical_manager.get_stale_tickers(tickers)
                        
                        # Periodic error detection (every 5 cycles = ~25 minutes)
                        error_check_cycle += 1
                        problematic_tickers = []
                        if error_check_cycle >= 5:  
                            error_check_cycle = 0
                            if self.verbose:
                                logger.info("Performing periodic data quality check...")
                            
                            problematic_tickers = self.historical_manager.get_problematic_tickers(tickers)
                            
                            if problematic_tickers:
                                logger.info(f"Found {len(problematic_tickers)} tickers with data quality issues: {problematic_tickers}")
                        
                        # Combine stale and problematic tickers for update
                        tickers_to_update = list(set(stale_tickers + problematic_tickers))
                        
                        if tickers_to_update:
                            if self.verbose:
                                stale_count = len(stale_tickers)
                                problem_count = len(problematic_tickers)
                                logger.info(f"Updating historical data for {len(tickers_to_update)} tickers "
                                          f"({stale_count} stale, {problem_count} problematic)")
                            
                            # Update historical data for tickers that need it
                            self._update_historical_data_for_tickers(tickers_to_update)
                        
                except Exception as e:
                    logger.error(f"Error in continuous historical update: {e}")
                
                # Sleep for the configured update interval
                time.sleep(self.config.HISTORICAL_UPDATE_INTERVAL)
            
            if self.verbose:
                logger.info("Continuous historical data updates stopped")
        
        self._historical_update_thread = threading.Thread(target=continuous_update_worker, daemon=True)
        self._historical_update_thread.start()
        
        if self.verbose:
            logger.info("Started continuous historical data updates")
    
    def _stop_continuous_historical_updates(self):
        """Stop continuous background updates for historical data."""
        self._historical_update_running = False
        if self._historical_update_thread:
            # Don't join here as it might be called from destructor
            self._historical_update_thread = None
        
        if self.verbose:
            logger.info("Stopped continuous historical data updates")

    def _perform_initial_data_quality_check(self):
        """Perform initial data quality check on startup and fix issues.
        
        This checks for:
        1. Missing or problematic data (data quality issues)
        2. Stale data (data older than threshold)
        
        Uses bulk fetch to efficiently refresh all stale/problematic tickers.
        """
        try:
            tickers = [stock.ticker for stock in self.stocks.values()]
            
            if self.verbose:
                logger.info(f"Performing initial data quality check on {len(tickers)} tickers...")
            
            # Check for problematic data (missing files, quality issues)
            problematic_tickers = self.historical_manager.get_problematic_tickers(tickers)
            
            # Check for stale data (data older than threshold)
            stale_tickers = []
            for ticker in tickers:
                if self.historical_manager.is_historical_data_stale(
                    ticker,
                    self.config.DEFAULT_HISTORICAL_PERIOD,
                    self.config.DEFAULT_HISTORICAL_INTERVAL
                ):
                    stale_tickers.append(ticker)
            
            # Combine problematic and stale tickers (remove duplicates)
            tickers_to_refresh = list(set(problematic_tickers + stale_tickers))
            
            if tickers_to_refresh:
                logger.info(f"Found {len(tickers_to_refresh)} tickers needing refresh at startup:")
                logger.info(f"  - Problematic: {len(problematic_tickers)}")
                logger.info(f"  - Stale: {len(stale_tickers)}")
                logger.info(f"  - Total unique: {len(tickers_to_refresh)}")
                
                # Use bulk fetch for efficiency (1 API call for all tickers)
                self._bulk_refresh_historical_data(tickers_to_refresh)
            else:
                if self.verbose:
                    logger.info("Initial data quality check: All tickers have fresh, good quality data")
                    
        except Exception as e:
            logger.error(f"Error during initial data quality check: {e}")
            # Don't fail startup if quality check fails
    
    def _bulk_refresh_historical_data(self, tickers: List[str]):
        """Bulk refresh historical data for multiple tickers efficiently.
        
        Uses a single API call to fetch all tickers at once.
        """
        if not tickers:
            return
        
        logger.info(f"Bulk refreshing historical data for {len(tickers)} tickers (1 API call)...")
        
        try:
            # Fetch all historical data in one bulk call
            bulk_data = self.historical_manager.bulk_fetch_historical(
                tickers,
                period=self.config.DEFAULT_HISTORICAL_PERIOD,
                interval=self.config.DEFAULT_HISTORICAL_INTERVAL
            )
            
            successful = []
            failed = []
            warnings = []  # Tickers with issues but saved anyway
            
            # Process and save each ticker's data
            for ticker in tickers:
                try:
                    df = bulk_data.get(ticker)
                    
                    if df is None or df.empty:
                        logger.warning(f"No data received for {ticker} in bulk fetch")
                        failed.append(ticker)
                        continue
                    
                    # Convert to SEK
                    df = self.historical_manager._convert_dataframe_to_sek(df, ticker)
                    
                    # Validate data quality
                    issues = self.historical_manager._validate_historical_data_quality(ticker, df)
                    
                    # Check if issues are critical (should not save)
                    critical_issues = [
                        issue for issue in issues 
                        if any(critical in issue for critical in [
                            'missing_columns',
                            'insufficient_data',
                            'flat_close_data',
                            'invalid_prices'
                        ])
                    ]
                    
                    if critical_issues:
                        logger.error(f"Critical data quality issues for {ticker}, NOT saving: {', '.join(critical_issues)}")
                        failed.append(ticker)
                        continue
                    
                    # Save data (even with non-critical warnings)
                    if issues:
                        logger.warning(f"Non-critical data quality issues for {ticker}, saving anyway: {', '.join(issues[:3])}")
                        warnings.append(ticker)
                    
                    # Save to CSV
                    filepath = self.data_manager.get_historical_filepath(
                        ticker,
                        self.config.DEFAULT_HISTORICAL_PERIOD,
                        self.config.DEFAULT_HISTORICAL_INTERVAL,
                        convert_to_sek=True
                    )
                    
                    self.data_manager.save_csv(df, filepath)
                    successful.append(ticker)
                    
                except Exception as e:
                    logger.error(f"Failed to process bulk data for {ticker}: {e}")
                    failed.append(ticker)
            
            # Don't invalidate cache - let it expire naturally after 2 minutes
            # This prevents view switching slowdowns when background updates are running
            # self._invalidate_stock_prices_cache()
            
            logger.info(f"Bulk refresh complete: {len(successful)}/{len(tickers)} successful")
            if warnings:
                logger.warning(f"Saved with warnings: {warnings}")
            if failed:
                logger.warning(f"Failed to refresh: {failed}")
                
        except Exception as e:
            logger.error(f"Bulk historical refresh failed: {e}")
    
    def _update_historical_data_for_tickers(self, tickers: List[str]):
        """Update historical data for specified tickers with individual validation."""
        if not tickers:
            return
            
        successful_updates = []
        failed_updates = []
        fallback_used = []
        
        logger.info(f"Starting individual historical data update for {len(tickers)} tickers")
        
        try:
            # First, identify problematic tickers that need force refresh
            problematic_tickers = self.historical_manager.get_problematic_tickers(tickers)
            
            if problematic_tickers:
                logger.info(f"Found {len(problematic_tickers)} problematic tickers requiring force refresh: {problematic_tickers}")
                
                # Force refresh problematic tickers (invalidate cache and files)
                for ticker in problematic_tickers:
                    logger.info(f"Force refreshing problematic ticker: {ticker}")
                    self.historical_manager.force_refresh_ticker(ticker)
            
            # Process each ticker individually with detailed validation
            for ticker in tickers:
                try:
                    result = self._update_single_ticker_historical(ticker)
                    
                    if result['status'] == 'success':
                        successful_updates.append(ticker)
                        if self.verbose:
                            logger.info(f"✓ {ticker}: {result['message']}")
                    elif result['status'] == 'fallback':
                        fallback_used.append(ticker)
                        logger.warning(f"⚠ {ticker}: {result['message']}")
                    else:
                        failed_updates.append(ticker)
                        logger.error(f"✗ {ticker}: {result['message']}")
                        
                except Exception as e:
                    failed_updates.append(ticker)
                    logger.error(f"✗ {ticker}: Exception during update - {e}")
            
            # Verify updated data quality for previously problematic tickers
            if problematic_tickers:
                still_problematic = self.historical_manager.get_problematic_tickers(problematic_tickers)
                if still_problematic:
                    logger.warning(f"Tickers still have data quality issues after refresh: {still_problematic}")
                else:
                    logger.info(f"Successfully fixed data quality issues for: {problematic_tickers}")
            
            # Invalidate bulk history cache to ensure UI updates
            all_updated = successful_updates + fallback_used
            if all_updated:
                self._invalidate_bulk_history(all_updated)
                # Don't invalidate stock prices cache - let it expire naturally (2 minutes)
                # This prevents massive slowdowns when background updates are running
                # self._invalidate_stock_prices_cache()
            
            # Report summary
            total = len(tickers)
            success_count = len(successful_updates)
            fallback_count = len(fallback_used)
            failed_count = len(failed_updates)
            
            logger.info(f"Historical data update summary: {total} total, {success_count} successful, "
                       f"{fallback_count} fallback, {failed_count} failed")
            
            if failed_updates:
                logger.warning(f"Failed to update: {failed_updates}")
            if fallback_used:
                logger.info(f"Using fallback data: {fallback_used}")
            
        except Exception as e:
            logger.error(f"Failed to update historical data for tickers {tickers}: {e}")
    
    def _update_single_ticker_historical(self, ticker: str) -> Dict[str, str]:
        """Update historical data for a single ticker with detailed validation."""
        try:
            # Load historical data (includes staleness check and fallback logic)
            df = self.historical_manager.load_historical_data(
                ticker,
                period=self.config.DEFAULT_HISTORICAL_PERIOD,
                interval=self.config.DEFAULT_HISTORICAL_INTERVAL,
                convert_to_sek=True
            )
            
            if df is None or df.empty:
                return {
                    'status': 'failed',
                    'message': 'No historical data available'
                }
            
            # Validate data quality
            validation_issues = self.historical_manager._validate_historical_data_quality(ticker, df)
            
            if validation_issues:
                return {
                    'status': 'fallback',
                    'message': f'Data quality issues detected: {", ".join(validation_issues[:2])}'
                }
            
            # Save to CSV
            filepath = self.data_manager.get_historical_filepath(
                ticker, 
                self.config.DEFAULT_HISTORICAL_PERIOD,
                self.config.DEFAULT_HISTORICAL_INTERVAL,
                convert_to_sek=True
            )
            
            self.data_manager.save_csv(df, filepath)
            
            # Check if data is fresh or using fallback
            is_stale = self.historical_manager.is_historical_data_stale(
                ticker, 
                self.config.DEFAULT_HISTORICAL_PERIOD,
                self.config.DEFAULT_HISTORICAL_INTERVAL
            )
            
            if is_stale:
                return {
                    'status': 'fallback',
                    'message': f'Using stale data (fallback), {len(df)} rows'
                }
            else:
                return {
                    'status': 'success',
                    'message': f'Fresh data loaded, {len(df)} rows'
                }
                
        except Exception as e:
            return {
                'status': 'failed',
                'message': f'Exception: {str(e)[:100]}'
            }
    
    def add_stock(self, name: str, ticker: str) -> bool:
        """Add a stock to the portfolio."""
        # Check if name already exists
        if name in self.stocks:
            logger.error(f"Stock name '{name}' already exists in portfolio")
            return False
        
        # Check if ticker already exists
        existing_name = self.find_stock_name_by_ticker(ticker)
        if existing_name:
            logger.error(f"Ticker '{ticker}' already exists with name '{existing_name}'")
            return False
        
        # Validate ticker
        if not self.ticker_validator.is_valid(ticker):
            logger.error(f"Invalid ticker: {ticker}")
            return False
        
        try:
            # Create and add stock
            stock = Stock(ticker, self.data_manager, self.real_time_manager)
            self.stocks[name] = stock
            self.real_time_manager.add_stock(ticker)
            
            # Update portfolio data and save
            self._portfolio_data[name] = ticker
            self.save_portfolio()
            
            # Queue for historical data loading
            with self._historical_lock:
                self._historical_pending.append(ticker)
            
            # Start background loading if needed
            if self._historical_mode == HistoricalMode.BACKGROUND:
                self._start_historical_background_thread()
            
            logger.info(f"Added stock {name} ({ticker}) to portfolio")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add stock {name} ({ticker}): {e}")
            return False
    
    def remove_stock(self, name: str) -> bool:
        """Remove a stock from the portfolio."""
        if name not in self.stocks:
            logger.error(f"Stock '{name}' not found in portfolio")
            return False
        
        try:
            stock = self.stocks[name]
            ticker = stock.ticker
            
            # Remove from managers
            self.real_time_manager.remove_stock(ticker)
            
            # Remove files
            try:
                os.remove(stock.file_path)
            except Exception:
                pass
            
            # Remove profit file if exists
            profit_file = os.path.join(self.path, f"{name}_profit.json")
            try:
                os.remove(profit_file)
            except Exception:
                pass
            
            # Remove from data structures
            del self.stocks[name]
            if name in self._portfolio_data:
                del self._portfolio_data[name]
            
            # Update historical tracking
            with self._historical_lock:
                if ticker in self._historical_pending:
                    self._historical_pending.remove(ticker)
                self._historical_done.discard(ticker)
            
            # Save portfolio
            self.save_portfolio()
            
            logger.info(f"Removed stock {name} ({ticker}) from portfolio")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove stock {name}: {e}")
            return False
    
    def highlight_stock(self, name: str) -> bool:
        """Add a stock to the highlighted list."""
        if name not in self.stocks:
            logger.error(f"Stock '{name}' not found in portfolio")
            return False
        
        if name in self.highlighted_stocks:
            logger.info(f"Stock '{name}' is already highlighted")
            return True
        
        self.highlighted_stocks.add(name)
        self._save_highlighted_stocks()
        logger.info(f"Highlighted stock {name}")
        return True
    
    def unhighlight_stock(self, name: str) -> bool:
        """Remove a stock from the highlighted list."""
        if name not in self.highlighted_stocks:
            logger.info(f"Stock '{name}' is not highlighted")
            return True
        
        self.highlighted_stocks.discard(name)
        self._save_highlighted_stocks()
        logger.info(f"Unhighlighted stock {name}")
        return True
    
    def is_highlighted(self, name: str) -> bool:
        """Check if a stock is highlighted."""
        return name in self.highlighted_stocks
    
    def _save_highlighted_stocks(self) -> bool:
        """Save highlighted stocks to file."""
        try:
            highlighted_list = sorted(list(self.highlighted_stocks))
            return self.data_manager.save_json(self._highlighted_filepath, highlighted_list)
        except Exception as e:
            logger.error(f"Failed to save highlighted stocks: {e}")
            return False
    
    def add_shares(self, stock_name: str, volume: int, price: float, fee: float = 0.0) -> bool:
        """Add shares to a stock in the portfolio.
        
        Args:
            stock_name: Stock ticker
            volume: Number of shares to add
            price: Price per share
            fee: Optional broker fee (default: 0.0)
        """
        if stock_name not in self.stocks:
            logger.error(f"Stock '{stock_name}' not found in portfolio")
            return False
        
        success = self.stocks[stock_name].add_shares(volume, price)
        
        # Record capital event if tracking is initialized
        if success and self.capital_tracker.is_initialized():
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            self.capital_tracker.record_buy(stock_name, volume, price, today_str, fee)
            self.capital_tracker.save()
        
        return success
    
    def sell_shares(self, stock_name: str, volume: int, sell_price: float, fee: float = 0.0) -> bool:
        """Sell shares using FIFO (First In, First Out) strategy.
        
        Args:
            stock_name: Stock ticker
            volume: Number of shares to sell
            sell_price: Selling price per share
            fee: Optional broker fee (default: 0.0)
        """
        if stock_name not in self.stocks:
            logger.error(f"Stock '{stock_name}' not found in portfolio")
            return False
        
        stock = self.stocks[stock_name]
        if volume <= 0:
            logger.error("Volume must be greater than 0")
            return False
        
        if stock.get_total_shares() < volume:
            logger.error(f"Insufficient shares. Available: {stock.get_total_shares()}, Requested: {volume}")
            return False
        
        # Sort by price (FIFO - lowest price first)
        stock.sort_holdings_by_price()
        
        shares_to_sell = volume
        sold_holdings = []
        profit_records = []
        total_profit = 0.0
        today = datetime.date.today().strftime("%m/%d/%Y")
        
        # Sell shares starting from lowest priced holdings
        for holding in stock.holdings[:]:
            if shares_to_sell <= 0:
                break
            
            if holding.volume <= shares_to_sell:
                # Sell entire holding
                profit = (sell_price - holding.price) * holding.volume
                profit_records.append({
                    "stockName": stock_name,
                    "uid": holding.uid,
                    "buy_price": holding.price,
                    "sell_price": sell_price,
                    "volume": holding.volume,
                    "profit": profit,
                    "buy_date": holding.date,
                    "sell_date": today
                })
                
                sold_holdings.append((holding, holding.volume))
                shares_to_sell -= holding.volume
                total_profit += profit
                stock.holdings.remove(holding)
                
            else:
                # Sell partial holding
                profit = (sell_price - holding.price) * shares_to_sell
                profit_records.append({
                    "stockName": stock_name,
                    "uid": holding.uid,
                    "buy_price": holding.price,
                    "sell_price": sell_price,
                    "volume": shares_to_sell,
                    "profit": profit,
                    "buy_date": holding.date,
                    "sell_date": today
                })
                
                sold_holdings.append((holding, shares_to_sell))
                holding.volume -= shares_to_sell
                total_profit += profit
                shares_to_sell = 0
        
        # Save updated holdings
        stock.save_holdings()
        
        # Record profit
        self._record_sell_profits(stock_name, profit_records)
        
        # Record capital event if tracking is initialized
        if self.capital_tracker.is_initialized():
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            self.capital_tracker.record_sell(stock_name, volume, sell_price, total_profit, today_str, fee)
            self.capital_tracker.save()
        
        # Log transaction
        logger.info(f"Sold {volume} shares of {stock_name} for total profit: {total_profit:.2f} SEK (fee: {fee:.2f})")
        for holding, vol in sold_holdings:
            logger.info(f"  - {vol} shares at buy price {holding.price:.2f}")
        
        return True
    
    def _record_sell_profits(self, stock_name: str, profit_records: List[Dict]):
        """Record sell profits to file."""
        profit_file = os.path.join(self.path, f"{stock_name}_profit.json")
        
        existing_profits = self.data_manager.load_json(profit_file) or []
        existing_profits.extend(profit_records)
        
        self.data_manager.save_json(profit_file, existing_profits)
    
    def get_recent_sells(self, limit: int = 20) -> List[Dict]:
        """Get recent sell records across all stocks, grouped by sell_date + stock.
        
        Returns a list of sell "transactions" with all profit records grouped together.
        Each transaction dict has: stock_name, sell_date, sell_price, total_volume,
        total_profit, records (list of individual profit records with indices).
        """
        all_sells = []
        
        # Scan all profit files
        import glob
        profit_files = glob.glob(os.path.join(self.path, "*_profit.json"))
        
        for profit_file in profit_files:
            stock_name = os.path.basename(profit_file).replace("_profit.json", "")
            records = self.data_manager.load_json(profit_file) or []
            
            # Group records by sell_date + sell_price (they form a single sell transaction)
            from collections import defaultdict
            groups = defaultdict(list)
            for idx, record in enumerate(records):
                key = (record.get("sell_date", ""), record.get("sell_price", 0))
                groups[key].append((idx, record))
            
            for (sell_date, sell_price), group_records in groups.items():
                total_volume = sum(r["volume"] for _, r in group_records)
                total_profit = sum(r["profit"] for _, r in group_records)
                all_sells.append({
                    "stock_name": stock_name,
                    "sell_date": sell_date,
                    "sell_price": sell_price,
                    "total_volume": total_volume,
                    "total_profit": total_profit,
                    "records": group_records,  # list of (index, record_dict)
                    "profit_file": profit_file,
                })
        
        # Sort by sell_date descending (newest first)
        def parse_date(d):
            try:
                return datetime.datetime.strptime(d, "%m/%d/%Y").date()
            except Exception:
                try:
                    return datetime.datetime.strptime(d, "%Y-%m-%d").date()
                except Exception:
                    return datetime.date.min
        
        all_sells.sort(key=lambda x: parse_date(x["sell_date"]), reverse=True)
        return all_sells[:limit]
    
    def revert_sell(self, sell_transaction: Dict) -> bool:
        """Revert a sell transaction by restoring holdings and removing profit records.
        
        Args:
            sell_transaction: A transaction dict from get_recent_sells()
            
        Returns:
            True if successful, False otherwise.
        """
        stock_name = sell_transaction["stock_name"]
        profit_file = sell_transaction["profit_file"]
        records_to_remove = sell_transaction["records"]  # list of (index, record_dict)
        
        try:
            # 1. Restore holdings back to the stock
            if stock_name not in self.stocks:
                logger.error(f"Stock '{stock_name}' not found in portfolio for revert")
                return False
            
            stock = self.stocks[stock_name]
            
            for _, record in records_to_remove:
                buy_price = record["buy_price"]
                volume = record["volume"]
                buy_date = record.get("buy_date", datetime.date.today().strftime("%m/%d/%Y"))
                uid = record.get("uid", str(uuid.uuid4()))
                
                # Re-add holdings
                stock.holdings.append(StockSharesItem(volume, buy_price, buy_date, uid))
            
            stock.save_holdings()
            
            # 2. Remove profit records from the profit file
            existing_profits = self.data_manager.load_json(profit_file) or []
            
            # Remove by index (sort indices descending to avoid shifting)
            indices_to_remove = sorted([idx for idx, _ in records_to_remove], reverse=True)
            for idx in indices_to_remove:
                if 0 <= idx < len(existing_profits):
                    existing_profits.pop(idx)
            
            self.data_manager.save_json(profit_file, existing_profits)
            
            # 3. Remove capital tracker sell event if it exists
            if self.capital_tracker.is_initialized():
                sell_price = sell_transaction["sell_price"]
                total_volume = sell_transaction["total_volume"]
                total_amount = total_volume * sell_price
                
                # Find and remove the matching sell event
                events_to_keep = []
                removed = False
                for event in reversed(self.capital_tracker.events):
                    if (not removed and 
                        event.get('type') == 'sell' and 
                        event.get('stock') == stock_name and
                        event.get('volume') == total_volume and
                        abs(event.get('amount', 0) - total_amount) < 0.01):
                        # Found the matching event - skip it
                        removed = True
                        # Reverse the cash balance change
                        fee = event.get('fee', 0.0)
                        self.capital_tracker.cash_balance -= (total_amount - fee)
                        continue
                    events_to_keep.append(event)
                
                if removed:
                    self.capital_tracker.events = list(reversed(events_to_keep))
                    self.capital_tracker._update_summary()
                    self.capital_tracker.save()
            
            logger.info(f"Reverted sell: {sell_transaction['total_volume']} shares of {stock_name} "
                       f"(sell_date: {sell_transaction['sell_date']}, profit: {sell_transaction['total_profit']:.2f})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to revert sell for {stock_name}: {e}")
            return False
    
    def get_recent_buys(self, limit: int = 20) -> List[Dict]:
        """Get recent buy holdings across all stocks.
        
        Returns a list of buy records sorted by date (newest first).
        Each record has: stock_name, volume, price, date, uid.
        """
        all_buys = []
        
        for stock_name, stock in self.stocks.items():
            for holding in stock.holdings:
                all_buys.append({
                    "stock_name": stock_name,
                    "volume": holding.volume,
                    "price": holding.price,
                    "date": holding.date,
                    "uid": holding.uid,
                })
        
        # Sort by date descending (newest first)
        # Dates are in "MM/DD/YYYY" format
        def parse_date(d):
            try:
                return datetime.datetime.strptime(d, "%m/%d/%Y").date()
            except Exception:
                try:
                    return datetime.datetime.strptime(d, "%Y-%m-%d").date()
                except Exception:
                    return datetime.date.min
        
        all_buys.sort(key=lambda x: parse_date(x["date"]), reverse=True)
        return all_buys[:limit]
    
    def revert_buy(self, buy_record: Dict) -> bool:
        """Revert a buy transaction by removing the holding and capital event.
        
        Args:
            buy_record: A record dict from get_recent_buys()
            
        Returns:
            True if successful, False otherwise.
        """
        stock_name = buy_record["stock_name"]
        uid = buy_record["uid"]
        volume = buy_record["volume"]
        price = buy_record["price"]
        
        try:
            if stock_name not in self.stocks:
                logger.error(f"Stock '{stock_name}' not found in portfolio for revert")
                return False
            
            stock = self.stocks[stock_name]
            
            # 1. Remove the holding by uid
            holding_found = False
            for holding in stock.holdings[:]:
                if holding.uid == uid:
                    stock.holdings.remove(holding)
                    holding_found = True
                    break
            
            if not holding_found:
                logger.error(f"Holding with uid '{uid}' not found in {stock_name}")
                return False
            
            stock.save_holdings()
            
            # 2. Remove capital tracker buy event if it exists
            if self.capital_tracker.is_initialized():
                total_amount = volume * price
                
                events_to_keep = []
                removed = False
                for event in reversed(self.capital_tracker.events):
                    if (not removed and 
                        event.get('type') == 'buy' and 
                        event.get('stock') == stock_name and
                        event.get('volume') == volume and
                        abs(event.get('price', 0) - price) < 0.01):
                        # Found the matching event - skip it
                        removed = True
                        fee = event.get('fee', 0.0)
                        self.capital_tracker.cash_balance += (total_amount + fee)
                        continue
                    events_to_keep.append(event)
                
                if removed:
                    self.capital_tracker.events = list(reversed(events_to_keep))
                    self.capital_tracker._update_summary()
                    self.capital_tracker.save()
            
            logger.info(f"Reverted buy: {volume} shares of {stock_name} at {price:.2f} "
                       f"(date: {buy_record['date']})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to revert buy for {stock_name}: {e}")
            return False
    
    def save_portfolio(self) -> bool:
        """Save portfolio data to file."""
        return self.data_manager.save_json(self.filepath, self._portfolio_data)
    
    def find_stock_name_by_ticker(self, ticker: str) -> Optional[str]:
        """Find stock name by ticker symbol."""
        for name, stock in self.stocks.items():
            if stock.ticker == ticker:
                return name
        return None
    
    def get_stock_details(self) -> List[Dict]:
        """Get detailed information about all stocks in the portfolio."""
        details = []
        
        for name, stock in self.stocks.items():
            price_info = stock.get_price_info()
            
            # Skip invalid tickers
            if not self.ticker_validator.is_valid(stock.ticker):
                continue
            
            current_price_sek = price_info.get_current_sek() if price_info else 0.0
            avg_price = stock.get_average_price()
            avg_price_sek = self.currency_manager.convert_to_sek(avg_price, stock.ticker)
            
            details.append({
                "name": name,
                "ticker": stock.ticker,
                "shares": stock.get_total_shares(),
                "avg_price": avg_price_sek,
                "current_price": current_price_sek,
                "currency": self.currency_manager.get_currency(stock.ticker),
                "market_value": current_price_sek * stock.get_total_shares() if current_price_sek else 0.0,
                "total_cost": avg_price_sek * stock.get_total_shares() if avg_price_sek else 0.0,
                "unrealized_gain": ((current_price_sek - avg_price_sek) * stock.get_total_shares() 
                                  if current_price_sek and avg_price_sek else 0.0)
            })
        
        return details
    
    def get_stock_prices(self, include_zero_shares: bool = False, 
                        compute_history: bool = True) -> List[Dict]:
        """Get current price information for all stocks with in-memory caching."""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.debug(f"[Instance {self._instance_id}] get_stock_prices called: compute_history={compute_history}, include_zero_shares={include_zero_shares}")
        
        # Check cache if computing history (historical data doesn't change frequently)
        if compute_history:
            # Acquire lock for the entire cache check and rebuild operation
            with self._stock_prices_cache_lock:
                # Use cache if less than 2 minutes old (historical data is slow-changing)
                cache_age = time.time() - self._stock_prices_cache_time
                if self._stock_prices_cache is not None and cache_age < 120.0:
                    # Only update current prices if enough time has passed (throttle updates)
                    # This prevents excessive updates when switching views rapidly
                    if cache_age > 0.5:  # Update at most every 0.5 seconds
                        logger.info(f"[Instance {self._instance_id}] Cache HIT - updating current prices (age: {cache_age:.2f}s)")
                        self._update_cached_current_prices()
                        self._stock_prices_cache_time = time.time()
                    else:
                        logger.info(f"[Instance {self._instance_id}] Cache HIT - using without update (age: {cache_age:.2f}s)")
                    return self._stock_prices_cache
                
                # Cache miss or expired - rebuild with lock held
                if self._stock_prices_cache is None:
                    logger.warning(f"[Instance {self._instance_id}] Cache MISS - cache is None, rebuilding...")
                else:
                    logger.warning(f"[Instance {self._instance_id}] Cache EXPIRED - age {cache_age:.1f}s > 120s, rebuilding...")
        
                logger.warning(f"[Instance {self._instance_id}] Rebuilding stock prices cache (slow operation)...")
                results = self._build_stock_prices_data(include_zero_shares, compute_history=True)
                
                # Store in cache before releasing lock
                self._stock_prices_cache = results
                self._stock_prices_cache_time = time.time()
                logger.info(f"[Instance {self._instance_id}] Cache rebuilt and stored successfully")
                return results
        
        # No caching for compute_history=False
        return self._build_stock_prices_data(include_zero_shares, compute_history=False)
    
    def _build_stock_prices_data(self, include_zero_shares: bool, compute_history: bool) -> List[Dict]:
        """Build stock prices data (separated for cleaner code)."""
        import logging
        logger = logging.getLogger(__name__)
        
        build_start = time.time()
        results = []
        
        for name, stock in self.stocks.items():
            if not include_zero_shares and stock.get_total_shares() == 0:
                continue
            
            price_info = stock.get_price_info()
            if not price_info:
                continue
            
            # Calculate shares and total value
            total_shares = stock.get_total_shares()
            current_price_sek = price_info.get_current_sek()
            total_value = current_price_sek * total_shares if current_price_sek else 0.0
            
            data = {
                "name": name,
                "ticker": stock.ticker,
                "shares": total_shares,
                "price": current_price_sek,
                "total_value": total_value,
                "current": current_price_sek,
                "high": price_info.get_high_sek(),
                "low": price_info.get_low_sek(),
                "opening": price_info.get_opening_sek(),
                "currency": price_info.currency,
                # Original currency values (before SEK conversion)
                "current_native": price_info.current,
                "high_native": price_info.high,
                "low_native": price_info.low,
                "opening_native": price_info.opening,
            }
            
            if compute_history:
                # Add historical comparisons
                historical_periods = [1, 2, 3, 7, 14, 21, 63, 126, 365]  # days
                period_names = ["1d", "2d", "3d", "1w", "2w", "1m", "3m", "6m", "1y"]
                
                for days, period_name in zip(historical_periods, period_names):
                    hist_close_sek = price_info.get_historical_close(days)
                    hist_close_native = price_info.get_historical_close_native(days)
                    
                    # Store both SEK and native values
                    data[f"-{period_name}"] = hist_close_sek
                    data[f"-{period_name}_native"] = hist_close_native
                    
                    # Calculate percentage using native currency values
                    if hist_close_native and data["current_native"]:
                        pct_change = ((data["current_native"] - hist_close_native) / hist_close_native) * 100
                        data[f"%{period_name}"] = pct_change
                    else:
                        data[f"%{period_name}"] = None
            
            results.append(data)
        
        build_time = (time.time() - build_start) * 1000
        if build_time > 100:
            logger.warning(f"_build_stock_prices_data took {build_time:.1f}ms for {len(results)} stocks")
        
        # Return results (caching is handled in get_stock_prices)
        return results
    
    def _invalidate_stock_prices_cache(self):
        """Invalidate the stock prices cache when historical data changes."""
        with self._stock_prices_cache_lock:
            self._stock_prices_cache = None
            self._stock_prices_cache_time = 0
    
    def _update_cached_current_prices(self):
        """Update only the current prices in the cached stock prices data."""
        import logging
        logger = logging.getLogger(__name__)
        
        if self._stock_prices_cache is None:
            return
        
        start_time = time.time()
        count = 0
        
        # Update current prices in-place to avoid full recalculation
        for cached_data in self._stock_prices_cache:
            count += 1
            stock_name = cached_data.get("name")
            if stock_name and stock_name in self.stocks:
                stock = self.stocks[stock_name]
                price_info = stock.get_price_info()
                if price_info:
                    # Check if current price has actually changed
                    old_current_native = cached_data.get("current_native")
                    new_current_native = price_info.current
                    
                    # Only update if price changed (skip if both None or same value)
                    if old_current_native != new_current_native:
                        # Update SEK values
                        cached_data["current"] = price_info.get_current_sek()
                        cached_data["high"] = price_info.get_high_sek()
                        cached_data["low"] = price_info.get_low_sek()
                        cached_data["opening"] = price_info.get_opening_sek()
                        
                        # Update native currency values (critical for dot comparison)
                        cached_data["current_native"] = new_current_native
                        cached_data["high_native"] = price_info.high
                        cached_data["low_native"] = price_info.low
                        cached_data["opening_native"] = price_info.opening
                        
                        # Recalculate percentage changes using native currency values (consistent with get_stock_prices)
                        period_names = ["1d", "2d", "3d", "1w", "2w", "1m", "3m", "6m", "1y"]
                        for period_name in period_names:
                            hist_close_native = cached_data.get(f"-{period_name}_native")
                            if hist_close_native and cached_data["current_native"]:
                                pct_change = ((cached_data["current_native"] - hist_close_native) / hist_close_native) * 100
                                cached_data[f"%{period_name}"] = pct_change
                            else:
                                cached_data[f"%{period_name}"] = None
        
        elapsed = time.time() - start_time
        logger.info(f"[Instance {self._instance_id}] _update_cached_current_prices updated {count} stocks in {elapsed:.4f}s")
    
    def _batch_update_historical(self, tickers: List[str], 
                               specs: List[Tuple[str, str]] = None,
                               convert_to_sek: bool = True) -> Dict:
        """Internal method to batch update historical data for continuous updates."""
        specs = specs or [(self.config.DEFAULT_HISTORICAL_PERIOD, self.config.DEFAULT_HISTORICAL_INTERVAL)]
        results = {}
        
        if not tickers:
            return results
        
        today = datetime.date.today()
        
        for period, interval in specs:
            # Determine which tickers need refresh based on staleness
            tickers_to_refresh = []
            
            for ticker in tickers:
                filepath = self.data_manager.get_historical_filepath(ticker, period, interval, convert_to_sek)
                
                needs_refresh = not os.path.exists(filepath)
                
                if not needs_refresh:
                    # Check if data is current based on staleness threshold
                    needs_refresh = self.historical_manager.is_historical_data_stale(ticker, period, interval)
                
                if needs_refresh:
                    tickers_to_refresh.append(ticker)
            
            if not tickers_to_refresh:
                continue
            
            # Batch fetch historical data
            bulk_data = self.historical_manager.bulk_fetch_historical(
                tickers_to_refresh, period=period, interval=interval
            )
            
            # Process and save each ticker's data
            for ticker, df in bulk_data.items():
                if df is None or df.empty:
                    results[(ticker, period, interval)] = None
                    continue
                
                # Convert to SEK if requested
                if convert_to_sek:
                    df = self.historical_manager._convert_dataframe_to_sek(df, ticker)
                
                # Save to CSV
                filepath = self.data_manager.get_historical_filepath(ticker, period, interval, convert_to_sek)
                self.data_manager.save_csv(df, filepath)
                
                results[(ticker, period, interval)] = df
        
        return results
    
    def _invalidate_bulk_history(self, tickers: List[str]):
        """Invalidate bulk history cache for specified tickers."""
        for ticker in tickers:
            stock_price = self.real_time_manager.get_stock_price(ticker)
            if stock_price:
                stock_price.clear_cache()
        
        # Ensure bulk historical data is updated
        self.real_time_manager.ensure_bulk_history()
    
    def get_ticker_validation_status(self, ticker: str) -> Dict[str, any]:
        """Get detailed validation status for a specific ticker."""
        try:
            # Load current historical data
            df = self.historical_manager.load_historical_data(
                ticker,
                period=self.config.DEFAULT_HISTORICAL_PERIOD,
                interval=self.config.DEFAULT_HISTORICAL_INTERVAL,
                convert_to_sek=True
            )
            
            if df is None or df.empty:
                return {
                    'ticker': ticker,
                    'status': 'no_data',
                    'data_available': False,
                    'rows': 0,
                    'issues': ['No data available'],
                    'is_stale': True,
                    'last_date': None
                }
            
            # Check staleness
            is_stale = self.historical_manager.is_historical_data_stale(
                ticker,
                self.config.DEFAULT_HISTORICAL_PERIOD,
                self.config.DEFAULT_HISTORICAL_INTERVAL
            )
            
            # Validate data quality
            issues = self.historical_manager._validate_historical_data_quality(ticker, df)
            
            # Determine overall status
            if issues:
                status = 'has_issues'
            elif is_stale:
                status = 'stale'
            else:
                status = 'good'
            
            return {
                'ticker': ticker,
                'status': status,
                'data_available': True,
                'rows': len(df),
                'issues': issues,
                'is_stale': is_stale,
                'last_date': df.index[-1].date() if not df.empty else None,
                'date_range': f"{df.index[0].date()} to {df.index[-1].date()}" if not df.empty else None
            }
            
        except Exception as e:
            return {
                'ticker': ticker,
                'status': 'error',
                'data_available': False,
                'rows': 0,
                'issues': [f"Validation error: {str(e)[:100]}"],
                'is_stale': True,
                'last_date': None
            }
    
    def validate_all_tickers(self) -> Dict[str, Dict]:
        """Get validation status for all tickers in the portfolio."""
        tickers = [stock.ticker for stock in self.stocks.values()]
        results = {}
        
        logger.info(f"Validating historical data for {len(tickers)} tickers")
        
        for ticker in tickers:
            results[ticker] = self.get_ticker_validation_status(ticker)
        
        # Summary statistics
        statuses = [result['status'] for result in results.values()]
        good_count = statuses.count('good')
        stale_count = statuses.count('stale')
        issues_count = statuses.count('has_issues')
        no_data_count = statuses.count('no_data')
        error_count = statuses.count('error')
        
        logger.info(f"Validation summary: {good_count} good, {stale_count} stale, "
                   f"{issues_count} with issues, {no_data_count} no data, {error_count} errors")
        
        return results

    def get_historical_progress(self) -> Tuple[int, int]:
        """Get historical data loading progress."""
        with self._historical_lock:
            total = len(self._historical_done) + len(self._historical_pending)
            done = len(self._historical_done)
            return done, total
    
    def get_update_stats(self) -> Dict:
        """Get update statistics including both real-time and historical updates."""
        bulk_count, last_update = self.real_time_manager.get_update_stats()
        yf_count, last_yf_call = self.historical_manager.get_call_stats()
        
        # Get historical update status
        historical_update_status = {
            "continuous_updates_running": self._historical_update_running,
            "update_interval_seconds": self.config.HISTORICAL_UPDATE_INTERVAL,
            "stale_threshold_seconds": self.config.HISTORICAL_STALE_THRESHOLD,
        }
        
        # Check for stale tickers
        tickers = [stock.ticker for stock in self.stocks.values()]
        stale_tickers = self.historical_manager.get_stale_tickers(tickers) if tickers else []
        
        return {
            "bulk_updates": bulk_count,
            "last_bulk_update": last_update.strftime('%H:%M:%S') if last_update else None,
            "yfinance_calls": yf_count,
            "last_yfinance_call": last_yf_call.isoformat() if last_yf_call else None,
            "historical_updates": historical_update_status,
            "stale_tickers_count": len(stale_tickers),
            "stale_tickers": stale_tickers[:5] if stale_tickers else []  # Show first 5 for display
        }
    
    def is_valid_ticker(self, ticker: str) -> bool:
        """Check if a ticker is valid."""
        return self.ticker_validator.is_valid(ticker)
    
    def get_currency(self, ticker: str) -> str:
        """Get currency for a ticker."""
        return self.currency_manager.get_currency(ticker)
    
    def convert_to_sek(self, amount: float, ticker: str) -> Optional[float]:
        """Convert amount to SEK."""
        return self.currency_manager.convert_to_sek(amount, ticker)
    
    def __del__(self):
        """Cleanup resources."""
        try:
            self._stop_continuous_historical_updates()
            self.real_time_manager.stop_monitoring()
        except Exception:
            pass


# Legacy compatibility aliases (for gradual migration)
StockInventoryItem = StockSharesItem  # Old name compatibility
StockDataManager = RealTimeDataManager  # Partial compatibility