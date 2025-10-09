"""
AI Assistant Menu Handler
Provides interactive AI chat interface for portfolio analysis and assistance.
"""

import curses
import textwrap
from typing import List, Tuple

try:
    from ai_agent import YSpyAIAgent
    from ai_agent.prompts import get_quick_response, get_contextual_prompt
    from config.ai_config import get_cost_summary
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False


class AIAssistantHandler:
    """Handler for AI Assistant menu."""
    
    def __init__(self, stdscr, portfolio):
        """
        Initialize AI assistant handler.
        
        Args:
            stdscr: Curses window
            portfolio: PortfolioManager instance
        """
        self.stdscr = stdscr
        self.portfolio = portfolio
        self.agent = None
        
        if AI_AVAILABLE:
            try:
                self.agent = YSpyAIAgent(portfolio)
            except Exception as e:
                self.error_message = str(e)
        else:
            self.error_message = "AI agent dependencies not installed. Run: pip install anthropic openai google-generativeai pypdf"
    
    def safe_addstr(self, y, x, text, attr=curses.A_NORMAL):
        """Safely add string to screen."""
        try:
            if y < curses.LINES and x < curses.COLS:
                max_len = curses.COLS - x - 1
                if len(text) > max_len:
                    text = text[:max_len]
                self.stdscr.addstr(y, x, text, attr)
        except curses.error:
            pass
    
    def handle(self):
        """Main handler for AI Assistant menu."""
        if not AI_AVAILABLE or not self.agent or not self.agent.is_available:
            self._show_setup_instructions()
            return
        
        # Show AI Assistant menu
        while True:
            choice = self._show_ai_menu()
            
            if choice == '0':
                break
            elif choice == '1':
                self._chat_interface()
            elif choice == '2':
                self._quick_portfolio_analysis()
            elif choice == '3':
                self._analyze_specific_stock()
            elif choice == '4':
                self._show_usage_and_costs()
            elif choice == '5':
                self._show_settings()
            elif choice == '6':
                self._test_connection()
    
    def _show_ai_menu(self) -> str:
        """Show AI Assistant menu and get selection."""
        self.stdscr.clear()
        
        row = 0
        self.safe_addstr(row, 0, "=" * min(curses.COLS - 1, 80))
        row += 1
        self.safe_addstr(row, 0, "🤖 AI ASSISTANT", curses.A_BOLD)
        row += 1
        self.safe_addstr(row, 0, "=" * min(curses.COLS - 1, 80))
        row += 2
        
        self.safe_addstr(row, 0, "1. Chat with AI")
        row += 1
        self.safe_addstr(row, 0, "2. Quick Portfolio Analysis")
        row += 1
        self.safe_addstr(row, 0, "3. Analyze Specific Stock")
        row += 1
        self.safe_addstr(row, 0, "4. Usage & Costs")
        row += 1
        self.safe_addstr(row, 0, "5. Settings & Status")
        row += 1
        self.safe_addstr(row, 0, "6. Test Connection")
        row += 2
        self.safe_addstr(row, 0, "0. Back to Main Menu")
        row += 2
        
        self.safe_addstr(row, 0, "Select option: ")
        self.stdscr.refresh()
        
        # Use getch() for single key press (like main menu)
        try:
            key = self.stdscr.getch()
            choice = chr(key) if 32 <= key <= 126 else '0'
        except:
            choice = '0'
        
        return choice
    
    def _chat_interface(self):
        """Interactive chat interface."""
        self.stdscr.clear()
        
        messages = []
        scroll_pos = 0
        
        while True:
            # Calculate layout
            header_lines = 3
            footer_lines = 5
            chat_area_height = curses.LINES - header_lines - footer_lines
            
            # Display header
            self.safe_addstr(0, 0, "=" * min(curses.COLS - 1, 80))
            self.safe_addstr(1, 0, "💬 AI Chat (Type 'exit' or 'quit' to return, 'clear' to clear history)")
            self.safe_addstr(2, 0, "=" * min(curses.COLS - 1, 80))
            
            # Display messages
            display_messages = self._format_messages_for_display(messages)
            visible_start = max(0, len(display_messages) - chat_area_height + scroll_pos)
            visible_end = visible_start + chat_area_height
            
            row = header_lines
            for line in display_messages[visible_start:visible_end]:
                if row >= curses.LINES - footer_lines:
                    break
                
                # Color code: You vs AI
                if line.startswith("You: "):
                    self.safe_addstr(row, 0, line, curses.A_BOLD)
                elif line.startswith("AI: "):
                    self.safe_addstr(row, 0, line, curses.color_pair(3) if curses.has_colors() else curses.A_NORMAL)
                else:
                    self.safe_addstr(row, 0, line)
                row += 1
            
            # Display input prompt
            input_row = curses.LINES - 3
            self.safe_addstr(input_row, 0, "-" * min(curses.COLS - 1, 80))
            self.safe_addstr(input_row + 1, 0, "You: ")
            self.stdscr.refresh()
            
            # Get input
            curses.echo()
            try:
                user_input = self.stdscr.getstr(input_row + 1, 5, curses.COLS - 10).decode('utf-8').strip()
            except:
                user_input = ""
            curses.noecho()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['exit', 'quit']:
                break
            
            if user_input.lower() == 'clear':
                messages = []
                self.agent.clear_conversation()
                continue
            
            # Add user message
            messages.append(('user', user_input))
            
            # Show "thinking" indicator
            self.safe_addstr(curses.LINES - 2, 0, "AI is thinking...", curses.A_DIM)
            self.stdscr.refresh()
            
            # Get AI response
            response = self.agent.chat(user_input, include_portfolio_context=False)
            
            # Add AI response
            messages.append(('ai', response['response']))
            if response['cost'] > 0:
                messages.append(('system', f"[Cost: ${response['cost']:.6f}]"))
            
            # Clear screen for next iteration
            self.stdscr.clear()
    
    def _format_messages_for_display(self, messages: List[Tuple[str, str]]) -> List[str]:
        """Format messages for display with word wrapping."""
        display_lines = []
        max_width = min(curses.COLS - 2, 78)
        
        for sender, content in messages:
            if sender == 'user':
                prefix = "You: "
            elif sender == 'ai':
                prefix = "AI: "
            else:  # system
                prefix = ""
            
            # Word wrap the content
            wrapped = textwrap.wrap(content, width=max_width - len(prefix))
            
            if wrapped:
                display_lines.append(prefix + wrapped[0])
                for line in wrapped[1:]:
                    display_lines.append(" " * len(prefix) + line)
            else:
                display_lines.append(prefix)
            
            display_lines.append("")  # Empty line between messages
        
        return display_lines
    
    def _quick_portfolio_analysis(self):
        """Run quick portfolio analysis."""
        self.stdscr.clear()
        
        self.safe_addstr(0, 0, "=" * min(curses.COLS - 1, 80))
        self.safe_addstr(1, 0, "📊 Quick Portfolio Analysis", curses.A_BOLD)
        self.safe_addstr(2, 0, "=" * min(curses.COLS - 1, 80))
        self.safe_addstr(4, 0, "Analyzing your portfolio with AI...")
        self.stdscr.refresh()
        
        # Get analysis
        analysis = self.agent.quick_analyze_portfolio()
        
        # Display results
        self.stdscr.clear()
        self.safe_addstr(0, 0, "=" * min(curses.COLS - 1, 80))
        self.safe_addstr(1, 0, "📊 Portfolio Analysis Results", curses.A_BOLD)
        self.safe_addstr(2, 0, "=" * min(curses.COLS - 1, 80))
        
        # Word wrap and display
        max_width = min(curses.COLS - 2, 78)
        wrapped_lines = []
        for line in analysis.split('\n'):
            if line.strip():
                wrapped_lines.extend(textwrap.wrap(line, width=max_width))
            else:
                wrapped_lines.append("")
        
        row = 4
        max_visible = curses.LINES - 6
        for i, line in enumerate(wrapped_lines[:max_visible]):
            self.safe_addstr(row + i, 0, line)
        
        if len(wrapped_lines) > max_visible:
            self.safe_addstr(curses.LINES - 3, 0, f"... ({len(wrapped_lines) - max_visible} more lines)", curses.A_DIM)
        
        self.safe_addstr(curses.LINES - 2, 0, "Press any key to continue...")
        self.stdscr.refresh()
        self.stdscr.getch()
    
    def _analyze_specific_stock(self):
        """Analyze a specific stock."""
        self.stdscr.clear()
        
        self.safe_addstr(0, 0, "=" * min(curses.COLS - 1, 80))
        self.safe_addstr(1, 0, "📈 Analyze Specific Stock", curses.A_BOLD)
        self.safe_addstr(2, 0, "=" * min(curses.COLS - 1, 80))
        self.safe_addstr(4, 0, "Enter stock ticker: ")
        self.stdscr.refresh()
        
        curses.echo()
        try:
            ticker = self.stdscr.getstr(4, 20, 20).decode('utf-8').strip().upper()
        except:
            ticker = ""
        curses.noecho()
        
        if not ticker:
            return
        
        self.safe_addstr(6, 0, f"Analyzing {ticker}...")
        self.stdscr.refresh()
        
        # Get analysis
        analysis = self.agent.analyze_stock(ticker)
        
        # Display results
        self.stdscr.clear()
        self.safe_addstr(0, 0, "=" * min(curses.COLS - 1, 80))
        self.safe_addstr(1, 0, f"📈 Analysis: {ticker}", curses.A_BOLD)
        self.safe_addstr(2, 0, "=" * min(curses.COLS - 1, 80))
        
        # Word wrap and display
        max_width = min(curses.COLS - 2, 78)
        wrapped_lines = []
        for line in analysis.split('\n'):
            if line.strip():
                wrapped_lines.extend(textwrap.wrap(line, width=max_width))
            else:
                wrapped_lines.append("")
        
        row = 4
        max_visible = curses.LINES - 6
        for i, line in enumerate(wrapped_lines[:max_visible]):
            self.safe_addstr(row + i, 0, line)
        
        if len(wrapped_lines) > max_visible:
            self.safe_addstr(curses.LINES - 3, 0, f"... ({len(wrapped_lines) - max_visible} more lines)", curses.A_DIM)
        
        self.safe_addstr(curses.LINES - 2, 0, "Press any key to continue...")
        self.stdscr.refresh()
        self.stdscr.getch()
    
    def _show_usage_and_costs(self):
        """Show AI usage and cost information."""
        self.stdscr.clear()
        
        self.safe_addstr(0, 0, "=" * min(curses.COLS - 1, 80))
        self.safe_addstr(1, 0, "💰 AI Usage & Costs", curses.A_BOLD)
        self.safe_addstr(2, 0, "=" * min(curses.COLS - 1, 80))
        
        # Get cost summary
        summary = get_cost_summary()
        
        row = 4
        for line in summary.split('\n'):
            self.safe_addstr(row, 0, line)
            row += 1
        
        self.safe_addstr(curses.LINES - 2, 0, "Press any key to continue...")
        self.stdscr.refresh()
        self.stdscr.getch()
    
    def _show_settings(self):
        """Show AI settings and status."""
        self.stdscr.clear()
        
        self.safe_addstr(0, 0, "=" * min(curses.COLS - 1, 80))
        self.safe_addstr(1, 0, "⚙️  AI Settings & Status", curses.A_BOLD)
        self.safe_addstr(2, 0, "=" * min(curses.COLS - 1, 80))
        
        # Get status
        status = self.agent.get_status()
        
        row = 4
        for line in status.split('\n'):
            self.safe_addstr(row, 0, line)
            row += 1
        
        self.safe_addstr(curses.LINES - 2, 0, "Press any key to continue...")
        self.stdscr.refresh()
        self.stdscr.getch()
    
    def _test_connection(self):
        """Test connection to AI provider."""
        self.stdscr.clear()
        
        self.safe_addstr(0, 0, "=" * min(curses.COLS - 1, 80))
        self.safe_addstr(1, 0, "🔌 Testing AI Connection", curses.A_BOLD)
        self.safe_addstr(2, 0, "=" * min(curses.COLS - 1, 80))
        self.safe_addstr(4, 0, "Testing connection...")
        self.stdscr.refresh()
        
        success, msg = self.agent.test_connection()
        
        self.safe_addstr(6, 0, msg, curses.A_BOLD if success else curses.A_NORMAL)
        
        self.safe_addstr(curses.LINES - 2, 0, "Press any key to continue...")
        self.stdscr.refresh()
        self.stdscr.getch()
    
    def _show_setup_instructions(self):
        """Show setup instructions when AI is not available."""
        self.stdscr.clear()
        
        self.safe_addstr(0, 0, "=" * min(curses.COLS - 1, 80))
        self.safe_addstr(1, 0, "🤖 AI Assistant Setup Required", curses.A_BOLD)
        self.safe_addstr(2, 0, "=" * min(curses.COLS - 1, 80))
        
        row = 4
        if not AI_AVAILABLE:
            instructions = [
                "AI Assistant requires additional Python packages.",
                "",
                "To install:",
                "  1. Open a terminal",
                "  2. Run: pip install anthropic openai google-generativeai pypdf",
                "  3. Or: pip install -r requirements.txt",
                "",
                "Supported AI providers:",
                "  - Anthropic Claude (recommended)",
                "  - OpenAI GPT-4",
                "  - Google Gemini",
            ]
        else:
            instructions = [
                f"AI Assistant could not be initialized:",
                f"  {self.error_message}",
                "",
                "Setup steps:",
                "  1. Choose an AI provider (Anthropic Claude recommended)",
                "  2. Get an API key from the provider's website:",
                "     - Anthropic: https://console.anthropic.com/",
                "     - OpenAI: https://platform.openai.com/api-keys",
                "     - Gemini: https://makersuite.google.com/app/apikey",
                "  3. Set the environment variable:",
                "     export ANTHROPIC_API_KEY='your-key-here'",
                "  4. Restart yspy",
                "",
                "For more details, see ai_config.py",
            ]
        
        for line in instructions:
            if row < curses.LINES - 3:
                self.safe_addstr(row, 0, line)
                row += 1
        
        self.safe_addstr(curses.LINES - 2, 0, "Press any key to continue...")
        self.stdscr.refresh()
        self.stdscr.getch()
