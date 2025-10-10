#!/usr/bin/env python3
"""
yspy - Menu Handler Classes

Each major menu operation is handled by a dedicated class providing
clean separation of concerns and maintainable code structure.

Project: https://github.com/H4jen/yspy
"""

import curses
import os
import json
import logging
from typing import List, Optional, Tuple
from src.app_config import config
from src.ui_handlers import BaseUIHandler, ScrollableUIHandler, RefreshableUIHandler
from ui.display_utils import color_for_value, get_portfolio_list_lines, get_portfolio_shares_lines
from ui.stock_display import display_colored_stock_prices, display_portfolio_totals, format_stock_price_lines, display_single_stock_price
from ui.profit_utils import get_portfolio_allprofits_lines, get_portfolio_profit_lines


class AddStockHandler(BaseUIHandler):
    """Handler for adding new stocks to the portfolio."""
    
    def handle(self) -> None:
        """Handle adding a new stock to the portfolio."""
        row = self.clear_and_display_header("Add New Stock")
        
        # Get stock ticker
        ticker = self.get_user_input("Enter stock ticker symbol: ", row)
        if not ticker:
            self.show_message("Invalid ticker symbol.", row + 2)
            return
        
        ticker = ticker.upper()
        
        # Check if stock already exists
        if ticker in self.portfolio.stocks:
            self.show_message(f"Stock {ticker} already exists in portfolio.", row + 2)
            return
        
        # Get stock name
        name = self.get_user_input(f"Enter stock name for {ticker}: ", row + 1)
        if not name:
            self.show_message("Invalid stock name.", row + 3)
            return
        
        # Add stock to portfolio
        success = self.portfolio.add_stock(name, ticker)
        if success:
            self.portfolio.save_portfolio()
            self.show_message(f"Successfully added {ticker} ({name}) to portfolio!", row + 3)
        else:
            self.show_message(f"Failed to add {ticker}. It may be invalid or already exist.", row + 3)


class RemoveStockHandler(BaseUIHandler):
    """Handler for removing stocks from the portfolio."""
    
    def handle(self) -> None:
        """Handle removing a stock from the portfolio."""
        row = self.clear_and_display_header("Remove Stock")
        
        # Get list of stocks to choose from
        if not self.portfolio.stocks:
            self.show_message("No stocks in portfolio.", row)
            return
        
        # Display available stocks
        self.safe_addstr(row, 0, "Available stocks:")
        stock_list = list(self.portfolio.stocks.keys())
        
        for i, ticker in enumerate(stock_list):
            stock = self.portfolio.stocks[ticker]
            total_shares = sum(share.volume for share in stock.holdings)
            self.safe_addstr(row + 1 + i, 0, f"{i+1}. {ticker} (Shares: {total_shares})")
        
        # Get stock selection
        choice = self.get_numeric_input(
            "Select stock number to remove (or 0 to cancel): ", 
            row + 1 + len(stock_list), 
            min_val=0, 
            max_val=len(stock_list), 
            integer_only=True
        )
        
        if not choice or choice == 0 or choice > len(stock_list):
            return
        
        selected_ticker = stock_list[int(choice) - 1]
        stock = self.portfolio.stocks[selected_ticker]
        total_shares = sum(share.volume for share in stock.holdings)
        
        # Warn if stock has shares
        message_row = row + 2 + len(stock_list)
        if total_shares > 0:
            self.safe_addstr(message_row, 0, f"WARNING: {selected_ticker} has {total_shares} shares!")
            self.safe_addstr(message_row + 1, 0, "Removing this stock will delete all share records.")
            confirm_message = f"Confirm removal of {selected_ticker}?"
        else:
            confirm_message = f"Confirm removal of {selected_ticker}?"
        
        if self.confirm_action(confirm_message, message_row + 2):
            success = self.portfolio.remove_stock(selected_ticker)
            if success:
                self.portfolio.save_portfolio()
                self.show_message(f"Successfully removed {selected_ticker} from portfolio!", message_row + 4)
            else:
                self.show_message(f"Failed to remove {selected_ticker} from portfolio!", message_row + 4)
        else:
            self.show_message("Removal cancelled.", message_row + 4)


class ListStocksHandler(BaseUIHandler):
    """Handler for listing all stocks in the portfolio."""
    
    def handle(self) -> None:
        """Handle listing all stocks."""
        lines = get_portfolio_list_lines(self.portfolio)
        self.display_scrollable_list("Stock List", lines)


class ListSharesHandler(RefreshableUIHandler, ScrollableUIHandler):
    """Handler for listing shares with auto-refresh and scrolling."""
    
    def handle(self) -> None:
        """Handle listing shares with auto-refresh."""
        self.stdscr.nodelay(True)
        self._watch_mode = True  # Enable auto-refresh mode
        
        try:
            while True:
                lines = get_portfolio_shares_lines(self.portfolio)
                max_lines = curses.LINES - config.MAX_DISPLAY_LINES_OFFSET
                
                # Display shares with auto-refresh
                for refresh_cycle in range(40):  # 4 seconds = 40 * 0.1s
                    self.stdscr.clear()
                    self.safe_addstr(0, 0, "Share Details (Use UP/DOWN arrows to scroll, ESC to exit, auto-refresh every 4s)")
                    self.safe_addstr(1, 0, "-" * 80)
                    
                    # Display lines with scrolling and color profit/loss
                    for idx, line in enumerate(lines[self.scroll_pos:self.scroll_pos + max_lines - 2]):
                        display_row = idx + 2
                        if display_row < curses.LINES - 1:
                            self._display_line_with_profit_color(display_row, line, idx)
                    
                    # Show scroll indicator
                    if len(lines) > max_lines - 2:
                        scroll_info = f"Showing {self.scroll_pos + 1}-{min(self.scroll_pos + max_lines - 2, len(lines))} of {len(lines)}"
                        self.safe_addstr(curses.LINES - 1, 0, scroll_info)
                    
                    self.stdscr.refresh()
                    
                    # Check for key input
                    key = self.stdscr.getch()
                    if key != -1:  # Key was pressed
                        if key == 27 or key == ord('q'):  # ESC or 'q' to exit
                            return
                        elif self.handle_scroll_keys(key, max_lines - 2, len(lines)):
                            break  # Break refresh cycle to immediately show scroll
                    
                    import time
                    time.sleep(0.1)
                
                # Refresh data after completing cycle
                continue
                
        finally:
            self.stdscr.nodelay(False)
    
    def _display_line_with_profit_color(self, display_row: int, line: str, line_idx: int):
        """Display a line with profit/loss coloring if applicable."""
        # Check if this is a data line that contains profit/loss value
        if line_idx >= 2 and not line.startswith('-') and line.strip() and len(line.split()) >= 5:
            try:
                # Parse the line to extract profit/loss value
                parts = line.split()
                profit_loss_str = parts[4]
                profit_loss_value = float(profit_loss_str)
                
                # Find position of profit/loss column
                profit_loss_start = line.find(profit_loss_str, line.find(parts[3]) + len(parts[3]))
                
                # Display line parts with color for profit/loss
                if profit_loss_start > 0:
                    # Display everything before profit/loss
                    before_part = line[:profit_loss_start]
                    self.safe_addstr(display_row, 0, before_part[:curses.COLS-1])
                    
                    # Display profit/loss with color
                    col_pos = len(before_part)
                    if col_pos < curses.COLS - len(profit_loss_str):
                        color_attr = color_for_value(profit_loss_value)
                        self.safe_addstr(display_row, col_pos, profit_loss_str, color_attr)
                        
                        # Display everything after profit/loss
                        after_part = line[profit_loss_start + len(profit_loss_str):]
                        col_pos += len(profit_loss_str)
                        if col_pos < curses.COLS - 1 and after_part:
                            self.safe_addstr(display_row, col_pos, after_part[:curses.COLS-col_pos-1])
                else:
                    self.safe_addstr(display_row, 0, line[:curses.COLS-1])
            except (ValueError, IndexError):
                self.safe_addstr(display_row, 0, line[:curses.COLS-1])
        else:
            self.safe_addstr(display_row, 0, line[:curses.COLS-1])


class BuySharesHandler(BaseUIHandler):
    """Handler for buying shares."""
    
    def handle(self) -> None:
        """Handle buying shares."""
        row = self.clear_and_display_header("Buy Shares")
        
        # Get list of stocks to choose from
        if not self.portfolio.stocks:
            self.show_message("No stocks in portfolio. Add a stock first.", row)
            return
        
        # Display available stocks
        self.safe_addstr(row, 0, "Available stocks:")
        stock_list = list(self.portfolio.stocks.keys())
        
        for i, ticker in enumerate(stock_list):
            stock = self.portfolio.stocks[ticker]
            total_shares = sum(share.volume for share in stock.holdings)
            self.safe_addstr(row + 1 + i, 0, f"{i+1}. {ticker} (Current shares: {total_shares})")
        
        # Get stock selection
        choice = self.get_numeric_input(
            "Select stock number (or 0 to cancel): ", 
            row + 1 + len(stock_list), 
            min_val=0, 
            max_val=len(stock_list), 
            integer_only=True
        )
        
        if not choice or choice == 0 or choice > len(stock_list):
            return
        
        selected_ticker = stock_list[int(choice) - 1]
        
        # Get number of shares
        shares = self.get_numeric_input(
            f"Enter number of shares to buy for {selected_ticker}: ", 
            row + 3 + len(stock_list), 
            min_val=1, 
            integer_only=True
        )
        
        if not shares:
            self.show_message("Invalid number of shares.", row + 5 + len(stock_list))
            return
        
        # Get price per share
        price = self.get_numeric_input(
            "Enter price per share: ", 
            row + 4 + len(stock_list), 
            min_val=0.01
        )
        
        if not price:
            self.show_message("Invalid price.", row + 6 + len(stock_list))
            return
        
        # Get broker fee
        fee = self.get_numeric_input(
            "Enter broker fee (or 0 for no fee): ", 
            row + 5 + len(stock_list), 
            min_val=0.0
        )
        
        if fee is None:
            fee = 0.0
        
        # Confirm purchase
        total_cost = shares * price + fee
        message_row = row + 7 + len(stock_list)
        self.safe_addstr(message_row, 0, f"Confirm purchase: {int(shares)} shares of {selected_ticker} at ${price:.2f} each")
        self.safe_addstr(message_row + 1, 0, f"Stock cost: ${shares * price:.2f}, Fee: ${fee:.2f}, Total: ${total_cost:.2f}")
        
        if self.confirm_action("Confirm purchase?", message_row + 2):
            success = self.portfolio.add_shares(selected_ticker, int(shares), price, fee)
            if success:
                self.portfolio.save_portfolio()
                self.show_message(f"Successfully bought {int(shares)} shares of {selected_ticker}!", message_row + 4)
            else:
                self.show_message(f"Failed to add shares to {selected_ticker}!", message_row + 4)
        else:
            self.show_message("Purchase cancelled.", message_row + 4)


