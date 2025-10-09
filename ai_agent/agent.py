"""
YSpy AI Agent - Main agent class
Orchestrates AI conversations with tool calling and context management.
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from .cloud_provider import CloudProvider
from .tools import AITools
from config.ai_config import AI_CONFIG, anonymize_portfolio_data, get_cost_summary


class YSpyAIAgent:
    """Main AI agent for yspy portfolio assistant."""
    
    def __init__(self, portfolio=None):
        """
        Initialize AI agent.
        
        Args:
            portfolio: PortfolioManager instance
        """
        self.portfolio = portfolio
        self.tools = AITools(portfolio)
        self.provider = None
        self.conversation_history = []
        
        # Store conversation in data/ai/conversations directory
        conv_dir = Path('data/ai/conversations')
        conv_dir.mkdir(parents=True, exist_ok=True)
        conv_file = AI_CONFIG.get('conversation_file', 'conversation.json')
        self.conversation_file = conv_dir / conv_file
        
        # Try to initialize provider
        try:
            self.provider = CloudProvider()
            self.is_available = True
        except Exception as e:
            self.is_available = False
            self.error_message = str(e)
    
    def get_system_prompt(self) -> str:
        """Get the system prompt for the AI."""
        return """You are a financial assistant for yspy, a Swedish stock portfolio management application.

Your role is to help users:
- Understand their portfolio performance and composition
- Analyze individual stocks and their relationships
- Download and reference company reports and financial data
- Provide insights on diversification and risk
- Answer questions about Swedish stock market companies

You have access to tools that can:
- get_portfolio_summary: Get portfolio overview with holdings
- get_stock_info: Get detailed info about specific stocks
- calculate_portfolio_metrics: Calculate diversification, top/worst performers
- search_web: Search the internet for company info, reports, news
- download_file: Download files from URLs (reports, PDFs, etc.)
- download_company_report: Get guidance on finding company reports
- analyze_stock_correlation: Analyze stock correlations
- list_downloads: List all previously downloaded files
- open_file: Open a file that's already been downloaded

Guidelines:
1. Be concise but informative in your responses
2. Use actual data from the portfolio when available
3. Always mention when you're using a tool to get data
4. For financial advice, remind users this is for informational purposes only
5. When discussing Swedish companies, you can use Swedish terms naturally
6. Focus on actionable insights rather than just data dumps

**IMPORTANT - Downloading Reports:**
When users ask for company reports:
1. First use search_web to find the report URL (e.g., "search_web Alleima Q2 2024 interim report PDF")
2. Then use download_file with the URL you find
3. Be proactive - if you find a URL, download it immediately without asking
4. Example workflow:
   User: "Get Alleima's Q2 report"
   You: [search_web for "Alleima Q2 2024 interim report filetype:pdf"]
        [If URL found: download_file with that URL]
        "I found and downloaded the report to ~/Downloads/yspy/"

**File Management:**
- When users ask to "open" a file, use list_downloads first to see available files
- Then use open_file with the exact filename (e.g., open_file("ALLEI_Q3_2024.pdf"))
- You can open files even if they were downloaded in a previous session
- All downloaded files are in ~/Downloads/yspy/
- Example: User: "Open the Alleima report" → [list_downloads] → [open_file with matching filename]

**Web Search Tips:**
- Add "filetype:pdf" to find PDFs
- Include "investor relations" or "ir" for company pages  
- Swedish companies often have .com/en/investors or .se/investerare
- Try: "[Company] delårsrapport Q2 2024" for Swedish
- Or: "[Company] interim report Q2 2024 PDF" for English

Common Swedish company IR URLs:
- Volvo: volvogroup.com/investors
- Boliden: boliden.com/investors
- SSAB: ssab.com/investors
- ASSA ABLOY: assaabloy.com/investors
- Alleima: alleima.com/investors

Currency: All values are in Swedish Krona (SEK) unless otherwise noted.

