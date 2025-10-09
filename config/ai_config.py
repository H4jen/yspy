"""
AI Agent Configuration for yspy
Manages settings for cloud AI providers, security, and cost controls.
"""

import os
from datetime import datetime, timedelta

# AI Provider Configuration
AI_CONFIG = {
    # Provider settings - choose: 'anthropic', 'openai', or 'gemini'
    'provider': 'anthropic',
    
    # API Key (stored in environment variable for security)
    'api_key_env': 'YSPY_AI_API_KEY',
    
    # Model settings
        # Model settings
    'model': 'claude-sonnet-4-20250514',  # Claude Sonnet 4 (latest)
    'max_tokens': 4000,
    'temperature': 0.3,  # Lower = more factual and consistent
    
    # Cost management
    'cache_responses': True,
    'cache_duration': 3600,  # 1 hour in seconds
    'max_cost_per_day': 5.00,  # USD - daily spending limit
    'cost_tracking_file': 'ai_costs.json',
    
    # Security
    'anonymize_data': True,  # Remove sensitive info before sending to cloud
    'anonymize_amounts': True,  # Replace exact monetary amounts with ranges
    'share_portfolio_structure': True,  # Allow sharing stock tickers and ratios
    
    # Features
    'enable_web_search': True,
    'enable_report_download': True,
    'enable_pdf_viewing': True,
    'pdf_viewer': 'xdg-open',  # or 'evince', 'okular', 'firefox', etc.
    
    # Conversation settings
    'max_conversation_history': 10,  # Keep last N messages
    'conversation_file': 'ai_conversations.json',
}

# Provider-specific models
MODELS = {
    'anthropic': {
        'default': 'claude-sonnet-4-20250514',  # Claude Sonnet 4 (latest)
        'fast': 'claude-3-haiku-20240307',
        'advanced': 'claude-3-opus-latest',
    },
    'openai': {
        'default': 'gpt-4-turbo-preview',
        'fast': 'gpt-3.5-turbo',
        'advanced': 'gpt-4',
    },
    'gemini': {
        'default': 'gemini-1.5-pro',
        'fast': 'gemini-1.5-flash',
        'advanced': 'gemini-1.5-pro',
    }
}

# Cost per 1M tokens (approximate, check provider for latest)
COSTS = {
    'anthropic': {
        'claude-sonnet-4-20250514': {'input': 3.00, 'output': 15.00},
        'claude-3-5-sonnet-20241022': {'input': 3.00, 'output': 15.00},
        'claude-3-haiku-20240307': {'input': 0.25, 'output': 1.25},
        'claude-3-opus-latest': {'input': 15.00, 'output': 75.00},
    },
    'openai': {
        'gpt-4-turbo-preview': {'input': 10.00, 'output': 30.00},
        'gpt-3.5-turbo': {'input': 0.50, 'output': 1.50},
        'gpt-4': {'input': 30.00, 'output': 60.00},
    },
    'gemini': {
        'gemini-1.5-pro': {'input': 0.00, 'output': 0.00},  # Free tier
        'gemini-1.5-flash': {'input': 0.00, 'output': 0.00},  # Free tier
    }
}

def get_api_key():
    """Get API key from environment variable."""
    env_var = AI_CONFIG['api_key_env']
    api_key = os.environ.get(env_var)
    
    if not api_key:
        # Try alternative environment variable names
        if AI_CONFIG['provider'] == 'anthropic':
            api_key = os.environ.get('ANTHROPIC_API_KEY')
        elif AI_CONFIG['provider'] == 'openai':
            api_key = os.environ.get('OPENAI_API_KEY')
        elif AI_CONFIG['provider'] == 'gemini':
            api_key = os.environ.get('GOOGLE_API_KEY')
    
    return api_key

def get_model():
    """Get the model name for current provider."""
    provider = AI_CONFIG['provider']
    return AI_CONFIG.get('model') or MODELS.get(provider, {}).get('default')

def estimate_cost(input_tokens, output_tokens):
    """Estimate cost for a query."""
    provider = AI_CONFIG['provider']
    model = get_model()
    
    costs = COSTS.get(provider, {}).get(model, {'input': 0, 'output': 0})
    
    input_cost = (input_tokens / 1_000_000) * costs['input']
    output_cost = (output_tokens / 1_000_000) * costs['output']
    
    return input_cost + output_cost

