#!/usr/bin/env python3
"""
Short selling data initialization for watch stocks screen.
Handles loading and validating short selling data at startup.
"""

import os
import time
import logging
from typing import Dict, Tuple, Optional


class ShortDataInitializer:
    """Initializes short selling data for the watch screen."""
    
    def __init__(self, portfolio, short_integration, logger: Optional[logging.Logger] = None):
        self.portfolio = portfolio
        self.short_integration = short_integration
        self.logger = logger or logging.getLogger(__name__)
    
    def initialize(self) -> Tuple[Dict[str, float], Dict[str, any], bool]:
        """
        Initialize short selling data if available.
        
        Returns:
            Tuple of (short_data_by_name, short_trend_by_name, data_available)
        """
        short_data_by_name = {}
        short_trend_by_name = {}
        
        if not self.short_integration:
            return short_data_by_name, short_trend_by_name, False
        
        try:
            # Check if remote config exists
            config_exists = (os.path.exists('remote_config.json') or 
                           os.path.exists('config/remote_config.json'))
            
            if not config_exists:
                self.logger.info("No remote config found, skipping short features")
                return short_data_by_name, short_trend_by_name, False
            
            # Validate cache
            if not self._is_cache_valid():
                self.logger.info("Short data cache not valid, skipping short features")
                self.logger.info("Tip: Press 'U' in watch screen to fetch fresh data")
                return short_data_by_name, short_trend_by_name, False
            
            # Load from cache
            self._load_from_cache(short_data_by_name, short_trend_by_name)
            
            data_available = len(short_data_by_name) > 0
            return short_data_by_name, short_trend_by_name, data_available
            
        except Exception as e:
            self.logger.warning(f"Failed to initialize short data: {e}")
            return short_data_by_name, short_trend_by_name, False
    
    def _is_cache_valid(self) -> bool:
        """Check if the short data cache is valid."""
        try:
            from short_selling.remote_short_data import load_remote_config, RemoteShortDataFetcher
            remote_config = load_remote_config()
            fetcher = RemoteShortDataFetcher(remote_config)
            return fetcher._is_cache_valid()
        except Exception:
            return False
    
    def _load_from_cache(self, short_data_by_name: Dict, short_trend_by_name: Dict):
        """Load short selling data from cache with timeout."""
        start_time = time.time()
        max_time = 2.0  # Maximum 2 seconds
        
        try:
            summary = self.short_integration.get_portfolio_short_summary()
            portfolio_shorts = summary.get('portfolio_short_positions', [])
            
            # Map by stock name (not ticker)
            for stock_data in portfolio_shorts:
                # Check timeout
                if time.time() - start_time > max_time:
                    self.logger.warning("Short data loading timed out after 2s")
                    break
                
                ticker = stock_data['ticker']
                company_name = stock_data.get('company', '')
                
                # Find stock name in portfolio by ticker
                for name, stock_obj in self.portfolio.stocks.items():
                    if stock_obj.ticker == ticker:
                        short_data_by_name[name] = stock_data['percentage']
                        
                        # Calculate trend if company name available
                        if company_name:
                            try:
                                trend_info = self.short_integration.calculate_short_trend(
                                    company_name,
                                    lookback_days=7,
                                    threshold=0.1
                                )
                                short_trend_by_name[name] = trend_info
                            except Exception as e:
                                self.logger.debug(f"Failed to calculate trend for {name}: {e}")
                        break
                        
        except Exception as e:
            self.logger.warning(f"Error loading short data from cache: {e}")
