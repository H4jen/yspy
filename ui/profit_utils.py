import os
import json
from collections import defaultdict


def _profit_record_year(record):
    """Return the sale year from a profit record, or None when unavailable."""
    for date_field in ("sell_date", "sellDate", "date", "timestamp"):
        date_value = record.get(date_field)
        if not date_value:
            continue
        date_text = str(date_value)
        try:
            if "/" in date_text:
                return int(date_text.split("/")[-1][:4])
            return int(date_text[:4])
        except (TypeError, ValueError):
            continue
    return None


def _instrument_fees(portfolio, instrument_name, profit_records):
    """Return all fees for display and legacy-only fees for total P/L adjustment."""
    capital_tracker = getattr(portfolio, "capital_tracker", None)
    events = getattr(capital_tracker, "events", None)
    if events is not None:
        instrument_events = [
            event
            for event in events
            if (
                event.get("stock") == instrument_name
                or event.get("stock_name") == instrument_name
            )
        ]
        displayed_fees = -sum(
            float(event.get("fee", 0.0) or 0.0) + float(event.get("fx_fee", 0.0) or 0.0)
            for event in instrument_events
        )
        legacy_fee_adjustment = -sum(
            float(event.get("fee", 0.0) or 0.0) + float(event.get("fx_fee", 0.0) or 0.0)
            for event in instrument_events
            if not event.get("trade_id")
        )
        return displayed_fees, legacy_fee_adjustment

    recorded_fees = -sum(float(record.get("fee", 0.0) or 0.0) for record in profit_records)
    return recorded_fees, recorded_fees


