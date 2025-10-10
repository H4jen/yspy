import curses
from .display_utils import color_for_value


def safe_addstr(stdscr, row, col, text, attr=0):
    """Safely add a string to the curses window without raising ERR.

    Truncates text to fit in the remaining columns and silently ignores
    writes that would start outside the window (e.g. when the list of
    stocks exceeds the terminal height). This prevents intermittent
    _curses.error: addwstr() returned ERR exceptions when the terminal
    is resized smaller or there are more rows than screen lines.
    """
    if row < 0 or col < 0:
        return
    max_lines = curses.LINES if hasattr(curses, 'LINES') else 0
    max_cols = curses.COLS if hasattr(curses, 'COLS') else 0
    if row >= max_lines or col >= max_cols:
        return
    remaining = max_cols - col - 1
    if remaining <= 0:
        return
    try:
        stdscr.addstr(row, col, text[:remaining], attr)
    except curses.error:
        # Silently ignore if curses still complains (e.g. race with resize)
        pass

def format_stock_price_lines(stock_prices, short_data=None, short_trend=None):
    """
    Formats the output of Portfolio.get_stock_prices() for ncurses display.
    Now includes: -1d, %1d, -2d, %2d, -3d, %3d, -1w, %1w, -2w, %2w, -1m, %1m, -3m, %3m, -6m, %6m, -1y, %1y.
    
    Args:
        stock_prices: List of stock price dictionaries
        short_data: Optional dict mapping stock names to short position percentages
        short_trend: Optional dict mapping stock names to trend info (with 'arrow' and 'trend' keys)
    """
    lines = []
    # Name: 16, Short%: 8, Δ Short: 7, spacing: 2, Current+dots: 11 (7+6 for value with * + dots), High: 10, Low: 10, then the rest
    header = (
        "{:<16}{:>8}{:>9}  {:>6}{:>17}{:>10}"
        "{:>10}{:>8}{:>10}{:>8}{:>10}{:>8}"
        "{:>10}{:>8}{:>10}{:>8}{:>10}{:>8}{:>10}{:>8}{:>10}{:>8}{:>10}{:>8}".format(
            "Name", "Short%", "Δ Short", "Current", "High", "Low",
            "-1d", "%1d", "-2d", "%2d", "-3d", "%3d",
            "-1w", "%1w", "-2w", "%2w", "-1m", "%1m", "-3m", "%3m", "-6m", "%6m", "-1y", "%1y"
        )
    )
    lines.append(header)
    lines.append("-" * len(header))
    for stock in stock_prices:
        lines.append(stock)  # We'll handle coloring in the display, not here
    return lines

def display_colored_stock_prices(stdscr, stock_prices, prev_stock_prices=None, dot_states=None, portfolio=None, skip_header=False, base_row=2, short_data=None, short_trend=None, update_dots=True):
    """
    Displays the stock prices with colored changes.
    The -1d, -2d, -3d, -1w, -2w, -1m, -3m, -6m, -1y column values are colored green if smaller than current, red if bigger.
    dot_states: dict to maintain persistent dot indicators (now tracks last 6 changes)
    portfolio: Portfolio object to check share counts for grouping
    short_data: Optional dict mapping stock names to short position percentages
    short_trend: Optional dict mapping stock names to trend info (with 'arrow' and 'trend' keys)
    update_dots: Whether to update dot indicators for price changes (default: True)
    """
    lines = format_stock_price_lines(stock_prices, short_data, short_trend)
    # Print header and separator unless caller already handled
    if not skip_header:
        for idx, line in enumerate(lines[:2]):
            safe_addstr(stdscr, idx, 0, line)

    # Build a lookup for previous values by stock name
    prev_lookup = {}
    if prev_stock_prices:
        for stock in prev_stock_prices:
            prev_lookup[stock.get("name", "")] = stock

    # Initialize dot_states if not provided
    if dot_states is None:
        dot_states = {}

    # Separate stocks with shares and without shares
    stocks_with_shares = []
    stocks_without_shares = []
    
    if portfolio:
        for stock in stock_prices:
            name = stock.get("name", "")
            # Find the stock in portfolio by ticker (name in stock_prices corresponds to ticker)
            stock_obj = portfolio.stocks.get(name)
            
            if stock_obj:
                total_shares = sum(share.volume for share in stock_obj.holdings)
                if total_shares > 0:
                    stocks_with_shares.append(stock)
                else:
                    stocks_without_shares.append(stock)
            else:
                stocks_without_shares.append(stock)
    else:
        stocks_with_shares = stock_prices

    # Display stocks with shares first
    current_row = base_row
    for stock in stocks_with_shares:
        current_row = display_single_stock_price(stdscr, stock, current_row, prev_lookup, dot_states, update_dots=update_dots, short_data=short_data, short_trend=short_trend)
    
    # Add empty line if we have both groups
    if stocks_with_shares and stocks_without_shares:
        current_row += 1
    
    # Display stocks without shares
    for stock in stocks_without_shares:
        current_row = display_single_stock_price(stdscr, stock, current_row, prev_lookup, dot_states, update_dots=update_dots, short_data=short_data, short_trend=short_trend)

