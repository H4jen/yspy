#!/usr/bin/env python3
"""
TickerTerm - Base UI Handler Classes

Provides common functionality and abstract base classes for all UI handlers,
ensuring consistent behavior across the application.

Project: https://github.com/H4jen/tickerterm
"""

import curses
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Any
from app_config import config


class BaseUIHandler(ABC):
    """Base class for all UI handlers providing common functionality."""
    
    def __init__(self, stdscr, portfolio):
        self.stdscr = stdscr
        self.portfolio = portfolio
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def safe_addstr(self, row: int, col: int, text: str, attr: int = 0) -> None:
        """Safely add string to screen, handling window boundary checks."""
        try:
            if row < 0 or col < 0:
                return
            h, w = self.stdscr.getmaxyx()
            if row >= h or col >= w:
                return
            if text is None:
                text = ""
            max_len = w - col - 1
            if max_len <= 0:
                return
            self.stdscr.addstr(row, col, str(text)[:max_len], attr)
        except curses.error:
            # Ignore curses errors (e.g., writing to last cell)
            pass
        except Exception as e:
            self.logger.warning(f"Error in safe_addstr: {e}")
    
    def get_user_input(self, prompt: str, row: int, col: int = 0, 
                      validator=None, max_length: Optional[int] = None) -> Optional[str]:
        """Get user input with validation."""
        self.safe_addstr(row, col, prompt)
        self.stdscr.refresh()
        
        curses.echo()
        self.stdscr.nodelay(False)
        try:
            user_input = self.stdscr.getstr().decode('utf-8').strip()
            if max_length and len(user_input) > max_length:
                user_input = user_input[:max_length]
            
            if validator and not validator(user_input):
                return None
                
            return user_input
        except (ValueError, UnicodeDecodeError):
            return None
        finally:
            curses.noecho()
    
    def get_numeric_input(self, prompt: str, row: int, col: int = 0, 
                         min_val: Optional[float] = None, 
                         max_val: Optional[float] = None,
                         integer_only: bool = False) -> Optional[float]:
        """Get numeric input from user with validation."""
        def validator(value: str) -> bool:
            try:
                if integer_only:
                    num = int(value)
                else:
                    num = float(value)
                
                if min_val is not None and num < min_val:
                    return False
                if max_val is not None and num > max_val:
                    return False
                return True
            except ValueError:
                return False
        
        result = self.get_user_input(prompt, row, col, validator)
        if result is None:
            return None
        
        try:
            return int(result) if integer_only else float(result)
        except ValueError:
            return None
    
    def confirm_action(self, message: str, row: int, col: int = 0) -> bool:
        """Show confirmation dialog and return True if confirmed."""
        self.safe_addstr(row, col, f"{message} (y/n): ")
        self.stdscr.refresh()
        
        curses.echo()
        try:
            response = self.stdscr.getstr().decode('utf-8').strip().lower()
            return response in ('y', 'yes')
        except (ValueError, UnicodeDecodeError):
            return False
        finally:
            curses.noecho()
    
    def show_message(self, message: str, row: int = None, wait_for_key: bool = True) -> None:
        """Display a message and optionally wait for key press."""
        if row is None:
            row = curses.LINES - 2
        
        self.safe_addstr(row, 0, message)
        if wait_for_key:
            self.safe_addstr(row + 1, 0, "Press any key to continue...")
            self.stdscr.refresh()
            self.stdscr.getch()
    
    def display_scrollable_list(self, title: str, lines: List[str], 
                               color_callback=None, 
                               instructions: str = "Use UP/DOWN arrows to scroll, ESC to exit") -> None:
        """Display a scrollable list with optional color coding."""
        scroll_pos = 0
        max_lines = curses.LINES - config.MAX_DISPLAY_LINES_OFFSET
        
        self.stdscr.nodelay(True) if hasattr(self, '_watch_mode') else None
        
        try:
            while True:
                self.stdscr.clear()
                self.safe_addstr(0, 0, title)
                self.safe_addstr(1, 0, "-" * min(80, curses.COLS - 1))
                
                # Display lines with scrolling
                for idx, line in enumerate(lines[scroll_pos:scroll_pos + max_lines - 2]):
                    display_row = idx + 2
                    if display_row >= curses.LINES - 1:
                        break
                    
                    if color_callback:
                        color_callback(display_row, line)
                    else:
                        self.safe_addstr(display_row, 0, line)
                
                # Show scroll indicator
                if len(lines) > max_lines - 2:
                    scroll_info = f"Showing {scroll_pos + 1}-{min(scroll_pos + max_lines - 2, len(lines))} of {len(lines)}"
                    self.safe_addstr(curses.LINES - 2, 0, scroll_info)
                
                self.safe_addstr(curses.LINES - 1, 0, instructions)
                self.stdscr.refresh()
                
                # Handle key input
                key = self.stdscr.getch()
                if key == -1:  # No key pressed (non-blocking mode)
                    continue
                elif key == 27 or key == ord('q'):  # ESC or 'q' to exit
                    break
                elif key == curses.KEY_UP and scroll_pos > 0:
                    scroll_pos -= 1
                elif key == curses.KEY_DOWN and scroll_pos < len(lines) - (max_lines - 2):
                    scroll_pos += 1
                elif hasattr(self, 'handle_additional_keys'):
                    # Allow subclasses to handle additional keys
                    if self.handle_additional_keys(key, scroll_pos):
                        continue
                else:
                    break
                    
        finally:
            self.stdscr.nodelay(False)
    
    def clear_and_display_header(self, title: str) -> int:
        """Clear screen and display header, return next available row."""
        self.stdscr.clear()
        self.safe_addstr(0, 0, title)
        self.safe_addstr(1, 0, "-" * min(len(title) + 10, curses.COLS - 1))
        return 3
    
    @abstractmethod
    def handle(self) -> None:
        """Handle the main logic for this UI handler."""
        pass


class ScrollableUIHandler(BaseUIHandler):
    """Base class for handlers that need scrolling functionality."""
    
    def __init__(self, stdscr, portfolio):
        super().__init__(stdscr, portfolio)
        self.scroll_pos = 0
    
    def reset_scroll(self):
        """Reset scroll position to top."""
        self.scroll_pos = 0
    
    def handle_scroll_keys(self, key: int, max_lines: int, total_lines: int) -> bool:
        """Handle scrolling keys. Returns True if key was handled."""
        if key == curses.KEY_UP and self.scroll_pos > 0:
            self.scroll_pos -= 1
            return True
        elif key == curses.KEY_DOWN and self.scroll_pos < total_lines - max_lines:
            self.scroll_pos += 1
            return True
        return False


class RefreshableUIHandler(BaseUIHandler):
    """Base class for handlers that auto-refresh data."""
    
    def __init__(self, stdscr, portfolio):
        super().__init__(stdscr, portfolio)
        self._refresh_cycle = 0
        self._max_refresh_cycles = config.refresh_ticks
    
    def should_refresh(self) -> bool:
        """Check if data should be refreshed."""
        self._refresh_cycle += 1
        if self._refresh_cycle >= self._max_refresh_cycles:
            self._refresh_cycle = 0
            return True
        return False
    
    def wait_for_refresh_or_key(self) -> Optional[int]:
        """Wait for refresh interval or key press. Returns key code if pressed."""
        for _ in range(config.refresh_ticks):
            key = self.stdscr.getch()
            if key != -1:
                return key
            import time
            time.sleep(config.REFRESH_TICK_SLICE)
        return None