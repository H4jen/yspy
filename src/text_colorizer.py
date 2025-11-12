#!/usr/bin/env python3
"""
Text coloring utilities for stock data display.
Handles profit/loss and price change color coding.
"""

import curses
import re
from typing import Tuple, Optional


class TextColorizer:
    """Handles colored text rendering for stock values."""
    
    def __init__(self, screen):
        self.screen = screen
    
    def safe_addstr(self, row: int, col: int, text: str, attr=None):
        """Safely add string to screen without crashing on boundary."""
        try:
            if attr is not None:
                self.screen.addstr(row, col, text, attr)
            else:
                self.screen.addstr(row, col, text)
        except curses.error:
            pass
    
    def color_shares_line(self, row: int, line: str, line_index: int, 
                         shares_compressed: bool, max_cols: int) -> bool:
        """
        Color a shares detail line with profit/loss and -1d values.
        
        Args:
            row: Screen row to draw on
            line: Text line to color
            line_index: Index in the shares list (for skipping headers)
            shares_compressed: Whether in compressed mode
            max_cols: Maximum columns available
            
        Returns:
            True if coloring was applied, False if line drawn normally
        """
        # Skip headers and separators
        if line_index < 2 or line.startswith('-') or not line.strip():
            self.safe_addstr(row, 0, line)
            return False
        
        parts = line.split()
        if len(parts) < 4:
            self.safe_addstr(row, 0, line)
            return False
        
        try:
            # Handle TOTAL row in compressed view
            if shares_compressed and line.strip().startswith("TOTAL"):
                return self._color_total_row(row, line, max_cols)
            
            # Regular data rows
            if len(parts) < 6:
                self.safe_addstr(row, 0, line)
                return False
            
            profit_loss_str = parts[4]
            day_1d_str = parts[5]
            
            profit_loss_val = float(profit_loss_str)
            day_1d_val = float(day_1d_str)
            
            # Find positions of values in the line
            if shares_compressed and len(parts) >= 4:
                # Skip past first 4 columns to find profit/loss
                search_start = 0
                for i in range(4):
                    search_start = line.find(parts[i], search_start) + len(parts[i])
                pl_start = line.find(profit_loss_str, search_start)
            else:
                pl_start = line.find(profit_loss_str)
            
            day_1d_start = line.find(day_1d_str, pl_start + len(profit_loss_str))
            
            if pl_start <= 0 or day_1d_start <= 0:
                self.safe_addstr(row, 0, line)
                return False
            
            # Render line with colors
            self._render_colored_segments(row, line, pl_start, day_1d_start,
                                         profit_loss_str, day_1d_str,
                                         profit_loss_val, day_1d_val, max_cols)
            return True
            
        except (ValueError, IndexError):
            self.safe_addstr(row, 0, line)
            return False
    
    def _color_total_row(self, row: int, line: str, max_cols: int) -> bool:
        """Color the TOTAL summary row in compressed view."""
        try:
            # Find all numeric values
            numbers = re.findall(r'-?\d+\.\d+', line)
            if len(numbers) < 3:
                self.safe_addstr(row, 0, line)
                return False
            
            # Numbers are: TotalCost, Profit/Loss, -1d
            profit_loss_str = numbers[1]
            day_1d_str = numbers[2]
            profit_loss_val = float(profit_loss_str)
            day_1d_val = float(day_1d_str)
            
            pl_start = line.find(profit_loss_str)
            day_1d_start = line.find(day_1d_str, pl_start + len(profit_loss_str))
            
            if pl_start <= 0 or day_1d_start <= 0:
                self.safe_addstr(row, 0, line)
                return False
            
            self._render_colored_segments(row, line, pl_start, day_1d_start,
                                         profit_loss_str, day_1d_str,
                                         profit_loss_val, day_1d_val, max_cols)
            return True
            
        except Exception:
            self.safe_addstr(row, 0, line)
            return False
    
    def _render_colored_segments(self, row: int, line: str, 
                                 pl_start: int, day_1d_start: int,
                                 profit_loss_str: str, day_1d_str: str,
                                 profit_loss_val: float, day_1d_val: float,
                                 max_cols: int):
        """Render a line with colored profit/loss and -1d segments."""
        from ui.display_utils import color_for_value
        
        # Text before profit/loss
        before = line[:pl_start]
        self.safe_addstr(row, 0, before)
        col_pos = len(before)
        
        # Profit/loss with color
        if col_pos < max_cols - len(profit_loss_str):
            self.safe_addstr(row, col_pos, profit_loss_str, color_for_value(profit_loss_val))
            col_pos += len(profit_loss_str)
        
        # Text between profit/loss and -1d
        between = line[pl_start + len(profit_loss_str):day_1d_start]
        if between and col_pos < max_cols - len(between):
            self.safe_addstr(row, col_pos, between)
            col_pos += len(between)
        
        # -1d with color
        if col_pos < max_cols - len(day_1d_str):
            self.safe_addstr(row, col_pos, day_1d_str, color_for_value(day_1d_val))
            col_pos += len(day_1d_str)
        
        # Remaining text
        after = line[day_1d_start + len(day_1d_str):]
        if after and col_pos < max_cols - 1:
            self.safe_addstr(row, col_pos, after)
