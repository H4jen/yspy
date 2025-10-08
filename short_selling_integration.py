"""
Short Selling Integration for yspy Portfolio Manager

Extends the existing portfolio management system to include short selling tracking.
"""

import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ShortSellingIntegration:
    """Integration class to add short selling capabilities to the portfolio manager."""
    
    def __init__(self, portfolio_manager):
        self.portfolio = portfolio_manager
        self.short_tracker = None
        self._initialize_short_tracker()
    
    def _initialize_short_tracker(self):
        """Initialize the short selling tracker."""
        try:
            from short_selling_tracker import ShortSellingTracker
            # Use portfolio.path instead of portfolio.portfolio_path
            portfolio_path = getattr(self.portfolio, 'path', 'portfolio')
            self.short_tracker = ShortSellingTracker(portfolio_path)
        except ImportError:
            logger.warning("Short selling tracker not available")
        except Exception as e:
            logger.error(f"Error initializing short selling tracker: {e}")
            self.short_tracker = None
    
    def get_stock_short_data(self, ticker: str) -> Optional[Dict]:
        """Get short selling data for a specific stock."""
        if not self.short_tracker:
            return None
        return self.short_tracker.get_short_data_for_stock(ticker)
    
    def get_portfolio_short_summary(self) -> Dict:
        """Get short selling summary for the entire portfolio."""
        if not self.short_tracker:
            return {'error': 'Short selling tracker not available'}
        return self.short_tracker.get_portfolio_short_summary()
    
    def update_short_data(self) -> bool:
        """Update short selling data for all portfolio stocks."""
        if not self.short_tracker:
            return False
        return self.short_tracker.update_short_positions()
    
    def add_short_data_to_stock_info(self, stock_info: Dict, ticker: str) -> Dict:
        """Add short selling information to stock info dictionary."""
        if not self.short_tracker:
            return stock_info
            
        short_data = self.get_stock_short_data(ticker)
        if short_data:
            stock_info['short_selling'] = short_data
            
        return stock_info