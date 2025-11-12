#!/usr/bin/env python3
"""
Page calculation utilities for watch stocks screen.
Handles complex row counting for proper pagination.
"""

from typing import List, Dict, Any


class PageCalculator:
    """Calculates pagination metrics for stocks and shares views."""
    
    @staticmethod
    def calculate_stocks_view_metrics(owned_count: int, highlighted_count: int, 
                                      other_count: int, indices_count: int,
                                      total_lines: int) -> Dict[str, int]:
        """
        Calculate row pointer and max body lines for stocks view.
        
        Args:
            owned_count: Number of owned stocks
            highlighted_count: Number of highlighted stocks
            other_count: Number of other stocks
            indices_count: Number of market indices
            total_lines: Total screen lines (curses.LINES)
            
        Returns:
            Dict with row_ptr, max_body_lines, reserved_bottom_lines
        """
        row_ptr = 1  # Status line
        
        # Header and separator
        row_ptr += 2
        
        # Owned stocks section
        if owned_count > 0:
            row_ptr += owned_count
            if highlighted_count > 0 or other_count > 0:
                row_ptr += 1  # Blank separator
        
        # Highlighted stocks section
        if highlighted_count > 0:
            row_ptr += highlighted_count
            if other_count > 0:
                row_ptr += 1  # Blank separator
        
        # Other stocks section
        row_ptr += other_count
        
        # Market indices section
        if indices_count > 0:
            if owned_count > 0 or highlighted_count > 0 or other_count > 0:
                row_ptr += 1  # Blank separator
            row_ptr += 1  # Separator line
            row_ptr += indices_count
        
        reserved_bottom_lines = 5  # Scroll, totals (2), currency, instructions
        max_body_lines = max(0, total_lines - row_ptr - reserved_bottom_lines)
        
        return {
            'row_ptr': row_ptr,
            'max_body_lines': max_body_lines,
            'reserved_bottom_lines': reserved_bottom_lines
        }
    
    @staticmethod
    def calculate_shares_view_metrics(owned_count: int, highlighted_count: int,
                                      indices_count: int, total_lines: int) -> Dict[str, int]:
        """
        Calculate row pointer and max body lines for shares view.
        
        Args:
            owned_count: Number of owned stocks
            highlighted_count: Number of highlighted stocks (without shares)
            indices_count: Number of highlighted indices
            total_lines: Total screen lines (curses.LINES)
            
        Returns:
            Dict with row_ptr, max_body_lines, reserved_bottom_lines
        """
        row_ptr = 1  # Status line
        
        display_stocks = owned_count + highlighted_count
        if display_stocks > 0:
            row_ptr += 2  # Header + separator
            row_ptr += owned_count  # Owned stock lines
            
            if owned_count > 0 and highlighted_count > 0:
                row_ptr += 1  # Blank row between groups
            
            row_ptr += highlighted_count  # Highlighted stock lines
            row_ptr += 1  # Spacing after display_stocks
        
        if indices_count > 0:
            row_ptr += 1  # Separator line
            row_ptr += indices_count  # Index lines
            row_ptr += 1  # Spacing after indices
        
        row_ptr += 2  # Share details header + separator
        
        reserved_bottom_lines = 5  # Scroll indicator + totals (2 lines) + spacing
        max_body_lines = max(0, total_lines - row_ptr - reserved_bottom_lines)
        
        return {
            'row_ptr': row_ptr,
            'max_body_lines': max_body_lines,
            'reserved_bottom_lines': reserved_bottom_lines
        }
    
    @staticmethod
    def calculate_page_info(scroll_pos: int, max_scroll: int, max_body_lines: int) -> Dict[str, int]:
        """
        Calculate current page and total pages.
        
        Args:
            scroll_pos: Current scroll position
            max_scroll: Maximum scroll position
            max_body_lines: Lines visible in body
            
        Returns:
            Dict with current_page and total_pages
        """
        if max_body_lines <= 0:
            return {'current_page': 1, 'total_pages': 1}
        
        total_pages = (max_scroll + max_body_lines - 1) // max_body_lines + 1
        
        # If at max_scroll, we're on the last page
        if scroll_pos >= max_scroll and max_scroll > 0:
            current_page = total_pages
        else:
            current_page = scroll_pos // max_body_lines + 1
        
        return {
            'current_page': current_page,
            'total_pages': total_pages
        }
