"""
Short Selling Integration for yspy Portfolio Manager

Extends the existing portfolio management system to include short selling tracking.
"""

import logging
from typing import Dict, Optional, List
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
    
    def update_short_data(self) -> Dict:
        """
        Update short selling data for all portfolio stocks.
        
        Returns:
            Dict with success status, update status, message, and stats
        """
        if not self.short_tracker:
            return {
                'success': False,
                'updated': False,
                'message': 'Short selling tracker not available',
                'stats': {}
            }
        return self.short_tracker.update_short_positions()
    
    def add_short_data_to_stock_info(self, stock_info: Dict, ticker: str) -> Dict:
        """Add short selling information to stock info dictionary."""
        if not self.short_tracker:
            return stock_info
            
        short_data = self.get_stock_short_data(ticker)
        if short_data:
            stock_info['short_selling'] = short_data
            
        return stock_info
    
    def get_positions_by_holder(self) -> Dict:
        """Get all positions grouped by holder name."""
        if not self.short_tracker:
            return {}
        return self.short_tracker.get_positions_by_holder()
    
    def get_historical_data(self) -> Dict:
        """
        Get historical short position data from remote source.
        
        Returns:
            Dict with company names as keys, containing ticker and history data
        """
        try:
            from remote_short_data import load_remote_config, RemoteShortDataFetcher
            
            config = load_remote_config()
            fetcher = RemoteShortDataFetcher(config)
            success, data = fetcher.fetch_data()
            
            if success and data and 'historical' in data:
                return data['historical']
            
            return {}
            
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return {}
    
    def get_stock_history(self, company_name: str, days: int = 30) -> Dict:
        """
        Get historical data for a specific company.
        
        Args:
            company_name: Name of the company
            days: Number of days to retrieve
            
        Returns:
            Dict with dates as keys and position data as values
        """
        historical = self.get_historical_data()
        
        if company_name not in historical:
            return {}
        
        company_data = historical[company_name]
        history = company_data.get('history', {})
        
        # Filter to last N days
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
        
        return {
            'ticker': company_data.get('ticker', ''),
            'history': {
                date: data for date, data in history.items()
                if date >= cutoff
            }
        }
    
    def get_companies_with_history(self) -> List[str]:
        """Get list of companies that have historical data."""
        historical = self.get_historical_data()
        return sorted(historical.keys())