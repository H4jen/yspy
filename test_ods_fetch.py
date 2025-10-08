#!/usr/bin/env python3
"""
Test script to fetch and examine .ods files from Finansinspektionen
"""

import sys
from pathlib import Path
import logging

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from short_selling_tracker import ShortSellingTracker

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    print("\n" + "="*70)
    print("Testing FI .ods File Fetching")
    print("="*70 + "\n")
    
    tracker = ShortSellingTracker(portfolio_path=Path(__file__).parent / "portfolio")
    
    # Test fetching current positions file
    print("\n--- Testing Current Positions File ---")
    df_current = tracker.fetch_fi_ods_file('current')
    if df_current is not None:
        print(f"✓ Current positions file downloaded successfully")
        print(f"  Shape: {df_current.shape}")
        print(f"  Columns: {list(df_current.columns)}")
        print(f"\nFirst 5 rows:")
        print(df_current.head())
        
        # Parse to ShortPosition objects
        positions = tracker.parse_fi_dataframe(df_current, 'current')
        print(f"\n✓ Parsed {len(positions)} positions")
        if positions:
            print("\nTop 5 by short percentage:")
            sorted_pos = sorted(positions, key=lambda p: p.position_percentage, reverse=True)
            for i, pos in enumerate(sorted_pos[:5], 1):
                print(f"  {i}. {pos.company_name}: {pos.position_percentage:.2f}%")
    else:
        print("✗ Failed to download current positions file")
    
    # Test fetching aggregated positions file
    print("\n--- Testing Aggregated Positions File ---")
    df_agg = tracker.fetch_fi_ods_file('aggregated')
    if df_agg is not None:
        print(f"✓ Aggregated positions file downloaded successfully")
        print(f"  Shape: {df_agg.shape}")
        print(f"  Columns: {list(df_agg.columns)}")
        print(f"\nFirst 5 rows:")
        print(df_agg.head())
        
        # Parse to ShortPosition objects
        positions_agg = tracker.parse_fi_dataframe(df_agg, 'aggregated')
        print(f"\n✓ Parsed {len(positions_agg)} aggregated positions")
        
        # Show positions in 0.1-0.5% range
        low_range = [p for p in positions_agg if 0.1 <= p.position_percentage < 0.5]
        print(f"\nPositions in 0.1-0.5% range: {len(low_range)}")
        if low_range:
            print("Examples:")
            for pos in low_range[:5]:
                print(f"  • {pos.company_name}: {pos.position_percentage:.2f}%")
    else:
        print("✗ Failed to download aggregated positions file")
    
    # Test fetching historical positions file
    print("\n--- Testing Historical Positions File ---")
    df_hist = tracker.fetch_fi_ods_file('historical')
    if df_hist is not None:
        print(f"✓ Historical positions file downloaded successfully")
        print(f"  Shape: {df_hist.shape}")
        print(f"  Columns: {list(df_hist.columns)}")
        print(f"\nFirst 5 rows:")
        print(df_hist.head())
    else:
        print("✗ Failed to download historical positions file")
    
    # Now test the full fetch_swedish_short_positions with new .ods logic
    print("\n" + "="*70)
    print("Testing Full Swedish Short Position Fetch")
    print("="*70 + "\n")
    
    all_positions = tracker.fetch_swedish_short_positions()
    print(f"\n✓ Total positions fetched: {len(all_positions)}")
    
    if all_positions:
        print("\nTop 10 by short percentage:")
        sorted_all = sorted(all_positions, key=lambda p: p.position_percentage, reverse=True)
        for i, pos in enumerate(sorted_all[:10], 1):
            print(f"  {i:2d}. {pos.company_name:40s} {pos.position_percentage:6.2f}%")
    
    print("\n" + "="*70)
    print("Test Complete")
    print("="*70 + "\n")

if __name__ == '__main__':
    main()
