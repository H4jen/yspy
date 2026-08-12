#!/usr/bin/env python3
"""
Differential updater for historical prices - only fetches missing days since last update.
Integrated into app startup for automatic updates.
Automatically discovers all stocks from portfolio.
Converts all prices to SEK for consistent profit/loss calculations.
"""

import json
import logging
import yfinance as yf
import time
import sys
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.portfolio_manager import CurrencyManager

logger = logging.getLogger(__name__)

PRICES_FILE = 'portfolio/historical_prices.json'
PORTFOLIO_DIR = 'portfolio'
PORTFOLIO_FILE = 'portfolio/stockPortfolio.json'
YFINANCE_BATCH_SIZE = 10


def discover_portfolio_stocks() -> Dict[str, str]:
    """
    Discover stocks that need historical data by checking:
    1. Stocks with current holdings (own shares now)
    2. Stocks with profit history (previously sold)
    
    This ensures we update historical prices for any stock you own or have traded,
    while skipping stocks that were added but never bought.
    
    Returns:
        Dict mapping stock_name -> ticker (e.g., {'alleima': 'ALLEI.ST'})
    """
    portfolio_path = Path(PORTFOLIO_FILE)
    
    if not portfolio_path.exists():
        logger.warning(f"Portfolio file not found: {PORTFOLIO_FILE}")
        return {}
    
    try:
        with open(portfolio_path) as f:
            portfolio_data = json.load(f)
        
        stocks = {}
        portfolio_dir = Path(PORTFOLIO_DIR)
        
        for stock_name, ticker in portfolio_data.items():
            if not ticker or not isinstance(ticker, str):
                continue
            
            # Check 1: Does it have current holdings?
            ticker_file = ticker.replace('.', '_') + '.json'
            holdings_path = portfolio_dir / ticker_file
            has_holdings = False
            
            if holdings_path.exists():
                try:
                    with open(holdings_path) as hf:
                        holdings = json.load(hf)
                        has_holdings = isinstance(holdings, list) and len(holdings) > 0
                except:
                    pass
            
            # Check 2: Does it have profit history?
            profit_path = portfolio_dir / f"{stock_name}_profit.json"
            has_profit_history = False
            
            if profit_path.exists():
                try:
                    with open(profit_path) as pf:
                        profits = json.load(pf)
                        has_profit_history = isinstance(profits, list) and len(profits) > 0
                except:
                    pass
            
            # Include if either condition is true
            if has_holdings or has_profit_history:
                stocks[stock_name] = ticker
                status = []
                if has_holdings:
                    status.append("holdings")
                if has_profit_history:
                    status.append("profit history")
                logger.debug(f"Including {stock_name}: {', '.join(status)}")
        
        logger.info(f"Discovered {len(stocks)} stocks with holdings or profit history: {', '.join(stocks.keys())}")
        return stocks
        
    except Exception as e:
        logger.error(f"Failed to discover portfolio stocks: {e}")
        return {}