def get_portfolio_allprofits_lines(portfolio):
    """
    Returns a list of strings representing all profits information,
    similar to the stockinventory allprofits command.
    """
    lines = []
    
    if not portfolio.stocks and not getattr(portfolio, "funds", {}):
        lines.append("No stocks in portfolio.")
        return lines

    # Header for all profits display
    header = "{:<12} {:>12} {:>12} {:>12} {:>12} {:>12} {:>12}".format(
        "Ticker", "Prev", "Year(R)", "Realized", "Fees", "Unrealized", "Total"
    )
    lines.append(header)
    lines.append("-" * len(header))
    
    total_realized = 0.0
    total_unrealized = 0.0
    total_displayed_fees = 0.0
    total_fee_adjustment = 0.0
    total_year_realized = 0.0
    total_previous_year_realized = 0.0
    realized_by_year = defaultdict(float)
    has_unavailable_market_price = False
    
    import datetime
    current_year = datetime.datetime.now().year
    previous_year = current_year - 1
    
    for ticker, stock in portfolio.stocks.items():
        # Get realized profit from sold shares
        profit_file = os.path.join(portfolio.path, f"{ticker}_profit.json")
        realized_profit = 0.0
        fees = 0.0
        fee_adjustment = 0.0
        year_realized_profit = 0.0
        previous_year_realized_profit = 0.0
        
        if os.path.exists(profit_file):
            try:
                with open(profit_file, "r") as f:
                    profit_records = json.load(f)
                    fees, fee_adjustment = _instrument_fees(portfolio, ticker, profit_records)
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

                        sale_year = _profit_record_year(record)
                        if sale_year is not None:
                            realized_by_year[sale_year] += profit
                            if sale_year == previous_year:
                                previous_year_realized_profit += profit
            except Exception:
                pass
        
        # Calculate unrealized profit from current holdings
        current_shares = sum(share.volume for share in stock.holdings)
        unrealized_profit = 0.0
        invested_amount = 0.0
        market_price_unavailable = False
        
        if current_shares > 0:
            # Calculate total invested in current shares
            invested_amount = sum(share.volume * share.price for share in stock.holdings)
            
            # Get current market value
            try:
                price_obj = stock.get_price_info()
                if price_obj and price_obj.get_current_sek() is not None:
                    current_value = current_shares * float(price_obj.get_current_sek())
                    unrealized_profit = current_value - invested_amount
                else:
                    market_price_unavailable = True
            except Exception:
                market_price_unavailable = True
        
        # Calculate total profit (simplified - no percentage)
        total_profit = realized_profit + unrealized_profit + fee_adjustment
        
        # Skip rows where both realized and unrealized are zero
        if realized_profit != 0.0 or unrealized_profit != 0.0 or fees != 0.0 or market_price_unavailable:
            unrealized_display = "N/A" if market_price_unavailable else f"{unrealized_profit:.2f}"
            total_display = "N/A" if market_price_unavailable else f"{total_profit:.2f}"
            lines.append(
                "{:<12} {:>12.2f} {:>12.2f} {:>12.2f} {:>12.2f} {:>12} {:>12}".format(
                    ticker[:12],
                    previous_year_realized_profit,
                    year_realized_profit,
                    realized_profit,
                    fees,
                    unrealized_display,
                    total_display,
                )
            )
        if market_price_unavailable:
            has_unavailable_market_price = True
            lines.append(f"{ticker[:12]} Current price unavailable; unrealized and total P/L are N/A.")
        
        total_realized += realized_profit
        total_unrealized += unrealized_profit
        total_displayed_fees += fees
        total_fee_adjustment += fee_adjustment
        total_year_realized += year_realized_profit
        total_previous_year_realized += previous_year_realized_profit
    
    # --- Managed funds ---
    funds = getattr(portfolio, "funds", {})
    for name, fund in funds.items():
        realized_profit = 0.0
        fees = 0.0
        fee_adjustment = 0.0
        year_realized_profit = 0.0
        previous_year_realized_profit = 0.0

        if os.path.exists(fund._profit_file):
            try:
                with open(fund._profit_file, "r") as f:
                    profit_records = json.load(f)
                    fees, fee_adjustment = _instrument_fees(portfolio, name, profit_records)
                    for record in profit_records:
                        profit = record.get("profit", 0.0)
                        realized_profit += profit
                        date_str = None
                        for date_field in ["sell_date", "date", "sellDate", "timestamp"]:
                            if date_field in record:
                                date_str = str(record[date_field])
                                break
                        if date_str:
                            try:
                                if "/" in date_str:
                                    parts = date_str.split("/")
                                    if len(parts) == 3 and int(parts[2]) == current_year:
                                        year_realized_profit += profit
                                elif "-" in date_str:
                                    parts = date_str.split("-")
                                    if len(parts) >= 1 and int(parts[0]) == current_year:
                                        year_realized_profit += profit
                            except Exception:
                                pass

                        sale_year = _profit_record_year(record)
                        if sale_year is not None:
                            realized_by_year[sale_year] += profit
                            if sale_year == previous_year:
                                previous_year_realized_profit += profit
            except Exception:
                pass

        # Unrealised P/L from current holdings
        total_units = fund.get_total_units()
        unrealized_profit = 0.0
        market_price_unavailable = False
        if total_units > 0:
            invested = sum(l.volume * l.price for l in fund.holdings)
            try:
                price_obj = fund.get_price_info()
                if price_obj and price_obj.get_current_sek() is not None:
                    current_value = total_units * float(price_obj.get_current_sek())
                    unrealized_profit = current_value - invested
                else:
                    market_price_unavailable = True
            except Exception:
                market_price_unavailable = True

        total_profit = realized_profit + unrealized_profit + fee_adjustment
        if realized_profit != 0.0 or unrealized_profit != 0.0 or fees != 0.0 or market_price_unavailable:
            unrealized_display = "N/A" if market_price_unavailable else f"{unrealized_profit:.2f}"
            total_display = "N/A" if market_price_unavailable else f"{total_profit:.2f}"
            lines.append(
                "{:<12} {:>12.2f} {:>12.2f} {:>12.2f} {:>12.2f} {:>12} {:>12}".format(
                    name[:12],
                    previous_year_realized_profit,
                    year_realized_profit,
                    realized_profit,
                    fees,
                    unrealized_display,
                    total_display,
                )
            )
        if market_price_unavailable:
            has_unavailable_market_price = True
            lines.append(f"{name[:12]} Current price unavailable; unrealized and total P/L are N/A.")

        total_realized       += realized_profit
        total_displayed_fees += fees
        total_fee_adjustment += fee_adjustment
        total_unrealized     += unrealized_profit
        total_year_realized  += year_realized_profit
        total_previous_year_realized += previous_year_realized_profit

    # Add summary line
    lines.append("-" * len(header))
    total_profit_sum = total_realized + total_unrealized + total_fee_adjustment
    total_profit_display = "N/A" if has_unavailable_market_price else f"{total_profit_sum:.2f}"

    lines.append(
        "{:<12} {:>12.2f} {:>12.2f} {:>12.2f} {:>12.2f} {:>12.2f} {:>12}".format(
            "TOTAL",
            total_previous_year_realized,
            total_year_realized,
            total_realized,
            total_displayed_fees,
            total_unrealized,
            total_profit_display,
        )
    )

    if realized_by_year:
        lines.append("")
        lines.append("REALIZED PROFIT BY YEAR (SEK)")
        yearly_header = "{:<12} {:>12}".format("Year", "Realized")
        lines.append(yearly_header)
        lines.append("-" * len(yearly_header))
        for year in sorted(realized_by_year):
            lines.append("{:<12} {:>12.2f}".format(year, realized_by_year[year]))

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
        "Ticker", "Shares", "Buy Price", "Sell Price", "Net P/L*", "Return*", "Date"
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
                        sorted_records = sorted(
                            profit_records,
                            key=lambda record: record.get("sell_date", record.get("date", "")),
                        )
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
                        cost_basis = buy_price * float(shares)
                        if cost_basis > 0:
                            pct_change = (float(profit_loss) / cost_basis) * 100
                        
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

                    _, fee_adjustment = _instrument_fees(portfolio, ticker, profit_records)
                    total_profit += fee_adjustment
                        
            except Exception as e:
                lines.append(f"{ticker:<12} Error reading profit records: {str(e)}")
                # Add debug info about the file content
                try:
                    with open(profit_file, "r") as f:
                        content = f.read()
                        lines.append(f"Debug: File content sample: {content[:100]}...")
                except:
                    lines.append(f"Debug: Could not read file {profit_file}")

    # --- Managed funds sell records ---
    funds = getattr(portfolio, "funds", {})
    if selected_ticker and selected_ticker not in portfolio.stocks:
        # Might be a fund name
        funds_to_process = {selected_ticker: funds[selected_ticker]} if selected_ticker in funds else {}
    elif not selected_ticker:
        funds_to_process = funds
    else:
        funds_to_process = {}

    for name, fund in funds_to_process.items():
        if not os.path.exists(fund._profit_file):
            continue
        try:
            with open(fund._profit_file, "r") as f:
                profit_records = json.load(f)
            if not profit_records:
                continue
            has_records = True
            try:
                sorted_records = sorted(profit_records, key=lambda x: x.get("sell_date", x.get("date", "")))
            except Exception:
                sorted_records = profit_records
            for record in sorted_records:
                shares     = float(record.get("volume", record.get("shares", 0)))
                buy_price  = record.get("buy_price",  record.get("buyPrice", 0.0))
                sell_price = record.get("sell_price", record.get("sellPrice", 0.0))
                profit_loss = record.get("profit", 0.0)
                date_str = "Unknown"
                for df in ["date", "sell_date", "sellDate", "timestamp"]:
                    if df in record:
                        v = record[df]
                        date_str = str(v)[:10] if isinstance(v, str) else str(v)
                        break
                cost_basis = buy_price * shares
                pct_change = (profit_loss / cost_basis * 100) if cost_basis > 0 else 0.0
                lines.append(
                    "{:<12} {:>8} {:>12.2f} {:>12.2f} {:>12.2f} {:>11.2f}% {}".format(
                        name[:12], f"{shares:.4f}", buy_price, sell_price,
                        profit_loss, pct_change, date_str,
                    )
                )
                total_profit += profit_loss
            _, fee_adjustment = _instrument_fees(portfolio, name, profit_records)
            total_profit += fee_adjustment
        except Exception as exc:
            lines.append(f"{name:<12} Error reading fund profit records: {exc}")

    if not has_records:
        if selected_ticker:
            lines.append(f"No sell records found for {selected_ticker}.")
        else:
            lines.append("No sell records found.")

        return lines

    # Add summary line
    lines.append("-" * len(header))
    lines.append(
        "{:<12} {:>8} {:>12} {:>12} {:>12.2f} {:>12} {}".format(
            "TOTAL", "", "", "", total_profit, "", ""
        )
    )
    lines.append("* New trades are net of their linked fees. Legacy rows exclude unlinked fees; TOTAL includes them.")

    return lines
