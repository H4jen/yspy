#!/usr/bin/env python3
"""
AI Chat Window - Separate GUI for AI Assistant
Runs alongside the main ncurses terminal application.
"""

import tkinter as tk
from tkinter import scrolledtext, ttk
import threading
import queue
from datetime import datetime

try:
    from ai_agent import YSpyAIAgent
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False


class AIChatWindow:
    """Standalone GUI window for AI chat."""
    
    def __init__(self, portfolio):
        """
        Initialize AI chat window.
        
        Args:
            portfolio: PortfolioManager instance
        """
        self.portfolio = portfolio
        self.agent = None
        self.root = None
        self.message_queue = queue.Queue()
        self.running = False
        
        # Font size settings
        self.chat_font_size = 12
        self.input_font_size = 12
        
        if AI_AVAILABLE:
            try:
                self.agent = YSpyAIAgent(portfolio)
            except Exception as e:
                self.error_message = str(e)
                self.agent = None
        else:
            self.error_message = "AI dependencies not installed"
    
    def start_window(self):
        """Start the GUI window in a separate thread."""
        if not AI_AVAILABLE or not self.agent:
            return
        
        self.running = True
        thread = threading.Thread(target=self._run_gui, daemon=True)
        thread.start()
    
    def _run_gui(self):
        """Run the tkinter GUI (runs in separate thread)."""
        self.root = tk.Tk()
        self.root.title("YSpy AI Assistant 🤖")
        self.root.geometry("750x800")  # Larger window for 12pt font
        
        # Dark mode colors
        self.bg_color = '#1e1e1e'          # Dark background
        self.fg_color = '#d4d4d4'          # Light text
        self.input_bg = '#2d2d2d'          # Slightly lighter for input
        self.chat_bg = '#252526'           # Chat area background
        self.header_bg = '#2d2d30'         # Header background
        self.button_bg = '#0e639c'         # Button background (VS Code blue)
        self.button_fg = '#ffffff'         # Button text
        self.user_color = '#4ec9b0'        # Cyan for user messages
        self.ai_color = '#9cdcfe'          # Light blue for AI messages
        self.system_color = '#808080'      # Gray for system messages
        self.error_color = '#f48771'       # Light red for errors
        
        # Configure root window
        self.root.configure(bg=self.bg_color)
        
        # Make it stay on top initially
        self.root.attributes('-topmost', True)
        self.root.after(1000, lambda: self.root.attributes('-topmost', False))
        
        # Configure style for dark mode
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure dark theme colors
        style.configure('TFrame', background=self.bg_color)
        style.configure('TLabel', background=self.bg_color, foreground=self.fg_color)
        style.configure('TButton', 
                       background=self.button_bg, 
                       foreground=self.button_fg,
                       borderwidth=0,
                       focuscolor='none')
        style.map('TButton',
                 background=[('active', '#1177bb'), ('pressed', '#0d5a8f')])
        style.configure('TLabelframe', background=self.bg_color, foreground=self.fg_color)
        style.configure('TLabelframe.Label', background=self.bg_color, foreground=self.fg_color)
        
        # Create main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Header
        header = ttk.Label(
            main_frame,
            text="🤖 YSpy AI Assistant",
            font=('Arial', 14, 'bold')
        )
        header.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky=tk.W)
        
        # Status label - get model from AI_CONFIG
        try:
            from config.ai_config import AI_CONFIG
            model_name = AI_CONFIG.get('model', 'Unknown')[:30]
        except:
            model_name = 'Claude'
        
        self.status_label = ttk.Label(
            main_frame,
            text=f"Ready | Model: {model_name}...",
            font=('Arial', 9),
            foreground='#4ec9b0'  # Cyan color for status
        )
        self.status_label.grid(row=0, column=1, pady=(0, 10), sticky=tk.E)
        
        # Chat display area
        chat_frame = ttk.Frame(main_frame)
        chat_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)
        
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            width=70,
            height=30,
            font=('Consolas', self.chat_font_size),
            state='disabled',
            bg=self.chat_bg,
            fg=self.fg_color,
            insertbackground=self.fg_color,  # Cursor color
            selectbackground='#264f78',      # Selection background
            selectforeground=self.fg_color   # Selection text
        )
        self.chat_display.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure text tags for styling with dark mode colors
        self.chat_display.tag_config('user', foreground=self.user_color, font=('Consolas', self.chat_font_size, 'bold'))
        self.chat_display.tag_config('ai', foreground=self.ai_color, font=('Consolas', self.chat_font_size))
        self.chat_display.tag_config('system', foreground=self.system_color, font=('Consolas', self.chat_font_size - 1, 'italic'))
        self.chat_display.tag_config('error', foreground=self.error_color, font=('Consolas', self.chat_font_size))
        
        # Quick action buttons frame
        quick_frame = ttk.LabelFrame(main_frame, text="Quick Actions", padding="5")
        quick_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Button(
            quick_frame,
            text="📊 Portfolio Analysis",
            command=self._quick_portfolio_analysis
        ).grid(row=0, column=0, padx=5, pady=2)
        
        ttk.Button(
            quick_frame,
            text="📈 Stock Metrics",
            command=self._quick_metrics
        ).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Button(
            quick_frame,
            text="💡 Suggestions",
            command=self._quick_suggestions
        ).grid(row=0, column=2, padx=5, pady=2)
        
        ttk.Button(
            quick_frame,
            text="🔄 Clear Chat",
            command=self._clear_chat
        ).grid(row=0, column=3, padx=5, pady=2)
        
        # Font size controls
        ttk.Label(quick_frame, text="Font:").grid(row=0, column=4, padx=(15, 2), pady=2)
        
        ttk.Button(
            quick_frame,
            text="A-",
            width=3,
            command=self._decrease_font_size
        ).grid(row=0, column=5, padx=2, pady=2)
        
        self.font_size_label = ttk.Label(quick_frame, text=f"{self.chat_font_size}")
        self.font_size_label.grid(row=0, column=6, padx=2, pady=2)
        
        ttk.Button(
            quick_frame,
            text="A+",
            width=3,
            command=self._increase_font_size
        ).grid(row=0, column=7, padx=2, pady=2)
        
        # Input area
        input_frame = ttk.Frame(main_frame)
        input_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E))
        input_frame.columnconfigure(0, weight=1)
        
        ttk.Label(input_frame, text="Ask AI:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        self.input_text = tk.Text(
            input_frame,
            height=3,
            width=50,
            font=('Consolas', self.input_font_size),
            wrap=tk.WORD,
            bg=self.input_bg,
            fg=self.fg_color,
            insertbackground=self.fg_color,  # Cursor color
            selectbackground='#264f78',
            selectforeground=self.fg_color,
            relief=tk.FLAT,
            borderwidth=2
        )
        self.input_text.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=(0, 10))
        
        # Bind Enter key (with Shift+Enter for newline)
        self.input_text.bind('<Return>', self._on_enter_key)
        self.input_text.bind('<Shift-Return>', self._on_shift_enter)
        
        send_button = ttk.Button(
            input_frame,
            text="Send ➤",
            command=self._send_message
        )
        send_button.grid(row=1, column=1, sticky=(tk.N, tk.S))
        
        # Cost info
        self.cost_label = ttk.Label(
            main_frame,
            text="Session cost: $0.00",
            font=('Arial', 9),
            foreground=self.system_color
        )
        self.cost_label.grid(row=4, column=0, columnspan=2, pady=(10, 0), sticky=tk.W)
        
        # Welcome message
        self._add_system_message("Welcome! Ask me anything about your portfolio or stocks.")
        self._add_system_message("Try: 'How is my portfolio performing?' or 'Analyze my top holdings'")
        
        # Start processing queue
        self.root.after(100, self._process_queue)
        
        # Focus input
        self.input_text.focus_set()
        
        # Run
        self.root.mainloop()
    
    def _on_enter_key(self, event):
        """Handle Enter key press."""
        self._send_message()
        return 'break'  # Prevent newline
    
    def _on_shift_enter(self, event):
        """Handle Shift+Enter for newline."""
        return  # Allow default newline behavior
    
    def _send_message(self):
        """Send user message to AI."""
        message = self.input_text.get('1.0', tk.END).strip()
        
        if not message:
            return
        
        # Clear input
        self.input_text.delete('1.0', tk.END)
        
        # Display user message
        self._add_user_message(message)
        
        # Update status (orange/yellow for thinking)
        self.status_label.config(text="AI is thinking...", foreground='#ce9178')
        
        # Process in background thread to avoid blocking GUI
        thread = threading.Thread(target=self._process_message, args=(message,), daemon=True)
        thread.start()
    
    def _process_message(self, message):
        """Process message in background thread."""
        try:
            response = self.agent.chat(message, include_portfolio_context=True)
            
            # Queue response for GUI thread
            self.message_queue.put({
                'type': 'ai',
                'content': response['response'],
                'cost': response.get('cost', 0)
            })
            
        except Exception as e:
            self.message_queue.put({
                'type': 'error',
                'content': f"Error: {str(e)}"
            })
    
    def _process_queue(self):
        """Process messages from background threads."""
        try:
            while True:
                msg = self.message_queue.get_nowait()
                
                if msg['type'] == 'ai':
                    self._add_ai_message(msg['content'])
                    if msg.get('cost', 0) > 0:
                        self._update_cost(msg['cost'])
                    self.status_label.config(text="Ready", foreground='#4ec9b0')  # Cyan
                    
                elif msg['type'] == 'error':
                    self._add_error_message(msg['content'])
                    self.status_label.config(text="Error", foreground='#f48771')  # Light red
                    
                elif msg['type'] == 'system':
                    self._add_system_message(msg['content'])
                    
        except queue.Empty:
            pass
        
        # Schedule next check
        if self.running:
            self.root.after(100, self._process_queue)
    
    def _add_user_message(self, message):
        """Add user message to chat display."""
        self.chat_display.config(state='normal')
        timestamp = datetime.now().strftime('%H:%M')
        self.chat_display.insert(tk.END, f"\n[{timestamp}] ", 'system')
        self.chat_display.insert(tk.END, f"You: ", 'user')
        self.chat_display.insert(tk.END, f"{message}\n", 'user')
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')
    
    def _add_ai_message(self, message):
        """Add AI message to chat display."""
        self.chat_display.config(state='normal')
        timestamp = datetime.now().strftime('%H:%M')
        self.chat_display.insert(tk.END, f"[{timestamp}] ", 'system')
        self.chat_display.insert(tk.END, f"AI: ", 'ai')
        self.chat_display.insert(tk.END, f"{message}\n", 'ai')
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')
    
    def _add_system_message(self, message):
        """Add system message to chat display."""
        self.chat_display.config(state='normal')
        self.chat_display.insert(tk.END, f"ℹ️  {message}\n", 'system')
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')
    
    def _add_error_message(self, message):
        """Add error message to chat display."""
        self.chat_display.config(state='normal')
        self.chat_display.insert(tk.END, f"❌ {message}\n", 'error')
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')
    
    def _update_cost(self, cost):
        """Update cost display."""
        current = float(self.cost_label.cget('text').split('$')[1])
        new_total = current + cost
        self.cost_label.config(text=f"Session cost: ${new_total:.6f}")
    
    def _quick_portfolio_analysis(self):
        """Quick portfolio analysis."""
        self._add_system_message("Running portfolio analysis...")
        self.status_label.config(text="Analyzing...", foreground='#ce9178')  # Orange
        
        thread = threading.Thread(target=self._run_quick_analysis, daemon=True)
        thread.start()
    
    def _run_quick_analysis(self):
        """Run quick analysis in background."""
        try:
            analysis = self.agent.quick_analyze_portfolio()
            self.message_queue.put({
                'type': 'ai',
                'content': analysis,
                'cost': 0
            })
        except Exception as e:
            self.message_queue.put({
                'type': 'error',
                'content': f"Analysis failed: {str(e)}"
            })
    
    def _quick_metrics(self):
        """Quick portfolio metrics."""
        self.input_text.delete('1.0', tk.END)
        self.input_text.insert('1.0', "Show me key portfolio metrics and diversification")
        self._send_message()
    
    def _quick_suggestions(self):
        """Quick suggestions."""
        self.input_text.delete('1.0', tk.END)
        self.input_text.insert('1.0', "Give me actionable suggestions to improve my portfolio")
        self._send_message()
    
    def _clear_chat(self):
        """Clear chat history."""
        self.chat_display.config(state='normal')
        self.chat_display.delete('1.0', tk.END)
        self.chat_display.config(state='disabled')
        
        if self.agent:
            self.agent.clear_conversation()
        
        self._add_system_message("Chat cleared. How can I help you?")
        self.cost_label.config(text="Session cost: $0.00")
    
    def _increase_font_size(self):
        """Increase font size."""
        if self.chat_font_size < 20:  # Max size
            self.chat_font_size += 1
            self.input_font_size += 1
            self._update_fonts()
    
    def _decrease_font_size(self):
        """Decrease font size."""
        if self.chat_font_size > 8:  # Min size
            self.chat_font_size -= 1
            self.input_font_size -= 1
            self._update_fonts()
    
    def _update_fonts(self):
        """Update all fonts to current size."""
        # Update chat display font
        self.chat_display.config(font=('Consolas', self.chat_font_size))
        
        # Update text tags
        self.chat_display.tag_config('user', foreground=self.user_color, font=('Consolas', self.chat_font_size, 'bold'))
        self.chat_display.tag_config('ai', foreground=self.ai_color, font=('Consolas', self.chat_font_size))
        self.chat_display.tag_config('system', foreground=self.system_color, font=('Consolas', max(8, self.chat_font_size - 1), 'italic'))
        self.chat_display.tag_config('error', foreground=self.error_color, font=('Consolas', self.chat_font_size))
        
        # Update input font
        self.input_text.config(font=('Consolas', self.input_font_size))
        
        # Update font size label
        self.font_size_label.config(text=f"{self.chat_font_size}")
    
    def stop(self):
        """Stop the window."""
        self.running = False
        if self.root:
            self.root.quit()


def launch_ai_chat_window(portfolio):
    """
    Launch AI chat window.
    
    Args:
        portfolio: PortfolioManager instance
        
    Returns:
        AIChatWindow instance or None if not available
    """
    if not AI_AVAILABLE:
        print("AI chat window not available: AI dependencies not installed")
        print("Install with: pip install anthropic openai google-generativeai pypdf")
        return None
    
    try:
        window = AIChatWindow(portfolio)
        if window.agent and window.agent.is_available:
            window.start_window()
            return window
        else:
            # Agent not available - show why
            if not window.agent:
                print("AI chat window not available: Could not create AI agent")
                print(f"Error: {window.error_message if hasattr(window, 'error_message') else 'Unknown'}")
            else:
                print("AI chat window not available: AI agent not ready")
                print(f"Reason: {window.agent.error_message if hasattr(window.agent, 'error_message') else 'API key not set?'}")
                print("\nTo enable AI Assistant:")
                print("1. Get an API key from https://console.anthropic.com/")
                print("2. Set environment variable: export ANTHROPIC_API_KEY='your-key-here'")
                print("3. Restart yspy")
    except Exception as e:
        print(f"Failed to launch AI chat window: {e}")
        import traceback
        traceback.print_exc()
    
    return None