def get_missing_date_range(prices_file: str = PRICES_FILE) -> Optional[tuple]:
    """
    Determine what date range needs to be fetched.
    
    Returns:
        (start_date, end_date) tuple if update needed, None if current
    """
    path = Path(prices_file)
    if not path.exists():
        logger.info("Historical prices file not found - full fetch needed")
        return ("2025-02-01", date.today().strftime('%Y-%m-%d'))
    
    try:
        with open(path) as f:
            data = json.load(f)
        
        # Get the last date we have data for (look at actual price dates, not fetch_date)
        last_data_date = data.get('end_date', '')
        if last_data_date:
            last_date = datetime.strptime(last_data_date, '%Y-%m-%d').date()
        else:
            # Fallback: find latest date in actual price data
            latest = date(2025, 2, 1)
            for stock_data in data['stocks'].values():
                if stock_data.get('prices'):
                    dates = [datetime.strptime(d, '%Y-%m-%d').date() 
                            for d in stock_data['prices'].keys()]
                    if dates:
                        latest = max(latest, max(dates))
            last_date = latest
        
        today = date.today()
        
        if last_date >= today:
            logger.info(f"Historical data is current (last: {last_date})")
            return None
        
        # Need to fetch from day after last_date to today
        start_date = (last_date + timedelta(days=1)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
        
        days_missing = (today - last_date).days
        logger.info(f"Need to fetch {days_missing} missing days ({start_date} to {end_date})")
        
        return (start_date, end_date)
        
    except Exception as e:
        logger.error(f"Error checking existing data: {e}")
        # If error, do full fetch
        return ("2025-02-01", date.today().strftime('%Y-%m-%d'))


def fetch_missing_prices(start_date: str, end_date: str, ticker_map: Dict[str, str],
                         currency_manager: CurrencyManager = None,
                         batch_size: int = YFINANCE_BATCH_SIZE) -> Dict:
    """
    Fetch only the missing date range for all stocks.
    Converts all prices to SEK for consistent profit/loss calculations.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        ticker_map: Dictionary mapping stock_name -> ticker
        currency_manager: CurrencyManager for currency conversion
        batch_size: Maximum number of tickers per Yahoo Finance download
        
    Returns:
        Dictionary of stock -> {date -> price_in_sek}
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    new_prices = {}

    # Initialize currency manager if not provided
    if currency_manager is None:
        currency_manager = CurrencyManager(PORTFOLIO_DIR, allow_online_lookup=True)

    stock_items = list(ticker_map.items())
    for batch_start in range(0, len(stock_items), batch_size):
        stock_batch = stock_items[batch_start:batch_start + batch_size]
        batch_tickers = list(dict.fromkeys(ticker for _, ticker in stock_batch))
        bulk_data = None

        try:
            bulk_data = yf.download(
                batch_tickers,
                start=start_date,
                end=end_date,
                auto_adjust=True,
                group_by='ticker',
                progress=False,
            )
        except Exception as e:
            logger.warning(f"Bulk Yahoo Finance fetch failed for {batch_tickers}: {e}")

        for stock_name, ticker in stock_batch:
            df = None
            if bulk_data is not None and not bulk_data.empty:
                if len(batch_tickers) == 1:
                    df = bulk_data
                elif getattr(bulk_data.columns, 'nlevels', 1) > 1:
                    available_tickers = bulk_data.columns.get_level_values(0)
                    if ticker in available_tickers:
                        df = bulk_data.xs(ticker, level=0, axis=1)

            # Keep the former request path only for symbols absent from a batch.
            if df is None or df.empty:
                try:
                    df = yf.Ticker(ticker).history(start=start_date, end=end_date, auto_adjust=True)
                except Exception as e:
                    logger.error(f"Error fetching {stock_name}: {e}")
                    df = None
                time.sleep(0.3)

            if df is None or df.empty:
                new_prices[stock_name] = {}
                logger.warning(f"✗ No new data for {stock_name}")
                continue

            try:
                df = df[['Close']].copy()
                if getattr(df.index, 'tz', None) is not None:
                    df.index = df.index.tz_localize(None)

                currency = currency_manager.get_currency(ticker)
                rate = currency_manager.exchange_rates.get(currency, 1.0)
                prices = {
                    date_value.strftime('%Y-%m-%d'): float(price) * rate
                    for date_value, price in df['Close'].items()
                }
                new_prices[stock_name] = prices
                if currency != 'SEK':
                    logger.info(f"✓ Fetched {len(prices)} new days for {stock_name} ({currency} -> SEK, rate={rate:.4f})")
                else:
                    logger.info(f"✓ Fetched {len(prices)} new days for {stock_name}")
            except Exception as e:
                logger.error(f"Error processing {stock_name}: {e}")
                new_prices[stock_name] = {}

        if batch_start + batch_size < len(stock_items):
            time.sleep(0.3)  # Rate limiting between bulk requests

    return new_prices


def update_historical_prices_differential(prices_file: str = PRICES_FILE) -> bool:
    """
    Perform differential update - only fetch and merge missing days.
    Automatically discovers stocks from portfolio.
    All prices are converted to SEK for consistent profit/loss calculations.
    
    Returns:
        True if update was performed, False if data was already current
    """
    # Discover all stocks from portfolio
    ticker_map = discover_portfolio_stocks()
    
    if not ticker_map:
        logger.warning("No stocks found in portfolio")
        return False
    
    # Initialize currency manager for converting prices to SEK
    currency_manager = CurrencyManager(PORTFOLIO_DIR, allow_online_lookup=True)
    
    # Load existing data to check for missing stocks
    path = Path(prices_file)
    if path.exists():
        with open(path) as f:
            existing_data = json.load(f)
    else:
        # Initialize new structure with discovered stocks
        existing_data = {
            'fetch_date': '',
            'start_date': '2025-02-01',
            'end_date': '',
            'stocks': {}
        }
    
    # Check for missing stocks even if dates are current
    missing_stocks = []
    for name, ticker in ticker_map.items():
        if name not in existing_data['stocks']:
            missing_stocks.append((name, ticker))
    
    date_range = get_missing_date_range(prices_file)
    
    # If no missing dates AND no missing stocks, we're truly current
    if date_range is None and not missing_stocks:
        return False  # Already current
    
    # Determine date range to fetch
    if date_range is not None:
        start_date, end_date = date_range
    else:
        # No missing dates, but we have missing stocks - fetch recent data for new stocks
        from datetime import date, timedelta
        today = date.today()
        # Fetch last 30 days for new stocks to get sufficient historical data
        start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
        logger.info(f"No missing dates, but found {len(missing_stocks)} new stocks: {[name for name, _ in missing_stocks]}")
    
    # Ensure all current portfolio stocks are in the structure
    for name, ticker in ticker_map.items():
        if name not in existing_data['stocks']:
            # New stock added to portfolio - initialize it
            # All prices are stored in SEK after conversion
            existing_data['stocks'][name] = {
                'ticker': ticker,
                'currency': 'SEK',  # All prices converted to SEK
                'prices': {},
                'data_points': 0
            }
            logger.info(f"Added new stock to historical data: {name} ({ticker})")
    
    # Fetch missing prices (converted to SEK)
    logger.info(f"Fetching missing historical prices from {start_date} to {end_date}...")
    new_prices = fetch_missing_prices(start_date, end_date, ticker_map, currency_manager)
    
    # Merge new prices into existing data
    for stock_name, prices in new_prices.items():
        if stock_name in existing_data['stocks']:
            existing_data['stocks'][stock_name]['prices'].update(prices)
            existing_data['stocks'][stock_name]['data_points'] = len(
                existing_data['stocks'][stock_name]['prices']
            )
    
    # Update metadata
    existing_data['fetch_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    existing_data['end_date'] = end_date
    
    # Save merged data
    with open(path, 'w') as f:
        json.dump(existing_data, f, indent=2)
    
    total_new = sum(len(p) for p in new_prices.values())
    logger.info(f"✓ Added {total_new} new price points across {len(new_prices)} stocks")
    
    return True


if __name__ == '__main__':
    import argparse
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    parser = argparse.ArgumentParser(description='Update historical prices differentially')
    parser.add_argument('--check-only', '-c', action='store_true',
                        help='Only check what needs updating, don\'t update')
    
    args = parser.parse_args()
    
    if args.check_only:
        date_range = get_missing_date_range()
        if date_range:
            print(f"Update needed: {date_range[0]} to {date_range[1]}")
            exit(1)
        else:
            print("Data is current")
            exit(0)
    else:
        updated = update_historical_prices_differential()
        if updated:
            print("✓ Historical prices updated")
        else:
            print("✓ Historical prices already current")
        exit(0)