def anonymize_portfolio_data(data):
    """
    Anonymize sensitive portfolio data before sending to cloud.
    Preserves structure and relationships while removing exact values.
    """
    if not AI_CONFIG['anonymize_data']:
        return data
    
    import json
    import copy
    
    anonymized = copy.deepcopy(data)
    
    if AI_CONFIG['anonymize_amounts']:
        # Replace exact amounts with ranges
        def anonymize_amount(amount):
            if amount < 1000:
                return "<1k"
            elif amount < 10000:
                return "1k-10k"
            elif amount < 100000:
                return "10k-100k"
            elif amount < 500000:
                return "100k-500k"
            else:
                return ">500k"
        
        # Process the data structure (this will vary based on your data format)
        if isinstance(anonymized, dict):
            for key in anonymized:
                if 'value' in key.lower() or 'total' in key.lower() or 'cost' in key.lower():
                    if isinstance(anonymized[key], (int, float)):
                        anonymized[key] = anonymize_amount(anonymized[key])
    
    return anonymized

def check_daily_cost_limit():
    """
    Check if daily cost limit has been exceeded.
    Returns (is_allowed, remaining_budget, message)
    """
    import json
    from pathlib import Path
    
    cost_file = Path(AI_CONFIG['cost_tracking_file'])
    max_daily = AI_CONFIG['max_cost_per_day']
    
    if not cost_file.exists():
        return True, max_daily, f"Budget available: ${max_daily:.2f}"
    
    try:
        with open(cost_file, 'r') as f:
            cost_data = json.load(f)
        
        today = datetime.now().strftime('%Y-%m-%d')
        today_cost = sum(entry['cost'] for entry in cost_data if entry['date'] == today)
        
        remaining = max_daily - today_cost
        
        if remaining <= 0:
            return False, 0, f"Daily budget of ${max_daily:.2f} exceeded. Used: ${today_cost:.2f}"
        
        return True, remaining, f"Remaining budget: ${remaining:.2f} of ${max_daily:.2f}"
    
    except Exception as e:
        return True, max_daily, f"Could not check budget: {e}"

def log_cost(input_tokens, output_tokens, cost):
    """Log API usage cost."""
    import json
    from pathlib import Path
    
    cost_file = Path(AI_CONFIG['cost_tracking_file'])
    
    entry = {
        'timestamp': datetime.now().isoformat(),
        'date': datetime.now().strftime('%Y-%m-%d'),
        'provider': AI_CONFIG['provider'],
        'model': get_model(),
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'cost': cost
    }
    
    # Load existing data
    if cost_file.exists():
        with open(cost_file, 'r') as f:
            cost_data = json.load(f)
    else:
        cost_data = []
    
    cost_data.append(entry)
    
    # Keep only last 30 days
    cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    cost_data = [e for e in cost_data if e['date'] >= cutoff]
    
    # Save
    with open(cost_file, 'w') as f:
        json.dump(cost_data, f, indent=2)

def get_cost_summary():
    """Get cost summary for display."""
    import json
    from pathlib import Path
    from collections import defaultdict
    
    cost_file = Path(AI_CONFIG['cost_tracking_file'])
    
    if not cost_file.exists():
        return "No usage data available."
    
    try:
        with open(cost_file, 'r') as f:
            cost_data = json.load(f)
        
        today = datetime.now().strftime('%Y-%m-%d')
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        today_cost = sum(e['cost'] for e in cost_data if e['date'] == today)
        week_cost = sum(e['cost'] for e in cost_data if e['date'] >= week_ago)
        month_cost = sum(e['cost'] for e in cost_data if e['date'] >= month_ago)
        
        today_queries = len([e for e in cost_data if e['date'] == today])
        
        summary = f"""
AI Usage Summary:
-----------------
Today:     ${today_cost:.4f} ({today_queries} queries)
Last 7d:   ${week_cost:.4f}
Last 30d:  ${month_cost:.4f}

Daily limit: ${AI_CONFIG['max_cost_per_day']:.2f}
Remaining:   ${AI_CONFIG['max_cost_per_day'] - today_cost:.2f}
"""
        return summary.strip()
    
    except Exception as e:
        return f"Error reading cost data: {e}"
