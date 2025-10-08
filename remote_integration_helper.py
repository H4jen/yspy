#!/usr/bin/env python3
"""
Integration helper for remote short selling data.

This module provides a drop-in replacement for local short selling data fetching
that uses the remote data system instead.

Usage:
    # In short_selling_integration.py, replace:
    from short_selling_tracker import ShortSellingTracker
    
    # With:
    from remote_integration_helper import RemoteShortSellingTracker as ShortSellingTracker
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from remote_short_data import (
    RemoteDataConfig,
    RemoteShortDataFetcher,
    load_remote_config
)

logger = logging.getLogger(__name__)


class RemoteShortSellingTracker:
    """
    Drop-in replacement for ShortSellingTracker that uses remote data.
    
    Compatible with existing short_selling_integration.py code.
    """
    
    def __init__(self, portfolio_path: str = "portfolio"):
        """
        Initialize tracker with remote data source.
        
        Args:
            portfolio_path: Path to portfolio directory (for compatibility)
        """
        self.portfolio_path = Path(portfolio_path)
        
        # Load remote configuration
        try:
            self.remote_config = load_remote_config('remote_config.json')
            self.remote_fetcher = RemoteShortDataFetcher(self.remote_config)
            self.use_remote = True
            logger.info("Remote data source configured successfully")
        except Exception as e:
            logger.warning(f"Could not configure remote data: {e}")
            logger.info("Falling back to local tracker")
            # Fallback to local tracker
            from short_selling_tracker import ShortSellingTracker
            self.local_tracker = ShortSellingTracker(portfolio_path)
            self.use_remote = False
        
        # Cache for positions
        self._positions_cache = []
        self._positions_by_holder_cache = {}
        self._cache_timestamp = None
    
    def update_short_positions(self) -> Dict:
        """
        Update short positions (fetch from remote or trigger local update).
        
        Returns:
            Dict with keys: success, updated, message, stats
        """
        if self.use_remote:
            try:
                # Force refresh from remote
                success, data = self.remote_fetcher.fetch_data(force_refresh=True)
                
                if success and data:
                    # Update cache
                    self._positions_cache = data['positions']
                    self._cache_timestamp = datetime.now()
                    
                    # Convert to ShortPosition objects for compatibility
                    from short_selling_tracker import ShortPosition
                    self._positions_cache = [
                        self._dict_to_position(pos) for pos in data['positions']
                    ]
                    
                    # Calculate stats
                    stats = {
                        'total_positions': len(self._positions_cache),
                        'positions_with_holders': sum(
                            1 for pos in self._positions_cache 
                            if pos.individual_holders
                        ),
                        'last_update': data.get('last_updated'),
                        'source': 'remote'
                    }
                    
                    return {
                        'success': True,
                        'updated': True,
                        'message': f"Updated from remote source: {len(self._positions_cache)} positions",
                        'stats': stats
                    }
                else:
                    return {
                        'success': False,
                        'updated': False,
                        'message': "Failed to fetch from remote source",
                        'stats': {}
                    }
                    
            except Exception as e:
                logger.error(f"Error updating from remote: {e}")
                return {
                    'success': False,
                    'updated': False,
                    'message': f"Error: {str(e)}",
                    'stats': {}
                }
        else:
            # Use local tracker
            return self.local_tracker.update_short_positions()
    
    def get_portfolio_short_data(self, stock_portfolio: Dict) -> Dict:
        """
        Get short selling data for portfolio stocks.
        
        Args:
            stock_portfolio: Dictionary with stock data
            
        Returns:
            Dict mapping ticker to short position data
        """
        if self.use_remote:
            # Ensure we have fresh data
            if not self._positions_cache:
                self._load_cached_data()
            
            # Build result dict
            result = {}
            for ticker, stock_data in stock_portfolio.items():
                # Find matching position
                company_name = stock_data.get('company_name', ticker.replace('_', '.'))
                
                for pos in self._positions_cache:
                    if (pos.ticker == company_name or 
                        pos.company_name.lower() == company_name.lower()):
                        result[ticker] = {
                            'ticker': pos.ticker,
                            'company_name': pos.company_name,
                            'position_percentage': pos.position_percentage,
                            'position_date': pos.position_date,
                            'individual_holders': pos.individual_holders,
                            'holder_count': len(pos.individual_holders) if pos.individual_holders else 0
                        }
                        break
            
            return result
        else:
            return self.local_tracker.get_portfolio_short_data(stock_portfolio)
    
    def get_short_position(self, ticker: str) -> Optional[object]:
        """
        Get short position for a specific ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            ShortPosition object or None
        """
        if self.use_remote:
            if not self._positions_cache:
                self._load_cached_data()
            
            # Normalize ticker
            ticker_normalized = ticker.replace('_', '.')
            
            for pos in self._positions_cache:
                if (pos.ticker.upper() == ticker_normalized.upper() or
                    ticker_normalized.upper() in pos.ticker.upper()):
                    return pos
            
            return None
        else:
            return self.local_tracker.get_short_position(ticker)
    
    def get_high_short_interest_stocks(self, threshold: float = 10.0) -> List:
        """
        Get stocks with high short interest.
        
        Args:
            threshold: Minimum short interest percentage
            
        Returns:
            List of ShortPosition objects
        """
        if self.use_remote:
            if not self._positions_cache:
                self._load_cached_data()
            
            return [
                pos for pos in self._positions_cache
                if pos.position_percentage >= threshold
            ]
        else:
            return self.local_tracker.get_high_short_interest_stocks(threshold)
    
    def get_positions_by_holder(self) -> Dict[str, List]:
        """
        Get all positions grouped by holder.
        
        Returns:
            Dict mapping holder name to list of positions
        """
        if self.use_remote:
            if not self._positions_by_holder_cache:
                self._build_holder_cache()
            
            return self._positions_by_holder_cache
        else:
            return self.local_tracker.get_positions_by_holder()
    
    def get_short_history(self, ticker: str, days: int = 30) -> Dict:
        """
        Get historical short position data for a ticker.
        
        Args:
            ticker: Stock ticker
            days: Number of days to retrieve
            
        Returns:
            Dict with dates as keys and position data as values
        """
        if self.use_remote:
            try:
                success, data = self.remote_fetcher.fetch_data()
                
                if success and data and 'historical' in data:
                    historical = data['historical']
                    
                    # Find matching company
                    ticker_normalized = ticker.replace('_', '.')
                    
                    for company_name, company_data in historical.items():
                        if (company_data.get('ticker', '').upper() == ticker_normalized.upper() or
                            ticker_normalized.upper() in company_data.get('ticker', '').upper()):
                            
                            # Filter to last N days
                            cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
                            history = company_data.get('history', {})
                            
                            return {
                                date: data for date, data in history.items()
                                if date >= cutoff
                            }
                
                return {}
                
            except Exception as e:
                logger.error(f"Error fetching history: {e}")
                return {}
        else:
            # Local tracker might not have this method
            logger.warning("Historical data not available with local tracker")
            return {}
    
    def _load_cached_data(self):
        """Load data from cache or remote."""
        try:
            success, data = self.remote_fetcher.fetch_data()
            
            if success and data:
                from short_selling_tracker import ShortPosition
                self._positions_cache = [
                    self._dict_to_position(pos) for pos in data['positions']
                ]
                self._cache_timestamp = datetime.now()
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            self._positions_cache = []
    
    def _dict_to_position(self, pos_dict: Dict):
        """Convert dict to ShortPosition object."""
        from short_selling_tracker import ShortPosition, PositionHolder
        
        # Convert individual holders
        holders = []
        for h in pos_dict.get('individual_holders', []):
            holders.append(PositionHolder(
                holder_name=h['holder_name'],
                position_percentage=h['position_percentage'],
                position_date=h['position_date']
            ))
        
        return ShortPosition(
            ticker=pos_dict['ticker'],
            company_name=pos_dict['company_name'],
            position_holder=pos_dict['position_holder'],
            position_percentage=pos_dict['position_percentage'],
            position_date=pos_dict['position_date'],
            market=pos_dict['market'],
            threshold_crossed=pos_dict.get('threshold_crossed'),
            individual_holders=holders if holders else None
        )
    
    def _build_holder_cache(self):
        """Build the positions-by-holder cache."""
        if not self._positions_cache:
            self._load_cached_data()
        
        self._positions_by_holder_cache = {}
        
        for pos in self._positions_cache:
            if pos.individual_holders:
                for holder in pos.individual_holders:
                    if holder.holder_name not in self._positions_by_holder_cache:
                        self._positions_by_holder_cache[holder.holder_name] = []
                    
                    self._positions_by_holder_cache[holder.holder_name].append(pos)


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing RemoteShortSellingTracker...")
    print()
    
    tracker = RemoteShortSellingTracker()
    
    if tracker.use_remote:
        print("✅ Using remote data source")
        
        # Test update
        print("\nTesting update...")
        result = tracker.update_short_positions()
        print(f"  Success: {result['success']}")
        print(f"  Message: {result['message']}")
        if result.get('stats'):
            print(f"  Total positions: {result['stats']['total_positions']}")
        
        # Test get high interest
        print("\nTesting high short interest...")
        high_shorts = tracker.get_high_short_interest_stocks(10.0)
        print(f"  Found {len(high_shorts)} stocks with >10% short interest")
        
        # Test holders
        print("\nTesting position holders...")
        holders = tracker.get_positions_by_holder()
        print(f"  Found {len(holders)} unique holders")
        
    else:
        print("⚠️  Using local data source (remote not configured)")
