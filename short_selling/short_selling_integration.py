"""
Short Selling Integration for yspy Portfolio Manager

Extends the existing portfolio management system to include short selling tracking.
Supports both local fetching and remote data (from server via SSH/HTTP/file).
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Check if remote data is configured
def _check_remote_config():
    """Check if remote_config.json exists and is valid."""
    config_paths = [
        Path('remote_config.json'),
        Path(__file__).parent.parent / 'remote_config.json',
    ]
    for path in config_paths:
        if path.exists():
            return path
    return None


class ShortSellingIntegration:
    """Integration class to add short selling capabilities to the portfolio manager."""
    
    def __init__(self, portfolio_manager, use_remote: bool = None):
        """
        Initialize short selling integration.
        
        Args:
            portfolio_manager: The portfolio manager instance
            use_remote: Force remote (True), local (False), or auto-detect (None)
        """
        self.portfolio = portfolio_manager
        self.short_tracker = None
        self.use_remote = use_remote
        self._initialize_short_tracker()
    
    def _initialize_short_tracker(self):
        """Initialize the short selling tracker (remote or local)."""
        # Auto-detect: use remote if config exists
        if self.use_remote is None:
            remote_config = _check_remote_config()
            self.use_remote = remote_config is not None
            if self.use_remote:
                logger.info(f"Remote config found at {remote_config}, using remote data")
        
        if self.use_remote:
            self._initialize_remote_tracker()
        else:
            self._initialize_local_tracker()
    
    def _initialize_remote_tracker(self):
        """Initialize remote short selling tracker."""
        try:
            from remote.remote_integration_helper import RemoteShortSellingTracker
            portfolio_path = getattr(self.portfolio, 'path', 'portfolio')
            self.short_tracker = RemoteShortSellingTracker(portfolio_path)
            logger.info("Using REMOTE short selling data source")
        except ImportError as e:
            logger.warning(f"Remote tracker not available: {e}, falling back to local")
            self._initialize_local_tracker()
        except Exception as e:
            logger.error(f"Error initializing remote tracker: {e}, falling back to local")
            self._initialize_local_tracker()
    
    def _initialize_local_tracker(self):
        """Initialize local short selling tracker."""
        try:
            from short_selling.short_selling_tracker import ShortSellingTracker
            portfolio_path = getattr(self.portfolio, 'path', 'portfolio')
            self.short_tracker = ShortSellingTracker(portfolio_path)
            logger.info("Using LOCAL short selling data source")
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
    
    def update_short_data(self, force: bool = False) -> Dict:
        """
        Update short selling data for all portfolio stocks.
        
        Args:
            force: If True, force update even if data is current
        
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
        return self.short_tracker.update_short_positions(force=force)
    
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
            from short_selling.remote_short_data import load_remote_config, RemoteShortDataFetcher
            
            config = load_remote_config()
            fetcher = RemoteShortDataFetcher(config)
            # Don't force refresh - use cache if available (important for performance)
            success, data = fetcher.fetch_data(force_refresh=False)
            
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
    
    def calculate_short_trend(self, company_name: str, lookback_days: int = 7, 
                             threshold: float = 0.3) -> Dict:
        """
        Calculate short selling trend for a company.
        
        Compares current short percentage to N days ago to determine if shorts
        are increasing (bearish), decreasing (bullish), or stable.
        
        Args:
            company_name: Name of the company
            lookback_days: Number of days to look back for comparison (default: 7)
            threshold: Minimum change (%) to show directional arrow (default: 0.3)
            
        Returns:
            Dict with keys:
            - trend: 'up', 'down', 'stable', 'strong_up', 'strong_down', 'no_data'
            - arrow: '↑', '↓', '→', '⬆', '⬇', '?'
            - change: Absolute percentage change
            - current: Current percentage
            - past: Past percentage (or None)
        """
        try:
            # Get historical data with extra days for buffer
            history_data = self.get_stock_history(company_name, days=lookback_days + 5)
            
            if not history_data or 'history' not in history_data:
                return {
                    'trend': 'no_data',
                    'arrow': '?',
                    'change': 0.0,
                    'current': None,
                    'past': None
                }
            
            history = history_data['history']
            
            if len(history) < 2:
                return {
                    'trend': 'no_data',
                    'arrow': '?',
                    'change': 0.0,
                    'current': None,
                    'past': None
                }
            
            # Get current (most recent)
            dates = sorted(history.keys(), reverse=True)
            current_date = dates[0]
            current_pct = history[current_date]['percentage']
            
            # Find date approximately N days ago
            target_date = (datetime.now() - timedelta(days=lookback_days)).date()
            target_date_str = target_date.isoformat()
            
            # Find closest past date (on or before target date)
            past_pct = None
            past_date = None
            for date_str in sorted(history.keys(), reverse=True):
                if date_str <= target_date_str:
                    past_pct = history[date_str]['percentage']
                    past_date = date_str
                    break
            
            if past_pct is None:
                # Try to use oldest available date if no date before target
                oldest_date = sorted(history.keys())[0]
                past_pct = history[oldest_date]['percentage']
                past_date = oldest_date
            
            # Calculate change
            change = current_pct - past_pct
            
            # Determine trend with multiple thresholds
            # Strong threshold at 0.5% for double arrows
            strong_threshold = 0.5
            
            if abs(change) < threshold:
                trend = 'stable'
                arrow = '→'
            elif change >= strong_threshold:
                trend = 'strong_up'
                arrow = '⬆'
            elif change > threshold:
                trend = 'up'
                arrow = '↑'
            elif change <= -strong_threshold:
                trend = 'strong_down'
                arrow = '⬇'
            else:  # change < -threshold
                trend = 'down'
                arrow = '↓'
            
            return {
                'trend': trend,
                'arrow': arrow,
                'change': change,
                'current': current_pct,
                'past': past_pct
            }
            
        except Exception as e:
            logger.debug(f"Error calculating trend for {company_name}: {e}")
            return {
                'trend': 'no_data',
                'arrow': '?',
                'change': 0.0,
                'current': None,
                'past': None
            }