def display_single_stock_price(stdscr, stock, row, prev_lookup, dot_states, update_dots=True, short_data=None, short_trend=None):
    """
    Display a single stock's price information at the specified row.
    Returns the next available row number.
    
    Args:
        short_trend: Optional dict mapping stock names to trend info (with 'arrow' and 'trend' keys)
    """
    name = str(stock.get("name", ""))
    currency = stock.get("currency", "SEK")
    
    # Use native currency values if available, otherwise fall back to SEK
    current_native = stock.get("current_native")
    high_native = stock.get("high_native")
    low_native = stock.get("low_native")
    
    # Display native values for all stocks
    current = current_native if current_native is not None else stock.get("current", 0.0)
    high = high_native if high_native is not None else stock.get("high", 0.0)
    low = low_native if low_native is not None else stock.get("low", 0.0)
    
    # Mark foreign currency with (*)
    is_foreign = currency != "SEK"
    
    # Add currency code to name for foreign stocks
    if is_foreign:
        name_display = f"{name} ({currency})"[:16]  # Truncate to fit column width
    else:
        name_display = name

    prev_stock = prev_lookup.get(name, {})
    # Use native currency for comparison to avoid false changes due to currency conversion
    prev_current_native = prev_stock.get("current_native") if prev_stock.get("current_native") is not None else None
    prev_current = prev_stock.get("current") if prev_stock.get("current") is not None else None

    changes = [
        ("-1d", "%1d"),
        ("-2d", "%2d"),
        ("-3d", "%3d"),
        ("-1w", "%1w"),
        ("-2w", "%2w"),
        ("-1m", "%1m"),
        ("-3m", "%3m"),
        ("-6m", "%6m"),
        ("-1y", "%1y"),
    ]
    col = 0
    # Stop rendering if we've run out of vertical space
    if row >= curses.LINES - 1:
        return row  # Do not attempt further writes

    # Display stock name
    safe_addstr(stdscr, row, col, f"{name_display:<16}")
    col += 16
    
    # Display short percentage with trend arrow if available
    # Fixed column width: 8 chars for short data + 2 for spacing = 10 total
    short_col_start = col
    
    if short_data and name in short_data:
        short_pct = short_data[name]
        
        # Get trend arrow if available
        arrow = ''
        arrow_color = curses.color_pair(0)
        
        if short_trend and name in short_trend:
            trend_info = short_trend[name]
            arrow_char = trend_info.get('arrow', '')
            trend_type = trend_info.get('trend', 'no_data')
            
            if arrow_char:
                arrow = arrow_char
                
                # Color based on trend direction
                if trend_type in ('up', 'strong_up'):
                    arrow_color = curses.color_pair(2)  # Red - shorts increasing (bearish)
                elif trend_type in ('down', 'strong_down'):
                    arrow_color = curses.color_pair(1)  # Green - shorts decreasing (bullish)
                elif trend_type == 'stable':
                    arrow_color = curses.color_pair(3)  # Yellow - stable
                else:  # no_data
                    arrow_color = curses.color_pair(0)  # Default/gray
        
        # Color code short % based on risk level
        if short_pct > 10:
            short_color = curses.color_pair(2)  # Red - very high risk
        elif short_pct > 5:
            short_color = curses.color_pair(3)  # Yellow - high risk
        elif short_pct > 2:
            short_color = curses.color_pair(3)  # Yellow - moderate risk
        else:
            short_color = curses.color_pair(1)  # Green - low risk
        
        # Format: arrow (1 char) + percentage (6 chars with %) = 7 chars, right-aligned in 8 char field
        if arrow:
            # Arrow + space + percentage: "↑ 15.2%"
            short_str = f"{arrow}{short_pct:>6.2f}%"
            safe_addstr(stdscr, row, short_col_start, arrow, arrow_color)
            safe_addstr(stdscr, row, short_col_start + 1, short_str[1:], short_color)
        else:
            # Just percentage, right-aligned: "  15.2%"
            safe_addstr(stdscr, row, short_col_start, f"{short_pct:>7.2f}%", short_color)
    else:
        # No short data available
        safe_addstr(stdscr, row, short_col_start, f"{'N/A':>8}")
    
    col = short_col_start + 8  # Move to start of delta column
    
    # Display delta short change (7 chars wide) - absolute difference in percentage points
    delta_col_start = col
    
    if short_trend and name in short_trend:
        trend_info = short_trend[name]
        delta_change = trend_info.get('change', 0.0)  # This is already the absolute difference
        trend_type = trend_info.get('trend', 'no_data')
        
        # Only display if we have valid data
        if trend_type != 'no_data' and delta_change is not None:
            # Color based on direction (red for increasing, green for decreasing)
            if delta_change > 0:
                delta_color = curses.color_pair(2)  # Red - shorts increasing (bearish)
            elif delta_change < 0:
                delta_color = curses.color_pair(1)  # Green - shorts decreasing (bullish)
            else:
                delta_color = curses.color_pair(3)  # Yellow - no change
            
            # Format with + or - sign showing absolute difference: "+0.50" or "-0.30"
            delta_str = f"{delta_change:+6.2f}"
            safe_addstr(stdscr, row, delta_col_start, f"{delta_str:>7}", delta_color)
        else:
            # No trend data available
            safe_addstr(stdscr, row, delta_col_start, f"{'N/A':>7}")
    else:
        # No trend data available
        safe_addstr(stdscr, row, delta_col_start, f"{'N/A':>7}")
    
    col = delta_col_start + 9  # 7 for delta + 2 for spacing
    
    # Check if we have space for current price
    if col + 13 >= curses.COLS:
        return row + 1
    
    # Compare native currency values if available to avoid false changes due to currency conversion
    prev_compare = prev_current_native if prev_current_native is not None else prev_current
    current_compare = current_native if current_native is not None else current
    
    # Display current price with (*) marker for foreign currencies and six-dot history
    # Using 8-char width - all numbers align at decimal, asterisk added after if foreign
    current_str = f"{current:>8.2f}"  # All prices right-aligned to 8 chars
    if is_foreign:
        current_str += "*"  # Add asterisk after, doesn't affect number alignment
    
    # Check if current price changed - we'll show delta instead of highlighting
    current_changed = (prev_compare is not None and current_compare != prev_compare)
    
    # Initialize dot history for this stock if not exists
    if name not in dot_states:
        dot_states[name] = [(" ", curses.A_NORMAL)] * 6  # 6 dots: [newest, ..., oldest]
    
    if update_dots and prev_compare is not None and current_compare != prev_compare:
        # Shift dots right (oldest falls off)
        dot_states[name] = dot_states[name][:-1]
        
        # Add new dot at the beginning
        if current_compare > prev_compare:
            new_dot = ("●", curses.color_pair(1))  # Green dot for increase
        elif current_compare < prev_compare:
            new_dot = ("●", curses.color_pair(2))  # Red dot for decrease
        else:
            new_dot = (" ", curses.A_NORMAL)  # No change (shouldn't happen but handle it)
        
        dot_states[name] = [new_dot] + dot_states[name]
    
    # Display current price OR delta if price just changed (delta shown for one refresh cycle - 2 seconds)
    if current_changed:
        delta = current_compare - prev_compare
        delta_str = f"{delta:+8.2f}"  # Format with sign: +1.23 or -0.45, 8-char width to match price
        if is_foreign:
            delta_str += "*"  # Add asterisk to maintain alignment
        # Bold cyan for positive, bold magenta for negative
        delta_color = curses.color_pair(4) if delta > 0 else curses.color_pair(5)
        delta_attr = delta_color | curses.A_BOLD
        safe_addstr(stdscr, row, col, delta_str, delta_attr)
    else:
        safe_addstr(stdscr, row, col, current_str, curses.A_NORMAL)
    col += 9  # 8 for number + 1 for potential asterisk
    
    # Add a space between price/delta and dots
    if col < curses.COLS:
        safe_addstr(stdscr, row, col, " ")
    col += 1
    
    # Display six dots (newest to oldest, left to right)
    if col + 6 <= curses.COLS:
        for i, (dot_char, dot_attr) in enumerate(dot_states[name]):
            if col + i < curses.COLS:
                safe_addstr(stdscr, row, col + i, dot_char, dot_attr)
    col += 6
    
    # Check if we have space for high price
    if col + 10 >= curses.COLS:
        return row + 1
    high_str = f"{high:>10.2f}"  # All prices right-aligned to 10 chars
    if is_foreign:
        high_str += "*"  # Add asterisk after, doesn't affect number alignment
    
    # Check if high changed - show delta instead of value for 2 seconds
    prev_high_native = prev_stock.get("high_native") if prev_stock.get("high_native") is not None else None
    prev_high = prev_stock.get("high") if prev_stock.get("high") is not None else None
    prev_high_compare = prev_high_native if prev_high_native is not None else prev_high
    high_compare = high_native if high_native is not None else high
    high_changed = (prev_high_compare is not None and high_compare != prev_high_compare)
    
    # Display high price OR delta if high just changed
    if high_changed:
        delta = high_compare - prev_high_compare
        delta_str = f"{delta:+10.2f}"  # Format with sign, 10-char width to match high price
        if is_foreign:
            delta_str += "*"
        # Bold cyan for positive, bold magenta for negative
        delta_color = curses.color_pair(4) if delta > 0 else curses.color_pair(5)
        delta_attr = delta_color | curses.A_BOLD
        safe_addstr(stdscr, row, col, delta_str, delta_attr)
    else:
        safe_addstr(stdscr, row, col, high_str, curses.A_NORMAL)
    col += 11  # 10 for number + 1 for potential asterisk
    
    # Check if we have space for low price
    if col + 10 >= curses.COLS:
        return row + 1
    low_str = f"{low:>10.2f}"  # All prices right-aligned to 10 chars
    if is_foreign:
        low_str += "*"  # Add asterisk after, doesn't affect number alignment
    
    # Check if low changed - show delta instead of value for 2 seconds
    prev_low_native = prev_stock.get("low_native") if prev_stock.get("low_native") is not None else None
    prev_low = prev_stock.get("low") if prev_stock.get("low") is not None else None
    prev_low_compare = prev_low_native if prev_low_native is not None else prev_low
    low_compare = low_native if low_native is not None else low
    low_changed = (prev_low_compare is not None and low_compare != prev_low_compare)
    
    # Display low price OR delta if low just changed
    if low_changed:
        delta = low_compare - prev_low_compare
        delta_str = f"{delta:+10.2f}"  # Format with sign, 10-char width to match low price
        if is_foreign:
            delta_str += "*"
        # Bold cyan for positive, bold magenta for negative
        delta_color = curses.color_pair(4) if delta > 0 else curses.color_pair(5)
        delta_attr = delta_color | curses.A_BOLD
        safe_addstr(stdscr, row, col, delta_str, delta_attr)
    else:
        safe_addstr(stdscr, row, col, low_str, curses.A_NORMAL)
    col += 11  # 10 for number + 1 for potential asterisk


    for idx, (abs_key, pct_key) in enumerate(changes):
        # Use native currency values for historical data if available
        native_key = f"{abs_key}_native"
        native_val = stock.get(native_key)
        abs_key_val = stock.get(abs_key)
        abs_val = native_val if native_val is not None else (abs_key_val if abs_key_val is not None else 0.0)
        pct_val = stock.get(pct_key)

        # Check if we have enough space for the absolute value column
        if col + 10 >= curses.COLS:
            break

        # Display with (*) marker if foreign currency
        # All numbers align at decimal, asterisk added after
        abs_str = f"{abs_val:>10.2f}"
        if is_foreign and abs_val != 0.0:
            abs_str += "*"  # Add asterisk after, doesn't affect number alignment
        safe_addstr(stdscr, row, col, abs_str)
        col += 11  # 10 for number + 1 for potential asterisk

        # Check if we have enough space for the percentage column
        if col + 8 >= curses.COLS:
            break

        # Percent value coloring - handle None values
        if pct_val is not None:
            pct_str = f"{pct_val:.2f}%"
            pct_attr = color_for_value(pct_val)
        else:
            pct_str = "N/A"
            pct_attr = curses.A_NORMAL
        safe_addstr(stdscr, row, col, f"{pct_str:>8}", pct_attr)
        col += 8
    
    return row + 1