class SellSharesHandler(BaseUIHandler):
    """Handler for selling shares."""
    
    def handle(self) -> None:
        """Handle selling shares."""
        row = self.clear_and_display_header("Sell Shares")
        
        # Get list of stocks with shares to choose from
        stocks_with_shares = []
        for ticker, stock in self.portfolio.stocks.items():
            total_shares = sum(share.volume for share in stock.holdings)
            if total_shares > 0:
                stocks_with_shares.append((ticker, total_shares))
        
        if not stocks_with_shares:
            self.show_message("No stocks with shares to sell.", row)
            return
        
        # Display available stocks with shares
        self.safe_addstr(row, 0, "Stocks available for sale:")
        for i, (ticker, total_shares) in enumerate(stocks_with_shares):
            self.safe_addstr(row + 1 + i, 0, f"{i+1}. {ticker} (Available shares: {total_shares})")
        
        # Get stock selection
        choice = self.get_numeric_input(
            "Select stock number (or 0 to cancel): ", 
            row + 1 + len(stocks_with_shares), 
            min_val=0, 
            max_val=len(stocks_with_shares), 
            integer_only=True
        )
        
        if not choice or choice == 0 or choice > len(stocks_with_shares):
            return
        
        selected_ticker, available_shares = stocks_with_shares[int(choice) - 1]
        
        # Get number of shares to sell
        shares_to_sell = self.get_numeric_input(
            f"Enter number of shares to sell for {selected_ticker} (max {available_shares}): ", 
            row + 3 + len(stocks_with_shares), 
            min_val=1, 
            max_val=available_shares, 
            integer_only=True
        )
        
        if not shares_to_sell:
            self.show_message(f"Invalid number of shares. Must be between 1 and {available_shares}.", 
                            row + 5 + len(stocks_with_shares))
            return
        
        # Get selling price per share
        sell_price = self.get_numeric_input(
            "Enter selling price per share: ", 
            row + 4 + len(stocks_with_shares), 
            min_val=0.01
        )
        
        if not sell_price:
            self.show_message("Invalid price.", row + 6 + len(stocks_with_shares))
            return
        
        # Get broker fee
        fee = self.get_numeric_input(
            "Enter broker fee (or 0 for no fee): ", 
            row + 5 + len(stocks_with_shares), 
            min_val=0.0
        )
        
        if fee is None:
            fee = 0.0
        
        # Calculate estimated profit
        stock = self.portfolio.stocks[selected_ticker]
        sorted_shares = sorted([s for s in stock.holdings if s.volume > 0], key=lambda s: s.price)
        shares_left = int(shares_to_sell)
        estimated_profit = 0.0
        
        for share in sorted_shares:
            if shares_left <= 0:
                break
            sell_volume = min(share.volume, shares_left)
            estimated_profit += (sell_price - share.price) * sell_volume
            shares_left -= sell_volume
        
        # Confirm sale
        total_sale_value = shares_to_sell * sell_price
        net_proceeds = total_sale_value - fee
        message_row = row + 7 + len(stocks_with_shares)
        self.safe_addstr(message_row, 0, f"Confirm sale: {int(shares_to_sell)} shares of {selected_ticker} at ${sell_price:.2f} each")
        self.safe_addstr(message_row + 1, 0, f"Gross proceeds: ${total_sale_value:.2f}, Fee: ${fee:.2f}, Net: ${net_proceeds:.2f}")
        self.safe_addstr(message_row + 2, 0, f"Estimated P/L: ${estimated_profit:.2f} (before fee)")
        
        if self.confirm_action("Confirm sale?", message_row + 3):
            try:
                success = self.portfolio.sell_shares(selected_ticker, int(shares_to_sell), sell_price, fee)
                if success:
                    self.portfolio.save_portfolio()
                    self.show_message(f"Successfully sold {int(shares_to_sell)} shares of {selected_ticker}!\nProfit/loss has been recorded.", 
                                    message_row + 5)
                else:
                    self.show_message("Error: Failed to sell shares (insufficient shares or other error)", 
                                    message_row + 5)
            except Exception as e:
                self.show_message(f"Error selling shares: {str(e)}", message_row + 5)
        else:
            self.show_message("Sale cancelled.", message_row + 5)


