#!/usr/bin/env python3
"""
Display manager for watch stocks screen.
Handles rendering of stocks and shares views with proper layout and coloring.
"""

import curses
from typing import List, Dict, Any, Optional
from src.stock_grouper import StockGrouper
from src.page_calculator import PageCalculator
from src.text_colorizer import TextColorizer
from ui.display_utils import get_portfolio_shares_lines, get_portfolio_shares_summary, color_for_value
from ui.stock_display import (display_colored_stock_prices, display_portfolio_totals,
                              format_stock_price_lines, display_single_stock_price)


class WatchDisplayManager:
    """Manages display rendering for the watch stocks screen."""
    
    def __init__(self, screen, portfolio, logger):
        self.screen = screen
        self.portfolio = portfolio
        self.logger = logger
        self.grouper = StockGrouper(portfolio)
        self.colorizer = TextColorizer(screen)
    
    def safe_addstr(self, row: int, col: int, text: str, attr=None):
        """Safely add string without crashing on boundaries."""
        try:
            if attr is not None:
                self.screen.addstr(row, col, text, attr)
            else:
                self.screen.addstr(row, col, text)
        except curses.error:
            pass
    
    def display_stocks_view(self, stock_prices: List[Dict], prev_stock_prices: Optional[List[Dict]],
                           dot_states: Dict, delta_counters: Dict, minute_trend_tracker: Dict,
                           stocks_scroll_pos: int, skip_dot_update_once: bool,
                           short_data_by_name: Dict, short_trend_by_name: Dict):
        """Render the stocks view with grouped stocks."""
        # Get update stats
        stats = self.portfolio.get_update_stats()
        status = self._format_status_line(stats)
        
        # Group stocks
        owned, highlighted, other, indices = self.grouper.group_stocks(stock_prices)
        
        # Build display list with blank separators
        all_stocks = self._build_stocks_display_list(owned, highlighted, other, indices)
        
        # Calculate pagination
        metrics = PageCalculator.calculate_stocks_view_metrics(
            len(owned), len(highlighted), len(other), len(indices), curses.LINES
        )
        max_body_lines = metrics['max_body_lines']
        
        # Apply scrolling
        max_scroll = max(0, len(all_stocks) - max_body_lines)
        actual_scroll_pos = min(stocks_scroll_pos, max_scroll)
        visible_stocks = all_stocks[actual_scroll_pos:actual_scroll_pos + max_body_lines]
        
        # Display
        base_row = 1
        self.safe_addstr(0, 0, status[:curses.COLS - 1], curses.color_pair(3))
        
        effective_prev = None if skip_dot_update_once else prev_stock_prices
        display_colored_stock_prices(self.screen, visible_stocks, effective_prev, dot_states,
                                    self.portfolio, skip_header=True, base_row=base_row,
                                    delta_counters=delta_counters,
                                    minute_trend_tracker=minute_trend_tracker,
                                    update_dots=not skip_dot_update_once,
                                    short_data=short_data_by_name,
                                    short_trend=short_trend_by_name)
        
        # Fixed bottom layout
        self._display_bottom_layout_stocks(len(all_stocks), max_body_lines, actual_scroll_pos, max_scroll, stock_prices)
    
    def display_shares_view(self, stock_prices: List[Dict], prev_stock_prices: Optional[List[Dict]],
                           dot_states: Dict, delta_counters: Dict, minute_trend_tracker: Dict,
                           shares_scroll_pos: int, skip_dot_update_once: bool,
                           short_data_by_name: Dict, short_trend_by_name: Dict,
                           shares_compressed: bool):
        """Render the shares view with detailed share information."""
        # Get update stats
        stats = self.portfolio.get_update_stats()
        status = self._format_status_line(stats)
        
        # Group stocks for shares view
        owned, highlighted, indices = self.grouper.group_for_shares_view(stock_prices)
        
        row_ptr = 0
        maxw = curses.COLS - 1
        
        # Status line
        self.safe_addstr(row_ptr, 0, status[:maxw], curses.color_pair(3))
        row_ptr += 1
        
        # Display stock summary
        row_ptr = self._display_shares_stock_summary(
            owned, highlighted, indices, prev_stock_prices, dot_states,
            delta_counters, minute_trend_tracker, skip_dot_update_once,
            short_data_by_name, short_trend_by_name, row_ptr
        )
        
        # Display share details
        row_ptr = self._display_share_details(
            stock_prices, shares_scroll_pos, shares_compressed, row_ptr
        )
    
    def _build_stocks_display_list(self, owned, highlighted, other, indices):
        """Build display list with proper blank separators."""
        all_stocks = []
        
        # Owned stocks
        if owned:
            all_stocks.extend(owned)
            if highlighted or other:
                all_stocks.append({"_blank": True})
        
        # Highlighted stocks
        if highlighted:
            all_stocks.extend(highlighted)
            if other:
                all_stocks.append({"_blank": True})
        
        # Other stocks
        all_stocks.extend(other)
        
        # Market indices
        if indices:
            if owned or highlighted or other:
                all_stocks.append({"_blank": True})
            all_stocks.append({"_separator": "---------- Market Indexes ----------"})
            all_stocks.extend(indices)
        
        return all_stocks
    
    def _display_shares_stock_summary(self, owned, highlighted, indices, prev_stock_prices,
                                     dot_states, delta_counters, minute_trend_tracker,
                                     skip_dot_update_once, short_data_by_name,
                                     short_trend_by_name, row_ptr):
        """Display the stock price summary section in shares view."""
        display_stocks = owned + highlighted
        
        if display_stocks:
            header_lines = format_stock_price_lines(display_stocks, short_data_by_name, short_trend_by_name)[:2]
            if header_lines:
                header = header_lines[0]
                separator = header_lines[1] if len(header_lines) > 1 else ""
                self.safe_addstr(row_ptr, 0, header[:curses.COLS - 1])
                row_ptr += 1
                self.safe_addstr(row_ptr, 0, separator[:curses.COLS - 1])
                row_ptr += 1
            
            effective_prev_stocks = None if skip_dot_update_once else prev_stock_prices
            prev_lookup = {}
            if effective_prev_stocks:
                for pst in effective_prev_stocks:
                    prev_lookup[pst.get("name", "")] = pst
            
            # Display owned stocks
            for ost in owned:
                if row_ptr >= curses.LINES - 1:
                    break
                row_ptr = display_single_stock_price(
                    self.screen, ost, row_ptr, prev_lookup, dot_states,
                    delta_counters, minute_trend_tracker, update_dots=not skip_dot_update_once,
                    short_data=short_data_by_name, short_trend=short_trend_by_name
                )
            
            # Blank row between owned and highlighted
            if owned and highlighted and row_ptr < curses.LINES - 1:
                self.safe_addstr(row_ptr, 0, "")
                row_ptr += 1
            
            # Display highlighted stocks
            for hst in highlighted:
                if row_ptr >= curses.LINES - 1:
                    break
                row_ptr = display_single_stock_price(
                    self.screen, hst, row_ptr, prev_lookup, dot_states,
                    delta_counters, minute_trend_tracker, update_dots=not skip_dot_update_once,
                    short_data=short_data_by_name, short_trend=short_trend_by_name
                )
            
            if row_ptr < curses.LINES - 1:
                self.safe_addstr(row_ptr, 0, "")
                row_ptr += 1
        
        # Display highlighted indices
        if indices:
            if row_ptr < curses.LINES - 1:
                self.safe_addstr(row_ptr, 0, "---------- Market Indexes ----------")
                row_ptr += 1
            
            for idx_stock in indices:
                if row_ptr >= curses.LINES - 1:
                    break
                row_ptr = display_single_stock_price(
                    self.screen, idx_stock, row_ptr, prev_lookup, dot_states,
                    delta_counters, minute_trend_tracker, update_dots=not skip_dot_update_once,
                    short_data=short_data_by_name, short_trend=short_trend_by_name
                )
            
            if row_ptr < curses.LINES - 1:
                self.safe_addstr(row_ptr, 0, "")
                row_ptr += 1
        
        return row_ptr
    
    def _display_share_details(self, stock_prices, shares_scroll_pos, shares_compressed, row_ptr):
        """Display the share details section."""
        # Get shares lines
        if shares_compressed:
            shares_lines = get_portfolio_shares_summary(self.portfolio, stock_prices)
            view_mode_text = "COMPRESSED"
        else:
            shares_lines = get_portfolio_shares_lines(self.portfolio, stock_prices)
            view_mode_text = "DETAILED"
        
        if row_ptr < curses.LINES - 1:
            self.safe_addstr(row_ptr, 0,
                           f"Share Details [{view_mode_text}] (PgUp/PgDn to scroll, 'd'=Toggle view, 's'=Stocks, any other key=Exit)")
            row_ptr += 1
        if row_ptr < curses.LINES - 1:
            self.safe_addstr(row_ptr, 0, "-" * min(curses.COLS - 1, 80))
            row_ptr += 1
        
        # Calculate visible area
        reserved_bottom_lines = 5
        max_body_lines = max(0, curses.LINES - row_ptr - reserved_bottom_lines)
        max_scroll_possible = max(0, len(shares_lines) - max_body_lines)
        actual_scroll_pos = min(shares_scroll_pos, max_scroll_possible)
        
        visible = shares_lines[actual_scroll_pos:actual_scroll_pos + max_body_lines]
        
        # Display with coloring
        for idx, line in enumerate(visible):
            display_row = row_ptr + idx
            if display_row >= curses.LINES - reserved_bottom_lines:
                break
            
            line_index = idx + actual_scroll_pos
            self.colorizer.color_shares_line(display_row, line, line_index,
                                            shares_compressed, curses.COLS)
        
        # Display bottom layout
        self._display_bottom_layout_shares(len(shares_lines), max_body_lines,
                                          actual_scroll_pos, max_scroll_possible, stock_prices)
        
        return row_ptr
    
    def _display_bottom_layout_stocks(self, total_stocks, max_body_lines,
                                     actual_scroll_pos, max_scroll, stock_prices=None):
        """Display fixed bottom layout for stocks view."""
        instr_row = curses.LINES - 1
        currency_row = curses.LINES - 2
        totals_row = curses.LINES - 4
        scroll_row = curses.LINES - 5
        
        # Page indicator
        if total_stocks > max_body_lines:
            page_info_dict = PageCalculator.calculate_page_info(
                actual_scroll_pos, max_scroll, max_body_lines
            )
            page_info = f"Page {page_info_dict['current_page']}/{page_info_dict['total_pages']} (PgUp/PgDn)"
            self.safe_addstr(scroll_row, 0, page_info, curses.color_pair(3))
        
        display_portfolio_totals(self.screen, self.portfolio, totals_row, stock_prices)
        self._display_currency_legend(currency_row)
        self.safe_addstr(instr_row, 0,
                        "View: STOCKS  |  's'=Shares  'r'=Refresh  'u'=Update Shorts  any other key=Exit")
    
    def _display_bottom_layout_shares(self, total_lines, max_body_lines,
                                     actual_scroll_pos, max_scroll, stock_prices=None):
        """Display fixed bottom layout for shares view."""
        scroll_indicator_row = curses.LINES - 4
        totals_row = curses.LINES - 3
        
        # Page indicator
        if total_lines > max_body_lines:
            page_info_dict = PageCalculator.calculate_page_info(
                actual_scroll_pos, max_scroll, max_body_lines
            )
            page_info = f"Page {page_info_dict['current_page']}/{page_info_dict['total_pages']} (PgUp/PgDn)"
            self.safe_addstr(scroll_indicator_row, 0, page_info, curses.color_pair(3))
        
        display_portfolio_totals(self.screen, self.portfolio, totals_row, stock_prices)
    
    def _display_currency_legend(self, row: int):
        """Display currency conversion rates."""
        # Get exchange rates
        rates = self.portfolio.get_exchange_rates()
        legend_parts = []
        
        for currency, rate in sorted(rates.items()):
            if currency != "SEK" and rate > 0:
                legend_parts.append(f"{currency}→SEK: {rate:.4f}")
        
        if legend_parts:
            legend = "  ".join(legend_parts)
            self.safe_addstr(row, 0, legend[:curses.COLS - 1], curses.color_pair(3))
    
    def _format_status_line(self, stats: Dict) -> str:
        """Format the status line with update statistics."""
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
        
        return status