def display_portfolio_totals(stdscr, portfolio, row_start):
    """
    Display portfolio totals at the bottom of the watch screen with color coding.
    """
    from .display_utils import calculate_portfolio_totals
    totals = calculate_portfolio_totals(portfolio)
    
    # Create formatted strings
    total_value_str = f"{totals['total_value']:>10.2f}"
    diff_str = f"{totals['diff']:>8.2f}"
    diff_1d_str = f"{totals['diff_1d']:>6.2f}"
    pct_1d_str = f"{totals['pct_1d']:>6.2f}%"
    
    # Determine colors for total value (compared to buy value)
    if totals['total_value'] >= totals['buy_value']:
        value_attr = curses.color_pair(1)  # Green
    else:
        value_attr = curses.color_pair(2)  # Red
    
    # Determine colors for difference
    if totals['diff'] > 0:
        diff_attr = curses.color_pair(1)  # Green
    elif totals['diff'] < 0:
        diff_attr = curses.color_pair(2)  # Red
    else:
        diff_attr = curses.A_NORMAL
    
    # Determine colors for -1d change
    if totals['diff_1d'] > 0:
        diff_1d_attr = curses.color_pair(1)  # Green
    elif totals['diff_1d'] < 0:
        diff_1d_attr = curses.color_pair(2)  # Red
    else:
        diff_1d_attr = curses.A_NORMAL
    
    # Determine colors for %1d change
    if totals['pct_1d'] > 0:
        pct_1d_attr = curses.color_pair(1)  # Green
    elif totals['pct_1d'] < 0:
        pct_1d_attr = curses.color_pair(2)  # Red
    else:
        pct_1d_attr = curses.A_NORMAL
    
    # Display the totals line with bounds checking
    if row_start < 0 or row_start >= curses.LINES - 1:
        return  # Don't attempt to write if row outside screen
    col = 0
    safe_addstr(stdscr, row_start, col, "Total stock value:")
    col += 18
    if col + 10 < curses.COLS:
        safe_addstr(stdscr, row_start, col, total_value_str, value_attr)
        col += 12
    if col + 5 < curses.COLS:
        safe_addstr(stdscr, row_start, col, "Diff:")
        col += 5
    if col + 8 < curses.COLS:
        safe_addstr(stdscr, row_start, col, diff_str, diff_attr)
        col += 10
    if col + 7 < curses.COLS:
        safe_addstr(stdscr, row_start, col, "vs -1d:")
        col += 7
    if col + 6 < curses.COLS:
        safe_addstr(stdscr, row_start, col, diff_1d_str, diff_1d_attr)
        col += 8
    if col + 8 < curses.COLS:
        safe_addstr(stdscr, row_start, col, pct_1d_str, pct_1d_attr)
    
    # Display cash available on the next line
    cash_row = row_start + 1
    if cash_row < curses.LINES - 1:
        # Get cash from capital tracker if available
        cash_amount = 0.0
        if hasattr(portfolio, 'capital_tracker') and portfolio.capital_tracker:
            cash_amount = portfolio.capital_tracker.cash_balance
        
        cash_str = f"{cash_amount:>10.2f}"
        col = 0
        safe_addstr(stdscr, cash_row, col, "Cash available:")
        col += 18
        if col + 10 < curses.COLS:
            safe_addstr(stdscr, cash_row, col, cash_str, curses.color_pair(3))  # Yellow/cyan color

