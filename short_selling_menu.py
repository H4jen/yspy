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
            self.safe_addstr(10, 0, "6. Position Holders Analysis")
            self.safe_addstr(11, 0, "7. All Portfolio Stocks Short Data")
            self.safe_addstr(12, 0, "0. Back to Main Menu")
            self.safe_addstr(14, 0, "Select an option: ")
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
            elif key == ord('6'):
                self._show_position_holders()
            elif key == ord('7'):
                self._show_all_portfolio_shorts()
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
                
                # Filter portfolio short positions to only show stocks we own
                portfolio_shorts = summary.get('portfolio_short_positions', [])
                owned_shorts = []
                
                for stock in portfolio_shorts:
                    ticker = stock['ticker']
                    # Find the stock name in portfolio by ticker
                    stock_name = None
                    for name, stock_obj in self.portfolio.stocks.items():
                        if stock_obj.ticker == ticker:
                            stock_name = name
                            break
                    
                    # Only include if we own shares (using get_total_shares method)
                    if stock_name:
                        total_shares = self.portfolio.stocks[stock_name].get_total_shares()
                        if total_shares > 0:
                            owned_shorts.append(stock)
                
                if owned_shorts:
                    lines.append(f"📈 YOUR PORTFOLIO SHORT POSITIONS ({len(owned_shorts)} stocks owned)")
                    lines.append("-" * 50)
                    for stock in owned_shorts[:20]:  # Limit to first 20
                        lines.append(f"{stock['ticker']:15} {stock['percentage']:5.2f}%  {stock['company']}")
                    if len(owned_shorts) > 20:
                        lines.append(f"... and {len(owned_shorts) - 20} more")
                else:
                    lines.append("📈 YOUR PORTFOLIO SHORT POSITIONS (0 stocks owned)")
                    lines.append("-" * 50)
                    lines.append("None of your currently owned stocks have reported short positions.")
                lines.append("")
                
                # Filter high short interest stocks to only show stocks we own
                high_short_stocks = summary.get('high_short_interest_stocks', [])
                owned_high_shorts = []
                
                for stock in high_short_stocks:
                    ticker = stock['ticker']
                    stock_name = None
                    for name, stock_obj in self.portfolio.stocks.items():
                        if stock_obj.ticker == ticker:
                            stock_name = name
                            break
                    
                    if stock_name:
                        total_shares = self.portfolio.stocks[stock_name].get_total_shares()
                        if total_shares > 0:
                            owned_high_shorts.append(stock)
                
                if owned_high_shorts:
                    lines.append("⚠️  HIGH SHORT INTEREST ALERTS (>5% in owned stocks)")
                    lines.append("-" * 50)
                    for stock in owned_high_shorts:
                        lines.append(f"{stock['ticker']:15} {stock['percentage']:5.2f}%  {stock['company']}")
                else:
                    lines.append("✅ No high short interest alerts in owned stocks")
            
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
            max_val=len(stock_list),
            integer_only=True
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
                    lines.append("-" * 50)
                    lines.append(f"Company: {data.get('company_name', 'N/A')}")
                    lines.append(f"Market: {data.get('market', 'N/A')}")
                    lines.append(f"Total Short Position: {data.get('short_percentage', 0):.2f}%")
                    lines.append(f"Position Date: {data.get('position_date', 'N/A')}")
                    lines.append(f"Reporting Threshold: {data.get('threshold_crossed', '0.5%')}")
                    
                    # Add risk indicator based on short percentage
                    short_pct = data.get('short_percentage', 0)
                    if short_pct > 10:
                        risk_level = "🔴 VERY HIGH"
                        risk_desc = "Extremely high short interest - major bearish pressure"
                    elif short_pct > 5:
                        risk_level = "🟠 HIGH"
                        risk_desc = "High short interest - significant bearish sentiment"
                    elif short_pct > 2:
                        risk_level = "🟡 MODERATE"
                        risk_desc = "Moderate short interest - some bearish sentiment"
                    else:
                        risk_level = "🟢 LOW"
                        risk_desc = "Low short interest - minimal bearish pressure"
                    
                    lines.append("")
                    lines.append(f"Risk Level: {risk_level}")
                    lines.append(f"Assessment: {risk_desc}")
                    
                    # Show match quality if available
                    if 'match_quality' in data:
                        quality = data['match_quality']
                        score = data.get('match_score', 0)
                        lines.append(f"Data Match Quality: {quality.title()} (score: {score})")
                    
                    # Show individual holders if available
                    individual_holders = data.get('individual_holders', [])
                    if individual_holders:
                        lines.append("")
                        lines.append(f"📋 Individual Position Holders ({len(individual_holders)}):")
                        lines.append("-" * 50)
                        
                        # Calculate total from individual holders for verification
                        total_from_holders = sum(h.get('position_percentage', 0) for h in individual_holders)
                        
                        for i, holder in enumerate(individual_holders[:15], 1):  # Show top 15
                            holder_name = holder.get('holder_name', 'Unknown')
                            holder_pct = holder.get('position_percentage', 0)
                            holder_date = holder.get('position_date', 'N/A')
                            
                            # Calculate percentage of total short position
                            pct_of_total = (holder_pct / short_pct * 100) if short_pct > 0 else 0
                            
                            lines.append(f"{i:2}. {holder_name:40} {holder_pct:5.2f}% ({pct_of_total:4.1f}% of total)")
                        
                        if len(individual_holders) > 15:
                            remaining = len(individual_holders) - 15
                            remaining_pct = sum(h.get('position_percentage', 0) for h in individual_holders[15:])
                            lines.append(f"    ... and {remaining} more holders totaling {remaining_pct:.2f}%")
                        
                        lines.append("")
                        lines.append(f"Note: Individual positions shown are from current reporting (>0.5%)")
                        lines.append(f"      Total may include historical positions still counted in aggregate.")
                    else:
                        lines.append("")
                        lines.append(f"Summary: {data.get('position_holder', 'Multiple holders')}")
                        lines.append("")
                        lines.append("Individual holder details not available for this position.")
                        lines.append("This may be due to:")
                        lines.append("• Position being historical (no longer >0.5% for individual holders)")
                        lines.append("• Data being aggregated from multiple reporting periods")
                        lines.append("• Position holders below individual reporting threshold")
                        
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
            result = self.short_integration.update_short_data()
            
            if result.get('success'):
                if result.get('updated'):
                    # Data was actually updated
                    self.safe_addstr(row + 3, 0, "✅ Short selling data updated successfully!", curses.color_pair(1))
                    self.safe_addstr(row + 4, 0, "")
                    self.safe_addstr(row + 5, 0, "Updated data includes:")
                    
                    stats = result.get('stats', {})
                    if stats:
                        self.safe_addstr(row + 6, 0, f"• Total positions tracked: {stats.get('total_positions', 0)}")
                        self.safe_addstr(row + 7, 0, f"• Positions with holder details: {stats.get('positions_with_holders', 0)}")
                        self.safe_addstr(row + 8, 0, f"• Portfolio matches: {stats.get('portfolio_matches', 0)}")
                        self.safe_addstr(row + 9, 0, f"• Nordic stocks in portfolio: {stats.get('nordic_stocks', 0)}")
                    else:
                        self.safe_addstr(row + 6, 0, "• Finansinspektionen (Swedish FSA) positions")
                        self.safe_addstr(row + 7, 0, "• Finanssivalvonta (Finnish FSA) positions") 
                        self.safe_addstr(row + 8, 0, "• Alternative data sources")
                else:
                    # Data was already current
                    self.safe_addstr(row + 3, 0, "ℹ️  Short selling data is already current", curses.color_pair(3))
                    self.safe_addstr(row + 4, 0, "")
                    self.safe_addstr(row + 5, 0, result.get('message', 'No update needed'))
                    self.safe_addstr(row + 6, 0, "")
                    self.safe_addstr(row + 7, 0, "Data is refreshed automatically every 24 hours.")
                    self.safe_addstr(row + 8, 0, "Use this option if you need to force an update.")
            else:
                self.safe_addstr(row + 3, 0, "❌ Failed to update short selling data", curses.color_pair(2))
                self.safe_addstr(row + 4, 0, "")
                self.safe_addstr(row + 5, 0, f"Error: {result.get('message', 'Unknown error')}")
                self.safe_addstr(row + 6, 0, "")
                self.safe_addstr(row + 7, 0, "Possible issues:")
                self.safe_addstr(row + 8, 0, "• Network connectivity problems")
                self.safe_addstr(row + 9, 0, "• Regulatory data sources unavailable")
                self.safe_addstr(row + 10, 0, "• API rate limits or access restrictions")
            
            self.safe_addstr(row + 12, 0, "Press any key to continue...")
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
        lines.append("")
        lines.append("Planned features:")
        lines.append("• Historical short interest tracking")
        lines.append("• Trend analysis and charts")
        lines.append("• Short squeeze probability indicators")
        lines.append("• Correlation with stock performance")
        lines.append("• Nordic market short selling patterns")
        
        self.display_scrollable_list("Short Trends", lines)
    
    def _show_position_holders(self):
        """Show all positions grouped by holder."""
        row = self.clear_and_display_header("Position Holders Analysis")
        
        self.safe_addstr(row, 0, "Loading position holders data...")
        self.stdscr.refresh()
        
        try:
            holder_positions = self.short_integration.get_positions_by_holder()
            
            if not holder_positions:
                self.show_message("No position holder data available.", row + 2)
                return
            
            # Sort holders by number of positions (most active first)
            sorted_holders = sorted(
                holder_positions.items(),
                key=lambda x: len(x[1]),
                reverse=True
            )
            
            # Display holder selection menu
            self.stdscr.clear()
            row = self.clear_and_display_header("Select Position Holder")
            
            self.safe_addstr(row, 0, f"Total holders: {len(sorted_holders)}")
            self.safe_addstr(row + 1, 0, "")
            
            # Create list for display
            holder_list = []
            for holder_name, positions in sorted_holders[:50]:  # Show top 50
                total_pct = sum(p['position_percentage'] for p in positions)
                holder_list.append({
                    'name': holder_name,
                    'positions': positions,
                    'count': len(positions),
                    'total_pct': total_pct
                })
            
            # Display holder list
            for i, holder in enumerate(holder_list):
                display_name = holder['name']
                if len(display_name) > 50:
                    display_name = display_name[:47] + "..."
                
                self.safe_addstr(
                    row + 2 + i, 0,
                    f"{i+1:2}. {display_name:52} ({holder['count']} positions, {holder['total_pct']:.2f}% total)"
                )
            
            if len(sorted_holders) > 50:
                self.safe_addstr(
                    row + 2 + len(holder_list) + 1, 0,
                    f"... and {len(sorted_holders) - 50} more holders"
                )
            
            # Get selection
            choice = self.get_numeric_input(
                "Enter holder number (or 0 to cancel): ",
                row + 2 + min(len(holder_list), 50) + 3,
                min_val=0,
                max_val=len(holder_list),
                integer_only=True
            )
            
            if not choice or choice == 0:
                return
            
            selected_holder = holder_list[choice - 1]
            self._display_holder_positions(selected_holder)
            
        except Exception as e:
            self.show_message(f"Error loading position holders: {e}", row + 2)
    
    def _display_holder_positions(self, holder_data: dict):
        """Display all positions for a specific holder."""
        holder_name = holder_data['name']
        positions = holder_data['positions']
        
        lines = []
        lines.append(f"Position Holder: {holder_name}")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Total Positions: {holder_data['count']}")
        lines.append(f"Total Short Interest: {holder_data['total_pct']:.2f}%")
        lines.append("")
        lines.append("Individual Positions:")
        lines.append("-" * 70)
        lines.append("")
        
        for i, pos in enumerate(positions, 1):
            company = pos['company_name']
            ticker = pos['ticker']
            holder_pct = pos['position_percentage']
            total_short = pos['total_company_short']
            pos_date = pos['position_date']
            
            # Calculate holder's share of total short position
            pct_of_total = (holder_pct / total_short * 100) if total_short > 0 else 0
            
            lines.append(f"{i:2}. {company}")
            lines.append(f"    Ticker: {ticker}")
            lines.append(f"    Holder's Position: {holder_pct:.2f}% ({pct_of_total:.1f}% of total short)")
            lines.append(f"    Total Company Short: {total_short:.2f}%")
            lines.append(f"    Position Date: {pos_date}")
            lines.append("")
        
        # Add summary statistics
        lines.append("Summary Statistics:")
        lines.append("-" * 70)
        avg_position = holder_data['total_pct'] / holder_data['count']
        lines.append(f"Average Position Size: {avg_position:.2f}%")
        
        largest_pos = max(positions, key=lambda x: x['position_percentage'])
        lines.append(f"Largest Position: {largest_pos['company_name']} ({largest_pos['position_percentage']:.2f}%)")
        
        smallest_pos = min(positions, key=lambda x: x['position_percentage'])
        lines.append(f"Smallest Position: {smallest_pos['company_name']} ({smallest_pos['position_percentage']:.2f}%)")
        
        self.display_scrollable_list(f"Positions - {holder_name[:40]}", lines)
    
    def _show_all_portfolio_shorts(self):
        """Show short selling data for all stocks in portfolio (owned or not)."""
        self.stdscr.clear()
        row = self.clear_and_display_header("All Portfolio Stocks - Short Data")
        
        self.safe_addstr(row, 0, "Loading short selling data for all portfolio stocks...")
        self.stdscr.refresh()
        
        try:
            summary = self.short_integration.get_portfolio_short_summary()
            
            lines = []
            lines.append("All Portfolio Stocks - Short Selling Data")
            lines.append("=" * 70)
            lines.append("")
            
            if 'error' in summary:
                lines.append(f"Error: {summary['error']}")
                lines.append("")
                lines.append("To enable short selling tracking:")
                lines.append("1. Select option 3 to update short selling data")
                lines.append("2. Wait for data to be fetched from regulatory sources")
            else:
                lines.append(f"Last Updated: {summary.get('last_updated', 'Unknown')}")
                lines.append(f"Total Portfolio Stocks: {summary.get('total_stocks_tracked', 0)}")
                lines.append("")
                
                portfolio_shorts = summary.get('portfolio_short_positions', [])
                
                if portfolio_shorts:
                    lines.append(f"📊 ALL PORTFOLIO STOCKS WITH SHORT DATA ({len(portfolio_shorts)} stocks)")
                    lines.append("-" * 70)
                    lines.append("")
                    
                    # Group by short interest level
                    very_high = []  # >10%
                    high = []       # 5-10%
                    moderate = []   # 2-5%
                    low = []        # <2%
                    
                    for stock in portfolio_shorts:
                        pct = stock['percentage']
                        # Check if we own this stock
                        ticker = stock['ticker']
                        owned = False
                        for name, stock_obj in self.portfolio.stocks.items():
                            if stock_obj.ticker == ticker:
                                total_shares = stock_obj.get_total_shares()
                                if total_shares > 0:
                                    owned = True
                                    break
                        
                        stock['owned'] = owned
                        
                        if pct > 10:
                            very_high.append(stock)
                        elif pct > 5:
                            high.append(stock)
                        elif pct > 2:
                            moderate.append(stock)
                        else:
                            low.append(stock)
                    
                    # Display by category
                    if very_high:
                        lines.append("🔴 VERY HIGH SHORT INTEREST (>10%)")
                        lines.append("-" * 70)
                        for stock in very_high:
                            owned_marker = "★" if stock['owned'] else " "
                            lines.append(f"{owned_marker} {stock['ticker']:12} {stock['percentage']:6.2f}%  {stock['company'][:45]}")
                        lines.append("")
                    
                    if high:
                        lines.append("🟠 HIGH SHORT INTEREST (5-10%)")
                        lines.append("-" * 70)
                        for stock in high:
                            owned_marker = "★" if stock['owned'] else " "
                            lines.append(f"{owned_marker} {stock['ticker']:12} {stock['percentage']:6.2f}%  {stock['company'][:45]}")
                        lines.append("")
                    
                    if moderate:
                        lines.append("🟡 MODERATE SHORT INTEREST (2-5%)")
                        lines.append("-" * 70)
                        for stock in moderate:
                            owned_marker = "★" if stock['owned'] else " "
                            lines.append(f"{owned_marker} {stock['ticker']:12} {stock['percentage']:6.2f}%  {stock['company'][:45]}")
                        lines.append("")
                    
                    if low:
                        lines.append("🟢 LOW SHORT INTEREST (<2%)")
                        lines.append("-" * 70)
                        for stock in low:
                            owned_marker = "★" if stock['owned'] else " "
                            lines.append(f"{owned_marker} {stock['ticker']:12} {stock['percentage']:6.2f}%  {stock['company'][:45]}")
                        lines.append("")
                    
                    lines.append("Legend:")
                    lines.append("  ★ = Currently owned in portfolio")
                    lines.append("")
                    
                    # Summary statistics
                    owned_count = sum(1 for s in portfolio_shorts if s['owned'])
                    lines.append("Summary Statistics:")
                    lines.append(f"  Total stocks tracked: {len(portfolio_shorts)}")
                    lines.append(f"  Currently owned: {owned_count}")
                    lines.append(f"  Previously owned/tracked: {len(portfolio_shorts) - owned_count}")
                    lines.append(f"  Very High Risk (>10%): {len(very_high)}")
                    lines.append(f"  High Risk (5-10%): {len(high)}")
                    lines.append(f"  Moderate Risk (2-5%): {len(moderate)}")
                    lines.append(f"  Low Risk (<2%): {len(low)}")
                else:
                    lines.append("📊 ALL PORTFOLIO STOCKS WITH SHORT DATA (0 stocks)")
                    lines.append("-" * 70)
                    lines.append("No short position data available for any portfolio stocks.")
                    lines.append("")
                    lines.append("This could mean:")
                    lines.append("• Stocks have no significant short positions (below reporting threshold)")
                    lines.append("• Data has not been fetched yet (use option 3 to update)")
                    lines.append("• Stocks are not traded on Nordic markets")
            
            self.display_scrollable_list("All Portfolio Shorts", lines)
            
        except Exception as e:
            self.show_message(f"Error loading portfolio short data: {e}", row + 2)
        
        self.display_scrollable_list("Short Trends", lines)