#!/usr/bin/env python3
"""
View state management for the watch stocks screen.
Centralizes all state variables for better organization and testability.
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class ViewState:
    """Encapsulates all view state for the watch stocks screen."""
    
    # View mode
    view_mode: str = 'stocks'  # 'stocks' or 'shares'
    
    # Scroll positions
    shares_scroll_pos: int = 0
    stocks_scroll_pos: int = 0
    
    # View options
    shares_compressed: bool = True  # Default to compressed view
    
    # Display flags
    skip_dot_update_once: bool = False
    first_cycle: bool = True
    force_history_next_cycle: bool = False
    
    # Tracking data
    dot_states: Dict[str, Any] = None
    delta_counters: Dict[str, int] = None
    minute_trend_tracker: Dict[str, Any] = None
    
    # Short selling data
    short_data_by_name: Dict[str, float] = None
    short_trend_by_name: Dict[str, Any] = None
    
    def __post_init__(self):
        """Initialize mutable default values."""
        if self.dot_states is None:
            self.dot_states = {}
        if self.delta_counters is None:
            self.delta_counters = {}
        if self.minute_trend_tracker is None:
            self.minute_trend_tracker = {}
        if self.short_data_by_name is None:
            self.short_data_by_name = {}
        if self.short_trend_by_name is None:
            self.short_trend_by_name = {}
    
    def reset_scroll_positions(self):
        """Reset both scroll positions to 0."""
        self.shares_scroll_pos = 0
        self.stocks_scroll_pos = 0
    
    def toggle_view_mode(self):
        """Toggle between stocks and shares view."""
        if self.view_mode == 'stocks':
            self.view_mode = 'shares'
        else:
            self.view_mode = 'stocks'
        self.skip_dot_update_once = True
        self.reset_scroll_positions()
    
    def toggle_shares_compression(self):
        """Toggle between compressed and detailed shares view."""
        self.shares_compressed = not self.shares_compressed
        self.shares_scroll_pos = 0
        self.skip_dot_update_once = True
