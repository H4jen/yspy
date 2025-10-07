#!/usr/bin/env python3
"""
yspy - Terminal Stock Portfolio Manager

Main executable for the yspy application. Launch this file to start
the terminal-based stock portfolio management interface.

Usage:
    ./yspy.py
    or
    python3 yspy.py

Key features:
- Real-time stock price monitoring
- Multi-timeframe historical data analysis
- Portfolio profit/loss tracking
- Correlation analysis and visualization
- Comprehensive error handling and logging

Usage:
    python ncurses_app.py

Dependencies:
    - curses (built-in)
    - pandas
    - numpy
    - matplotlib (optional, for plotting)
    - portfolio_manager module
    - ui.display_utils, ui.stock_display, ui.profit_utils modules

Author: yspy (formerly Stock Portfolio Management System)
Project: https://github.com/H4jen/yspy
Date: 2024-2025
"""

import curses
import logging
import sys
from yspy_app import StockPortfolioApp


def main():
    """
    Main entry point for the refactored Stock Portfolio Management Application.
    
    This function initializes and runs the main application using the curses wrapper
    for proper terminal handling and cleanup.
    
    The application provides the following features:
    - Stock portfolio management (add/remove stocks)
    - Share trading (buy/sell with profit tracking)
    - Real-time price monitoring with auto-refresh
    - Profit/loss analysis and reporting
    - Correlation analysis and historical data visualization
    - Scrollable interfaces for large datasets
    
    Error Handling:
        - User-friendly error messages displayed in the ncurses interface
    - Comprehensive logging to yspy.log
    - Graceful exit with proper cleanup
    
    Configuration:
    - All settings managed through app_config.py
    - Portfolio data stored in ./portfolio/ directory
    - Historical data cached for performance
    
    Raises:
        SystemExit: If critical initialization errors occur
    """
    try:
        # Set up logging to file only to prevent interference with ncurses
        logging.basicConfig(
                level=logging.INFO,
                handlers=[
                logging.FileHandler('yspy.log'),
                ]
            )
        
        logger = logging.getLogger(__name__)
        logger.info("Starting Stock Portfolio Management Application (Refactored)")
        
        # Run the main application
        StockPortfolioApp.main()
        
        logger.info("Application completed successfully")
        
    except KeyboardInterrupt:
        print("\\nApplication interrupted by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Critical error starting application: {e}")
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()