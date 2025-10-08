#!/usr/bin/env python3
"""
Visual demonstration of short selling trend arrows.
Shows what the watch screen will look like with trend indicators.
"""

import sys

# ANSI color codes for terminal
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
GRAY = '\033[90m'
RESET = '\033[0m'
BOLD = '\033[1m'

def print_demo():
    """Print a visual demonstration of the trend arrows."""
    
    print("\n" + "=" * 80)
    print(f"{BOLD}SHORT SELLING TREND ARROWS - VISUAL DEMONSTRATION{RESET}")
    print("=" * 80 + "\n")
    
    print(f"{BOLD}What you'll see in the Watch Screen (Press 7):{RESET}\n")
    
    # Header
    print(f"{'Stock Name':<18}{'Short%':>10}  {'Current':>10}  {'High':>10}  {'Low':>10}  ...")
    print("-" * 80)
    
    # Example stocks with different trends
    stocks = [
        ("VOLCAR-B", RED, "⬆", "4.80", "145.30", "Strong increase - Very bearish"),
        ("SSAB-B", RED, "↑", "3.45", "58.70", "Moderate increase - Bearish"),
        ("ABB", YELLOW, "→", "1.23", "520.00", "Stable - Neutral"),
        ("NIBE-B", GREEN, "↓", "2.15", "45.20", "Moderate decrease - Bullish"),
        ("BOL", GREEN, "⬇", "0.95", "312.50", "Strong decrease - Very bullish"),
        ("ASSA-B", GRAY, "?", "2.50", "289.40", "No historical data yet"),
    ]
    
    for name, color, arrow, short_pct, current, description in stocks:
        # Build the line with colored arrow
        stock_line = f"{name:<18}"
        arrow_part = f"{color}{arrow}{RESET} {short_pct}%"
        rest_part = f"  {current:>10}  {'N/A':>10}  {'N/A':>10}  ..."
        
        print(f"{stock_line}{arrow_part:>10}  {rest_part}")
    
    print("\n" + "-" * 80 + "\n")
    
    # Legend
    print(f"{BOLD}Legend:{RESET}\n")
    
    print(f"{RED}⬆{RESET} Strong upward trend   (>0.5% increase)  - Very bearish signal")
    print(f"{RED}↑{RESET} Upward trend          (>0.3% increase)  - Bearish signal")
    print(f"{YELLOW}→{RESET} Stable                (<0.3% change)    - Neutral")
    print(f"{GREEN}↓{RESET} Downward trend        (>0.3% decrease)  - Bullish signal")
    print(f"{GREEN}⬇{RESET} Strong downward trend (>0.5% decrease)  - Very bullish signal")
    print(f"{GRAY}?{RESET} No historical data    (insufficient data)")
    
    print("\n" + "-" * 80 + "\n")
    
    # Interpretation guide
    print(f"{BOLD}How to Interpret:{RESET}\n")
    
    print(f"📈 {RED}RED ARROWS (↑ ⬆){RESET}:")
    print("   • Short interest is INCREASING")
    print("   • More traders betting against the stock")
    print("   • BEARISH sentiment - Potential concern")
    print("   • Consider: Why are shorts increasing?\n")
    
    print(f"📉 {GREEN}GREEN ARROWS (↓ ⬇){RESET}:")
    print("   • Short interest is DECREASING")
    print("   • Fewer traders betting against the stock")
    print("   • BULLISH sentiment - Positive sign")
    print("   • Consider: Shorts covering or fundamentals improving?\n")
    
    print(f"➡️  {YELLOW}YELLOW ARROW (→){RESET}:")
    print("   • Short interest is STABLE")
    print("   • No significant change in last 7 days")
    print("   • NEUTRAL - Market still evaluating\n")
    
    print(f"❓ {GRAY}GRAY QUESTION MARK (?){RESET}:")
    print("   • Not enough historical data yet")
    print("   • Data collected daily from server")
    print("   • Wait a few days for trend to appear\n")
    
    print("-" * 80 + "\n")
    
    # Real-world example
    print(f"{BOLD}Real-World Example:{RESET}\n")
    
    print(f"Stock: VOLCAR-B (Volvo Cars)")
    print(f"Current short: 4.80%")
    print(f"7 days ago: 4.20%")
    print(f"Change: +0.60%")
    print(f"Display: {RED}⬆ 4.80%{RESET}")
    print(f"\nInterpretation:")
    print(f"  Short interest increased by 0.60 percentage points in a week.")
    print(f"  This is a strong increase (>0.5%), showing growing bearish sentiment.")
    print(f"  The RED double arrow ⬆ alerts you to investigate why shorts are rising.")
    print(f"  Possible reasons: earnings concerns, industry headwinds, etc.\n")
    
    print("-" * 80 + "\n")
    
    # Technical details
    print(f"{BOLD}Technical Details:{RESET}\n")
    
    print("• Look-back period: 7 days (configurable)")
    print("• Threshold for direction: 0.3% absolute change")
    print("• Strong threshold: 0.5% for double arrows (⬆⬇)")
    print("• Data source: short_positions_historical.json from remote server")
    print("• Update frequency: Daily via cron job")
    print("• Calculation: Simple subtraction (current - past)")
    print("• Performance: <1ms for all portfolio stocks\n")
    
    print("-" * 80 + "\n")
    
    # Next steps
    print(f"{BOLD}To See It in Action:{RESET}\n")
    
    print("1. Run: ./yspy.py")
    print("2. Press '7' to enter Watch Mode")
    print("3. Look for colored arrows before the Short% column")
    print("4. Press 's' to toggle between stocks and shares view")
    print("5. Arrows appear in both views\n")
    
    print(f"{BOLD}Note:{RESET} Trend arrows require historical short selling data.")
    print("      If your remote server is newly set up, wait a few days")
    print("      for sufficient data to accumulate.\n")
    
    print("=" * 80 + "\n")

if __name__ == "__main__":
    try:
        print_demo()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nError: {e}\n")
        sys.exit(1)