class WatchStocksHandler(RefreshableUIHandler):
    """Handler for watching stock prices with real-time updates."""
    
    def __init__(self, stdscr, portfolio):
        super().__init__(stdscr, portfolio)
        self.short_integration = None
        self._initialize_short_integration()
    
    def _initialize_short_integration(self):
        """Initialize short selling integration."""
        try:
            from short_selling.short_selling_integration import ShortSellingIntegration
            self.short_integration = ShortSellingIntegration(self.portfolio)
        except ImportError:
            pass
        except Exception:
            pass
    
    def handle(self) -> None:
        """Handle the watch stocks screen with real-time updates."""
        # Clear screen immediately to remove any leftover text from previous screens
        self.stdscr.clear()
        self.stdscr.refresh()
        
        self.stdscr.nodelay(True)
        prev_stock_prices = None
        dot_states = {}
        view_mode = 'stocks'  # 'stocks' or 'shares'
        shares_scroll_pos = 0
        first_cycle = True
        skip_dot_update_once = False
        force_history_next_cycle = False  # Flag to force historical data computation
        
        # Fetch short selling data once at start
        short_data_by_name = {}
        short_trend_by_name = {}
        if self.short_integration:
            try:
                summary = self.short_integration.get_portfolio_short_summary()
                portfolio_shorts = summary.get('portfolio_short_positions', [])
                # Map by stock name (not ticker) for display
                for stock_data in portfolio_shorts:
                    ticker = stock_data['ticker']
                    company_name = stock_data.get('company', '')  # Key is 'company', not 'company_name'
                    # Find stock name in portfolio by ticker
                    for name, stock_obj in self.portfolio.stocks.items():
                        if stock_obj.ticker == ticker:
                            short_data_by_name[name] = stock_data['percentage']
                            
                            # Calculate trend for this stock
                            if company_name:
                                try:
                                    trend_info = self.short_integration.calculate_short_trend(
                                        company_name,
                                        lookback_days=7,
                                        threshold=0.1
                                    )
                                    short_trend_by_name[name] = trend_info
                                    # Log successful trend calculation for debugging
                                    if trend_info.get('trend') != 'no_data':
                                        self.logger.debug(f"Trend for {name}: {trend_info.get('arrow')} ({trend_info.get('change'):+.2f}%)")
                                except Exception as e:
                                    self.logger.debug(f"Could not calculate trend for {name}: {e}")
                                    pass  # Skip trend calculation if it fails
                            break
            except Exception:
                pass  # Silently ignore errors loading short data
        
        # Note: Real-time prices and historical cache are already warmed at startup
        # No need for explicit _bulk_update() here - it's handled by startup and background threads
        
        refresh_cycle_count = 0  # Track refresh cycles
        
        try:
            while True:
                self.stdscr.clear()
                refresh_cycle_count += 1
                
                # Historical data is fast from cached files, always compute immediately
                should_compute_history = True  # Always show historical data since it's cached
                
                stock_prices = self.portfolio.get_stock_prices(include_zero_shares=True, compute_history=should_compute_history)
                
                if view_mode == 'stocks':
                    self._display_stocks_view(stock_prices, prev_stock_prices, dot_states, 
                                           skip_dot_update_once, short_data_by_name, short_trend_by_name)
                else:  # shares view
                    self._display_shares_view(stock_prices, prev_stock_prices, dot_states, 
                                           shares_scroll_pos, skip_dot_update_once, short_data_by_name, short_trend_by_name)
                
                self.stdscr.refresh()
                
                # Key handling loop
                key_pressed = False
                for _ in range(config.refresh_ticks):
                    key = self.stdscr.getch()
                    if key != -1:
                        if key in (ord('s'), ord('S')):
                            if view_mode == 'stocks':
                                view_mode = 'shares'
                                # Skip dots once when switching TO shares to avoid false change indicators
                                skip_dot_update_once = True
                            else:
                                view_mode = 'stocks'
                                # Skip dots once when switching BACK to stocks to avoid false change indicators
                                skip_dot_update_once = True
                            shares_scroll_pos = 0
                            key_pressed = True
                            break
                        elif key in (ord('r'), ord('R')) and view_mode == 'stocks':
                            # Trigger manual historical data refresh
                            # Show message at bottom without clearing screen
                            max_row = curses.LINES - 1
                            self.safe_addstr(max_row, 0, "Refreshing historical and short selling data... Please wait...", curses.color_pair(3))
                            self.stdscr.refresh()
                            
                            # Get all tickers and trigger bulk refresh
                            tickers = [stock.ticker for stock in self.portfolio.stocks.values()]
                            self.portfolio._bulk_refresh_historical_data(tickers)
                            
                            # Also refresh short selling data
                            if self.short_integration:
                                try:
                                    # Reload short data from disk (which was updated by the short selling menu)
                                    summary = self.short_integration.get_portfolio_short_summary()
                                    portfolio_shorts = summary.get('portfolio_short_positions', [])
                                    
                                    # Clear and rebuild short data mappings
                                    short_data_by_name.clear()
                                    short_trend_by_name.clear()
                                    
                                    # Map by stock name (not ticker) for display
                                    for stock_data in portfolio_shorts:
                                        ticker = stock_data['ticker']
                                        company_name = stock_data.get('company', '')
                                        # Find stock name in portfolio by ticker
                                        for name, stock_obj in self.portfolio.stocks.items():
                                            if stock_obj.ticker == ticker:
                                                short_data_by_name[name] = stock_data['percentage']
                                                
                                                # Calculate trend for this stock
                                                if company_name:
                                                    try:
                                                        trend_info = self.short_integration.calculate_short_trend(
                                                            company_name,
                                                            lookback_days=7,
                                                            threshold=0.1
                                                        )
                                                        short_trend_by_name[name] = trend_info
                                                    except Exception:
                                                        pass
                                                break
                                except Exception as e:
                                    self.logger.warning(f"Failed to refresh short selling data: {e}")
                            
                            # Show completion message briefly
                            self.safe_addstr(max_row, 0, "✓ Historical and short data refreshed!                              ", curses.color_pair(1))
                            self.stdscr.refresh()
                            import time
                            time.sleep(1)  # Show message for 1 second
                            
                            key_pressed = True
                            break
                        elif key in (ord('u'), ord('U')) and view_mode == 'stocks':
                            # Force update short selling data from remote server
                            max_row = curses.LINES - 1
                            self.safe_addstr(max_row, 0, "🔄 Fetching fresh short data from remote server... Please wait...", curses.color_pair(3))
                            self.stdscr.refresh()
                            
                            if self.short_integration:
                                try:
                                    # Force update from remote server
                                    update_result = self.short_integration.update_short_data(force=True)
                                    
                                    if update_result.get('success') and update_result.get('updated'):
                                        # Reload and rebuild short data mappings
                                        summary = self.short_integration.get_portfolio_short_summary()
                                        portfolio_shorts = summary.get('portfolio_short_positions', [])
                                        
                                        # Clear and rebuild
                                        short_data_by_name.clear()
                                        short_trend_by_name.clear()
                                        
                                        # Map by stock name
                                        for stock_data in portfolio_shorts:
                                            ticker = stock_data['ticker']
                                            company_name = stock_data.get('company', '')
                                            for name, stock_obj in self.portfolio.stocks.items():
                                                if stock_obj.ticker == ticker:
                                                    short_data_by_name[name] = stock_data['percentage']
                                                    
                                                    # Calculate trend
                                                    if company_name:
                                                        try:
                                                            trend_info = self.short_integration.calculate_short_trend(
                                                                company_name,
                                                                lookback_days=7,
                                                                threshold=0.1
                                                            )
                                                            short_trend_by_name[name] = trend_info
                                                        except Exception:
                                                            pass
                                                    break
                                        
                                        stats = update_result.get('stats', {})
                                        matches = stats.get('portfolio_matches', 0)
                                        self.safe_addstr(max_row, 0, f"✅ Short data updated from remote: {matches} stocks tracked                    ", curses.color_pair(1))
                                    else:
                                        self.safe_addstr(max_row, 0, "ℹ️  Short data already current (no update needed)                      ", curses.color_pair(3))
                                    
                                    self.stdscr.refresh()
                                    import time
                                    time.sleep(2)  # Show message for 2 seconds
                                except Exception as e:
                                    self.logger.warning(f"Failed to update short data from remote: {e}")
                                    self.safe_addstr(max_row, 0, f"❌ Failed to update: {str(e)[:50]}                                  ", curses.color_pair(2))
                                    self.stdscr.refresh()
                                    import time
                                    time.sleep(2)
                            else:
                                self.safe_addstr(max_row, 0, "⚠️  Short selling integration not available                          ", curses.color_pair(3))
                                self.stdscr.refresh()
                                import time
                                time.sleep(1)
                            
                            key_pressed = True
                            break
                        elif view_mode == 'shares' and key == curses.KEY_UP:
                            if shares_scroll_pos > 0:
                                shares_scroll_pos -= 1
                                key_pressed = True
                                break
                        elif view_mode == 'shares' and key == curses.KEY_DOWN:
                            # Use current stock_prices for consistent scroll calculation
                            shares_lines = get_portfolio_shares_lines(self.portfolio, stock_prices)
                            max_body_lines = curses.LINES - 3
                            max_scroll = max(0, len(shares_lines) - max_body_lines)
                            if shares_scroll_pos < max_scroll:
                                shares_scroll_pos += 1
                                key_pressed = True
                                break
                        else:
                            return
                    import time
                    time.sleep(config.REFRESH_TICK_SLICE)
                
                # Update first_cycle flag after a few cycles
                if first_cycle and refresh_cycle_count > 2:
                    first_cycle = False
                
                # Update prev_stock_prices for both views to enable proper dot comparison
                # This must happen BEFORE the key_pressed check to ensure dots update even when scrolling
                # Use deep copy to prevent cache modifications from affecting prev_stock_prices
                if not skip_dot_update_once:
                    import copy
                    prev_stock_prices = copy.deepcopy(stock_prices)
                
                # Handle skip_dot_update_once flag
                if skip_dot_update_once:
                    skip_dot_update_once = False
                
                if key_pressed:
                    continue
                        
        finally:
            self.stdscr.nodelay(False)
    
    def _display_currency_legend(self, start_row):
        """Display currency conversion rates legend."""
        try:
            # Get exchange rates from the currency manager
            currency_manager = self.portfolio.currency_manager
            rates = currency_manager.exchange_rates
            
            # Collect unique currencies from stocks (excluding SEK)
            currencies = set()
            for stock in self.portfolio.stocks.values():
                price_info = stock.get_price_info()
                if price_info and price_info.currency != 'SEK':
                    currencies.add(price_info.currency)
            
            if not currencies:
                return  # No foreign currencies to display
            
            # Build currency legend string
            legend_parts = ["(*) Currency rates:"]
            for currency in sorted(currencies):
                rate = rates.get(currency, 1.0)
                legend_parts.append(f"1 {currency} = {rate:.2f} SEK")
            
            legend_str = "  ".join(legend_parts)
            
            # Display the legend
            if start_row < curses.LINES - 1:
                self.safe_addstr(start_row, 0, legend_str[:curses.COLS - 1], curses.color_pair(3))
        except Exception:
            pass  # Silently ignore errors in legend display
    
    def _display_stocks_view(self, stock_prices, prev_stock_prices, dot_states, 
                           skip_dot_update_once, short_data_by_name=None, short_trend_by_name=None):
        """Display the stocks view with prices and totals."""
        lines = format_stock_price_lines(stock_prices, short_data_by_name, short_trend_by_name)
        stats = self.portfolio.get_update_stats()
        yf_count = stats['yfinance_calls']
        yf_last = stats.get('last_yfinance_call')
        
        # Convert string back to datetime if needed
        if isinstance(yf_last, str) and yf_last != 'None':
            try:
                from datetime import datetime
                yf_last = datetime.fromisoformat(yf_last)
            except:
                yf_last = None
        
        status = f"YF calls: {yf_count}"
        if yf_last:
            status += f" @{yf_last.strftime('%H:%M:%S')}"
        
        header = lines[0] if lines else ""
        separator = lines[1] if len(lines) > 1 else ""
        maxw = curses.COLS - 1
        
        # Status above header
        self.safe_addstr(0, 0, status[:maxw], curses.color_pair(3))
        self.safe_addstr(1, 0, header[:maxw])
        self.safe_addstr(2, 0, separator[:maxw])
        base_row = 3
        
        # Display stock prices with color coding
        # Don't update dots when skip_dot_update_once is True to prevent false indicators when switching views
        effective_prev = stock_prices if skip_dot_update_once else prev_stock_prices
        display_colored_stock_prices(self.stdscr, stock_prices, effective_prev, dot_states, 
                                   self.portfolio, skip_header=True, base_row=base_row, 
                                   short_data=short_data_by_name, short_trend=short_trend_by_name,
                                   update_dots=not skip_dot_update_once)
        
        # Calculate totals row position
        stocks_with_shares_count = 0
        stocks_without_shares_count = 0
        for stock in stock_prices:
            name = stock.get("name", "")
            stock_obj = self.portfolio.stocks.get(name)
            if stock_obj:
                total_shares = sum(share.volume for share in stock_obj.holdings)
                if total_shares > 0:
                    stocks_with_shares_count += 1
                else:
                    stocks_without_shares_count += 1
            else:
                stocks_without_shares_count += 1
        
        totals_row = 2 + stocks_with_shares_count + stocks_without_shares_count
        if stocks_with_shares_count and stocks_without_shares_count:
            totals_row += 1
        totals_row += 2
        
        display_portfolio_totals(self.stdscr, self.portfolio, totals_row)
        
        # Display currency conversion rates after totals (now includes cash line, so +1 extra row)
        currency_row = totals_row + 3
        if currency_row < curses.LINES - 2:
            self._display_currency_legend(currency_row)
        
        instr_row = totals_row + 5
        if instr_row < curses.LINES - 1:
            # Build instruction line - historical data is automatically managed
            self.safe_addstr(instr_row, 0, "View: STOCKS  |  's'=Shares  'r'=Refresh  'u'=Update Shorts  any other key=Exit")
    
    def _display_shares_view(self, stock_prices, prev_stock_prices, dot_states, 
                           shares_scroll_pos, skip_dot_update_once, short_data_by_name=None, short_trend_by_name=None):
        """Display the shares view with detailed share information."""
        stats = self.portfolio.get_update_stats()
        yf_count = stats['yfinance_calls']
        yf_last = stats.get('last_yfinance_call')
        
        if isinstance(yf_last, str) and yf_last != 'None':
            try:
                from datetime import datetime
                yf_last = datetime.fromisoformat(yf_last)
            except:
                yf_last = None
        
        status = f"YF calls: {yf_count}"
        if yf_last:
            status += f" @{yf_last.strftime('%H:%M:%S')}"
        
        owned_stocks = []
        for sp in stock_prices:
            name = sp.get("name", "")
            stock_obj = self.portfolio.stocks.get(name)
            if stock_obj and sum(sh.volume for sh in stock_obj.holdings) > 0:
                owned_stocks.append(sp)
        
        row_ptr = 0
        maxw = curses.COLS - 1
        
        # Status first
        self.safe_addstr(row_ptr, 0, status[:maxw], curses.color_pair(3))
        row_ptr += 1
        
        if owned_stocks:
            header_lines = format_stock_price_lines(owned_stocks, short_data_by_name, short_trend_by_name)[:2]
            if header_lines:
                header = header_lines[0]
                separator = header_lines[1] if len(header_lines) > 1 else ""
                self.safe_addstr(row_ptr, 0, header[:maxw])
                row_ptr += 1
                self.safe_addstr(row_ptr, 0, separator[:maxw])
                row_ptr += 1
            
            # Use the same effective_prev logic as in stocks view for consistent dot behavior
            effective_prev_stocks = stock_prices if skip_dot_update_once else prev_stock_prices
            
            prev_lookup = {}
            if effective_prev_stocks:
                for pst in effective_prev_stocks:
                    prev_lookup[pst.get("name", "")] = pst
            
            # Don't update dots when skip_dot_update_once is True to prevent false indicators when switching views
            for ost in owned_stocks:
                if row_ptr >= curses.LINES - 1:
                    break
                row_ptr = display_single_stock_price(self.stdscr, ost, row_ptr, prev_lookup, 
                                                   dot_states, update_dots=not skip_dot_update_once, 
                                                   short_data=short_data_by_name, short_trend=short_trend_by_name)
            
            if row_ptr < curses.LINES - 1:
                self.safe_addstr(row_ptr, 0, "")
                row_ptr += 1
        
        # Share details list below summary
        # Pass stock_prices to ensure share details use the same data snapshot as dots
        shares_lines = get_portfolio_shares_lines(self.portfolio, stock_prices)
        if row_ptr < curses.LINES - 1:
            self.safe_addstr(row_ptr, 0, "Share Details (UP/DOWN to scroll, 's'=Stocks, any other key=Exit)")
            row_ptr += 1
        if row_ptr < curses.LINES - 1:
            self.safe_addstr(row_ptr, 0, "-" * min(curses.COLS - 1, 80))
            row_ptr += 1
        
        max_body_lines = max(0, curses.LINES - row_ptr - 1)
        max_scroll_possible = max(0, len(shares_lines) - max_body_lines)
        if shares_scroll_pos > max_scroll_possible:
            shares_scroll_pos = max_scroll_possible
            
        visible = shares_lines[shares_scroll_pos:shares_scroll_pos + max_body_lines]
        for idx, line in enumerate(visible):
            row = row_ptr + idx
            if row >= curses.LINES - 1:
                break
                
            # Color profit/loss values
            if idx + shares_scroll_pos >= 2 and not line.startswith('-') and line.strip() and len(line.split()) >= 5:
                try:
                    parts = line.split()
                    profit_loss_str = parts[4]
                    profit_loss_val = float(profit_loss_str)
                    pl_start = line.find(profit_loss_str, line.find(parts[3]) + len(parts[3]))
                    
                    if pl_start > 0:
                        before = line[:pl_start]
                        self.safe_addstr(row, 0, before)
                        col_pos = len(before)
                        if col_pos < curses.COLS - len(profit_loss_str):
                            self.safe_addstr(row, col_pos, profit_loss_str, color_for_value(profit_loss_val))
                            after = line[pl_start + len(profit_loss_str):]
                            col_pos += len(profit_loss_str)
                            if after and col_pos < curses.COLS - 1:
                                self.safe_addstr(row, col_pos, after)
                    else:
                        self.safe_addstr(row, 0, line)
                except Exception:
                    self.safe_addstr(row, 0, line)
            else:
                self.safe_addstr(row, 0, line)
        
        footer_row = row_ptr + len(visible)
        if len(shares_lines) > max_body_lines and footer_row < curses.LINES - 1:
            self.safe_addstr(footer_row, 0, f"Lines {shares_scroll_pos + 1}-{shares_scroll_pos + len(visible)} of {len(shares_lines)}")
            footer_row += 1
        
        # Display portfolio totals at the bottom after share details
        if footer_row < curses.LINES - 5:  # Need at least 5 lines for totals
            footer_row += 1  # Add spacing
            display_portfolio_totals(self.stdscr, self.portfolio, footer_row)
    
    def _show_short_positions_overlay(self):
        """Show short positions data for portfolio stocks as an overlay."""
        # Temporarily disable nodelay to wait for user input
        self.stdscr.nodelay(False)
        
        try:
            self.stdscr.clear()
            row = 0
            
            # Header
            self.safe_addstr(row, 0, "=" * min(curses.COLS - 1, 80))
            row += 1
            self.safe_addstr(row, 0, "SHORT POSITIONS - PORTFOLIO STOCKS (Press 'h' in watch mode)")
            row += 1
            self.safe_addstr(row, 0, "=" * min(curses.COLS - 1, 80))
            row += 1
            
            if not self.short_integration:
                self.safe_addstr(row, 0, "Short selling data not available.")
                row += 1
                self.safe_addstr(row, 0, "")
                row += 1
                self.safe_addstr(row, 0, "To enable, go to main menu option 8 (Short Selling) and update data.")
            else:
                # Get short data
                summary = self.short_integration.get_portfolio_short_summary()
                
                if 'error' in summary:
                    self.safe_addstr(row, 0, f"Error: {summary['error']}")
                    row += 1
                    self.safe_addstr(row, 0, "")
                    row += 1
                    self.safe_addstr(row, 0, "Use main menu option 8 -> 3 to update short selling data.")
                else:
                    portfolio_shorts = summary.get('portfolio_short_positions', [])
                    
                    if not portfolio_shorts:
                        self.safe_addstr(row, 0, "No short selling data available for portfolio stocks.")
                    else:
                        # Display summary
                        self.safe_addstr(row, 0, f"Last Updated: {summary.get('last_updated', 'Unknown')[:19]}")
                        row += 1
                        self.safe_addstr(row, 0, f"Stocks tracked: {len(portfolio_shorts)}")
                        row += 1
                        self.safe_addstr(row, 0, "")
                        row += 1
                        
                        # Group by risk level for compact display
                        very_high = [s for s in portfolio_shorts if s['percentage'] > 10]
                        high = [s for s in portfolio_shorts if 5 < s['percentage'] <= 10]
                        moderate = [s for s in portfolio_shorts if 2 < s['percentage'] <= 5]
                        low = [s for s in portfolio_shorts if s['percentage'] <= 2]
                        
                        # Header for table
                        self.safe_addstr(row, 0, f"{'Stock':<15} {'Short %':<10} {'Company':<40}")
                        row += 1
                        self.safe_addstr(row, 0, "-" * min(curses.COLS - 1, 80))
                        row += 1
                        
                        # Display each category
                        max_display_lines = curses.LINES - row - 4  # Leave room for footer
                        lines_used = 0
                        
                        if very_high and lines_used < max_display_lines:
                            self.safe_addstr(row, 0, "🔴 VERY HIGH (>10%)", curses.color_pair(2))
                            row += 1
                            lines_used += 1
                            for stock in very_high:
                                if lines_used >= max_display_lines:
                                    break
                                # Check if owned
                                owned = self._is_stock_owned(stock['ticker'])
                                marker = "★ " if owned else "  "
                                self.safe_addstr(row, 0, f"{marker}{stock['ticker']:<13} {stock['percentage']:6.2f}%    {stock['company'][:38]}")
                                row += 1
                                lines_used += 1
                        
                        if high and lines_used < max_display_lines:
                            if lines_used > 1:  # Add spacing if not first category
                                row += 1
                                lines_used += 1
                            if lines_used < max_display_lines:
                                self.safe_addstr(row, 0, "🟠 HIGH (5-10%)", curses.color_pair(3))
                                row += 1
                                lines_used += 1
                                for stock in high:
                                    if lines_used >= max_display_lines:
                                        break
                                    owned = self._is_stock_owned(stock['ticker'])
                                    marker = "★ " if owned else "  "
                                    self.safe_addstr(row, 0, f"{marker}{stock['ticker']:<13} {stock['percentage']:6.2f}%    {stock['company'][:38]}")
                                    row += 1
                                    lines_used += 1
                        
                        if moderate and lines_used < max_display_lines:
                            if lines_used > 1:
                                row += 1
                                lines_used += 1
                            if lines_used < max_display_lines:
                                self.safe_addstr(row, 0, "🟡 MODERATE (2-5%)", curses.color_pair(3))
                                row += 1
                                lines_used += 1
                                for stock in moderate[:min(len(moderate), max_display_lines - lines_used)]:
                                    owned = self._is_stock_owned(stock['ticker'])
                                    marker = "★ " if owned else "  "
                                    self.safe_addstr(row, 0, f"{marker}{stock['ticker']:<13} {stock['percentage']:6.2f}%    {stock['company'][:38]}")
                                    row += 1
                                    lines_used += 1
                        
                        if low and lines_used < max_display_lines:
                            remaining = max_display_lines - lines_used
                            if remaining > 2:  # Only show if we have room
                                if lines_used > 1:
                                    row += 1
                                    lines_used += 1
                                if lines_used < max_display_lines:
                                    self.safe_addstr(row, 0, f"🟢 LOW (<2%) - showing {min(len(low), remaining - 1)}/{len(low)}", curses.color_pair(1))
                                    row += 1
                                    lines_used += 1
                                    for stock in low[:min(len(low), remaining - 1)]:
                                        owned = self._is_stock_owned(stock['ticker'])
                                        marker = "★ " if owned else "  "
                                        self.safe_addstr(row, 0, f"{marker}{stock['ticker']:<13} {stock['percentage']:6.2f}%    {stock['company'][:38]}")
                                        row += 1
                                        lines_used += 1
            
            # Footer
            row = curses.LINES - 2
            self.safe_addstr(row, 0, "")
            row += 1
            self.safe_addstr(row, 0, "★ = Currently owned  |  Press any key to return to watch screen")
            
            self.stdscr.refresh()
            self.stdscr.getch()  # Wait for key press
            
        finally:
            # Re-enable nodelay mode
            self.stdscr.nodelay(True)
    
    def _is_stock_owned(self, ticker: str) -> bool:
        """Check if a stock is currently owned in the portfolio."""
        for stock in self.portfolio.stocks.values():
            if stock.ticker == ticker:
                total_shares = sum(share.volume for share in stock.holdings)
                return total_shares > 0
        return False


