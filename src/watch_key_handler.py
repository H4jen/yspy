#!/usr/bin/env python3
"""
Key handler for watch stocks screen.
Centralizes all keyboard input handling logic.
"""

import curses
import time as timing_module
from typing import Dict, Any, Optional, Callable
from src.watch_view_state import ViewState
from src.stock_grouper import StockGrouper
from src.page_calculator import PageCalculator
from ui.display_utils import get_portfolio_shares_lines, get_portfolio_shares_summary


class WatchKeyHandler:
    """Handles keyboard input for the watch stocks screen."""
    
    def __init__(self, portfolio, logger, short_integration=None):
        self.portfolio = portfolio
        self.logger = logger
        self.short_integration = short_integration
        self.grouper = StockGrouper(portfolio)
    
    def handle_key(self, key: int, view_state: ViewState, stock_prices: list,
                   short_data_by_name: Dict, short_trend_by_name: Dict) -> Dict[str, Any]:
        """
        Process a keypress and return the action to take.
        
        Args:
            key: The key code from curses
            view_state: Current view state
            stock_prices: Current stock price data
            short_data_by_name: Short selling data by stock name
            short_trend_by_name: Short selling trend by stock name
            
        Returns:
            Dict with action type and any necessary data:
            {
                'action': 'exit' | 'refresh' | 'update_shorts' | 'toggle_view' | 
                          'toggle_compression' | 'page_up' | 'page_down' | 'none',
                'view_state': updated ViewState,
                'needs_redraw': bool,
                'short_data_by_name': updated short data (if changed),
                'short_trend_by_name': updated short trend (if changed)
            }
        """
        result = {
            'action': 'none',
            'view_state': view_state,
            'needs_redraw': False,
            'short_data_by_name': short_data_by_name,
            'short_trend_by_name': short_trend_by_name
        }
        
        # View toggle (s/S)
        if key in (ord('s'), ord('S')):
            t_start = timing_module.time()
            view_state.toggle_view_mode()
            t_end = timing_module.time()
            switch_time = (t_end - t_start) * 1000
            if switch_time > 10:
                self.logger.warning(f"SLOW view switch processing: {switch_time:.1f}ms")
            result['action'] = 'toggle_view'
            result['needs_redraw'] = True
            return result
        
        # Compression toggle (d/D) - only in shares view
        if view_state.view_mode == 'shares' and key in (ord('d'), ord('D')):
            view_state.toggle_shares_compression()
            result['action'] = 'toggle_compression'
            result['needs_redraw'] = True
            return result
        
        # Refresh (r/R) - only in stocks view
        if key in (ord('r'), ord('R')) and view_state.view_mode == 'stocks':
            result['action'] = 'refresh'
            return result
        
        # Update shorts (u/U) - only in stocks view
        if key in (ord('u'), ord('U')) and view_state.view_mode == 'stocks':
            if self.short_integration:
                updated_data = self._update_short_data()
                result['action'] = 'update_shorts'
                result['short_data_by_name'] = updated_data['short_data_by_name']
                result['short_trend_by_name'] = updated_data['short_trend_by_name']
                result['update_result'] = updated_data.get('update_result')
            return result
        
        # Page Up
        if key == curses.KEY_PPAGE:
            page_result = self._handle_page_up(view_state, stock_prices)
            result.update(page_result)
            return result
        
        # Page Down
        if key == curses.KEY_NPAGE:
            page_result = self._handle_page_down(view_state, stock_prices)
            result.update(page_result)
            return result
        
        # ESC - exit
        if key == 27:
            result['action'] = 'exit'
            return result
        
        # Any other key - exit
        if key != -1:
            result['action'] = 'exit'
            return result
        
        return result
    
    def _handle_page_up(self, view_state: ViewState, stock_prices: list) -> Dict[str, Any]:
        """Handle Page Up key press."""
        result = {
            'action': 'page_up',
            'view_state': view_state,
            'needs_redraw': False
        }
        
        if view_state.view_mode == 'stocks':
            # Stocks view pagination
            owned, highlighted, other, indices = self.grouper.group_stocks(stock_prices)
            
            # Build full stock list
            all_stocks = []
            if owned:
                all_stocks.extend(owned)
                if highlighted or other:
                    all_stocks.append({"_blank": True})
            if highlighted:
                all_stocks.extend(highlighted)
                if other:
                    all_stocks.append({"_blank": True})
            all_stocks.extend(other)
            if indices:
                if owned or highlighted or other:
                    all_stocks.append({"_blank": True})
                all_stocks.append({"_separator": "---------- Market Indexes ----------"})
                all_stocks.extend(indices)
            
            metrics = PageCalculator.calculate_stocks_view_metrics(
                len(owned), len(highlighted), len(other), len(indices), 80  # Mock curses.LINES
            )
            max_body_lines = metrics['max_body_lines']
            page_size = max(1, max_body_lines)
            
            if view_state.stocks_scroll_pos > 0:
                current_page = view_state.stocks_scroll_pos // page_size
                if current_page > 0:
                    view_state.stocks_scroll_pos = (current_page - 1) * page_size
                else:
                    view_state.stocks_scroll_pos = 0
                view_state.skip_dot_update_once = True
                result['needs_redraw'] = True
        
        else:  # shares view
            # Get shares lines
            if view_state.shares_compressed:
                shares_lines = get_portfolio_shares_summary(self.portfolio, stock_prices)
            else:
                shares_lines = get_portfolio_shares_lines(self.portfolio, stock_prices)
            
            owned, highlighted, indices = self.grouper.group_for_shares_view(stock_prices)
            
            metrics = PageCalculator.calculate_shares_view_metrics(
                len(owned), len(highlighted), len(indices), 80  # Mock curses.LINES
            )
            max_body_lines = max(1, metrics['max_body_lines'])
            page_size = max(1, max_body_lines)
            
            if view_state.shares_scroll_pos > 0:
                current_page = view_state.shares_scroll_pos // page_size
                if current_page > 0:
                    view_state.shares_scroll_pos = (current_page - 1) * page_size
                else:
                    view_state.shares_scroll_pos = 0
                view_state.skip_dot_update_once = True
                result['needs_redraw'] = True
        
        return result
    
    def _handle_page_down(self, view_state: ViewState, stock_prices: list) -> Dict[str, Any]:
        """Handle Page Down key press."""
        result = {
            'action': 'page_down',
            'view_state': view_state,
            'needs_redraw': False
        }
        
        if view_state.view_mode == 'stocks':
            # Stocks view pagination
            owned, highlighted, other, indices = self.grouper.group_stocks(stock_prices)
            
            # Build full stock list
            all_stocks = []
            if owned:
                all_stocks.extend(owned)
                if highlighted or other:
                    all_stocks.append({"_blank": True})
            if highlighted:
                all_stocks.extend(highlighted)
                if other:
                    all_stocks.append({"_blank": True})
            all_stocks.extend(other)
            if indices:
                if owned or highlighted or other:
                    all_stocks.append({"_blank": True})
                all_stocks.append({"_separator": "---------- Market Indexes ----------"})
                all_stocks.extend(indices)
            
            metrics = PageCalculator.calculate_stocks_view_metrics(
                len(owned), len(highlighted), len(other), len(indices), 80  # Mock curses.LINES
            )
            max_body_lines = metrics['max_body_lines']
            max_scroll = max(0, len(all_stocks) - max_body_lines)
            page_size = max(1, max_body_lines)
            
            if view_state.stocks_scroll_pos < max_scroll:
                current_page = view_state.stocks_scroll_pos // page_size
                next_page_start = (current_page + 1) * page_size
                view_state.stocks_scroll_pos = min(max_scroll, next_page_start)
                view_state.skip_dot_update_once = True
                result['needs_redraw'] = True
        
        else:  # shares view
            # Get shares lines
            if view_state.shares_compressed:
                shares_lines = get_portfolio_shares_summary(self.portfolio, stock_prices)
            else:
                shares_lines = get_portfolio_shares_lines(self.portfolio, stock_prices)
            
            owned, highlighted, indices = self.grouper.group_for_shares_view(stock_prices)
            
            metrics = PageCalculator.calculate_shares_view_metrics(
                len(owned), len(highlighted), len(indices), 80  # Mock curses.LINES
            )
            max_body_lines = max(1, metrics['max_body_lines'])
            max_scroll = max(0, len(shares_lines) - max_body_lines)
            page_size = max(1, max_body_lines)
            
            if view_state.shares_scroll_pos < max_scroll:
                current_page = view_state.shares_scroll_pos // page_size
                next_page_start = (current_page + 1) * page_size
                view_state.shares_scroll_pos = min(max_scroll, next_page_start)
                view_state.skip_dot_update_once = True
                result['needs_redraw'] = True
        
        return result
    
    def _update_short_data(self) -> Dict[str, Any]:
        """Update short selling data from remote source."""
        result = {
            'short_data_by_name': {},
            'short_trend_by_name': {},
            'update_result': None
        }
        
        if not self.short_integration:
            return result
        
        try:
            start_time = timing_module.time()
            update_result = self.short_integration.update_short_data(force=True)
            elapsed = timing_module.time() - start_time
            
            if update_result.get('success') and update_result.get('updated'):
                # Reload and rebuild short data mappings
                summary = self.short_integration.get_portfolio_short_summary()
                portfolio_shorts = summary.get('portfolio_short_positions', [])
                
                max_trend_time = 5.0
                trend_start = timing_module.time()
                
                # Map by stock name
                for stock_data in portfolio_shorts:
                    if timing_module.time() - trend_start > max_trend_time:
                        break
                    
                    ticker = stock_data['ticker']
                    company_name = stock_data.get('company', '')
                    
                    for name, stock_obj in self.portfolio.stocks.items():
                        if stock_obj.ticker == ticker:
                            result['short_data_by_name'][name] = stock_data['percentage']
                            
                            # Calculate trend
                            if company_name:
                                try:
                                    trend_info = self.short_integration.calculate_short_trend(
                                        company_name,
                                        lookback_days=7,
                                        threshold=0.1
                                    )
                                    result['short_trend_by_name'][name] = trend_info
                                except Exception:
                                    pass
                            break
                
                result['update_result'] = update_result
        
        except Exception as e:
            self.logger.warning(f"Failed to update short data: {e}")
            result['update_result'] = {'success': False, 'error': str(e)}
        
        return result
