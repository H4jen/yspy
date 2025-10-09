import curses
import os
import json
import time

def color_for_value(value):
    """
    Returns a curses color pair number based on the value:
    - Green for positive
    - Red for negative
    - Yellow for zero or None
    """
    if value is None:
        return curses.color_pair(3)  # Yellow
    try:
        v = float(value)
        if v > 0:
            return curses.color_pair(1)  # Green
        elif v < 0:
            return curses.color_pair(2)  # Red
        else:
            return curses.color_pair(3)  # Yellow
    except Exception:
        return curses.color_pair(3)  # Yellow

def get_portfolio_list_lines(portfolio):
    """
    Returns a list of strings representing the portfolio,
    using Portfolio.get_stock_details, with aligned columns.
    """
    lines = []
    stock_details = portfolio.get_stock_details()
    if not stock_details:
        lines.append("No stocks in portfolio.")
        return lines

    # Adjusted column widths: Ticker 12, Name 12, Shares 10, Avg Price 12, Current Price 15
    header = "{:<12} {:<12} {:>10} {:>12} {:>15}".format(
        "Ticker", "Name", "Shares", "Avg Price", "Current Price"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for stock in stock_details:
        lines.append(
            "{:<12} {:<12} {:>10} {:>12.2f} {:>15.2f}".format(
                stock['ticker'],
                stock['name'],
                stock['shares'],
                stock['avg_price'] if stock['avg_price'] is not None else 0.0,
                stock['current_price'] if stock['current_price'] is not None else 0.0
            )
        )
    return lines

def get_portfolio_shares_lines(portfolio):
    """
    Returns a list of strings representing detailed share information,
    showing each individual share purchase with dates and prices.
    """
    lines = []
    if not portfolio.stocks:
        lines.append("No stocks in portfolio.")
        return lines

    # Header for shares listing - added Profit/Loss column
    header = "{:<16} {:>8} {:>10} {:>14} {:>14} {}".format(
        "Ticker", "Shares", "Price", "Total", "Profit/Loss", "Date"
    )
    lines.append(header)
    lines.append("-" * len(header))
    
    for ticker, stock in portfolio.stocks.items():
        if not hasattr(stock, 'holdings') or not stock.holdings:
            continue
        
        # Get current price for profit/loss calculation
        current_price = 0.0
        try:
            price_obj = stock.get_price_info()
            if price_obj and price_obj.get_current_sek() is not None:
                current_price = float(price_obj.get_current_sek())
        except Exception as e:
            current_price = 0.0
            
        # Get actual profit/loss from sold shares
        profit_file = os.path.join(portfolio.path, f"{ticker}_profit.json")
        actual_profit = 0.0
        if os.path.exists(profit_file):
            try:
                with open(profit_file, "r") as f:
                    profit_records = json.load(f)
                    actual_profit = sum(record.get("profit", 0.0) for record in profit_records)
            except Exception:
                pass
            
        # Sort shares by date
        try:
            sorted_shares = sorted(stock.holdings, key=lambda x: x.date)
        except:
            sorted_shares = stock.holdings  # Fall back to unsorted if date sorting fails
        
        for share in sorted_shares:
            total_value = share.volume * share.price
            # Calculate unrealized profit/loss for this specific share
            if current_price > 0:
                current_value = share.volume * current_price
                unrealized_profit_loss = current_value - total_value
            else:
                unrealized_profit_loss = 0.0
            
            # Handle different date formats
            try:
                if hasattr(share.date, 'strftime'):
                    date_str = share.date.strftime("%Y-%m-%d")
                elif hasattr(share.date, 'isoformat'):
                    date_str = share.date.isoformat()[:10]
                else:
                    date_str = str(share.date)
            except:
                date_str = "Unknown"
            
            lines.append(
                "{:<16} {:>8} {:>10.2f} {:>14.2f} {:>14.2f} {}".format(
                    ticker,
                    share.volume,
                    share.price,
                    total_value,
                    unrealized_profit_loss,
                    date_str
                )
            )
        
        # Add summary line for this stock
        total_shares = sum(s.volume for s in stock.holdings)
        total_cost = sum(s.volume * s.price for s in stock.holdings)
        avg_price = total_cost / total_shares if total_shares > 0 else 0
        
        # Calculate total unrealized profit/loss (only for current holdings)
        if current_price > 0:
            total_current_value = total_shares * current_price
            total_unrealized_profit_loss = total_current_value - total_cost
        else:
            total_unrealized_profit_loss = 0.0
        
        lines.append(
            "{:<16} {:>8} {:>10.2f} {:>14.2f} {:>14.2f} {}".format(
                f"[{ticker}]",
                total_shares,
                avg_price,
                total_cost,
                total_unrealized_profit_loss,  # Only unrealized profit/loss
                "TOTAL"
            )
        )
        lines.append("")  # Empty line between stocks
    
    return lines

def calculate_portfolio_totals(portfolio):
    """
    Calculate total portfolio value, buy value, and -1d value similar to stockinventory stockprice command.
    Returns a dict with the calculated values.
    """
    total_portfolio_value = 0.0
    total_portfolio_buy_value = 0.0
    total_portfolio_value_1d = 0.0
    
    for name, stock in portfolio.stocks.items():
        total_shares = sum(share.volume for share in stock.holdings)
        if total_shares == 0:
            continue
            
        price_obj = stock.get_price_info()
        current_price = price_obj.get_current_sek() if price_obj else None
        
        # Add to total portfolio value
        if current_price is not None:
            total_portfolio_value += total_shares * current_price
            
        # Add to total buy value (sum of all share purchases)
        total_portfolio_buy_value += sum(share.volume * share.price for share in stock.holdings)
        
        # For -1d portfolio value
        yest_close = price_obj.get_historical_close(1)
        if yest_close is not None:
            total_portfolio_value_1d += total_shares * yest_close
    
    diff = total_portfolio_value - total_portfolio_buy_value
    diff_1d = total_portfolio_value - total_portfolio_value_1d
    
    # Calculate percentage change from -1d
    pct_1d = 0.0
    if total_portfolio_value_1d != 0:
        pct_1d = ((total_portfolio_value - total_portfolio_value_1d) / total_portfolio_value_1d) * 100
    
    return {
        'total_value': total_portfolio_value,
        'buy_value': total_portfolio_buy_value,
        'value_1d': total_portfolio_value_1d,
        'diff': diff,
        'diff_1d': diff_1d,
        'pct_1d': pct_1d
    }
