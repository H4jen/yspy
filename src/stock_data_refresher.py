#!/usr/bin/env python3
"""
Stock data refresh manager for watch stocks screen.
Handles fetching and updating stock price data.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple


class StockDataRefresher:
    """Manages stock price data refreshing and updates."""
    
    def __init__(self, portfolio, logger: Optional[logging.Logger] = None):
        self.portfolio = portfolio
        self.logger = logger or logging.getLogger(__name__)
    
    def fetch_stock_prices(self) -> List[Dict[str, Any]]:
        """
        Fetch current stock prices for all stocks in portfolio.
        
        Returns:
            List of stock price dictionaries
        """
        stock_prices = []
        
        for ticker, stock in self.portfolio.stocks.items():
            try:
                price_obj = stock.get_price_info()
                if price_obj:
                    current_sek = price_obj.get_current_sek()
                    
                    stock_data = {
                        "name": stock.name,
                        "ticker": ticker,
                        "current": current_sek if current_sek is not None else 0.0,
                        "currency": price_obj.currency,
                        "-1d": price_obj.get_historical_close(1) or 0.0,
                        "-5d": price_obj.get_historical_close(5) or 0.0,
                        "-30d": price_obj.get_historical_close(30) or 0.0,
                    }
                    stock_prices.append(stock_data)
                else:
                    # No price data available
                    stock_prices.append({
                        "name": stock.name,
                        "ticker": ticker,
                        "current": 0.0,
                        "currency": "SEK",
                        "-1d": 0.0,
                        "-5d": 0.0,
                        "-30d": 0.0,
                    })
            except Exception as e:
                self.logger.warning(f"Error fetching price for {ticker}: {e}")
                stock_prices.append({
                    "name": stock.name,
                    "ticker": ticker,
                    "current": 0.0,
                    "currency": "SEK",
                    "-1d": 0.0,
                    "-5d": 0.0,
                    "-30d": 0.0,
                })
        
        return stock_prices
    
    def refresh_historical_data(self, tickers: Optional[List[str]] = None):
        """
        Trigger bulk refresh of historical data.
        
        Args:
            tickers: List of tickers to refresh, or None for all
        """
        if tickers is None:
            tickers = [stock.ticker for stock in self.portfolio.stocks.values()]
        
        try:
            self.portfolio._bulk_refresh_historical_data(tickers)
            self.logger.info(f"Refreshed historical data for {len(tickers)} stocks")
        except Exception as e:
            self.logger.error(f"Failed to refresh historical data: {e}")
    
    def should_compute_history(self, refresh_cycle_count: int, first_cycle: bool,
                              force_history: bool) -> bool:
        """
        Determine if historical data should be computed this cycle.
        
        Args:
            refresh_cycle_count: Number of refresh cycles completed
            first_cycle: Whether this is the first cycle
            force_history: Force history computation flag
            
        Returns:
            True if history should be computed
        """
        # Force if requested
        if force_history:
            return True
        
        # Always compute on first cycle
        if first_cycle:
            return True
        
        # Every 10 cycles (configurable)
        history_interval = 10
        return refresh_cycle_count % history_interval == 0
    
    def update_price_tracking(self, stock_prices: List[Dict], prev_stock_prices: Optional[List[Dict]],
                             minute_trend_tracker: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update minute-based price trend tracking.
        
        Args:
            stock_prices: Current stock prices
            prev_stock_prices: Previous stock prices
            minute_trend_tracker: Tracker dict to update
            
        Returns:
            Updated minute_trend_tracker
        """
        import time
        
        current_time = time.time()
        
        for sp in stock_prices:
            name = sp.get("name", "")
            current_price = sp.get("current", 0.0)
            
            if name not in minute_trend_tracker:
                minute_trend_tracker[name] = {
                    'samples': [],
                    'last_sample_time': current_time
                }
            
            tracker = minute_trend_tracker[name]
            
            # Add sample if enough time has passed (60 seconds)
            if current_time - tracker['last_sample_time'] >= 60:
                tracker['samples'].append({
                    'price': current_price,
                    'time': current_time
                })
                tracker['last_sample_time'] = current_time
                
                # Keep only last 5 samples (5 minutes)
                if len(tracker['samples']) > 5:
                    tracker['samples'] = tracker['samples'][-5:]
        
        return minute_trend_tracker
    
    def update_delta_counters(self, stock_prices: List[Dict], prev_stock_prices: Optional[List[Dict]],
                             delta_counters: Dict[str, int]) -> Dict[str, int]:
        """
        Update delta counters for tracking price changes.
        
        Args:
            stock_prices: Current stock prices
            prev_stock_prices: Previous stock prices
            delta_counters: Counter dict to update
            
        Returns:
            Updated delta_counters
        """
        if prev_stock_prices is None:
            return delta_counters
        
        # Build lookup of previous prices
        prev_lookup = {sp.get("name", ""): sp for sp in prev_stock_prices}
        
        for sp in stock_prices:
            name = sp.get("name", "")
            current = sp.get("current", 0.0)
            
            prev_sp = prev_lookup.get(name)
            if prev_sp:
                prev_current = prev_sp.get("current", 0.0)
                
                # If price changed, reset counter
                if abs(current - prev_current) > 0.001:
                    delta_counters[name] = 0
                else:
                    # Increment counter
                    delta_counters[name] = delta_counters.get(name, 0) + 1
            else:
                delta_counters[name] = 0
        
        return delta_counters