class ProfitPerStockHandler(ScrollableUIHandler):
    """Handler for displaying profit per stock."""
    
    def handle(self) -> None:
        """Handle profit per stock display."""
        row = self.clear_and_display_header("Profit per Stock - Select Stock")
        
        # Get list of stocks with profit records
        stocks_with_profits = []
        for ticker in self.portfolio.stocks.keys():
            profit_file = os.path.join(self.portfolio.path, f"{ticker}_profit.json")
            if os.path.exists(profit_file):
                try:
                    with open(profit_file, "r") as f:
                        profit_records = json.load(f)
                        if profit_records:
                            stocks_with_profits.append(ticker)
                except Exception:
                    pass
        
        if not stocks_with_profits:
            self.show_message("No stocks with profit records found.", row)
            return
        
        # Display available stocks
        self.safe_addstr(row, 0, "Stocks with profit records:")
        for i, ticker in enumerate(stocks_with_profits):
            self.safe_addstr(row + 1 + i, 0, f"{i+1}. {ticker}")
        
        self.safe_addstr(row + 1 + len(stocks_with_profits), 0, f"{len(stocks_with_profits)+1}. Show All Stocks")
        
        # Get stock selection
        choice = self.get_numeric_input(
            "Select option (or 0 to cancel): ", 
            row + 2 + len(stocks_with_profits), 
            min_val=0, 
            max_val=len(stocks_with_profits) + 1, 
            integer_only=True
        )
        
        if not choice or choice == 0:
            return
        elif choice <= len(stocks_with_profits):
            selected_ticker = stocks_with_profits[int(choice) - 1]
        elif choice == len(stocks_with_profits) + 1:
            selected_ticker = None  # Show all stocks
        else:
            return
        
        # Display profit records
        lines = get_portfolio_profit_lines(self.portfolio, selected_ticker)
        
        def color_callback(row: int, line: str):
            """Color code profit/loss values in the line."""
            self._display_profit_line_with_colors(row, line)
        
        title = f"Profit Records for {selected_ticker}" if selected_ticker else "Profit per Stock - All Records"
        self.display_scrollable_list(title, lines, color_callback)
    
    def _display_profit_line_with_colors(self, row: int, line: str):
        """Display profit record line with color coding."""
        # Check if this is a data line with profit/loss values
        if not line.startswith('-') and line.strip() and not line.startswith('No ') and not line.startswith('Error'):
            try:
                parts = line.split()
                if len(parts) >= 7:  # Updated for new format with date
                    # Color code the profit/loss and percentage columns
                    col_pos = 0
                    
                    # Display ticker, shares, buy price, sell price
                    ticker_part = f"{parts[0]:<12} "
                    shares_part = f"{int(parts[1]):>8} "
                    buy_price_part = f"{float(parts[2]):>12.2f} "
                    sell_price_part = f"{float(parts[3]):>12.2f} "
                    
                    self.safe_addstr(row, col_pos, ticker_part)
                    col_pos += len(ticker_part)
                    self.safe_addstr(row, col_pos, shares_part)
                    col_pos += len(shares_part)
                    self.safe_addstr(row, col_pos, buy_price_part)
                    col_pos += len(buy_price_part)
                    self.safe_addstr(row, col_pos, sell_price_part)
                    col_pos += len(sell_price_part)
                    
                    # Display profit/loss with color
                    try:
                        profit_val = float(parts[4])
                        color_attr = color_for_value(profit_val)
                        self.safe_addstr(row, col_pos, f"{profit_val:>12.2f} ", color_attr)
                    except ValueError:
                        self.safe_addstr(row, col_pos, f"{parts[4]:>13} ")
                    col_pos += 13
                    
                    # Display percentage with color
                    pct_str = parts[5].rstrip('%')
                    try:
                        pct_val = float(pct_str)
                        color_attr = color_for_value(pct_val)
                        self.safe_addstr(row, col_pos, f"{pct_val:>11.2f}% ", color_attr)
                    except ValueError:
                        self.safe_addstr(row, col_pos, f"{parts[5]:>13} ")
                    col_pos += 13
                    
                    # Display date
                    date_part = " ".join(parts[6:])
                    if col_pos < curses.COLS - len(date_part):
                        self.safe_addstr(row, col_pos, date_part)
                else:
                    self.safe_addstr(row, 0, line[:curses.COLS-1])
            except (ValueError, IndexError):
                self.safe_addstr(row, 0, line[:curses.COLS-1])
        else:
            # Handle total line with special coloring for profit
            if line.startswith("TOTAL") and len(line.split()) >= 5:
                try:
                    parts = line.split()
                    total_profit_val = float(parts[4])
                    
                    # Display TOTAL prefix
                    self.safe_addstr(row, 0, f"{parts[0]:<12} ")
                    col_pos = 13
                    
                    # Skip empty columns with proper spacing
                    self.safe_addstr(row, col_pos, f"{'':>8} {'':>12} {'':>12} ")
                    col_pos += 32
                    
                    # Display total profit with color
                    color_attr = color_for_value(total_profit_val)
                    self.safe_addstr(row, col_pos, f"{total_profit_val:>12.2f}", color_attr)
                except (ValueError, IndexError):
                    self.safe_addstr(row, 0, line[:curses.COLS-1])
            else:
                self.safe_addstr(row, 0, line[:curses.COLS-1])


