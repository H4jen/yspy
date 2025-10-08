#!/usr/bin/env python3
"""
Test script to preview what menu option 2 displays
"""

from portfolio_manager import Portfolio
from short_selling_integration import ShortSellingIntegration

portfolio = Portfolio('portfolio', 'stockPortfolio.json')
integration = ShortSellingIntegration(portfolio)

# Test with a few stocks
test_stocks = ['ELUX-B.ST', 'HTRO.ST', 'NIBE-B.ST', 'BOL.ST', 'ALFA.ST']

for ticker in test_stocks:
    data = integration.get_stock_short_data(ticker)
    
    if not data:
        print(f"\n{'='*70}")
        print(f"Stock: {ticker}")
        print("No short selling data available")
        continue
    
    inner_data = data['data']
    
    print(f"\n{'='*70}")
    print(f"Short Selling Data for {ticker}")
    print('='*70)
    
    print(f"\n📊 Official Regulatory Data")
    print("-" * 50)
    print(f"Company: {inner_data.get('company_name', 'N/A')}")
    print(f"Market: {inner_data.get('market', 'N/A')}")
    print(f"Total Short Position: {inner_data.get('short_percentage', 0):.2f}%")
    print(f"Position Date: {inner_data.get('position_date', 'N/A')}")
    print(f"Reporting Threshold: {inner_data.get('threshold_crossed', '0.5%')}")
    
    # Risk indicator
    short_pct = inner_data.get('short_percentage', 0)
    if short_pct > 10:
        risk_level = "🔴 VERY HIGH"
        risk_desc = "Extremely high short interest - major bearish pressure"
    elif short_pct > 5:
        risk_level = "🟠 HIGH"
        risk_desc = "High short interest - significant bearish sentiment"
    elif short_pct > 2:
        risk_level = "🟡 MODERATE"
        risk_desc = "Moderate short interest - some bearish sentiment"
    else:
        risk_level = "🟢 LOW"
        risk_desc = "Low short interest - minimal bearish pressure"
    
    print(f"\nRisk Level: {risk_level}")
    print(f"Assessment: {risk_desc}")
    
    if 'match_quality' in inner_data:
        quality = inner_data['match_quality']
        score = inner_data.get('match_score', 0)
        print(f"Data Match Quality: {quality.title()} (score: {score})")
    
    # Individual holders
    individual_holders = inner_data.get('individual_holders', [])
    if individual_holders:
        print(f"\n📋 Individual Position Holders ({len(individual_holders)}):")
        print("-" * 50)
        
        for i, holder in enumerate(individual_holders[:5], 1):
            holder_name = holder.get('holder_name', 'Unknown')
            holder_pct = holder.get('position_percentage', 0)
            pct_of_total = (holder_pct / short_pct * 100) if short_pct > 0 else 0
            print(f"{i:2}. {holder_name:40} {holder_pct:5.2f}% ({pct_of_total:4.1f}% of total)")
        
        if len(individual_holders) > 5:
            remaining = len(individual_holders) - 5
            remaining_pct = sum(h.get('position_percentage', 0) for h in individual_holders[5:])
            print(f"    ... and {remaining} more holders totaling {remaining_pct:.2f}%")
    else:
        print(f"\nSummary: {inner_data.get('position_holder', 'Multiple holders')}")
        print("\n⚠️  Individual holder details not available")
        print("    (Position may be historical or aggregated)")

print(f"\n{'='*70}")
print("Test complete!")
print('='*70)
