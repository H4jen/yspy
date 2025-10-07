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

def format_stock_price_lines(stock_prices):
    """
    Formats the output of Portfolio.get_stock_prices() for ncurses display.
    Now includes: -1d, %1d, -2d, %2d, -3d, %3d, -1w, %1w, -2w, %2w, -1m, %1m, -3m, %3m, -6m, %6m, -1y, %1y.
    """
    lines = []
    # Name: 16, spacing: 2, Current+dots: 11 (7+6 for value with * + dots), High: 10, Low: 10, then the rest
    header = (
        "{:<16}  {:>6}{:>17}{:>10}"
        "{:>10}{:>8}{:>10}{:>8}{:>10}{:>8}"
        "{:>10}{:>8}{:>10}{:>8}{:>10}{:>8}{:>10}{:>8}{:>10}{:>8}{:>10}{:>8}".format(
            "Name", "Current", "High", "Low",
            "-1d", "%1d", "-2d", "%2d", "-3d", "%3d",
            "-1w", "%1w", "-2w", "%2w", "-1m", "%1m", "-3m", "%3m", "-6m", "%6m", "-1y", "%1y"
        )
    )
    lines.append(header)
    lines.append("-" * len(header))
    for stock in stock_prices:
        lines.append(stock)  # We'll handle coloring in the display, not here
    return lines

def display_colored_stock_prices(stdscr, stock_prices, prev_stock_prices=None, dot_states=None, portfolio=None, skip_header=False, base_row=2):
    """
    Displays the stock prices with colored changes.
    The -1d, -2d, -3d, -1w, -2w, -1m, -3m, -6m, -1y column values are colored green if smaller than current, red if bigger.
    dot_states: dict to maintain persistent dot indicators (now tracks last 6 changes)
    portfolio: Portfolio object to check share counts for grouping
    """
    lines = format_stock_price_lines(stock_prices)
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
        current_row = display_single_stock_price(stdscr, stock, current_row, prev_lookup, dot_states, update_dots=True)
    
    # Add empty line if we have both groups
    if stocks_with_shares and stocks_without_shares:
        current_row += 1
    
    # Display stocks without shares
    for stock in stocks_without_shares:
        current_row = display_single_stock_price(stdscr, stock, current_row, prev_lookup, dot_states, update_dots=True)

def display_single_stock_price(stdscr, stock, row, prev_lookup, dot_states, update_dots=True):
    """
    Display a single stock's price information at the specified row.
    Returns the next available row number.
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

    safe_addstr(stdscr, row, col, f"{name_display:<16}")
    col += 18  # 16 for name + 2 for spacing
    
    # Check if we have space for current price
    if col + 13 >= curses.COLS:
        return row + 1
    
    # Display current price with (*) marker for foreign currencies and six-dot history
    if is_foreign:
        current_str = f"{current:>6.2f}*"  # 7 chars: 6 digits + asterisk
    else:
        current_str = f"{current:>7.2f}"   # 7 chars: no asterisk for SEK
    
    # Initialize dot history for this stock if not exists
    if name not in dot_states:
        dot_states[name] = [(" ", curses.A_NORMAL)] * 6  # 6 dots: [newest, ..., oldest]
    
    # Update dot history only when price changes
    # Compare native currency values if available to avoid false changes due to currency conversion
    prev_compare = prev_current_native if prev_current_native is not None else prev_current
    current_compare = current_native if current_native is not None else current
    
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
    
    # Display current price
    safe_addstr(stdscr, row, col, current_str)
    col += 7
    
    # Add a space between price and dots
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
    high_str = f"{high:>9.2f}*" if is_foreign else f"{high:>10.2f}"
    safe_addstr(stdscr, row, col, high_str)
    col += 10
    
    # Check if we have space for low price
    if col + 10 >= curses.COLS:
        return row + 1
    low_str = f"{low:>9.2f}*" if is_foreign else f"{low:>10.2f}"
    safe_addstr(stdscr, row, col, low_str)
    col += 10

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
        if is_foreign and abs_val != 0.0:
            abs_str = f"{abs_val:>9.2f}*"
        else:
            abs_str = f"{abs_val:>10.2f}"
        safe_addstr(stdscr, row, col, abs_str)
        col += 10

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