class AllProfitsHandler(ScrollableUIHandler):
    """Handler for displaying all profits summary."""
    
    def handle(self) -> None:
        """Handle all profits display."""
        lines = get_portfolio_allprofits_lines(self.portfolio)
        
        def color_callback(row: int, line: str):
            """Color code profit/loss values in the line."""
            # Check if this is a data line with profit/loss values
            if not line.startswith('-') and line.strip():
                try:
                    parts = line.split()
                    if len(parts) >= 4:
                        # Color code the profit/loss columns
                        col_pos = 0
                        
                        # Display ticker
                        ticker_part = f"{parts[0]:<12} "
                        self.safe_addstr(row, col_pos, ticker_part)
                        col_pos += len(ticker_part)
                        
                        # Display realized P/L with color
                        try:
                            realized_val = float(parts[1])
                            color_attr = color_for_value(realized_val)
                            self.safe_addstr(row, col_pos, f"{realized_val:>12.2f} ", color_attr)
                        except ValueError:
                            self.safe_addstr(row, col_pos, f"{parts[1]:>13} ")
                        col_pos += 13
                        
                        # Display unrealized P/L with color
                        try:
                            unrealized_val = float(parts[2])
                            color_attr = color_for_value(unrealized_val)
                            self.safe_addstr(row, col_pos, f"{unrealized_val:>12.2f} ", color_attr)
                        except ValueError:
                            self.safe_addstr(row, col_pos, f"{parts[2]:>13} ")
                        col_pos += 13
                        
                        # Display total P/L with color
                        try:
                            total_val = float(parts[3])
                            color_attr = color_for_value(total_val)
                            self.safe_addstr(row, col_pos, f"{total_val:>12.2f}", color_attr)
                        except ValueError:
                            self.safe_addstr(row, col_pos, f"{parts[3]:>12}")
                    else:
                        self.safe_addstr(row, 0, line[:curses.COLS-1])
                except (ValueError, IndexError):
                    self.safe_addstr(row, 0, line[:curses.COLS-1])
            else:
                self.safe_addstr(row, 0, line[:curses.COLS-1])
        
        self.display_scrollable_list("All Profits", lines, color_callback)

