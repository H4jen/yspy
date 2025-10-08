#!/usr/bin/env python3
"""
Standalone script to update short selling data via cron.

This script can run independently on a server without the full yspy application.
It fetches short selling data and stores it in a location accessible to yspy.

Usage:
    ./update_shorts_cron.py --output /path/to/shared/directory

Cron example (daily at 9 AM):
    0 9 * * * /path/to/yspy/.venv/bin/python3 /path/to/yspy/update_shorts_cron.py --output /shared/yspy_data
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from short_selling_tracker import ShortSellingTracker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/yspy_shorts_update.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def update_short_data(output_dir: Path, portfolio_dir: Path = None) -> bool:
    """
    Fetch and save short selling data.
    
    Args:
        output_dir: Directory to save the data files
        portfolio_dir: Optional portfolio directory (for ticker list)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info("=" * 70)
        logger.info("Starting short selling data update via cron")
        logger.info("=" * 70)
        
        # Create output directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize tracker
        # If no portfolio_dir specified, use a temporary one
        # The tracker will fetch ALL available short positions
        tracker = ShortSellingTracker(str(portfolio_dir) if portfolio_dir else "portfolio")
        
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"Fetching short positions from regulatory sources...")
        
        # Fetch all Swedish short positions (comprehensive)
        swedish_positions = tracker.fetch_swedish_short_positions()
        logger.info(f"✓ Fetched {len(swedish_positions)} Swedish positions")
        
        # Fetch Finnish positions
        finnish_positions = tracker.fetch_finnish_short_positions()
        logger.info(f"✓ Fetched {len(finnish_positions)} Finnish positions")
        
        # Combine all positions
        all_positions = swedish_positions + finnish_positions
        logger.info(f"✓ Total positions: {len(all_positions)}")
        
        # Count positions with individual holder details
        positions_with_holders = sum(1 for pos in all_positions if pos.individual_holders)
        logger.info(f"✓ Positions with holder details: {positions_with_holders}")
        
        # Prepare data structure
        current_data = {
            'last_updated': datetime.now().isoformat(),
            'update_source': 'cron_scheduled',
            'positions': [
                {
                    'ticker': pos.ticker,
                    'company_name': pos.company_name,
                    'position_holder': pos.position_holder,
                    'position_percentage': pos.position_percentage,
                    'position_date': pos.position_date,
                    'market': pos.market,
                    'threshold_crossed': pos.threshold_crossed,
                    'individual_holders': [
                        {
                            'holder_name': h.holder_name,
                            'position_percentage': h.position_percentage,
                            'position_date': h.position_date
                        }
                        for h in (pos.individual_holders or [])
                    ]
                }
                for pos in all_positions
            ]
        }
        
        # Save current snapshot
        current_file = output_dir / "short_positions_current.json"
        with open(current_file, 'w') as f:
            json.dump(current_data, f, indent=2)
        logger.info(f"✓ Saved current snapshot: {current_file}")
        
        # Save/append to historical data
        save_historical_snapshot(output_dir, all_positions)
        
        # Save metadata
        metadata = {
            'last_update': datetime.now().isoformat(),
            'next_update': 'daily_9am',
            'total_positions': len(all_positions),
            'positions_with_holders': positions_with_holders,
            'markets': ['SE', 'FI'],
            'status': 'success'
        }
        
        metadata_file = output_dir / "short_positions_meta.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        logger.info(f"✓ Saved metadata: {metadata_file}")
        
        logger.info("=" * 70)
        logger.info("✅ Short selling data update completed successfully")
        logger.info("=" * 70)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error updating short data: {e}", exc_info=True)
        
        # Save error metadata
        try:
            metadata = {
                'last_update': datetime.now().isoformat(),
                'status': 'error',
                'error_message': str(e)
            }
            metadata_file = output_dir / "short_positions_meta.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
        except:
            pass
        
        return False


def save_historical_snapshot(output_dir: Path, positions: list):
    """
    Save historical snapshot of short positions.
    
    Maintains a rolling history with daily snapshots.
    """
    try:
        historical_file = output_dir / "short_positions_historical.json"
        
        # Load existing historical data
        if historical_file.exists():
            with open(historical_file) as f:
                historical_data = json.load(f)
        else:
            historical_data = {}
        
        # Current date
        today = datetime.now().date().isoformat()
        
        # Add today's snapshot for each position
        for pos in positions:
            # Use company name as key (more stable than ticker)
            company_key = pos.company_name
            
            if company_key not in historical_data:
                historical_data[company_key] = {
                    'ticker': pos.ticker,
                    'market': pos.market,
                    'history': {}
                }
            
            # Update ticker if changed (rare but possible)
            historical_data[company_key]['ticker'] = pos.ticker
            
            # Add today's data point
            historical_data[company_key]['history'][today] = {
                'percentage': pos.position_percentage,
                'holders': len(pos.individual_holders) if pos.individual_holders else 0,
                'top_holder': pos.individual_holders[0].holder_name if pos.individual_holders else None,
                'top_holder_pct': pos.individual_holders[0].position_percentage if pos.individual_holders else None
            }
        
        # Purge old data (keep last 365 days)
        cutoff_date = (datetime.now().date() - timedelta(days=365)).isoformat()
        for company_key in list(historical_data.keys()):
            history = historical_data[company_key]['history']
            historical_data[company_key]['history'] = {
                date: data for date, data in history.items() 
                if date >= cutoff_date
            }
            
            # Remove company if no history left
            if not historical_data[company_key]['history']:
                del historical_data[company_key]
        
        # Save historical data
        with open(historical_file, 'w') as f:
            json.dump(historical_data, f, indent=2)
        
        logger.info(f"✓ Updated historical data: {len(historical_data)} companies tracked")
        
        # Log some statistics
        total_days = sum(len(data['history']) for data in historical_data.values())
        avg_days = total_days / len(historical_data) if historical_data else 0
        logger.info(f"  Average history: {avg_days:.1f} days per company")
        
    except Exception as e:
        logger.error(f"Error saving historical snapshot: {e}")


def main():
    """Main entry point for cron script."""
    parser = argparse.ArgumentParser(
        description='Update short selling data for yspy (cron-friendly)'
    )
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Output directory for data files (e.g., /shared/yspy_data)'
    )
    parser.add_argument(
        '--portfolio',
        type=str,
        default=None,
        help='Portfolio directory (optional, defaults to fetching all positions)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Convert paths
    output_dir = Path(args.output)
    portfolio_dir = Path(args.portfolio) if args.portfolio else None
    
    # Run update
    success = update_short_data(output_dir, portfolio_dir)
    
    # Exit with appropriate code for cron monitoring
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
