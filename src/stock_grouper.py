#!/usr/bin/env python3
"""
Stock grouping utilities for organizing stocks by category.
Separates stocks into owned, highlighted, other, and market indices.
"""

from typing import List, Dict, Any, Tuple


class StockGrouper:
    """Groups stocks into categories for organized display."""
    
    def __init__(self, portfolio):
        self.portfolio = portfolio
    
    def group_stocks(self, stock_prices: List[Dict[str, Any]]) -> Tuple[List, List, List, List]:
        """
        Group stocks into four categories:
        1. Stocks with shares (owned)
        2. Highlighted stocks (without shares)
        3. Other stocks (not owned, not highlighted)
        4. Market indices (tickers starting with ^)
        
        Args:
            stock_prices: List of stock price dictionaries
            
        Returns:
            Tuple of (owned_stocks, highlighted_stocks, other_stocks, market_indices)
        """
        owned_stocks = []
        highlighted_stocks = []
        other_stocks = []
        market_indices = []
        
        for sp in stock_prices:
            name = sp.get("name", "")
            ticker = sp.get("ticker", "")
            
            # Check if it's a market index
            if ticker.startswith('^'):
                market_indices.append(sp)
                continue
            
            # Get stock object and check ownership
            stock_obj = self.portfolio.stocks.get(name)
            has_shares = stock_obj and sum(sh.volume for sh in stock_obj.holdings) > 0
            is_highlighted = self.portfolio.is_highlighted(name)
            
            # Categorize
            if has_shares:
                owned_stocks.append(sp)
            elif is_highlighted:
                highlighted_stocks.append(sp)
            else:
                other_stocks.append(sp)
        
        return owned_stocks, highlighted_stocks, other_stocks, market_indices
    
    def group_for_shares_view(self, stock_prices: List[Dict[str, Any]]) -> Tuple[List, List, List]:
        """
        Group stocks for shares view:
        1. Stocks with shares (owned)
        2. Highlighted stocks (without shares)
        3. Highlighted indices
        
        Args:
            stock_prices: List of stock price dictionaries
            
        Returns:
            Tuple of (owned_stocks, highlighted_stocks, highlighted_indices)
        """
        owned_stocks = []
        highlighted_stocks = []
        highlighted_indices = []
        
        for sp in stock_prices:
            name = sp.get("name", "")
            ticker = sp.get("ticker", "")
            
            # Check if it's a market index
            if ticker.startswith('^'):
                if self.portfolio.is_highlighted(name):
                    highlighted_indices.append(sp)
                continue
            
            stock_obj = self.portfolio.stocks.get(name)
            has_shares = stock_obj and sum(sh.volume for sh in stock_obj.holdings) > 0
            is_highlighted = self.portfolio.is_highlighted(name)
            
            if has_shares:
                owned_stocks.append(sp)
            elif is_highlighted:
                highlighted_stocks.append(sp)
        
        return owned_stocks, highlighted_stocks, highlighted_indices
