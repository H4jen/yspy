#!/usr/bin/env python3
"""
Test script to preview the filtered Option 1 display
"""

from portfolio_manager import Portfolio
from short_selling_integration import ShortSellingIntegration

portfolio = Portfolio('portfolio', 'stockPortfolio.json')
integration = ShortSellingIntegration(portfolio)

# Get summary
summary = integration.get_portfolio_short_summary()

print("\n" + "="*70)
print("OPTION 1 - PORTFOLIO SHORT SELLING SUMMARY (FILTERED)")
print("="*70)

print(f"\nLast Updated: {summary.get('last_updated', 'Unknown')}")
print(f"Total Stocks Tracked: {summary.get('total_stocks_tracked', 0)}")
print(f"Stocks with Short Data: {summary.get('stocks_with_short_data', 0)}")
print("")

# Filter to owned stocks
portfolio_shorts = summary.get('portfolio_short_positions', [])
owned_shorts = []

for stock in portfolio_shorts:
    ticker = stock['ticker']
    stock_name = None
    for name, stock_obj in portfolio.stocks.items():
        if stock_obj.ticker == ticker:
            stock_name = name
            break
    
    if stock_name:
        total_shares = portfolio.stocks[stock_name].get_total_shares()
        if total_shares > 0:
            owned_shorts.append(stock)

if owned_shorts:
    print(f"📈 YOUR PORTFOLIO SHORT POSITIONS ({len(owned_shorts)} stocks owned)")
    print("-" * 50)
    for stock in owned_shorts:
        print(f"{stock['ticker']:15} {stock['percentage']:5.2f}%  {stock['company']}")
else:
    print("📈 YOUR PORTFOLIO SHORT POSITIONS (0 stocks owned)")
    print("-" * 50)
    print("None of your currently owned stocks have reported short positions.")

print("")

# Filter high short interest to owned stocks
high_short_stocks = summary.get('high_short_interest_stocks', [])
owned_high_shorts = []

for stock in high_short_stocks:
    ticker = stock['ticker']
    stock_name = None
    for name, stock_obj in portfolio.stocks.items():
        if stock_obj.ticker == ticker:
            stock_name = name
            break
    
    if stock_name:
        total_shares = portfolio.stocks[stock_name].get_total_shares()
        if total_shares > 0:
            owned_high_shorts.append(stock)

if owned_high_shorts:
    print("⚠️  HIGH SHORT INTEREST ALERTS (>5% in owned stocks)")
    print("-" * 50)
    for stock in owned_high_shorts:
        print(f"{stock['ticker']:15} {stock['percentage']:5.2f}%  {stock['company']}")
else:
    print("✅ No high short interest alerts in owned stocks")

print("\n" + "="*70)
print(f"Note: Showing only {len(owned_shorts)} owned stocks out of")
print(f"      {len(portfolio_shorts)} total stocks tracked with short data")
print("="*70 + "\n")