Current date: {date}
""".format(date=datetime.now().strftime("%Y-%m-%d"))
    
    def chat(self, user_message: str, include_portfolio_context: bool = False) -> Dict[str, Any]:
        """
        Chat with the AI agent.
        
        Args:
            user_message: User's message
            include_portfolio_context: Whether to include portfolio summary in context
            
        Returns:
            Dict with 'response', 'cost', 'tool_calls_made'
        """
        if not self.is_available:
            return {
                'response': f"❌ AI agent not available: {self.error_message}",
                'cost': 0,
                'tool_calls_made': []
            }
        
        # Add portfolio context if requested
        context_message = user_message
        if include_portfolio_context and self.portfolio:
            try:
                portfolio_summary = self.tools.get_portfolio_summary(include_details=False)
                if AI_CONFIG['anonymize_data']:
                    portfolio_summary = "Portfolio context available (anonymized for privacy)"
                context_message = f"Context: {portfolio_summary}\n\nUser question: {user_message}"
            except Exception:
                pass
        
        # Add to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": context_message
        })
        
        # Limit conversation history
        max_history = AI_CONFIG.get('max_conversation_history', 10)
        if len(self.conversation_history) > max_history * 2:  # *2 because user + assistant
            self.conversation_history = self.conversation_history[-max_history * 2:]
        
        # Get response from AI
        tool_calls_made = []
        total_cost = 0
        max_iterations = 5  # Prevent infinite tool calling loops
        first_iteration = True
        
        for iteration in range(max_iterations):
            # On first iteration, use the user message
            # On subsequent iterations (after tools), the history already contains
            # the user message with tool results, so don't send a new message
            if first_iteration:
                response = self.provider.send_message(
                    message=context_message,
                    system_prompt=self.get_system_prompt(),
                    conversation_history=self.conversation_history[:-1],  # Exclude current message
                    tools=self.tools.get_tool_definitions()
                )
                first_iteration = False
            else:
                # After tool execution, conversation_history has tool results
                # Send request without adding a new message
                response = self.provider.send_message(
                    message="",  # Empty message
                    system_prompt=self.get_system_prompt(),
                    conversation_history=self.conversation_history,  # Include all history now
                    tools=self.tools.get_tool_definitions()
                )
            
            total_cost += response.get('cost', 0)
            
            # Check for errors
            if response.get('error'):
                return {
                    'response': response['content'],
                    'cost': total_cost,
                    'tool_calls_made': tool_calls_made
                }
            
            # Check if AI wants to use tools
            if response.get('tool_calls'):
                # Execute tool calls
                tool_results = []
                for tool_call in response['tool_calls']:
                    tool_name = tool_call['name']
                    tool_input = tool_call['input']
                    tool_calls_made.append(tool_name)
                    
                    # Execute the tool
                    result = self.tools.execute_tool(tool_name, tool_input)
                    tool_results.append({
                        'tool_call_id': tool_call['id'],
                        'tool_name': tool_name,
                        'result': result
                    })
                
                # Add tool results to conversation
                if self.provider.provider == 'anthropic':
                    # Anthropic format - assistant message with tool_use blocks
                    # Build content array with both text and tool_use blocks
                    assistant_content = []
                    
                    # Add any text content
                    if response.get('content'):
                        assistant_content.append({
                            "type": "text",
                            "text": response['content']
                        })
                    
                    # Add tool_use blocks
                    for tool_call in response['tool_calls']:
                        assistant_content.append({
                            "type": "tool_use",
                            "id": tool_call['id'],
                            "name": tool_call['name'],
                            "input": tool_call['input']
                        })
                    
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": assistant_content
                    })
                    
                    # Add tool results as user message
                    tool_results_content = []
                    for tool_result in tool_results:
                        tool_results_content.append({
                            "type": "tool_result",
                            "tool_use_id": tool_result['tool_call_id'],
                            "content": tool_result['result']
                        })
                    
                    self.conversation_history.append({
                        "role": "user",
                        "content": tool_results_content
                    })
                
                # Continue to get final response
                context_message = ""  # Empty message, let AI respond based on tool results
                continue
            
            # No more tool calls, this is the final response
            final_response = response['content']
            
            # Add to conversation history
            self.conversation_history.append({
                "role": "assistant",
                "content": final_response
            })
            
            # Save conversation
            self._save_conversation()
            
            return {
                'response': final_response,
                'cost': total_cost,
                'tool_calls_made': tool_calls_made
            }
        
        # Max iterations reached
        return {
            'response': "Response generation took too many steps. Please try rephrasing your question.",
            'cost': total_cost,
            'tool_calls_made': tool_calls_made
        }
    
    def clear_conversation(self):
        """Clear conversation history."""
        self.conversation_history = []
        self._save_conversation()
    
    def _save_conversation(self):
        """Save conversation history to file."""
        if not AI_CONFIG.get('cache_responses', True):
            return
        
        try:
            data = {
                'timestamp': datetime.now().isoformat(),
                'provider': AI_CONFIG['provider'],
                'model': self.provider.model if self.provider else None,
                'conversation': self.conversation_history
            }
            
            with open(self.conversation_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # Silently fail if can't save
    
    def load_conversation(self):
        """Load conversation history from file."""
        if not self.conversation_file.exists():
            return
        
        try:
            with open(self.conversation_file, 'r') as f:
                data = json.load(f)
            
            self.conversation_history = data.get('conversation', [])
        except Exception:
            pass  # Silently fail if can't load
    
    def get_status(self) -> str:
        """Get agent status information."""
        if not self.is_available:
            return f"❌ AI Agent: Not available\nReason: {self.error_message}"
        
        status = f"""✓ AI Agent: Available
