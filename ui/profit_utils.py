import os
import json

def get_portfolio_allprofits_lines(portfolio):
    """
    Returns a list of strings representing all profits information,
    similar to the stockinventory allprofits command.
    """
    lines = []
    
    if not portfolio.stocks:
        lines.append("No stocks in portfolio.")
        return lines

    # Header for all profits display
    header = "{:<12} {:>12} {:>12} {:>12} {:>12}".format(
        "Ticker", "Year(R)", "Realized", "Unrealized", "Total"
    )
    lines.append(header)
    lines.append("-" * len(header))
    
    total_realized = 0.0
    total_unrealized = 0.0
    total_year_realized = 0.0
    
    import datetime
    current_year = datetime.datetime.now().year
    
    for ticker, stock in portfolio.stocks.items():
        # Get realized profit from sold shares
        profit_file = os.path.join(portfolio.path, f"{ticker}_profit.json")
        realized_profit = 0.0
        year_realized_profit = 0.0
        
        if os.path.exists(profit_file):
            try:
                with open(profit_file, "r") as f:
                    profit_records = json.load(f)
                    for record in profit_records:
                        profit = record.get("profit", 0.0)
                        realized_profit += profit
                        
                        # Check date for current year
                        date_str = None
                        for date_field in ["sell_date", "sellDate", "date", "timestamp"]:
                            if date_field in record:
                                date_str = str(record[date_field])
                                break
                        
                        if date_str:
                            try:
                                # Try MM/DD/YYYY
                                if "/" in date_str:
                                    parts = date_str.split("/")
                                    if len(parts) == 3:
                                        # Assuming MM/DD/YYYY
                                        if int(parts[2]) == current_year:
                                            year_realized_profit += profit
                                # Try YYYY-MM-DD
                                elif "-" in date_str:
                                    parts = date_str.split("-")
                                    if len(parts) == 3:
                                        if int(parts[0]) == current_year:
                                            year_realized_profit += profit
                            except:
                                pass
            except Exception:
                pass
        
        # Calculate unrealized profit from current holdings
        current_shares = sum(share.volume for share in stock.holdings)
        unrealized_profit = 0.0
        invested_amount = 0.0
        
        if current_shares > 0:
            # Calculate total invested in current shares
            invested_amount = sum(share.volume * share.price for share in stock.holdings)
            
            # Get current market value
            try:
                price_obj = stock.get_price_info()
                if price_obj and price_obj.get_current_sek() is not None:
                    current_value = current_shares * float(price_obj.get_current_sek())
                    unrealized_profit = current_value - invested_amount
            except Exception:
                pass
        
        # Calculate total profit (simplified - no percentage)
        total_profit = realized_profit + unrealized_profit
        
        # Skip rows where both realized and unrealized are zero
        if realized_profit != 0.0 or unrealized_profit != 0.0:
            lines.append(
                "{:<12} {:>12.2f} {:>12.2f} {:>12.2f} {:>12.2f}".format(
                    ticker,
                    year_realized_profit,
                    realized_profit,
                    unrealized_profit,
                    total_profit
                )
            )
        
        total_realized += realized_profit
        total_unrealized += unrealized_profit
        total_year_realized += year_realized_profit
    
    # Add summary line
    lines.append("-" * len(header))
    total_profit_sum = total_realized + total_unrealized
    
    lines.append(
        "{:<12} {:>12.2f} {:>12.2f} {:>12.2f} {:>12.2f}".format(
            "TOTAL",
            total_year_realized,
            total_realized,
            total_unrealized,
            total_profit_sum
        )
    )
    
    return lines

def get_portfolio_profit_lines(portfolio, selected_ticker=None):
    """
    Returns a list of strings representing profit information per stock with sell records,
    similar to the stockinventory profit command.
    If selected_ticker is provided, only show records for that stock.
    """
    lines = []
    
    if not portfolio.stocks:
        lines.append("No stocks in portfolio.")
        return lines

    # Header for profit per stock display with sell records
    header = "{:<12} {:>8} {:>12} {:>12} {:>12} {:>12} {}".format(
        "Ticker", "Shares", "Buy Price", "Sell Price", "Profit/Loss", "% Change", "Date"
    )
    lines.append(header)
    lines.append("-" * len(header))
    
    total_profit = 0.0
    has_records = False
    
    # Determine which stocks to process
    stocks_to_process = {}
    if selected_ticker and selected_ticker in portfolio.stocks:
        stocks_to_process[selected_ticker] = portfolio.stocks[selected_ticker]
    else:
        stocks_to_process = portfolio.stocks
    
    for ticker, stock in stocks_to_process.items():
        # Check for sell records (profit records)
        profit_file = os.path.join(portfolio.path, f"{ticker}_profit.json")
        if os.path.exists(profit_file):
            try:
                with open(profit_file, "r") as f:
                    profit_records = json.load(f)
                    
                if profit_records:
                    has_records = True
                    # Sort records by date if possible
                    try:
                        sorted_records = sorted(profit_records, key=lambda x: x.get("date", ""))
                    except:
                        sorted_records = profit_records
                    
                    for record in sorted_records:
                        # Extract data - check what keys are actually available
                        shares = record.get("shares", record.get("volume", 0))
                        buy_price = record.get("buy_price", record.get("buyPrice", 0.0))
                        sell_price = record.get("sell_price", record.get("sellPrice", 0.0))
                        profit_loss = record.get("profit", 0.0)
                        
                        # Handle different date field names and formats
                        date_str = "Unknown"
                        for date_field in ["date", "sellDate", "sell_date", "timestamp"]:
                            if date_field in record:
                                date_value = record[date_field]
                                try:
                                    # Handle different date formats
                                    if hasattr(date_value, 'strftime'):
                                        date_str = date_value.strftime("%Y-%m-%d")
                                    elif hasattr(date_value, 'isoformat'):
                                        date_str = date_value.isoformat()[:10]
                                    elif isinstance(date_value, str):
                                        # Try to parse string date
                                        if len(date_value) >= 10:
                                            date_str = date_value[:10]  # Take first 10 chars (YYYY-MM-DD)
                                        else:
                                            date_str = date_value
                                    else:
                                        date_str = str(date_value)
                                    break
                                except:
                                    continue
                        
                        # Calculate percentage change
                        pct_change = 0.0
                        if buy_price > 0:
                            pct_change = ((sell_price - buy_price) / buy_price) * 100
                        
                        lines.append(
                            "{:<12} {:>8} {:>12.2f} {:>12.2f} {:>12.2f} {:>11.2f}% {}".format(
                                ticker,
                                shares,
                                buy_price,
                                sell_price,
                                profit_loss,
                                pct_change,
                                date_str
                            )
                        )
                        
                        total_profit += profit_loss
                        
            except Exception as e:
                lines.append(f"{ticker:<12} Error reading profit records: {str(e)}")
                # Add debug info about the file content
                try:
                    with open(profit_file, "r") as f:
                        content = f.read()
                        lines.append(f"Debug: File content sample: {content[:100]}...")
                except:
                    lines.append(f"Debug: Could not read file {profit_file}")
    
    if not has_records:
        if selected_ticker:
            lines.append(f"No sell records found for {selected_ticker}.")
        else:
            lines.append("No sell records found.")
    else:
        # Add summary line
        lines.append("-" * len(header))
        lines.append(
            "{:<12} {:>8} {:>12} {:>12} {:>12.2f} {:>12} {}".format(
                "TOTAL", "", "", "", total_profit, "", ""
            )
        )
    
    return lines
