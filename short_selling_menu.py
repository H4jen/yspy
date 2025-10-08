#!/usr/bin/env python3
"""
Short Selling Menu Handler for yspy

Provides a dedicated menu interface for viewing and managing short selling data.
"""

import curses
import logging
from typing import List, Dict, Optional
from ui_handlers import ScrollableUIHandler

logger = logging.getLogger(__name__)

class ShortSellingHandler(ScrollableUIHandler):
    """Handler for short selling analysis menu."""
    
    def __init__(self, stdscr, portfolio):
        super().__init__(stdscr, portfolio)
        self.short_integration = None
        self._initialize_short_integration()
    
    def _initialize_short_integration(self):
        """Initialize short selling integration."""
        try:
            from short_selling_integration import ShortSellingIntegration
            self.short_integration = ShortSellingIntegration(self.portfolio)
        except ImportError:
            logger.warning("Short selling integration not available")
        except Exception as e:
            logger.error(f"Error initializing short selling integration: {e}")
            self.short_integration = None
    
    def handle(self) -> None:
        """Handle the short selling analysis menu."""
        # Always show the menu, even if integration is not fully available
        while True:
            self.stdscr.clear()
            self.safe_addstr(0, 0, "═" * 70)
            self.safe_addstr(1, 0, "SHORT SELLING ANALYSIS")
            self.safe_addstr(2, 0, "═" * 70)
            
            # Show status indicator
            if self.short_integration and self.short_integration.short_tracker:
                self.safe_addstr(3, 0, "Status: ✅ Available", curses.color_pair(1))
            else:
                self.safe_addstr(3, 0, "Status: ⚠️  Limited (Framework Only)", curses.color_pair(3))
                
            self.safe_addstr(5, 0, "1. Portfolio Short Selling Summary")
            self.safe_addstr(6, 0, "2. Individual Stock Short Data")
            self.safe_addstr(7, 0, "3. Update Short Selling Data")
            self.safe_addstr(8, 0, "4. High Short Interest Alerts")
            self.safe_addstr(9, 0, "5. Short Selling Trends")
            self.safe_addstr(10, 0, "0. Back to Main Menu")
            self.safe_addstr(12, 0, "Select an option: ")
            self.stdscr.refresh()
            
            key = self.stdscr.getch()
            
            if key == ord('1'):
                self._show_portfolio_summary()
            elif key == ord('2'):
                self._show_individual_stock_data()
            elif key == ord('3'):
                self._update_short_data()
            elif key == ord('4'):
                self._show_high_short_alerts()
            elif key == ord('5'):
                self._show_short_trends()
            elif key == ord('0') or key == 27:  # 0 or ESC
                return
    
    def _show_unavailable_message(self):
        """Show message when short selling integration is not available."""
        self.stdscr.clear()
        self.safe_addstr(0, 0, "═" * 70)
        self.safe_addstr(1, 0, "SHORT SELLING ANALYSIS - NOT AVAILABLE")
        self.safe_addstr(2, 0, "═" * 70)
        self.safe_addstr(4, 0, "Short selling tracking is not yet implemented.")
        self.safe_addstr(6, 0, "This feature requires:")
        self.safe_addstr(7, 0, "• Integration with Nordic regulatory APIs")
        self.safe_addstr(8, 0, "• Access to Finansinspektionen data (Sweden)")
        self.safe_addstr(9, 0, "• Access to Finanssivalvonta data (Finland)")
        self.safe_addstr(11, 0, "Press any key to return...")
        self.stdscr.refresh()
        self.stdscr.getch()
    
    def _show_portfolio_summary(self):
        """Show portfolio-wide short selling summary."""
        self.stdscr.clear()
        row = self.clear_and_display_header("Portfolio Short Selling Summary")
        
        self.safe_addstr(row, 0, "Loading short selling data...")
        self.stdscr.refresh()
        
        try:
            summary = self.short_integration.get_portfolio_short_summary()
            
            lines = []
            lines.append("Portfolio Short Selling Summary")
            lines.append("=" * 50)
            lines.append("")
            
            if 'error' in summary:
                lines.append(f"Error: {summary['error']}")
                lines.append("")
                lines.append("To enable short selling tracking:")
                lines.append("1. Run: python3 short_selling_tracker.py --update")
                lines.append("2. Wait for data to be fetched from regulatory sources")
            else:
                lines.append(f"Last Updated: {summary.get('last_updated', 'Unknown')}")
                lines.append(f"Total Stocks Tracked: {summary.get('total_stocks_tracked', 0)}")
                lines.append(f"Stocks with Short Data: {summary.get('stocks_with_short_data', 0)}")
                lines.append(f"Stocks with Alternative Data: {summary.get('stocks_with_alternative_data', 0)}")
                lines.append("")
                
                # Show all portfolio short positions
                portfolio_shorts = summary.get('portfolio_short_positions', [])
                if portfolio_shorts:
                    lines.append(f"📈 PORTFOLIO SHORT POSITIONS ({len(portfolio_shorts)})")
                    lines.append("-" * 50)
                    for stock in portfolio_shorts[:20]:  # Limit to first 20
                        lines.append(f"{stock['ticker']:15} {stock['percentage']:5.2f}%  {stock['company']}")
                    if len(portfolio_shorts) > 20:
                        lines.append(f"... and {len(portfolio_shorts) - 20} more")
                    lines.append("")
                
                # Show high short interest stocks
                high_short_stocks = summary.get('high_short_interest_stocks', [])
                if high_short_stocks:
                    lines.append("⚠️  HIGH SHORT INTEREST STOCKS (>5%)")
                    lines.append("-" * 50)
                    for stock in high_short_stocks:
                        lines.append(f"{stock['ticker']:15} {stock['percentage']:5.2f}%  {stock['company']}")
                else:
                    lines.append("✅ No high short interest alerts")
            
            self.display_scrollable_list("Short Selling Summary", lines)
            
        except Exception as e:
            self.show_message(f"Error loading short data: {e}", row + 2)
    
    def _show_individual_stock_data(self):
        """Show short selling data for individual stocks."""
        row = self.clear_and_display_header("Individual Stock Short Data")
        
        # Get stock selection
        if not self.portfolio.stocks:
            self.show_message("No stocks in portfolio.", row)
            return
        
        # Display available stocks
        self.safe_addstr(row, 0, "Select a stock to view short selling data:")
        row += 1
        
        stock_list = list(self.portfolio.stocks.keys())
        for i, ticker in enumerate(stock_list):
            self.safe_addstr(row + i, 0, f"{i+1}. {ticker}")
        
        # Get selection
        choice = self.get_numeric_input(
            "Enter stock number (or 0 to cancel): ", 
            row + len(stock_list) + 1, 
            min_val=0, 
            max_val=len(stock_list)
        )
        
        if not choice or choice == 0:
            return
        
        selected_ticker = stock_list[choice - 1]
        self._display_stock_short_data(selected_ticker)
    
    def _display_stock_short_data(self, ticker: str):
        """Display short selling data for a specific stock."""
        self.stdscr.clear()
        row = self.clear_and_display_header(f"Short Data - {ticker}")
        
        try:
            # Get the actual ticker symbol for the stock
            stock_obj = self.portfolio.stocks.get(ticker)
            if not stock_obj:
                self.show_message(f"Stock {ticker} not found in portfolio", row)
                return
            
            actual_ticker = stock_obj.ticker
            short_data = self.short_integration.get_stock_short_data(actual_ticker)
            
            lines = []
            lines.append(f"Short Selling Data for {ticker} ({actual_ticker})")
            lines.append("=" * 50)
            lines.append("")
            
            if not short_data:
                lines.append("No short selling data available for this stock.")
                lines.append("")
                lines.append("Possible reasons:")
                lines.append("• No significant short positions (below disclosure threshold)")
                lines.append("• Data not yet fetched from regulatory sources")
                lines.append("• Stock not actively shorted")
            else:
                data_type = short_data['type']
                data = short_data['data']
                
                lines.append(f"Data Type: {data_type.title()}")
                lines.append("")
                
                if data_type == 'official':
                    lines.append("📊 Official Regulatory Data")
                    lines.append("-" * 30)
                    lines.append(f"Position Holder: {data.get('position_holder', 'N/A')}")
                    lines.append(f"Position Percentage: {data.get('position_percentage', 0):.2f}%")
                    lines.append(f"Position Date: {data.get('position_date', 'N/A')}")
                    lines.append(f"Market: {data.get('market', 'N/A')}")
                elif data_type == 'alternative':
                    lines.append("📈 Alternative Data Source")
                    lines.append("-" * 30)
                    if 'short_ratio' in data and data['short_ratio']:
                        lines.append(f"Short Ratio: {data['short_ratio']:.2f}")
                    if 'short_percent_of_float' in data and data['short_percent_of_float']:
                        lines.append(f"Short % of Float: {data['short_percent_of_float']:.2f}%")
                    lines.append(f"Last Updated: {data.get('last_updated', 'N/A')}")
            
            self.display_scrollable_list(f"Short Data - {ticker}", lines)
            
        except Exception as e:
            self.show_message(f"Error loading short data: {e}", row + 2)
    
    def _update_short_data(self):
        """Update short selling data from all sources."""
        row = self.clear_and_display_header("Update Short Selling Data")
        
        self.safe_addstr(row, 0, "Updating short selling data from regulatory sources...")
        self.safe_addstr(row + 1, 0, "This may take a few moments...")
        self.stdscr.refresh()
        
        try:
            success = self.short_integration.update_short_data()
            
            if success:
                self.safe_addstr(row + 3, 0, "✅ Short selling data updated successfully!", curses.color_pair(1))
                self.safe_addstr(row + 4, 0, "")
                self.safe_addstr(row + 5, 0, "Updated data includes:")
                self.safe_addstr(row + 6, 0, "• Finansinspektionen (Swedish FSA) positions")
                self.safe_addstr(row + 7, 0, "• Finanssivalvonta (Finnish FSA) positions") 
                self.safe_addstr(row + 8, 0, "• Alternative data sources")
            else:
                self.safe_addstr(row + 3, 0, "❌ Failed to update short selling data", curses.color_pair(2))
                self.safe_addstr(row + 4, 0, "")
                self.safe_addstr(row + 5, 0, "Possible issues:")
                self.safe_addstr(row + 6, 0, "• Network connectivity problems")
                self.safe_addstr(row + 7, 0, "• Regulatory data sources unavailable")
                self.safe_addstr(row + 8, 0, "• API rate limits or access restrictions")
            
            self.safe_addstr(row + 10, 0, "Press any key to continue...")
            self.stdscr.refresh()
            self.stdscr.getch()
            
        except Exception as e:
            self.show_message(f"Error updating short data: {e}", row + 3)
    
    def _show_high_short_alerts(self):
        """Show stocks with high short interest."""
        self.stdscr.clear()
        row = self.clear_and_display_header("High Short Interest Alerts")
        
        try:
            summary = self.short_integration.get_portfolio_short_summary()
            
            lines = []
            lines.append("High Short Interest Alerts (>10%)")
            lines.append("=" * 50)
            lines.append("")
            
            if 'error' in summary:
                lines.append(f"Error: {summary['error']}")
            else:
                high_short_stocks = summary.get('high_short_interest_stocks', [])
                
                if not high_short_stocks:
                    lines.append("✅ No high short interest alerts")
                    lines.append("")
                    lines.append("All portfolio stocks have short interest below 10%")
                    lines.append("or no reported short positions.")
                else:
                    lines.append("⚠️  The following stocks have high short interest:")
                    lines.append("")
                    
                    for stock in high_short_stocks:
                        lines.append(f"🔴 {stock['ticker']}")
                        lines.append(f"   Short Interest: {stock['percentage']:.1f}%")
                        lines.append(f"   Position Holder: {stock['holder']}")
                        lines.append("")
                    
                    lines.append("High short interest may indicate:")
                    lines.append("• Bearish sentiment from institutional investors")
                    lines.append("• Potential short squeeze opportunities")
                    lines.append("• Increased volatility risk")
            
            self.display_scrollable_list("High Short Interest", lines)
            
        except Exception as e:
            self.show_message(f"Error loading alerts: {e}", row + 2)
    
    def _show_short_trends(self):
        """Show short selling trends (placeholder for future implementation)."""
        self.stdscr.clear()
        row = self.clear_and_display_header("Short Selling Trends")
        
        lines = []
        lines.append("Short Selling Trends Analysis")
        lines.append("=" * 50)
        lines.append("")
        lines.append("🚧 This feature is under development")
        lines.append("")
        lines.append("Planned features:")
        lines.append("• Historical short interest tracking")
        lines.append("• Trend analysis and charts")
        lines.append("• Short squeeze probability indicators")
        lines.append("• Correlation with stock performance")
        lines.append("• Nordic market short selling patterns")
        
        self.display_scrollable_list("Short Trends", lines)