#!/usr/bin/env python3
"""
Check the latest available closing prices from yfinance for all portfolio stocks
"""

import yfinance as yf
from datetime import datetime, timedelta

# Portfolio stocks
SWEDISH_STOCKS = [
    "ALLEI.ST",
    "NIBE-B.ST",
    "SCA-B.ST",
    "VISC.ST",
    "HEXA-B.ST",
    "ELUX-B.ST"
]

print("=" * 80)
print(f"Checking latest available prices from yfinance")
print(f"Current date: {datetime.now().strftime('%Y-%m-%d %A')}")
print(f"Target: Closest to Nov 4, 2025 closing")
print("=" * 80)
print()

for ticker in SWEDISH_STOCKS:
    print(f"\n{ticker}:")
    print("-" * 40)
    
    try:
        stock = yf.Ticker(ticker)
        
        # Get last 10 days of data
        hist = stock.history(period='10d')
        
        if hist.empty:
            print(f"  ❌ No data available")
            continue
        
        # Show all available dates
        print(f"  Available dates:")
        for date_idx in hist.index:
            date_str = date_idx.strftime('%Y-%m-%d %A')
            close = hist.loc[date_idx, 'Close']
            print(f"    {date_str}: {close:.2f} SEK")
        
        # Get the latest available price
        latest_date = hist.index[-1]
        latest_close = hist.iloc[-1]['Close']
        
        print(f"\n  ✅ Latest available:")
        print(f"     Date: {latest_date.strftime('%Y-%m-%d %A')}")
        print(f"     Close: {latest_close:.2f} SEK")
        
        # Check if we have Nov 3 data (Monday before Nov 4)
        nov3_data = hist[hist.index.strftime('%Y-%m-%d') == '2025-11-03']
        if not nov3_data.empty:
            nov3_close = nov3_data.iloc[0]['Close']
            print(f"\n  📌 Nov 3 (closest before Nov 4):")
            print(f"     Close: {nov3_close:.2f} SEK")
            
    except Exception as e:
        print(f"  ❌ Error: {e}")

print("\n" + "=" * 80)
print("SUMMARY - Latest available closing prices:")
print("=" * 80)

for ticker in SWEDISH_STOCKS:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='10d')
        
        if not hist.empty:
            latest_date = hist.index[-1]
            latest_close = hist.iloc[-1]['Close']
            print(f"{ticker:15} {latest_date.strftime('%Y-%m-%d')}: {latest_close:.2f} SEK")
        else:
            print(f"{ticker:15} No data available")
            
    except Exception as e:
        print(f"{ticker:15} Error: {e}")

print("=" * 80)