Provider: {AI_CONFIG['provider']}
Model: {self.provider.model}
Conversation: {len(self.conversation_history)} messages

{get_cost_summary()}
"""
        return status.strip()
    
    def test_connection(self) -> tuple[bool, str]:
        """Test connection to AI provider."""
        if not self.is_available:
            return False, f"Not available: {self.error_message}"
        
        return self.provider.test_connection()
    
    def quick_analyze_portfolio(self) -> str:
        """Quick portfolio analysis using AI."""
        if not self.is_available:
            return f"AI agent not available: {self.error_message}"
        
        if not self.portfolio:
            return "No portfolio loaded."
        
        prompt = """Please provide a brief analysis of my portfolio:
1. Overall health and diversification
2. Top 3 strengths
3. Top 3 areas for improvement
4. Key risk factors

Keep it concise and actionable."""
        
        result = self.chat(prompt, include_portfolio_context=True)
        return result['response']
    
    def analyze_stock(self, ticker: str) -> str:
        """Analyze a specific stock using AI."""
        if not self.is_available:
            return f"AI agent not available: {self.error_message}"
        
        prompt = f"""Please analyze the stock {ticker} in my portfolio:
1. Current performance
2. Position size relative to portfolio
3. Recent trends (if data available)
4. Suggestions for this holding

Be specific and use actual data from my portfolio."""
        
        result = self.chat(prompt, include_portfolio_context=True)
        return result['response']


if __name__ == "__main__":
    # Test the agent
    print("Testing YSpy AI Agent...")
    print("=" * 60)
    
    agent = YSpyAIAgent()
    print("\nStatus:")
    print(agent.get_status())
    
    if agent.is_available:
        print("\nTesting connection...")
        success, msg = agent.test_connection()
        print(msg)
        
        if success:
            print("\nTesting chat...")
            response = agent.chat("Hello! Can you briefly introduce yourself?")
            print(f"\nAI: {response['response']}")
            print(f"\nCost: ${response['cost']:.6f}")
            print(f"Tools used: {response['tool_calls_made']}")
