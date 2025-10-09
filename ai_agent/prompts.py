"""
AI Prompt Templates
Collection of reusable prompts for different AI tasks.
"""

PORTFOLIO_ANALYSIS_PROMPT = """Please analyze my stock portfolio and provide:

1. **Overall Health**: Brief assessment of portfolio performance
2. **Diversification**: How well-diversified is the portfolio?
3. **Top Performers**: Which stocks are performing best and why?
4. **Areas of Concern**: What should I watch out for?
5. **Recommendations**: 2-3 specific actionable suggestions

Keep the analysis concise and focused on actionable insights."""

STOCK_ANALYSIS_PROMPT = """Analyze the stock {ticker} in my portfolio:

1. **Current Status**: Share count, average cost, current value, profit/loss
2. **Performance**: How is it performing relative to purchase price?
3. **Position Size**: Is this position appropriately sized in my portfolio?
4. **Recommendations**: Should I hold, add, or reduce this position? Why?

Base your analysis on the actual data from my portfolio."""

REPORT_SUMMARY_PROMPT = """I need help understanding a company report. Please:

1. Summarize the key financial metrics
2. Highlight any significant changes from previous periods
3. Identify important risks or opportunities mentioned
4. Provide an investor-focused summary in plain language

Focus on information that would help me make investment decisions."""

DIVERSIFICATION_PROMPT = """Evaluate my portfolio's diversification:

1. **Sector Exposure**: Am I overexposed to any sector?
2. **Geographic Distribution**: Sweden vs international exposure
3. **Market Cap**: Large cap vs mid/small cap distribution
4. **Correlation**: Are my holdings moving together or independently?
5. **Suggestions**: How can I improve diversification?

Provide specific actionable recommendations."""

MARKET_NEWS_PROMPT = """Search for recent market news about {topic}:

1. Recent developments or announcements
2. Impact on stock price or company performance
3. Analyst opinions or market sentiment
4. Implications for investors

Provide a balanced summary of the key information."""

COMPARISON_PROMPT = """Compare stocks {ticker1} and {ticker2} in my portfolio:

1. **Performance**: Which has performed better and by how much?
2. **Valuation**: Position sizes and relative valuations
3. **Correlation**: Do they move together or independently?
4. **Risk/Return**: Which offers better risk/return profile?
5. **Recommendation**: Should I rebalance between these two?

Use actual data from my portfolio for the comparison."""

RISK_ANALYSIS_PROMPT = """Analyze risk factors in my portfolio:

1. **Concentration Risk**: Are any positions too large?
2. **Sector Risk**: Overexposure to specific sectors?
3. **Market Risk**: Sensitivity to overall market movements
4. **Company-Specific Risks**: Individual stock concerns
5. **Mitigation Strategies**: How to reduce identified risks?

Provide practical risk management suggestions."""

PROFIT_LOSS_ANALYSIS_PROMPT = """Analyze my portfolio's profit and loss:

1. **Overall P/L**: Total profit/loss and percentage return
2. **Winners**: Best performing stocks and their contribution
3. **Losers**: Worst performing stocks and their impact
4. **Realized vs Unrealized**: Breakdown of gains/losses
5. **Tax Considerations**: Any suggestions for tax optimization?

Include specific numbers from my portfolio."""

def get_contextual_prompt(task: str, **kwargs) -> str:
    """
    Get a prompt template for a specific task.
    
    Args:
        task: Task type ('portfolio_analysis', 'stock_analysis', 'report_summary', etc.)
        **kwargs: Variables to fill in the template
        
    Returns:
        Formatted prompt string
    """
    prompts = {
        'portfolio_analysis': PORTFOLIO_ANALYSIS_PROMPT,
        'stock_analysis': STOCK_ANALYSIS_PROMPT,
        'report_summary': REPORT_SUMMARY_PROMPT,
        'diversification': DIVERSIFICATION_PROMPT,
        'market_news': MARKET_NEWS_PROMPT,
        'comparison': COMPARISON_PROMPT,
        'risk_analysis': RISK_ANALYSIS_PROMPT,
        'profit_loss': PROFIT_LOSS_ANALYSIS_PROMPT,
    }
    
    template = prompts.get(task, "")
    if not template:
        return ""
    
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


# Quick response templates
QUICK_RESPONSES = {
    'status': "I'm your yspy portfolio assistant. I can help you analyze your portfolio, understand stock performance, download reports, and answer questions about your investments. What would you like to know?",
    
    'help': """I can help you with:

📊 Portfolio Analysis
  - Overall portfolio health and performance
  - Diversification analysis
  - Risk assessment

📈 Stock Information
  - Individual stock analysis
  - Performance comparisons
  - Correlation analysis

📑 Reports & Research
  - Download company reports
  - Search for financial news
  - Summarize financial data

💡 Insights & Recommendations
  - Investment suggestions
  - Portfolio rebalancing ideas
  - Tax optimization tips

Just ask me a question or choose a task!""",
    
    'no_portfolio': "I don't have access to your portfolio data. Please ensure the portfolio is loaded in yspy.",
    
    'error': "I encountered an error processing your request. Please try rephrasing your question or contact support if the issue persists.",
}

def get_quick_response(key: str) -> str:
    """Get a pre-defined quick response."""
    return QUICK_RESPONSES.get(key, QUICK_RESPONSES['error'])
