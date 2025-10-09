#!/usr/bin/env python3
"""
yspy - Application Configuration

Centralized configuration management for the stock portfolio application.

Project: https://github.com/H4jen/yspy
"""

from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class AppConfig:
    """Application configuration settings."""
    
    # Refresh settings
    REFRESH_INTERVAL_SECONDS: float = 10.0
    REFRESH_TICK_SLICE: float = 0.1
    
    # File paths
    PORTFOLIO_DIRECTORY: str = "portfolio"
    PORTFOLIO_FILENAME: str = "stockPortfolio.json"
    
    # Display settings
    CORRELATION_COLUMN_WIDTH: int = 8
    MAX_DISPLAY_LINES_OFFSET: int = 3  # Lines reserved for headers/footers
    
    # Color thresholds
    POSITIVE_THRESHOLD: float = 0.0
    HIGH_CORRELATION_THRESHOLD: float = 0.7
    LOW_CORRELATION_THRESHOLD: float = -0.3
    
    # Historical data settings
    DEFAULT_PERIOD: str = "6mo"
    DEFAULT_INTERVAL: str = "1d"
    DEFAULT_CORRELATION_METHOD: str = "pearson"
    
    # UI settings
    MENU_TITLE: str = "Stock Portfolio Management"
    
    @property
    def refresh_ticks(self) -> int:
        """Calculate number of refresh ticks based on interval and slice."""
        return int(self.REFRESH_INTERVAL_SECONDS / self.REFRESH_TICK_SLICE)
    
    def get_portfolio_path(self, base_path: Optional[str] = None) -> str:
        """Get the full portfolio directory path."""
        if base_path is None:
            # Get project root (parent of src/)
            src_dir = os.path.dirname(os.path.abspath(__file__))
            base_path = os.path.dirname(src_dir)
        return os.path.join(base_path, self.PORTFOLIO_DIRECTORY)
    
    def get_portfolio_file_path(self, base_path: Optional[str] = None) -> str:
        """Get the full portfolio file path."""
        return os.path.join(self.get_portfolio_path(base_path), self.PORTFOLIO_FILENAME)


# Global configuration instance
config = AppConfig()