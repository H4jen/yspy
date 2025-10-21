"""
Helper functions for calculating historical portfolio values using market data.

This module provides utilities to reconstruct portfolio values at any historical
date by combining transaction history with fetched historical market prices.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def load_historical_prices(filepath: str = 'portfolio/historical_prices.json') -> Optional[Dict]:
    """
    Load historical price data from JSON file.
    
    Args:
        filepath: Path to the historical prices JSON file
        
    Returns:
        Dictionary with historical prices, or None if file doesn't exist
    """
    path = Path(filepath)
    if not path.exists():
        logger.warning(f"Historical prices file not found: {filepath}")
        return None
    
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading historical prices: {e}")
        return None


def get_stock_price_on_date(stock_name: str, date: str, historical_data: Dict) -> Optional[float]:
    """
    Get the closing price of a stock on a specific date.
    
    Args:
        stock_name: Portfolio stock name (e.g., 'ssab-b')
        date: Date in YYYY-MM-DD format
        historical_data: Historical prices data structure
        
    Returns:
        Price in native currency, or None if not available
    """
    if not historical_data or 'stocks' not in historical_data:
        return None
    
    stock_data = historical_data['stocks'].get(stock_name)
    if not stock_data or 'prices' not in stock_data:
        return None
    
    # Try exact date first
    price = stock_data['prices'].get(date)
    if price is not None:
        return price
    
    # If exact date not found, try looking back a few days (weekends, holidays)
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    for days_back in range(1, 5):
        prev_date = (date_obj - timedelta(days=days_back)).strftime('%Y-%m-%d')
        price = stock_data['prices'].get(prev_date)
        if price is not None:
            logger.debug(f"Using price from {prev_date} for {stock_name} on {date}")
            return price
    
    logger.warning(f"No price found for {stock_name} on or near {date}")
    return None


def calculate_holdings_on_date(events: List[Dict], target_date: str) -> Dict[str, Dict]:
    """
    Calculate stock holdings (shares owned) on a specific date using FIFO.
    
    Args:
        events: List of capital events sorted by date
        target_date: Target date in YYYY-MM-DD format
        
    Returns:
        Dictionary mapping stock_name -> {'shares': int, 'fifo_lots': List[{'shares': int, 'price': float}]}
    """
    holdings = {}
    target = datetime.strptime(target_date, '%Y-%m-%d')
    
    for event in events:
        event_date = datetime.strptime(event['date'], '%Y-%m-%d')
        if event_date > target:
            break
        
        if event['type'] == 'buy':
            stock = event['stock']
            volume = event['volume']
            price = event['price']
            
            if stock not in holdings:
                holdings[stock] = {'shares': 0, 'fifo_lots': []}
            
            holdings[stock]['shares'] += volume
            holdings[stock]['fifo_lots'].append({'shares': volume, 'price': price})
        
        elif event['type'] == 'sell':
            stock = event['stock']
            volume = abs(event['volume'])
            
            if stock not in holdings:
                logger.warning(f"Sell before buy for {stock} on {event['date']}")
                continue
            
            # Deduct using FIFO
            remaining = volume
            while remaining > 0 and holdings[stock]['fifo_lots']:
                lot = holdings[stock]['fifo_lots'][0]
                if lot['shares'] <= remaining:
                    remaining -= lot['shares']
                    holdings[stock]['fifo_lots'].pop(0)
                else:
                    lot['shares'] -= remaining
                    remaining = 0
            
            holdings[stock]['shares'] -= volume
            
            # Remove stock if no shares left
            if holdings[stock]['shares'] <= 0:
                del holdings[stock]
    
    return holdings


def calculate_portfolio_value_on_date(
    events: List[Dict],
    target_date: str,
    historical_data: Dict,
    exchange_rates: Optional[Dict[str, float]] = None
) -> Tuple[float, float, Dict]:
    """
    Calculate total portfolio value on a specific date.
    
    Args:
        events: List of capital events sorted by date
        target_date: Target date in YYYY-MM-DD format
        historical_data: Historical prices data
        exchange_rates: Optional dict of currency -> SEK rate (defaults to 1.0 for SEK)
        
    Returns:
        Tuple of (cash_balance, stock_market_value, holdings_detail)
    """
    if exchange_rates is None:
        exchange_rates = {'SEK': 1.0, 'NOK': 0.95, 'DKK': 1.5, 'EUR': 11.5}
    
    target = datetime.strptime(target_date, '%Y-%m-%d')
    
    # Calculate cash balance
    cash_balance = 0.0
    for event in events:
        event_date = datetime.strptime(event['date'], '%Y-%m-%d')
        if event_date > target:
            break
        
        if event['type'] in ['deposit', 'initial_deposit']:
            cash_balance += event['amount']
        elif event['type'] == 'withdrawal':
            cash_balance -= abs(event['amount'])
        elif event['type'] == 'buy':
            cash_balance -= event['amount'] + event.get('fee', 0.0)
        elif event['type'] == 'sell':
            cash_balance += event['amount'] - event.get('fee', 0.0)
    
    # Calculate stock holdings
    holdings = calculate_holdings_on_date(events, target_date)
    
    # Calculate market value of stocks
    stock_market_value = 0.0
    holdings_detail = {}
    
    for stock_name, holding_info in holdings.items():
        shares = holding_info['shares']
        price = get_stock_price_on_date(stock_name, target_date, historical_data)
        
        if price is None:
            logger.warning(f"Missing price for {stock_name} on {target_date}, using cost basis")
            # Fallback: use weighted average cost
            total_cost = sum(lot['shares'] * lot['price'] for lot in holding_info['fifo_lots'])
            price = total_cost / shares if shares > 0 else 0.0
        
        # Get currency and convert to SEK
        currency = historical_data['stocks'].get(stock_name, {}).get('currency', 'SEK')
        rate = exchange_rates.get(currency, 1.0)
        price_sek = price * rate
        
        value_sek = shares * price_sek
        stock_market_value += value_sek
        
        holdings_detail[stock_name] = {
            'shares': shares,
            'price': price,
            'currency': currency,
            'price_sek': price_sek,
            'value_sek': value_sek,
            'fifo_lots': holding_info.get('fifo_lots', [])  # Include FIFO lots for cost basis calculation
        }
    
    return cash_balance, stock_market_value, holdings_detail


def calculate_portfolio_timeline(
    events: List[Dict],
    historical_data: Dict,
    exchange_rates: Optional[Dict[str, float]] = None,
    portfolio_path: str = 'portfolio',
    portfolio: Optional[object] = None
) -> List[Dict]:
    """
    Calculate portfolio value at each event date.
    
    Args:
        events: List of capital events sorted by date
        historical_data: Historical prices data
        exchange_rates: Optional dict of currency -> SEK rate
        portfolio_path: Path to portfolio directory for loading profit files
        portfolio: Optional Portfolio object for getting actual holdings cost basis
        
    Returns:
        List of dicts with date, cash, stocks_value, total_value, realized_profit, etc.
    """
    import os
    import json
    from datetime import datetime
    
    timeline = []
    cumulative_deposits = 0.0
    cumulative_withdrawals = 0.0
    
    if exchange_rates is None:
        exchange_rates = {'SEK': 1.0, 'NOK': 0.95, 'DKK': 1.5, 'EUR': 11.5}
    
    # Get actual portfolio holdings cost basis if available
    actual_cost_basis = None
    if portfolio:
        actual_cost_basis = 0.0
        for ticker, stock in portfolio.stocks.items():
            if stock.holdings:
                actual_cost_basis += sum(share.volume * share.price for share in stock.holdings)
    
    # Load all profit records from profit files (these are always in SEK)
    all_profit_records = []
    profit_files = [f for f in os.listdir(portfolio_path) if f.endswith('_profit.json')]
    for profit_file in profit_files:
        try:
            with open(os.path.join(portfolio_path, profit_file), 'r') as f:
                records = json.load(f)
                all_profit_records.extend(records)
        except Exception as e:
            logger.warning(f"Could not load {profit_file}: {e}")
    
    for event in events:
        date = event['date']
        event_date = datetime.strptime(date, '%Y-%m-%d')
        
        # Update cumulative values
        if event['type'] in ['deposit', 'initial_deposit']:
            cumulative_deposits += event['amount']
        elif event['type'] == 'withdrawal':
            cumulative_withdrawals += abs(event['amount'])
        
        # Calculate cumulative realized profit from profit files up to this date
        # Profit files store values in SEK already
        cumulative_realized = 0.0
        for record in all_profit_records:
            sell_date_str = record.get('sell_date')
            if sell_date_str:
                try:
                    # Parse date (format: MM/DD/YYYY)
                    sell_date = datetime.strptime(sell_date_str, '%m/%d/%Y')
                    if sell_date <= event_date:
                        cumulative_realized += record.get('profit', 0.0)
                except:
                    pass
        
        # Calculate portfolio value at this date
        cash, stocks_value, holdings = calculate_portfolio_value_on_date(
            events, date, historical_data, exchange_rates
        )
        
        total_value = cash + stocks_value
        net_capital = cumulative_deposits - cumulative_withdrawals
        
        # Calculate cost basis of current holdings (what you paid for them) IN SEK
        # Use actual portfolio holdings if available (most accurate), otherwise use FIFO reconstruction
        if actual_cost_basis is not None and i == len(events) - 1:  # Only use for last point (today)
            cost_basis = actual_cost_basis
        else:
            # Calculate from FIFO lots for historical dates
            cost_basis = 0.0
            for stock_name, holding_info in holdings.items():
                # Get currency and exchange rate for this stock
                currency = holding_info.get('currency', 'SEK')
                rate = exchange_rates.get(currency, 1.0)
                
                # Sum up cost of all FIFO lots, converting to SEK
                fifo_lots = holding_info.get('fifo_lots', [])
                for lot in fifo_lots:
                    cost_basis += lot['shares'] * lot['price'] * rate
        
        # Unrealized profit = current market value - cost basis (both in SEK)
        unrealized_profit = stocks_value - cost_basis
        
        # Total profit = unrealized (current holdings) + realized (past sales)
        total_profit = unrealized_profit + cumulative_realized
        
        timeline.append({
            'date': date,
            'cash': cash,
            'stocks_value': stocks_value,
            'total_value': total_value,
            'net_capital': net_capital,
            'realized_profit': cumulative_realized,
            'unrealized_profit': unrealized_profit,
            'total_profit': total_profit,
            'return_pct': (total_profit / net_capital * 100) if net_capital > 0 else 0.0,
            'holdings': holdings
        })
    
    return timeline


def calculate_daily_portfolio_timeline(
    events: List[Dict],
    historical_data: Dict,
    exchange_rates: Optional[Dict[str, float]] = None,
    portfolio_path: str = 'portfolio',
    portfolio: Optional[object] = None
) -> List[Dict]:
    """
    Calculate portfolio value for EVERY DAY (not just event dates).
    
    This provides smooth daily data points for charting, eliminating artifacts
    from multiple transactions on the same day.
    
    Args:
        events: List of capital events sorted by date
        historical_data: Historical prices data
        exchange_rates: Optional dict of currency -> SEK rate
        portfolio_path: Path to portfolio directory for loading profit files
        portfolio: Optional Portfolio object for getting actual holdings cost basis
        
    Returns:
        List of dicts with date, cash, stocks_value, total_value, realized_profit, etc.
        One entry per calendar day from first event to last event.
    """
    import os
    import json
    from datetime import datetime, timedelta
    
    if not events:
        return []
    
    if exchange_rates is None:
        exchange_rates = {'SEK': 1.0, 'NOK': 0.95, 'DKK': 1.5, 'EUR': 11.5}
    
    # Get actual portfolio holdings cost basis if available
    actual_cost_basis = None
    if portfolio:
        actual_cost_basis = 0.0
        for ticker, stock in portfolio.stocks.items():
            if stock.holdings:
                actual_cost_basis += sum(share.volume * share.price for share in stock.holdings)
    
    # Load all profit records from profit files (these are always in SEK)
    all_profit_records = []
    profit_files = [f for f in os.listdir(portfolio_path) if f.endswith('_profit.json')]
    for profit_file in profit_files:
        try:
            with open(os.path.join(portfolio_path, profit_file), 'r') as f:
                records = json.load(f)
                all_profit_records.extend(records)
        except Exception as e:
            logger.warning(f"Could not load {profit_file}: {e}")
    
    # Get date range - start from first event, but extend to latest historical price date
    start_date = datetime.strptime(events[0]['date'], '%Y-%m-%d')
    end_date = datetime.strptime(events[-1]['date'], '%Y-%m-%d')
    
    # Find the latest date with historical prices (should be more recent than last event)
    latest_price_date = end_date
    for stock_name, stock_data in historical_data.get('stocks', {}).items():
        prices = stock_data.get('prices', {})
        if prices:
            stock_dates = [datetime.strptime(d, '%Y-%m-%d') for d in prices.keys()]
            if stock_dates:
                stock_latest = max(stock_dates)
                if stock_latest > latest_price_date:
                    latest_price_date = stock_latest
    
    # Use the latest available date (either last event or latest price)
    end_date = latest_price_date
    
    timeline = []
    current_date = start_date
    
    # Track cumulative values (updated as we process events)
    cumulative_deposits = 0.0
    cumulative_withdrawals = 0.0
    
    # Index for tracking which events we've processed
    event_idx = 0
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Process all events that occur on this date
        while event_idx < len(events) and events[event_idx]['date'] == date_str:
            event = events[event_idx]
            
            if event['type'] in ['deposit', 'initial_deposit']:
                cumulative_deposits += event['amount']
            elif event['type'] == 'withdrawal':
                cumulative_withdrawals += abs(event['amount'])
            
            event_idx += 1
        
        # Calculate cumulative realized profit from profit files up to this date
        # Profit files store values in SEK already
        cumulative_realized = 0.0
        for record in all_profit_records:
            sell_date_str = record.get('sell_date')
            if sell_date_str:
                try:
                    # Parse date (format: MM/DD/YYYY)
                    sell_date = datetime.strptime(sell_date_str, '%m/%d/%Y')
                    if sell_date <= current_date:
                        cumulative_realized += record.get('profit', 0.0)
                except:
                    pass
        
        # Calculate portfolio value at END of this day (after all transactions)
        cash, stocks_value, holdings = calculate_portfolio_value_on_date(
            events, date_str, historical_data, exchange_rates
        )
        
        total_value = cash + stocks_value
        net_capital = cumulative_deposits - cumulative_withdrawals
        
        # Calculate cost basis of current holdings (what you paid for them) IN SEK
        # Use actual portfolio holdings if available (most accurate), otherwise use FIFO reconstruction
        is_last_date = (current_date == end_date)
        if actual_cost_basis is not None and is_last_date:  # Only use for last date (today)
            cost_basis = actual_cost_basis
        else:
            # Calculate from FIFO lots for historical dates
            cost_basis = 0.0
            for stock_name, holding_info in holdings.items():
                # Get currency and exchange rate for this stock
                currency = holding_info.get('currency', 'SEK')
                rate = exchange_rates.get(currency, 1.0)
                
                # Sum up cost of all FIFO lots, converting to SEK
                fifo_lots = holding_info.get('fifo_lots', [])
                for lot in fifo_lots:
                    cost_basis += lot['shares'] * lot['price'] * rate
        
        # Unrealized profit = current market value - cost basis (both in SEK)
        unrealized_profit = stocks_value - cost_basis
        
        # Total profit = unrealized (current holdings) + realized (past sales)
        total_profit = unrealized_profit + cumulative_realized
        
        timeline.append({
            'date': date_str,
            'cash': cash,
            'stocks_value': stocks_value,
            'total_value': total_value,
            'net_capital': net_capital,
            'realized_profit': cumulative_realized,
            'unrealized_profit': unrealized_profit,
            'total_profit': total_profit,
            'return_pct': (total_profit / net_capital * 100) if net_capital > 0 else 0.0,
            'holdings': holdings
        })
        
        # Move to next day
        current_date += timedelta(days=1)
    
    return timeline