class CapitalManagementHandler(BaseUIHandler):
    """Handler for capital tracking management."""
    
    def handle(self) -> None:
        """Handle capital management menu."""
        # Ensure blocking mode for input
        self.stdscr.nodelay(False)
        
        # Check if capital tracking is initialized
        if not self.portfolio.capital_tracker.is_initialized():
            self._show_initialization_menu()
            # After initialization (or cancel), show the menu if initialized
            if not self.portfolio.capital_tracker.is_initialized():
                return  # User cancelled, go back to main menu
        
        # Show capital management menu
        while True:
            self.stdscr.clear()
            self.safe_addstr(0, 0, "═" * 70)
            self.safe_addstr(1, 0, "CAPITAL MANAGEMENT")
            self.safe_addstr(2, 0, "═" * 70)
            self.safe_addstr(4, 0, "1. View Capital Summary")
            self.safe_addstr(5, 0, "2. Record Deposit (money TO broker)")
            self.safe_addstr(6, 0, "3. Record Withdrawal (money FROM broker)")
            self.safe_addstr(7, 0, "4. View Transaction History")
            self.safe_addstr(8, 0, "5. View Returns Analysis")
            self.safe_addstr(9, 0, "6. Plot Profit & Returns (with Historical Data)")
            self.safe_addstr(10, 0, "0. Back to Main Menu")
            self.safe_addstr(12, 0, "Select an option: ")
            self.stdscr.refresh()
            
            key = self.stdscr.getch()
            
            if key == ord('1'):
                self._show_capital_summary()
            elif key == ord('2'):
                self._record_deposit()
            elif key == ord('3'):
                self._record_withdrawal()
            elif key == ord('4'):
                self._show_transaction_history()
            elif key == ord('5'):
                self._show_returns_analysis()
            elif key == ord('6'):
                self._plot_total_profit_with_historical()
            elif key == ord('0') or key == 27:  # 0 or ESC
                return
    
    def _show_initialization_menu(self):
        """Show first-time initialization menu."""
        # Ensure blocking mode for input
        self.stdscr.nodelay(False)
        
        self.stdscr.clear()
        self.safe_addstr(0, 0, "═" * 70)
        self.safe_addstr(1, 0, "CAPITAL TRACKING INITIALIZATION")
        self.safe_addstr(2, 0, "═" * 70)
        self.safe_addstr(4, 0, "Capital tracking is not yet initialized.")
        self.safe_addstr(5, 0, "This one-time setup will enable portfolio return tracking.")
        self.safe_addstr(7, 0, "Choose initialization method:")
        self.safe_addstr(9, 0, "1. Manual Entry - Enter historical capital deposits with dates")
        self.safe_addstr(10, 0, "   (Most accurate - tracks when money entered the system)")
        self.safe_addstr(12, 0, "2. Quick Start - Use current portfolio value as starting point")
        self.safe_addstr(13, 0, "   (Faster - tracks returns from today forward)")
        self.safe_addstr(15, 0, "3. Cancel")
        self.safe_addstr(17, 0, "Select option (1-3): ")
        self.stdscr.refresh()
        
        key = self.stdscr.getch()
        
        if key == ord('1'):
            self._manual_initialization()
        elif key == ord('2'):
            self._quick_initialization()
        # else cancel
    
    def _manual_initialization(self):
        """Manual historical deposits entry."""
        deposits = []
        
        self.stdscr.clear()
        self.safe_addstr(0, 0, "═" * 70)
        self.safe_addstr(1, 0, "MANUAL CAPITAL ENTRY")
        self.safe_addstr(2, 0, "═" * 70)
        self.safe_addstr(4, 0, "Enter historical capital transfers to your broker account.")
        self.safe_addstr(5, 0, "Format: Date (YYYY-MM-DD), Amount (SEK), Description")
        self.safe_addstr(6, 0, "Press Enter with empty date to finish.")
        self.stdscr.refresh()
        
        row = 8
        deposit_num = 1
        
        while True:
            self.safe_addstr(row, 0, f"Transfer #{deposit_num}:")
            row += 1
            
            # Get date
            date_str = self.get_user_input("  Date (YYYY-MM-DD): ", row)
            if not date_str:
                break
            
            # Validate date format
            try:
                import datetime
                datetime.datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                self.safe_addstr(row + 2, 0, "Invalid date format! Use YYYY-MM-DD")
                self.stdscr.getch()
                row += 3
                continue
            
            # Get amount
            amount = self.get_numeric_input("  Amount (SEK): ", row + 1, min_val=0.01)
            if not amount:
                break
            
            # Get description
            description = self.get_user_input("  Description: ", row + 2)
            if not description:
                description = f"Deposit {deposit_num}"
            
            deposits.append((date_str, amount, description))
            
            self.safe_addstr(row + 4, 0, f"✓ Added: {amount:,.2f} SEK on {date_str}", curses.color_pair(2))
            row += 6
            deposit_num += 1
            
            # Ask if more
            self.safe_addstr(row, 0, "Add another? (y/n): ")
            self.stdscr.refresh()
            key = self.stdscr.getch()
            if key != ord('y') and key != ord('Y'):
                break
            row += 2
        
        if not deposits:
            self.show_message("No deposits entered. Initialization cancelled.", row + 2)
            return
        
        # Show summary
        self.stdscr.clear()
        self.safe_addstr(0, 0, "═" * 70)
        self.safe_addstr(1, 0, "INITIALIZATION SUMMARY")
        self.safe_addstr(2, 0, "═" * 70)
        
        row = 4
        total = 0.0
        for date_str, amount, desc in deposits:
            self.safe_addstr(row, 0, f"{date_str}  {amount:>12,.2f} SEK  {desc}")
            total += amount
            row += 1
        
        self.safe_addstr(row + 1, 0, "─" * 70)
        self.safe_addstr(row + 2, 0, f"Total Capital: {total:,.2f} SEK")
        
        if self.confirm_action("Initialize with these deposits?", row + 4):
            self.portfolio.capital_tracker.initialize_manual(deposits)
            self.show_message("✓ Capital tracking initialized successfully!", row + 6, curses.color_pair(2))
        else:
            self.show_message("Initialization cancelled.", row + 6)
    
    def _quick_initialization(self):
        """Quick initialization from current portfolio."""
        # Calculate current portfolio value
        stock_prices = self.portfolio.get_stock_prices(include_zero_shares=False)
        
        total_value = 0.0
        for stock_data in stock_prices:
            total_value += stock_data.get('total_value', 0.0)
        
        self.stdscr.clear()
        self.safe_addstr(0, 0, "═" * 70)
        self.safe_addstr(1, 0, "QUICK START INITIALIZATION")
        self.safe_addstr(2, 0, "═" * 70)
        self.safe_addstr(4, 0, f"Current Portfolio Value: {total_value:,.2f} SEK")
        self.safe_addstr(6, 0, "This will record today as your initial capital entry.")
        self.safe_addstr(7, 0, "Return calculations will start from today.")
        
        if self.confirm_action("Initialize with current portfolio value?", 9):
            self.portfolio.capital_tracker.initialize_from_current_portfolio(total_value)
            self.show_message("✓ Capital tracking initialized successfully!", 11, curses.color_pair(2))
        else:
            self.show_message("Initialization cancelled.", 11)
    
    def _show_capital_summary(self):
        """Display comprehensive capital summary."""
        # Get current portfolio value
        stock_prices = self.portfolio.get_stock_prices(include_zero_shares=False)
        
        stock_value_market = 0.0
        stock_value_at_cost = 0.0
        
        # Try to get market value from prices
        for stock_data in stock_prices:
            stock_value_market += stock_data.get('total_value', 0.0)
        
        # Calculate CORRECT cost basis using FIFO from capital tracker events
        fifo_result = self.portfolio.capital_tracker.get_fifo_cost_basis()
        stock_value_at_cost = fifo_result['total_cost_basis']
        
        # Use market value if available, otherwise use cost basis
        stock_value_current = stock_value_market if stock_value_market > 0 else stock_value_at_cost
        
        cash_balance = self.portfolio.capital_tracker.get_current_cash()
        total_portfolio_value = stock_value_current + cash_balance
        
        # Get comprehensive summary
        summary = self.portfolio.capital_tracker.get_capital_summary(
            total_portfolio_value, 
            stock_value_current,
            stock_value_at_cost,  # Pass the FIFO cost basis
            self.portfolio  # Pass portfolio for true TWR calculation
        )
        
        # Display
        lines = []
        lines.append("═" * 70)
        lines.append("CAPITAL SUMMARY")
        lines.append("═" * 70)
        lines.append("")
        lines.append("💰 CAPITAL FLOW")
        lines.append(f"Total Deposits:            {summary['total_deposits']:>15,.2f} SEK")
        lines.append(f"Total Withdrawals:         {summary['total_withdrawals']:>15,.2f} SEK")
        lines.append(f"Net Capital Input:         {summary['net_capital_input']:>15,.2f} SEK")
        lines.append(f"Average Days Invested:     {summary['average_days_invested']:>15} days")
        lines.append("")
        lines.append("📊 CURRENT POSITION")
        lines.append(f"Cash in Broker:            {summary['cash_balance']:>15,.2f} SEK")
        lines.append(f"Stock Holdings (cost):     {summary['stock_value_at_cost']:>15,.2f} SEK")
        
        if stock_value_market > 0:
            lines.append(f"Stock Holdings (market):   {summary['stock_value_current']:>15,.2f} SEK")
            unrealized_on_holdings = stock_value_market - stock_value_at_cost
            lines.append(f"  Unrealized on holdings:  {unrealized_on_holdings:>15,.2f} SEK")
        else:
            lines.append(f"  (Using cost basis - market prices not loaded)")
        
        lines.append(f"Total Portfolio Value:     {summary['portfolio_value_total']:>15,.2f} SEK")
        lines.append("")
        lines.append("📈 RETURNS")
        lines.append(f"Realized Gain (from sales):{summary['realized_gain']:>15,.2f} SEK")
        
        if stock_value_market > 0:
            lines.append(f"Unrealized (on holdings):  {summary['unrealized_gain']:>15,.2f} SEK")
        else:
            lines.append(f"Unrealized (on holdings):  {summary['unrealized_gain']:>15,.2f} SEK  (need market prices)")
        
        lines.append(f"Total Gain/Loss:           {summary['total_gain']:>15,.2f} SEK")
        lines.append("")
        lines.append(f"Simple Return:             {summary['simple_return_percent']:>14.2f}%")
        lines.append(f"Time-Weighted Return:      {summary['time_weighted_return_percent']:>14.2f}%")
        lines.append(f"Annualized Return:         {summary['annualized_return_percent']:>14.2f}% per year")
        lines.append("")
        lines.append(f"Last Updated: {summary['last_updated']}")
        lines.append("═" * 70)
        
        self.display_scrollable_list("Capital Summary", lines)
    
    def _record_deposit(self):
        """Record a new deposit."""
        row = self.clear_and_display_header("Record Deposit")
        
        # Get amount
        amount = self.get_numeric_input("Enter deposit amount (SEK): ", row, min_val=0.01)
        if not amount:
            return
        
        # Get date (default to today)
        import datetime
        today = datetime.date.today().strftime("%Y-%m-%d")
        self.safe_addstr(row + 1, 0, f"Date (YYYY-MM-DD) [default: {today}]: ")
        self.stdscr.refresh()
        
        curses.echo()
        date_input = self.stdscr.getstr(row + 1, 50, 20).decode('utf-8').strip()
        curses.noecho()
        
        date_str = date_input if date_input else today
        
        # Get description
        description = self.get_user_input("Description (optional): ", row + 2)
        
        # Confirm
        self.safe_addstr(row + 4, 0, f"Record deposit of {amount:,.2f} SEK on {date_str}?")
        
        if self.confirm_action("Confirm?", row + 5):
            self.portfolio.capital_tracker.record_deposit(amount, date_str, description)
            self.portfolio.capital_tracker.save()
            self.show_message(f"✓ Deposit recorded: {amount:,.2f} SEK", row + 7, curses.color_pair(2))
        else:
            self.show_message("Cancelled.", row + 7)
    
    def _record_withdrawal(self):
        """Record a new withdrawal."""
        row = self.clear_and_display_header("Record Withdrawal")
        
        # Show current cash balance
        cash_balance = self.portfolio.capital_tracker.get_current_cash()
        self.safe_addstr(row, 0, f"Current cash balance: {cash_balance:,.2f} SEK")
        
        # Get amount
        amount = self.get_numeric_input("Enter withdrawal amount (SEK): ", row + 1, min_val=0.01)
        if not amount:
            return
        
        # Get date (default to today)
        import datetime
        today = datetime.date.today().strftime("%Y-%m-%d")
        self.safe_addstr(row + 2, 0, f"Date (YYYY-MM-DD) [default: {today}]: ")
        self.stdscr.refresh()
        
        curses.echo()
        date_input = self.stdscr.getstr(row + 2, 50, 20).decode('utf-8').strip()
        curses.noecho()
        
        date_str = date_input if date_input else today
        
        # Get description
        description = self.get_user_input("Description (optional): ", row + 3)
        
        # Confirm
        self.safe_addstr(row + 5, 0, f"Record withdrawal of {amount:,.2f} SEK on {date_str}?")
        
        if self.confirm_action("Confirm?", row + 6):
            self.portfolio.capital_tracker.record_withdrawal(amount, date_str, description)
            self.portfolio.capital_tracker.save()
            self.show_message(f"✓ Withdrawal recorded: {amount:,.2f} SEK", row + 8, curses.color_pair(2))
        else:
            self.show_message("Cancelled.", row + 8)
    
    def _show_transaction_history(self):
        """Display transaction history."""
        events = self.portfolio.capital_tracker.events
        
        if not events:
            lines = ["No transactions recorded yet."]
        else:
            lines = []
            lines.append("Date         Type          Stock         Amount          Description")
            lines.append("─" * 80)
            
            for event in reversed(events[-50:]):  # Show last 50
                date_str = event['date']
                event_type = event['type'].capitalize()
                stock = event.get('stock', '-')
                amount = event['amount']
                desc = event.get('description', '')
                
                # Format amount with sign
                if event_type == 'Withdrawal':
                    amount_str = f"-{abs(amount):,.2f}"
                else:
                    amount_str = f"{amount:,.2f}"
                
                lines.append(f"{date_str}  {event_type:<12}  {stock:<12}  {amount_str:>14} SEK  {desc[:30]}")
        
        self.display_scrollable_list("Transaction History", lines)
    
    def _show_returns_analysis(self):
        """Display detailed returns analysis."""
        # Get current values - fetch fresh prices
        stock_prices = self.portfolio.get_stock_prices(include_zero_shares=False)
        
        stock_value_market = 0.0
        stock_value_cost = 0.0
        
        # Try to get market value from prices
        for stock_data in stock_prices:
            stock_value_market += stock_data.get('total_value', 0.0)
        
        # Calculate CORRECT cost basis using FIFO from capital tracker events
        fifo_result = self.portfolio.capital_tracker.get_fifo_cost_basis()
        stock_value_cost = fifo_result['total_cost_basis']
        
        # Use market value if available, otherwise fall back to cost
        stock_value_current = stock_value_market if stock_value_market > 0 else stock_value_cost
        
        cash_balance = self.portfolio.capital_tracker.get_current_cash()
        total_portfolio_value = stock_value_current + cash_balance
        
        # Get returns
        simple_return = self.portfolio.capital_tracker.calculate_simple_return(total_portfolio_value)
        time_weighted_return = self.portfolio.capital_tracker.calculate_time_weighted_return(
            total_portfolio_value,
            self.portfolio  # Pass portfolio for true TWR calculation
        )
        
        lines = []
        lines.append("═" * 70)
        lines.append("RETURNS ANALYSIS")
        lines.append("═" * 70)
        lines.append("")
        lines.append("CURRENT PORTFOLIO VALUE")
        lines.append(f"  Cash Balance:     {cash_balance:>15,.2f} SEK")
        if stock_value_market > 0:
            lines.append(f"  Stock Holdings:   {stock_value_current:>15,.2f} SEK (market value)")
            if stock_value_cost != stock_value_market:
                lines.append(f"  Cost Basis:       {stock_value_cost:>15,.2f} SEK")
                lines.append(f"  Unrealized P/L:   {stock_value_market - stock_value_cost:>15,.2f} SEK")
        else:
            lines.append(f"  Stock Holdings:   {stock_value_current:>15,.2f} SEK (cost basis)")
            lines.append(f"  Note: Using cost basis - prices not loaded")
        lines.append(f"  Total Value:      {total_portfolio_value:>15,.2f} SEK")
        lines.append("")
        lines.append("SIMPLE RETURN (Money-Weighted)")
        lines.append(f"  Current Value:    {simple_return['portfolio_value']:>15,.2f} SEK")
        lines.append(f"  Capital Input:    {simple_return['net_capital']:>15,.2f} SEK")
        lines.append(f"  Gain/Loss:        {simple_return['simple_return_sek']:>15,.2f} SEK")
        lines.append(f"  Return:           {simple_return['simple_return_percent']:>14.2f}%")
        lines.append("")
        lines.append("TIME-WEIGHTED RETURN (Performance-Based)")
        
        # Show calculation method
        calc_method = time_weighted_return.get('calculation_method', 'unknown')
        if calc_method == 'true_twr':
            lines.append(f"  Calculation: True TWR (sub-period geometric linking)")
            num_periods = time_weighted_return.get('num_periods', 0)
            lines.append(f"  Sub-periods analyzed: {num_periods}")
        else:
            lines.append(f"  Calculation: Simple return (fallback)")
        
        total_days = time_weighted_return.get('total_days', 0)
        lines.append(f"  Total Days:             {total_days} days ({total_days/365:.2f} years)")
        lines.append(f"  Total Return:           {time_weighted_return['time_weighted_return_percent']:>14.2f}%")
        lines.append(f"  Annualized Return:      {time_weighted_return['annualized_return_percent']:>14.2f}% per year")
        lines.append("")
        lines.append("INTERPRETATION:")
        lines.append("  - Simple Return: Total gain/loss as % of money invested")
        lines.append("  - Time-Weighted: Adjusts for when money was added")
        lines.append("  - Annualized: Expected yearly return rate")
        lines.append("═" * 70)
        
        self.display_scrollable_list("Returns Analysis", lines)
    
    def _plot_profit_over_time(self):
        """Plot portfolio value and profit over time using matplotlib."""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            from datetime import datetime, timedelta
        except ImportError:
            self.stdscr.clear()
            self.safe_addstr(0, 0, "Error: matplotlib is required for plotting.")
            self.safe_addstr(1, 0, "Install with: pip install matplotlib")
            self.safe_addstr(3, 0, "Press any key to continue...")
            self.stdscr.refresh()
            self.stdscr.getch()
            return
        
        # Show loading message
        self.stdscr.clear()
        self.safe_addstr(0, 0, "Generating profit chart...")
        self.safe_addstr(1, 0, "This may take a moment...")
        self.stdscr.refresh()
        
        # Get all events sorted by date
        events = sorted(self.portfolio.capital_tracker.events, key=lambda e: e['date'])
        
        if not events:
            self.stdscr.clear()
            self.safe_addstr(0, 0, "No transaction data available to plot.")
            self.safe_addstr(2, 0, "Press any key to continue...")
            self.stdscr.refresh()
            self.stdscr.getch()
            return
        
        # Calculate portfolio value at each event date
        dates = []
        capital_input = []  # Net capital added
        portfolio_values = []  # Cash + stocks (at cost)
        realized_profits = []  # Cumulative realized profit only
        
        # Track running values
        cumulative_deposits = 0.0
        cumulative_withdrawals = 0.0
        cumulative_realized = 0.0
        
        for event in events:
            date_obj = datetime.strptime(event['date'], '%Y-%m-%d')
            
            if event['type'] in ['deposit', 'initial_deposit']:
                cumulative_deposits += event['amount']
            elif event['type'] == 'withdrawal':
                cumulative_withdrawals += abs(event['amount'])
            elif event['type'] == 'sell':
                # Note: 'profit' key is used in imported data, 'realized_profit' in new data
                profit = event.get('realized_profit', event.get('profit', 0.0))
                cumulative_realized += profit
            
            # Record state at this point
            dates.append(date_obj)
            net_capital = cumulative_deposits - cumulative_withdrawals
            capital_input.append(net_capital)
            realized_profits.append(cumulative_realized)
        
        # Add today's values (with current market prices if available)
        today = datetime.now()
        fifo_result = self.portfolio.capital_tracker.get_fifo_cost_basis()
        current_cost_basis = fifo_result['total_cost_basis']
        current_cash = self.portfolio.capital_tracker.get_current_cash()
        
        # Try to get market value
        stock_prices = self.portfolio.get_stock_prices(include_zero_shares=False)
        current_market_value = sum(s.get('total_value', 0.0) for s in stock_prices)
        if current_market_value == 0:
            current_market_value = current_cost_basis  # Fallback to cost basis
        
        current_portfolio_value = current_cash + current_market_value
        net_capital = cumulative_deposits - cumulative_withdrawals
        current_unrealized = current_market_value - current_cost_basis
        current_total_profit = cumulative_realized + current_unrealized
        
        dates.append(today)
        capital_input.append(net_capital)
        realized_profits.append(cumulative_realized)
        
        # Create the plot
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        fig.suptitle('Portfolio Performance Over Time', fontsize=16, fontweight='bold')
        
        # Top plot: Capital Input over time
        ax1.plot(dates, capital_input, label='Capital Input (Net)', linewidth=2, color='blue')
        ax1.axhline(y=net_capital, color='blue', linestyle='--', linewidth=1, alpha=0.5)
        ax1.fill_between(dates, 0, capital_input, alpha=0.2, color='blue')
        
        ax1.set_xlabel('Date', fontsize=12)
        ax1.set_ylabel('Capital (SEK)', fontsize=12)
        ax1.set_title('Net Capital Input Over Time', fontsize=14)
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Format y-axis with thousands separator
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
        
        # Bottom plot: Realized Profit over time
        ax2.plot(dates, realized_profits, label='Realized Profit', linewidth=2, color='darkgreen')
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax2.fill_between(dates, 0, realized_profits,
                         where=[p >= 0 for p in realized_profits],
                         alpha=0.3, color='green')
        ax2.fill_between(dates, 0, realized_profits,
                         where=[p < 0 for p in realized_profits],
                         alpha=0.3, color='red')
        
        ax2.set_xlabel('Date', fontsize=12)
        ax2.set_ylabel('Profit/Loss (SEK)', fontsize=12)
        ax2.set_title('Realized Profit Over Time (from completed sales)', fontsize=14)
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax2.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Format y-axis with thousands separator
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
        
        # Add summary text
        summary_text = (
            f"Current Portfolio Value: {current_portfolio_value:,.0f} SEK\n"
            f"Capital Input: {net_capital:,.0f} SEK\n"
            f"Total Profit: {current_total_profit:,.0f} SEK ({(current_total_profit/net_capital*100):.2f}%)\n"
            f"Realized Profit: {cumulative_realized:,.0f} SEK"
        )
        fig.text(0.02, 0.02, summary_text, fontsize=10, verticalalignment='bottom',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        plt.tight_layout()
        
        # Show the plot
        plt.show()
        
        # Show message after plot is closed
        self.stdscr.clear()
        self.safe_addstr(0, 0, "Plot closed. Press any key to continue...")
        self.stdscr.refresh()
        self.stdscr.getch()

    def _plot_total_profit_with_historical(self):
        """Plot total profit (realized + unrealized) and percentage returns using historical market data."""
        try:
            import matplotlib
            # Try to use an interactive backend for displaying plots
            # Check current backend and switch if needed
            current_backend = matplotlib.get_backend()
            if current_backend.lower() == 'agg':
                # Agg is non-interactive, try to switch to an interactive backend
                interactive_backends = ['TkAgg', 'Qt5Agg', 'GTK3Agg', 'WXAgg']
                backend_set = False
                for backend in interactive_backends:
                    try:
                        matplotlib.use(backend)
                        backend_set = True
                        break
                    except:
                        continue
                
                if not backend_set:
                    # If no interactive backend available, inform user
                    self.stdscr.clear()
                    self.safe_addstr(0, 0, "Warning: No interactive display backend available!")
                    self.safe_addstr(2, 0, "Matplotlib cannot display plots in GUI windows.")
                    self.safe_addstr(3, 0, "The plot will be saved to a file instead.")
                    self.safe_addstr(5, 0, "To enable interactive plots:")
                    self.safe_addstr(6, 0, "  1. Install an X server (VcXsrv, Xming, or X410)")
                    self.safe_addstr(7, 0, "  2. Set DISPLAY environment variable")
                    self.safe_addstr(8, 0, "  3. Install python3-tk: sudo apt install python3-tk")
                    self.safe_addstr(10, 0, "Press 's' to save plot to file, or any other key to cancel...")
                    self.stdscr.refresh()
                    
                    key = self.stdscr.getch()
                    if key != ord('s') and key != ord('S'):
                        return
                    
                    # User chose to save, continue with Agg backend
                    save_only = True
                else:
                    save_only = False
            else:
                save_only = False
            
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            from datetime import datetime
            from historical_portfolio_value import load_historical_prices, calculate_daily_portfolio_timeline
        except ImportError as e:
            self.stdscr.clear()
            self.safe_addstr(0, 0, f"Error: Required module not available: {e}")
            self.safe_addstr(1, 0, "Ensure matplotlib and historical_portfolio_value.py are available.")
            self.safe_addstr(3, 0, "Press any key to continue...")
            self.stdscr.refresh()
            self.stdscr.getch()
            return
        
        # Show loading message
        self.stdscr.clear()
        self.safe_addstr(0, 0, "Loading historical market data...")
        self.safe_addstr(1, 0, "This may take a moment...")
        self.stdscr.refresh()
        
        # Load historical prices
        historical_data = load_historical_prices('portfolio/historical_prices.json')
        if historical_data is None:
            self.stdscr.clear()
            self.safe_addstr(0, 0, "Error: Historical price data not found!")
            self.safe_addstr(1, 0, "")
            self.safe_addstr(2, 0, "Please run: python3 fetch_historical_market_data.py")
            self.safe_addstr(3, 0, "")
            self.safe_addstr(4, 0, "This will fetch historical market prices for all stocks.")
            self.safe_addstr(5, 0, "(Data will be saved to portfolio/historical_prices.json)")
            self.safe_addstr(7, 0, "Press any key to continue...")
            self.stdscr.refresh()
            self.stdscr.getch()
            return
        
        # Get all events sorted by date
        events = sorted(self.portfolio.capital_tracker.events, key=lambda e: e['date'])
        
        if not events:
            self.stdscr.clear()
            self.safe_addstr(0, 0, "No transaction data available to plot.")
            self.safe_addstr(2, 0, "Press any key to continue...")
            self.stdscr.refresh()
            self.stdscr.getch()
            return
        
        # Calculate complete timeline with historical market values
        self.stdscr.clear()
        self.safe_addstr(0, 0, "Calculating portfolio values for each day...")
        self.safe_addstr(1, 0, "This may take a moment...")
        self.stdscr.refresh()
        
        try:
            timeline = calculate_daily_portfolio_timeline(events, historical_data)
        except Exception as e:
            self.stdscr.clear()
            self.safe_addstr(0, 0, f"Error calculating timeline: {e}")
            self.safe_addstr(2, 0, "Press any key to continue...")
            self.stdscr.refresh()
            self.stdscr.getch()
            return
        
        if not timeline:
            self.stdscr.clear()
            self.safe_addstr(0, 0, "No timeline data generated.")
            self.safe_addstr(2, 0, "Press any key to continue...")
            self.stdscr.refresh()
            self.stdscr.getch()
            return
        
        # Extract data for plotting
        dates = [datetime.strptime(t['date'], '%Y-%m-%d') for t in timeline]
        capital_input = [t['net_capital'] for t in timeline]
        total_values = [t['total_value'] for t in timeline]
        total_profits = [t['total_profit'] for t in timeline]
        realized_profits = [t['realized_profit'] for t in timeline]
        unrealized_profits = [t['unrealized_profit'] for t in timeline]
        return_pcts = [t['return_pct'] for t in timeline]
        
        # Create figure with 3 subplots
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12))
        fig.suptitle('Portfolio Performance with Historical Market Data', fontsize=16, fontweight='bold')
        
        # ============================================================
        # Panel 1: Portfolio Value vs Capital Input
        # ============================================================
        ax1.plot(dates, capital_input, label='Capital Input', linewidth=2, color='blue', linestyle='--')
        ax1.plot(dates, total_values, label='Portfolio Value', linewidth=2.5, color='darkblue')
        ax1.fill_between(dates, capital_input, total_values,
                         where=[tv >= ci for tv, ci in zip(total_values, capital_input)],
                         alpha=0.3, color='green', label='Gain')
        ax1.fill_between(dates, capital_input, total_values,
                         where=[tv < ci for tv, ci in zip(total_values, capital_input)],
                         alpha=0.3, color='red', label='Loss')
        
        ax1.set_ylabel('Value (SEK)', fontsize=12)
        ax1.set_title('Portfolio Value vs Capital Input', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left', fontsize=10)
        ax1.grid(True, alpha=0.3)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
        
        # ============================================================
        # Panel 2: Total Profit (Realized + Unrealized)
        # ============================================================
        ax2.plot(dates, total_profits, label='Total Profit', linewidth=2.5, color='darkgreen')
        ax2.plot(dates, realized_profits, label='Realized Profit', linewidth=1.5, color='green', linestyle='--', alpha=0.7)
        ax2.plot(dates, unrealized_profits, label='Unrealized Profit', linewidth=1.5, color='orange', linestyle='--', alpha=0.7)
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
        ax2.fill_between(dates, 0, total_profits,
                         where=[p >= 0 for p in total_profits],
                         alpha=0.3, color='green')
        ax2.fill_between(dates, 0, total_profits,
                         where=[p < 0 for p in total_profits],
                         alpha=0.3, color='red')
        
        ax2.set_ylabel('Profit/Loss (SEK)', fontsize=12)
        ax2.set_title('Total Profit Over Time (Realized + Unrealized)', fontsize=14, fontweight='bold')
        ax2.legend(loc='upper left', fontsize=10)
        ax2.grid(True, alpha=0.3)
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
        
        # ============================================================
        # Panel 3: Percentage Return
        # ============================================================
        ax3.plot(dates, return_pcts, label='Return %', linewidth=2.5, color='purple')
        ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
        ax3.fill_between(dates, 0, return_pcts,
                         where=[r >= 0 for r in return_pcts],
                         alpha=0.3, color='green')
        ax3.fill_between(dates, 0, return_pcts,
                         where=[r < 0 for r in return_pcts],
                         alpha=0.3, color='red')
        
        ax3.set_xlabel('Date', fontsize=12)
        ax3.set_ylabel('Return (%)', fontsize=12)
        ax3.set_title('Percentage Return Over Time', fontsize=14, fontweight='bold')
        ax3.legend(loc='upper left', fontsize=10)
        ax3.grid(True, alpha=0.3)
        ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:.2f}%'))
        
        # Format x-axis for all panels
        for ax in [ax1, ax2, ax3]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Add summary text
        last = timeline[-1]
        summary_text = (
            f"Portfolio Value: {last['total_value']:,.0f} SEK  |  "
            f"Capital Input: {last['net_capital']:,.0f} SEK\n"
            f"Total Profit: {last['total_profit']:,.0f} SEK ({last['return_pct']:.2f}%)  |  "
            f"Realized: {last['realized_profit']:,.0f} SEK  |  "
            f"Unrealized: {last['unrealized_profit']:,.0f} SEK"
        )
        fig.text(0.5, 0.02, summary_text, fontsize=10, ha='center',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        plt.tight_layout(rect=[0, 0.04, 1, 1])
        
        # Show or save the plot depending on backend availability
        if save_only:
            # Save to file instead of showing
            import os
            import tempfile
            from datetime import datetime
            
            # Create output filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(self.portfolio.path, 'plots')
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f'portfolio_performance_{timestamp}.png')
            
            try:
                plt.savefig(output_file, dpi=150, bbox_inches='tight')
                plt.close()
                
                self.stdscr.clear()
                self.safe_addstr(0, 0, "✓ Plot saved successfully!")
                self.safe_addstr(2, 0, f"Location: {output_file}")
                self.safe_addstr(4, 0, "You can open this file with any image viewer.")
                self.safe_addstr(6, 0, "Press any key to continue...")
                self.stdscr.refresh()
                self.stdscr.getch()
            except Exception as e:
                plt.close()
                self.stdscr.clear()
                self.safe_addstr(0, 0, f"Error saving plot: {e}")
                self.safe_addstr(2, 0, "Press any key to continue...")
                self.stdscr.refresh()
                self.stdscr.getch()
        else:
            # Try to show the plot interactively
            try:
                plt.show()
                
                # Show message after plot is closed
                self.stdscr.clear()
                self.safe_addstr(0, 0, "Plot closed. Press any key to continue...")
                self.stdscr.refresh()
                self.stdscr.getch()
            except Exception as e:
                # If showing fails, offer to save instead
                plt.close()
                self.stdscr.clear()
                self.safe_addstr(0, 0, f"Error displaying plot: {e}")
                self.safe_addstr(2, 0, "Would you like to save the plot to a file instead? (y/n)")
                self.stdscr.refresh()
                
                key = self.stdscr.getch()
                if key == ord('y') or key == ord('Y'):
                    import os
                    from datetime import datetime
                    
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_dir = os.path.join(self.portfolio.path, 'plots')
                    os.makedirs(output_dir, exist_ok=True)
                    output_file = os.path.join(output_dir, f'portfolio_performance_{timestamp}.png')
                    
                    # Recreate the plot (since we closed it)
                    # ... (would need to refactor to avoid duplication, but for now just inform user)
                    self.stdscr.clear()
                    self.safe_addstr(0, 0, "Plot was closed. Please run the command again and choose save.")
                    self.safe_addstr(2, 0, "Press any key to continue...")
                    self.stdscr.refresh()
                    self.stdscr.getch()


