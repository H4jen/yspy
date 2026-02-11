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

def get_portfolio_shares_lines(portfolio, stock_prices=None):
    """
    Returns a list of strings representing detailed share information,
    showing each individual share purchase with dates and prices.
    
    Args:
        portfolio: Portfolio object
        stock_prices: Optional list of stock price dicts to use for synchronized display.
                     If provided, uses this snapshot instead of fetching fresh prices.
    """
    lines = []
    if not portfolio.stocks:
        lines.append("No stocks in portfolio.")
        return lines

    # Build a lookup from ticker to current price and -1d if stock_prices provided
    price_lookup = {}
    day_ago_lookup = {}
    if stock_prices:
        for sp in stock_prices:
            ticker = sp.get("ticker")
            current = sp.get("current")
            day_ago = sp.get("-1d")
            if ticker and current is not None:
                price_lookup[ticker] = current
            if ticker and day_ago is not None:
                day_ago_lookup[ticker] = day_ago

    # Header for shares listing - added Profit/Loss and -1d columns
    header = "{:<16} {:>8} {:>10} {:>14} {:>14} {:>10} {}".format(
        "Ticker", "Shares", "Price", "Total", "Profit/Loss", "-1d", "Date"
    )
    lines.append(header)
    lines.append("-" * len(header))
    
    for name, stock in portfolio.stocks.items():
        if not hasattr(stock, 'holdings') or not stock.holdings:
            continue
        
        # Get current price and -1d price for profit/loss calculation
        current_price = 0.0
        day_ago_price = 0.0
        actual_ticker = stock.ticker  # Use actual ticker for lookups
        if actual_ticker in price_lookup:
            # Use synchronized price from stock_prices snapshot
            current_price = price_lookup[actual_ticker]
        else:
            # Fallback to fetching fresh price
            try:
                price_obj = stock.get_price_info()
                if price_obj and price_obj.get_current_sek() is not None:
                    current_price = float(price_obj.get_current_sek())
            except Exception as e:
                current_price = 0.0
        
        # Get -1d price
        if actual_ticker in day_ago_lookup:
            day_ago_price = day_ago_lookup[actual_ticker]
        else:
            # Try to fetch from price info
            try:
                price_obj = stock.get_price_info()
                if price_obj:
                    day_ago_price = price_obj.get_historical_close(1) or 0.0
            except Exception:
                day_ago_price = 0.0
            
        # Get actual profit/loss from sold shares
        profit_file = os.path.join(portfolio.path, f"{name}_profit.json")
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
            
            # Calculate -1d change for this share
            # If the share was purchased today, -1d should be 0
            from datetime import date as date_type, datetime
            is_today = False
            try:
                if hasattr(share.date, 'date'):
                    # datetime object
                    is_today = share.date.date() == date_type.today()
                elif hasattr(share.date, 'year'):
                    # date object
                    is_today = share.date == date_type.today()
                else:
                    # String format - try multiple date formats
                    share_date_str = str(share.date)
                    today_str = date_type.today()
                    
                    # Try MM/DD/YYYY format (used by portfolio)
                    try:
                        parsed_date = datetime.strptime(share_date_str, "%m/%d/%Y").date()
                        is_today = parsed_date == today_str
                    except:
                        # Try YYYY-MM-DD format
                        try:
                            parsed_date = datetime.strptime(share_date_str[:10], "%Y-%m-%d").date()
                            is_today = parsed_date == today_str
                        except:
                            pass
            except:
                pass
            
            if is_today:
                value_change_1d = 0.0
            elif day_ago_price > 0:
                day_ago_value = share.volume * day_ago_price
                value_change_1d = current_value - day_ago_value
            else:
                value_change_1d = 0.0
            
            lines.append(
                "{:<16} {:>8} {:>10.2f} {:>14.2f} {:>14.2f} {:>10.2f} {}".format(
                    actual_ticker,
                    share.volume,
                    share.price,
                    total_value,
                    unrealized_profit_loss,
                    value_change_1d,
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
            total_current_value = 0.0
            total_unrealized_profit_loss = 0.0
        
        # Calculate -1d change for total (exclude shares purchased today)
        from datetime import date as date_type, datetime
        if day_ago_price > 0 and current_price > 0:
            # Only count shares NOT purchased today
            shares_not_today = 0
            for s in stock.holdings:
                is_today = False
                try:
                    if hasattr(s.date, 'date'):
                        is_today = s.date.date() == date_type.today()
                    elif hasattr(s.date, 'year'):
                        is_today = s.date == date_type.today()
                    else:
                        # String format - try multiple date formats
                        share_date_str = str(s.date)
                        today_str = date_type.today()
                        
                        # Try MM/DD/YYYY format (used by portfolio)
                        try:
                            parsed_date = datetime.strptime(share_date_str, "%m/%d/%Y").date()
                            is_today = parsed_date == today_str
                        except:
                            # Try YYYY-MM-DD format
                            try:
                                parsed_date = datetime.strptime(share_date_str[:10], "%Y-%m-%d").date()
                                is_today = parsed_date == today_str
                            except:
                                pass
                except:
                    pass
                
                if not is_today:
                    shares_not_today += s.volume
            
            total_day_ago_value = shares_not_today * day_ago_price
            current_value_not_today = shares_not_today * current_price
            total_value_change_1d = current_value_not_today - total_day_ago_value
        else:
            total_value_change_1d = 0.0
        
        lines.append(
            "{:<16} {:>8} {:>10.2f} {:>14.2f} {:>14.2f} {:>10.2f} {}".format(
                f"[{actual_ticker}]",
                total_shares,
                avg_price,
                total_cost,
                total_unrealized_profit_loss,
                total_value_change_1d,
                "TOTAL"
            )
        )
        lines.append("")  # Empty line between stocks
    
    return lines

def get_portfolio_shares_summary(portfolio, stock_prices=None):
    """
    Returns a list of strings representing compressed share information,
    showing only one summary line per stock (no individual purchases).
    
    Args:
        portfolio: Portfolio object
        stock_prices: Optional list of stock price dicts to use for synchronized display.
    """
    lines = []
    if not portfolio.stocks:
        lines.append("No stocks in portfolio.")
        return lines

    # Build a lookup from ticker to current price and -1d if stock_prices provided
    price_lookup = {}
    day_ago_lookup = {}
    if stock_prices:
        for sp in stock_prices:
            ticker = sp.get("ticker")
            current = sp.get("current")
            day_ago = sp.get("-1d")
            if ticker and current is not None:
                price_lookup[ticker] = current
            if ticker and day_ago is not None:
                day_ago_lookup[ticker] = day_ago

    # Header for compressed summary
    header = "{:<16} {:>8} {:>10} {:>14} {:>14} {:>10}".format(
        "Ticker", "Shares", "Avg Price", "Total Cost", "Profit/Loss", "-1d"
    )
    lines.append(header)
    lines.append("-" * len(header))
    
    # Track totals across all stocks
    grand_total_cost = 0.0
    grand_total_profit_loss = 0.0
    grand_total_1d_change = 0.0
    
    for name, stock in portfolio.stocks.items():
        if not hasattr(stock, 'holdings') or not stock.holdings:
            continue
        
        # Get current price and -1d price
        current_price = 0.0
        day_ago_price = 0.0
        actual_ticker = stock.ticker  # Use actual ticker for lookups
        if actual_ticker in price_lookup:
            current_price = price_lookup[actual_ticker]
        else:
            try:
                price_obj = stock.get_price_info()
                if price_obj and price_obj.get_current_sek() is not None:
                    current_price = float(price_obj.get_current_sek())
            except Exception as e:
                current_price = 0.0
        
        if actual_ticker in day_ago_lookup:
            day_ago_price = day_ago_lookup[actual_ticker]
        else:
            try:
                price_obj = stock.get_price_info()
                if price_obj:
                    day_ago_price = price_obj.get_historical_close(1) or 0.0
            except Exception:
                day_ago_price = 0.0
        
        # Calculate totals for this stock
        total_shares = sum(s.volume for s in stock.holdings)
        total_cost = sum(s.volume * s.price for s in stock.holdings)
        avg_price = total_cost / total_shares if total_shares > 0 else 0
        
        # Calculate total unrealized profit/loss
        if current_price > 0:
            total_current_value = total_shares * current_price
            total_unrealized_profit_loss = total_current_value - total_cost
        else:
            total_current_value = 0.0
            total_unrealized_profit_loss = 0.0
        
        # Calculate -1d change for total (exclude shares purchased today)
        from datetime import date as date_type, datetime
        if day_ago_price > 0 and current_price > 0:
            # Only count shares NOT purchased today
            shares_not_today = 0
            for s in stock.holdings:
                is_today = False
                try:
                    if hasattr(s.date, 'date'):
                        is_today = s.date.date() == date_type.today()
                    elif hasattr(s.date, 'year'):
                        is_today = s.date == date_type.today()
                    else:
                        # String format - try multiple date formats
                        share_date_str = str(s.date)
                        today_str = date_type.today()
                        
                        # Try MM/DD/YYYY format (used by portfolio)
                        try:
                            parsed_date = datetime.strptime(share_date_str, "%m/%d/%Y").date()
                            is_today = parsed_date == today_str
                        except:
                            # Try YYYY-MM-DD format
                            try:
                                parsed_date = datetime.strptime(share_date_str[:10], "%Y-%m-%d").date()
                                is_today = parsed_date == today_str
                            except:
                                pass
                except:
                    pass
                
                if not is_today:
                    shares_not_today += s.volume
            
            total_day_ago_value = shares_not_today * day_ago_price
            current_value_not_today = shares_not_today * current_price
            total_value_change_1d = current_value_not_today - total_day_ago_value
        else:
            total_value_change_1d = 0.0
        
        lines.append(
            "{:<16} {:>8} {:>10.2f} {:>14.2f} {:>14.2f} {:>10.2f}".format(
                actual_ticker,
                total_shares,
                avg_price,
                total_cost,
                total_unrealized_profit_loss,
                total_value_change_1d
            )
        )
        
        # Accumulate grand totals
        grand_total_cost += total_cost
        grand_total_profit_loss += total_unrealized_profit_loss
        grand_total_1d_change += total_value_change_1d
    
    # Add separator and summary line
    lines.append("-" * len(header))
    lines.append(
        "{:<16} {:>8} {:>10} {:>14.2f} {:>14.2f} {:>10.2f}".format(
            "TOTAL",
            "",
            "",
            grand_total_cost,
            grand_total_profit_loss,
            grand_total_1d_change
        )
    )
    
    return lines

def calculate_portfolio_totals(portfolio):
    """
    Calculate total portfolio value, buy value, and -1d value similar to stockinventory stockprice command.
    Returns a dict with the calculated values.
    """
    from datetime import date as date_type, datetime
    
    total_portfolio_value = 0.0
    total_portfolio_buy_value = 0.0
    total_portfolio_value_1d = 0.0
    total_portfolio_value_current_old_shares = 0.0  # Current value of only old shares
    
    for name, stock in portfolio.stocks.items():
        total_shares = sum(share.volume for share in stock.holdings)
        if total_shares == 0:
            continue
            
        price_obj = stock.get_price_info()
        current_price = price_obj.get_current_sek() if price_obj else None
        
        # Add to total portfolio value (ALL shares at current price)
        if current_price is not None:
            total_portfolio_value += total_shares * current_price
            
            # Add to total buy value (sum of all share purchases) - ONLY for stocks with valid price
            # This prevents massive negative diffs when a stock's price is missing (value=0 but cost>0)
            total_portfolio_buy_value += sum(share.volume * share.price for share in stock.holdings)
        
        # For -1d calculation: compare old shares today vs old shares yesterday
        yest_close = price_obj.get_historical_close(1)
        if yest_close is not None and current_price is not None:
            # Only count shares NOT purchased today (shares that existed yesterday)
            shares_not_today = 0
            for s in stock.holdings:
                is_today = False
                try:
                    if hasattr(s.date, 'date'):
                        is_today = s.date.date() == date_type.today()
                    elif hasattr(s.date, 'year'):
                        is_today = s.date == date_type.today()
                    else:
                        # String format - try multiple date formats
                        share_date_str = str(s.date)
                        today_str = date_type.today()
                        
                        # Try MM/DD/YYYY format (used by portfolio)
                        try:
                            parsed_date = datetime.strptime(share_date_str, "%m/%d/%Y").date()
                            is_today = parsed_date == today_str
                        except:
                            # Try YYYY-MM-DD format
                            try:
                                parsed_date = datetime.strptime(share_date_str[:10], "%Y-%m-%d").date()
                                is_today = parsed_date == today_str
                            except:
                                pass
                except:
                    pass
                
                if not is_today:
                    shares_not_today += s.volume
            
            # Portfolio value yesterday = old shares * yesterday's close price
            total_portfolio_value_1d += shares_not_today * yest_close
            # Current value of old shares = old shares * current price
            total_portfolio_value_current_old_shares += shares_not_today * current_price
    
    diff = total_portfolio_value - total_portfolio_buy_value
    # -1d change = (old shares at current price) - (old shares at yesterday's price)
    diff_1d = total_portfolio_value_current_old_shares - total_portfolio_value_1d
    
    # Calculate percentage change from -1d
    pct_1d = 0.0
    if total_portfolio_value_1d != 0:
        pct_1d = ((total_portfolio_value_current_old_shares - total_portfolio_value_1d) / total_portfolio_value_1d) * 100
    
    return {
        'total_value': total_portfolio_value,
        'buy_value': total_portfolio_buy_value,
        'value_1d': total_portfolio_value_1d,
        'diff': diff,
        'diff_1d': diff_1d,
        'pct_1d': pct_1d
    }
