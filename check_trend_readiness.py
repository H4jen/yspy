#!/usr/bin/env python3
"""
Quick test to see if trend arrows will show with current data.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

print("=" * 70)
print("SHORT TREND ARROW READINESS CHECK")
print("=" * 70)
print()

# Check 1: Historical data exists
hist_file = Path('portfolio/remote_cache/short_positions_historical.json')
if not hist_file.exists():
    print("✗ No historical data file found")
    print(f"  Expected: {hist_file}")
    print()
    print("Solution: Set up remote data source or wait for cron job")
    sys.exit(1)

print(f"✓ Historical data file exists: {hist_file}")

# Check 2: Parse historical data
with open(hist_file) as f:
    historical_data = json.load(f)

print(f"✓ Historical data loaded: {len(historical_data)} companies")
print()

# Check 3: Analyze data points per company
print("-" * 70)
print("DATA POINT ANALYSIS")
print("-" * 70)
print()

companies_with_1_point = 0
companies_with_2_7_points = 0  
companies_with_8plus_points = 0

sample_companies = []

for company_name, company_data in historical_data.items():
    history = company_data.get('history', {})
    num_points = len(history)
    
    if num_points == 1:
        companies_with_1_point += 1
    elif 2 <= num_points <= 7:
        companies_with_2_7_points += 1
        if len(sample_companies) < 3:
            sample_companies.append((company_name, num_points, history))
    else:
        companies_with_8plus_points += 1
        if len(sample_companies) < 3:
            sample_companies.append((company_name, num_points, history))

print(f"Companies with 1 data point:    {companies_with_1_point:>4}  (cannot calculate trend yet)")
print(f"Companies with 2-7 data points:  {companies_with_2_7_points:>4}  (can calculate trend)")
print(f"Companies with 8+ data points:   {companies_with_8plus_points:>4}  (full 7-day trend)")
print()

# Check 4: Show sample trend calculation
if sample_companies:
    print("-" * 70)
    print("SAMPLE TREND CALCULATIONS")
    print("-" * 70)
    print()
    
    for company_name, num_points, history in sample_companies[:3]:
        dates = sorted(history.keys())
        current_date = dates[-1]
        current_pct = history[current_date]['percentage']
        
        print(f"Company: {company_name}")
        print(f"  Data points: {num_points}")
        print(f"  Current: {current_pct:.2f}% ({current_date})")
        
        if num_points >= 2:
            # Try to find 7-day old data or use oldest
            target_date = (datetime.now() - timedelta(days=7)).date().isoformat()
            past_pct = None
            past_date = None
            
            for date_str in sorted(dates, reverse=True):
                if date_str <= target_date:
                    past_pct = history[date_str]['percentage']
                    past_date = date_str
                    break
            
            if past_pct is None:
                # Use oldest
                past_date = dates[0]
                past_pct = history[past_date]['percentage']
            
            change = current_pct - past_pct
            
            # Determine arrow
            if abs(change) < 0.3:
                arrow = "→"
                color = "YELLOW"
            elif change >= 0.5:
                arrow = "⬆"
                color = "RED"
            elif change > 0.3:
                arrow = "↑"
                color = "RED"
            elif change <= -0.5:
                arrow = "⬇"
                color = "GREEN"
            else:
                arrow = "↓"
                color = "GREEN"
            
            print(f"  Past: {past_pct:.2f}% ({past_date})")
            print(f"  Change: {change:+.2f}%")
            print(f"  Arrow: {arrow} ({color})")
        else:
            print(f"  Arrow: ? (need at least 2 data points)")
        
        print()

print("-" * 70)
print("SUMMARY")
print("-" * 70)
print()

if companies_with_2_7_points + companies_with_8plus_points > 0:
    print(f"✓ {companies_with_2_7_points + companies_with_8plus_points} companies have enough data for trends")
    print()
    print("Arrows WILL appear in watch screen for these companies!")
    print()
    print("To see them:")
    print("  1. Run: ./yspy.py")
    print("  2. Press '7' to enter watch mode")
    print("  3. Look for arrows before Short% column")
else:
    print(f"✗ Only {companies_with_1_point} companies with 1 data point")
    print()
    print("Arrows will show '?' (no data) until more daily data accumulates.")
    print()
    print("Wait 1-2 more days for trend arrows to appear.")
    print("Historical data is collected daily via cron job.")

print()
print("=" * 70)
