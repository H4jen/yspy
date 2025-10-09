#!/usr/bin/env python3
"""
yspy - Main Application Class

Provides the main application loop, menu system, and command handling
for the terminal-based stock portfolio management application.

Project: https://github.com/H4jen/yspy
"""

import curses
import logging
import os
import sys
from typing import Dict, Callable

from src.app_config import config
from src.portfolio_manager import Portfolio, HistoricalMode
from src.menu_handlers import (
    AddStockHandler, RemoveStockHandler, ListStocksHandler, ListSharesHandler,
    BuySharesHandler, SellSharesHandler, WatchStocksHandler, 
    ProfitPerStockHandler, AllProfitsHandler, CapitalManagementHandler
)
from src.correlation_analysis import CorrelationUIHandler

# Optional short selling support
try:
    from short_selling.short_selling_menu import ShortSellingHandler
    SHORT_SELLING_AVAILABLE = True
except ImportError:
    SHORT_SELLING_AVAILABLE = False


class StockPortfolioApp:
    """Main application class for the Stock Portfolio ncurses application."""
    
    def __init__(self):
        self.stdscr = None
        self.portfolio = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self.menu_handlers: Dict[str, Callable] = {}
        self.ai_window = None  # AI chat window instance
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up logging configuration for file output only."""
        # Configure root logger for file output to avoid ncurses interference
        root_logger = logging.getLogger()
        
        # Remove console handlers but keep file handlers
        handlers_to_remove = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler) and h.stream.name == '<stdout>']
        for handler in handlers_to_remove:
            root_logger.removeHandler(handler)
        
        # Add file handler if not present
        if not root_logger.handlers:
            file_handler = logging.FileHandler('yspy.log')
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            root_logger.addHandler(file_handler)
            root_logger.setLevel(logging.INFO)
    
    def _initialize_curses(self, stdscr):
        """Initialize curses settings and colors."""
        self.stdscr = stdscr
        
        # Initialize colors
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)  # Green
        curses.init_pair(2, curses.COLOR_RED, -1)    # Red
        curses.init_pair(3, curses.COLOR_YELLOW, -1) # Yellow
        
        # Clear screen and hide cursor
        stdscr.clear()
        curses.curs_set(0)
        
        # Set a reasonable timeout for responsive UI
        stdscr.timeout(500)  # 500ms timeout for responsive UI
        
        self.logger.info("Curses initialized successfully")
    
    def _initialize_portfolio(self):
        """Initialize the portfolio with proper directory setup."""
        try:
            # Get portfolio path (config handles finding project root)
            portfolio_path = config.get_portfolio_path()
            
            # Check if portfolio directory is missing
            if not os.path.isdir(portfolio_path):
                os.makedirs(portfolio_path, exist_ok=True)
                self.logger.info(f"Created portfolio directory: {portfolio_path}")
            
            # Show startup message
            if self.stdscr:
                self.stdscr.clear()
                self.stdscr.addstr(0, 0, "Initializing Stock Portfolio...")
                self.stdscr.addstr(1, 0, "Loading portfolio data...")
                self.stdscr.refresh()
            
            # Suppress warnings during startup to avoid cluttering the display
            import warnings
            warnings.filterwarnings('ignore', category=FutureWarning)
            
            # Initialize portfolio
            self.portfolio = Portfolio(
                path=portfolio_path,
                filename=config.PORTFOLIO_FILENAME,
                historical_mode=HistoricalMode.BACKGROUND,  # Load historical data in background
                verbose=False,  # Quiet startup for UI
                allow_online_currency_lookup=True
            )
            
            self.logger.info(f"Portfolio initialized with {len(self.portfolio.stocks)} stocks")
            
            # Update historical market prices (differential - only fetches missing days)
            if self.stdscr:
                self.stdscr.addstr(2, 0, "Checking historical market prices...")
                self.stdscr.refresh()
            
            try:
                from update_historical_prices import update_historical_prices_differential
                updated = update_historical_prices_differential()
                if updated:
                    self.logger.info("Historical market prices updated with new data")
                else:
                    self.logger.info("Historical market prices already current")
            except Exception as e:
                self.logger.warning(f"Could not update historical market prices: {e}")
            
            # Force immediate refresh of real-time prices and historical data
            if self.stdscr:
                self.stdscr.addstr(3, 0, f"Refreshing data for {len(self.portfolio.stocks)} stocks...")
                self.stdscr.refresh()
            
            # Trigger immediate real-time price update
            try:
                self.portfolio.real_time_manager._bulk_update()
                self.logger.info("Real-time prices refreshed at startup")
            except Exception as e:
                self.logger.warning(f"Failed to refresh real-time prices at startup: {e}")
            
            # Trigger immediate historical data check and refresh if needed
            try:
                tickers = [stock.ticker for stock in self.portfolio.stocks.values()]
                if tickers:
                    # Force check for stale historical data
                    stale_count = 0
                    for ticker in tickers:
                        if self.portfolio.historical_manager.is_historical_data_stale(ticker):
                            stale_count += 1
                    
                    if stale_count > 0:
                        self.logger.info(f"Found {stale_count} stocks with stale historical data, triggering refresh")
                        if self.stdscr:
                            self.stdscr.addstr(4, 0, f"Updating historical data ({stale_count} stocks need refresh)...")
                            self.stdscr.refresh()
                        
                        # The background thread will handle the actual refresh
                        # Force a check cycle now
                        self.portfolio._perform_initial_data_quality_check()
                    else:
                        self.logger.info("All historical data is fresh")
                        if self.stdscr:
                            self.stdscr.addstr(4, 0, "Historical data is up to date")
                            self.stdscr.refresh()
            except Exception as e:
                self.logger.warning(f"Failed to check historical data at startup: {e}")
            
            # Update short selling data if the feature is available
            if SHORT_SELLING_AVAILABLE:
                try:
                    if self.stdscr:
                        self.stdscr.addstr(4, 0, "Updating short selling data...")
                        self.stdscr.refresh()
                    
                    from short_selling.short_selling_integration import ShortSellingIntegration
                    short_integration = ShortSellingIntegration(self.portfolio)
                    
                    # Update short selling data in background
                    update_success = short_integration.update_short_data()
                    
                    if update_success:
                        self.logger.info("Short selling data updated successfully")
                        if self.stdscr:
                            self.stdscr.addstr(4, 0, "Short selling data updated              ")
                            self.stdscr.refresh()
                    else:
                        self.logger.info("Short selling data was already current")
                        if self.stdscr:
                            self.stdscr.addstr(4, 0, "Short selling data current              ")
                            self.stdscr.refresh()
                            
                except Exception as e:
                    self.logger.warning(f"Failed to update short selling data: {e}")
                    if self.stdscr:
                        self.stdscr.addstr(4, 0, "Short selling update failed             ")
                        self.stdscr.refresh()
            
            # Warm up the cache for watch screen by pre-computing historical data
            # This makes entering watch screen (pressing 7) nearly instant
            try:
                if self.stdscr:
                    self.stdscr.addstr(4, 0, "Preparing watch screen cache...")
                    self.stdscr.refresh()
                
                # Pre-compute stock prices with historical data to warm the cache
                # This is the same call that watch screen makes, so it populates the cache
                _ = self.portfolio.get_stock_prices(include_zero_shares=True, compute_history=True)
                
                self.logger.info("Watch screen cache warmed - watch screen will load instantly")
                if self.stdscr:
                    self.stdscr.addstr(4, 0, "Watch screen ready (cache warmed)            ")
                    self.stdscr.refresh()
            except Exception as e:
                self.logger.warning(f"Failed to warm watch screen cache: {e}")
            
            # Brief pause to show the message
            if self.stdscr:
                self.stdscr.addstr(6, 0, "Ready! Press any key to continue...")
                self.stdscr.refresh()
                self.stdscr.timeout(-1)  # Wait indefinitely for key
                self.stdscr.getch()
                self.stdscr.timeout(500)  # Restore timeout
                # Clear the startup messages before entering main menu
                self.stdscr.clear()
                self.stdscr.refresh()
            
        except Exception as e:
            self.logger.error(f"Failed to initialize portfolio: {e}")
            raise
    
    def _launch_ai_window(self):
        """Launch AI chat window if available and enabled in config."""
        # Check if AI assistant is enabled in configuration
        if not config.ENABLE_AI_ASSISTANT:
            self.logger.info("AI assistant disabled in configuration (ENABLE_AI_ASSISTANT=False)")
            return
            
        try:
            from ai_gui.ai_chat_window import launch_ai_chat_window
            
            self.logger.info("Launching AI chat window...")
            self.ai_window = launch_ai_chat_window(self.portfolio)
            
            if self.ai_window:
                self.logger.info("AI chat window launched successfully")
            else:
                self.logger.info("AI chat window not available")
                
        except ImportError:
            self.logger.info("AI chat window module not available")
        except Exception as e:
            self.logger.warning(f"Failed to launch AI chat window: {e}")
            # Don't fail the app if AI window fails
            pass
            raise
    
    def _setup_menu_handlers(self):
        """Set up menu handlers mapping."""
        self.menu_handlers = {
            '1': lambda: ListStocksHandler(self.stdscr, self.portfolio).handle(),
            '2': lambda: AddStockHandler(self.stdscr, self.portfolio).handle(),
            '3': lambda: RemoveStockHandler(self.stdscr, self.portfolio).handle(),
            '4': lambda: ListSharesHandler(self.stdscr, self.portfolio).handle(),
            '5': lambda: BuySharesHandler(self.stdscr, self.portfolio).handle(),
            '6': lambda: SellSharesHandler(self.stdscr, self.portfolio).handle(),
            '7': lambda: WatchStocksHandler(self.stdscr, self.portfolio).handle(),
            '8': lambda: ProfitPerStockHandler(self.stdscr, self.portfolio).handle(),
            '9': lambda: AllProfitsHandler(self.stdscr, self.portfolio).handle(),
            'a': lambda: CapitalManagementHandler(self.stdscr, self.portfolio).handle(),
            'A': lambda: CapitalManagementHandler(self.stdscr, self.portfolio).handle(),
            'c': lambda: CorrelationUIHandler(self.stdscr, self.portfolio).handle(),
            'C': lambda: CorrelationUIHandler(self.stdscr, self.portfolio).handle(),
        }
        
        # Add AI assistant menu
        try:
            from ai_gui.ai_menu_handler import AIAssistantHandler
            self.menu_handlers['i'] = lambda: AIAssistantHandler(self.stdscr, self.portfolio).handle()
            self.menu_handlers['I'] = lambda: AIAssistantHandler(self.stdscr, self.portfolio).handle()
        except ImportError:
            pass  # AI assistant not available
        
        # Add short selling menu if available
        if SHORT_SELLING_AVAILABLE:
            self.menu_handlers['s'] = lambda: ShortSellingHandler(self.stdscr, self.portfolio).handle()
            self.menu_handlers['S'] = lambda: ShortSellingHandler(self.stdscr, self.portfolio).handle()
    
    def _display_main_menu(self):
        """Display the main menu."""
        self.stdscr.clear()
        self.stdscr.addstr(0, 0, config.MENU_TITLE)
        self.stdscr.addstr(1, 0, "1. List Stocks")
        self.stdscr.addstr(2, 0, "2. Add Stock")
        self.stdscr.addstr(3, 0, "3. Remove Stock")
        self.stdscr.addstr(4, 0, "4. List Shares")
        self.stdscr.addstr(5, 0, "5. Buy Shares")
        self.stdscr.addstr(6, 0, "6. Sell Shares")
        self.stdscr.addstr(7, 0, f"7. Watch Stocks (refresh {int(config.REFRESH_INTERVAL_SECONDS)}s)")
        self.stdscr.addstr(8, 0, "8. Profit per Stock")
        self.stdscr.addstr(9, 0, "9. All Profits")
        self.stdscr.addstr(10, 0, "0. Exit")
        self.stdscr.addstr(11, 0, "a. Capital Management")
        self.stdscr.addstr(12, 0, "c. Correlation Analysis")
        
        # Add short selling menu if available
        menu_row = 13
        if SHORT_SELLING_AVAILABLE:
            self.stdscr.addstr(menu_row, 0, "s. Short Selling Analysis")
            menu_row += 1
        
        # Show AI assistant status if available
        if self.ai_window:
            self.stdscr.addstr(menu_row, 0, "🤖 AI Assistant: Running in separate window", curses.A_DIM)
            menu_row += 1
        
        # Note: AI menu handler ('i') is still available for fallback
        # but we don't show it since GUI window is preferred
            
        self.stdscr.addstr(menu_row, 0, "Select an option: ")
        self.stdscr.refresh()
    
    def _handle_menu_selection(self, key: int) -> bool:
        """Handle menu selection and return True if should continue, False to exit."""
        key_char = chr(key) if 32 <= key <= 126 else None
        
        try:
            if key == ord('0'):
                return False  # Exit
            elif key_char in self.menu_handlers:
                self.logger.info(f"Executing menu option: {key_char}")
                self.menu_handlers[key_char]()
                return True
            else:
                # Invalid key, just continue
                import time
                time.sleep(0.1)
                return True
                
        except KeyboardInterrupt:
            # User pressed Ctrl+C during a handler
            return True
        except Exception as e:
            self.logger.error(f"Error handling menu selection '{key_char}': {e}")
            self._show_error_message(f"Error: {str(e)}")
            return True
    
    def _show_error_message(self, message: str):
        """Show an error message to the user."""
        self.stdscr.clear()
        self.stdscr.addstr(0, 0, "ERROR")
        self.stdscr.addstr(1, 0, "-" * 40)
        
        # Break long messages into multiple lines
        max_width = curses.COLS - 1
        lines = []
        words = message.split()
        current_line = ""
        
        for word in words:
            if len(current_line + " " + word) <= max_width:
                current_line += " " + word if current_line else word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        for i, line in enumerate(lines[:10]):  # Limit to 10 lines
            self.stdscr.addstr(3 + i, 0, line)
        
        self.stdscr.addstr(min(15, curses.LINES - 2), 0, "Press any key to continue...")
        self.stdscr.refresh()
        self.stdscr.getch()
    
    def _main_loop(self):
        """Main application loop."""
        self.logger.info("Starting main application loop")
        
        # Display menu once initially
        self._display_main_menu()
        
        while True:
            try:
                key = self.stdscr.getch()
                
                # Handle timeout (getch returns -1 when no key is pressed within timeout)
                if key == -1:
                    continue  # No key pressed, just wait for next input
                
                # Key was pressed, handle it
                if not self._handle_menu_selection(key):
                    break
                
                # Redisplay menu after handling selection
                self._display_main_menu()
                    
            except KeyboardInterrupt:
                # User pressed Ctrl+C in main menu
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}")
                self._show_error_message(f"Unexpected error: {str(e)}")
                # Redisplay menu after error
                self._display_main_menu()
    
    def run(self, stdscr):
        """Main entry point for the application."""
        try:
            self._initialize_curses(stdscr)
            self._initialize_portfolio()
            self._setup_menu_handlers()
            
            # Launch AI chat window if available
            self._launch_ai_window()
            
            self._main_loop()
            
        except Exception as e:
            self.logger.error(f"Critical error in application: {e}")
            # Try to show error in curses if possible
            try:
                self._show_error_message(f"Critical error: {str(e)}")
            except:
                # If curses fails, fall back to print
                print(f"Critical error: {str(e)}")
        
        finally:
            # Clean up AI window
            if self.ai_window:
                self.ai_window.stop()
            self.logger.info("Application shutting down")
    
    @classmethod
    def main(cls):
        """Class method to run the application with curses wrapper."""
        app = cls()
        try:
            curses.wrapper(app.run)
        except Exception as e:
            print(f"Failed to start application: {e}")
            logging.error(f"Failed to start application: {e}")
            sys.exit(1)


def main():
    """Entry point for the application."""
    StockPortfolioApp.main()


if __name__ == "__main__":
    main()