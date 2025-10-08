#!/usr/bin/env python3
"""
Test script to demonstrate individual holder tracking
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from short_selling_tracker import ShortSellingTracker
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    print("\n" + "="*80)
    print("Testing Individual Holder Tracking")
    print("="*80 + "\n")
    
    tracker = ShortSellingTracker(portfolio_path=Path(__file__).parent / "portfolio")
    
    # Fetch positions with holder details
    positions = tracker.fetch_swedish_short_positions()
    
    if not positions:
        print("No positions fetched!")
        return
    
    print(f"\n✓ Fetched {len(positions)} companies")
    
    # Count how many have individual holder details
    with_holders = [p for p in positions if p.individual_holders]
    without_holders = [p for p in positions if not p.individual_holders]
    
    print(f"  - {len(with_holders)} companies with individual holder details")
    print(f"  - {len(without_holders)} companies with aggregated totals only")
    
    # Show top 5 by short % with holder details
    print("\n" + "="*80)
    print("Top 10 Companies by Short Interest (with holder details where available)")
    print("="*80 + "\n")
    
    sorted_positions = sorted(positions, key=lambda p: p.position_percentage, reverse=True)
    
    for i, pos in enumerate(sorted_positions[:10], 1):
        print(f"\n{i}. {pos.company_name}")
        print(f"   Total Short: {pos.position_percentage:.2f}%")
        print(f"   Date: {pos.position_date}")
        print(f"   Threshold: {pos.threshold_crossed}")
        
        if pos.individual_holders:
            print(f"   Individual Holders ({len(pos.individual_holders)}):")
            for j, holder in enumerate(pos.individual_holders[:5], 1):  # Show top 5 holders
                print(f"      {j}. {holder.holder_name:50s} {holder.position_percentage:5.2f}% ({holder.position_date})")
            if len(pos.individual_holders) > 5:
                remaining = len(pos.individual_holders) - 5
                remaining_pct = sum(h.position_percentage for h in pos.individual_holders[5:])
                print(f"      ... and {remaining} more holders ({remaining_pct:.2f}%)")
        else:
            print(f"   {pos.position_holder} (individual holder details not available)")
    
    # Show some examples of smaller positions (0.1-0.5% range)
    print("\n" + "="*80)
    print("Examples of Smaller Short Positions (0.1-0.5% range)")
    print("="*80 + "\n")
    
    small_positions = [p for p in positions if 0.1 <= p.position_percentage < 0.5]
    small_positions.sort(key=lambda p: p.position_percentage, reverse=True)
    
    print(f"Found {len(small_positions)} companies in 0.1-0.5% range\n")
    
    for pos in small_positions[:10]:
        print(f"  • {pos.company_name:50s} {pos.position_percentage:5.2f}%")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    main()
