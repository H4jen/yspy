# Migration Guide: Integrating Remote Short Data into yspy

This guide shows how to integrate the new remote short data system into your existing yspy application.

## Overview

The remote short data system is designed to be **non-invasive** and can be integrated gradually. You have two options:

### Option 1: Drop-in Replacement (Recommended - 5 minutes)
Replace the tracker import in one file. Everything else stays the same.

### Option 2: Gradual Integration (30 minutes)
Manually integrate the fetcher where needed, giving you more control.

---

## Option 1: Drop-in Replacement (Easiest)

### Step 1: Configure Remote Data Source

Create `remote_config.json` in the project root:

```json
{
  "protocol": "file",
  "location": "/mnt/yspy_data",
  "cache_ttl_hours": 6
}
```

*Adjust the location based on your setup (NFS mount, HTTP URL, SSH path, etc.)*

### Step 2: Modify short_selling_integration.py

Find this line (probably near the top):
```python
from short_selling_tracker import ShortSellingTracker
```

Replace with:
```python
from remote_integration_helper import RemoteShortSellingTracker as ShortSellingTracker
```

**That's it!** The rest of your code stays exactly the same.

### What This Does:
- `RemoteShortSellingTracker` has the same interface as `ShortSellingTracker`
- It tries to use remote data first
- Falls back to local tracker if remote unavailable
- All your existing code continues to work

### Testing:
```bash
# Run yspy normally
./yspy.py

# Check if remote data is being used
# Look for log message: "Remote data source configured successfully"
```

---

## Option 2: Gradual Integration

For more control, integrate the fetcher manually.

### Step 1: Add Remote Data Import

In `short_selling_integration.py`, add at the top:

```python
from remote_short_data import load_remote_config, RemoteShortDataFetcher
from datetime import datetime
```

### Step 2: Initialize in ShortSellingIntegration.__init__

```python
class ShortSellingIntegration:
    def __init__(self, portfolio_path="portfolio"):
        self.portfolio_path = Path(portfolio_path)
        self.tracker = ShortSellingTracker(portfolio_path)
        
        # NEW: Add remote fetcher
        try:
            self.remote_config = load_remote_config()
            self.remote_fetcher = RemoteShortDataFetcher(self.remote_config)
            self.use_remote = True
            logger.info("Remote data source enabled")
        except Exception as e:
            logger.warning(f"Remote data not available: {e}")
            self.use_remote = False
```

### Step 3: Modify update_short_data Method

```python
def update_short_data(self) -> Dict:
    """Update short selling data from remote or local source."""
    
    if self.use_remote:
        try:
            # Try remote first
            success, data = self.remote_fetcher.fetch_data(force_refresh=True)
            
            if success and data:
                logger.info(f"Updated from remote: {len(data['positions'])} positions")
                return {
                    'success': True,
                    'updated': True,
                    'message': f"Remote update: {len(data['positions'])} positions",
                    'stats': data.get('metadata', {})
                }
        except Exception as e:
            logger.warning(f"Remote update failed: {e}, falling back to local")
    
    # Fallback to local update
    return self.tracker.update_short_positions()
```

### Step 4: Modify get_portfolio_short_data Method

```python
def get_portfolio_short_data(self, stock_portfolio: Dict) -> Dict:
    """Get short data, preferring remote source."""
    
    if self.use_remote:
        try:
            success, data = self.remote_fetcher.fetch_data()
            
            if success and data:
                # Build result from remote data
                result = {}
                positions = data.get('positions', [])
                
                for ticker, stock_data in stock_portfolio.items():
                    company_name = stock_data.get('company_name', ticker.replace('_', '.'))
                    
                    # Find matching position
                    for pos in positions:
                        if self._matches_ticker(pos, ticker, company_name):
                            result[ticker] = self._format_position(pos)
                            break
                
                return result
        except Exception as e:
            logger.warning(f"Remote fetch failed: {e}, using local")
    
    # Fallback to local
    return self.tracker.get_portfolio_short_data(stock_portfolio)

def _matches_ticker(self, pos: Dict, ticker: str, company_name: str) -> bool:
    """Check if position matches ticker."""
    ticker_normalized = ticker.replace('_', '.')
    return (pos['ticker'].upper() == ticker_normalized.upper() or
            pos['company_name'].lower() == company_name.lower())

def _format_position(self, pos: Dict) -> Dict:
    """Format position dict for compatibility."""
    return {
        'ticker': pos['ticker'],
        'company_name': pos['company_name'],
        'position_percentage': pos['position_percentage'],
        'position_date': pos['position_date'],
        'individual_holders': pos.get('individual_holders', []),
        'holder_count': len(pos.get('individual_holders', []))
    }
```

### Step 5: Add Historical Data Support

```python
def get_short_history(self, ticker: str, days: int = 30) -> Dict:
    """Get historical short data (only available with remote)."""
    
    if not self.use_remote:
        logger.info("Historical data not available with local tracker")
        return {}
    
    try:
        success, data = self.remote_fetcher.fetch_data()
        
        if success and data and 'historical' in data:
            historical = data['historical']
            
            # Find matching company
            ticker_normalized = ticker.replace('_', '.')
            
            for company_name, company_data in historical.items():
                ticker_match = company_data.get('ticker', '').upper()
                if ticker_normalized.upper() in ticker_match:
                    # Filter to last N days
                    from datetime import datetime, timedelta
                    cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
                    history = company_data.get('history', {})
                    
                    return {
                        'ticker': company_data['ticker'],
                        'company': company_name,
                        'history': {
                            date: data for date, data in history.items()
                            if date >= cutoff
                        }
                    }
        
        return {}
        
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        return {}
```

---

## Testing the Integration

### Test 1: Basic Functionality
```bash
# Run yspy normally
./yspy.py

# Go to Short Selling menu
# Option 1: View portfolio summary
# Should show short data for your stocks
```

### Test 2: Remote Connection
```python
# Test in Python
python3 -c "
from short_selling_integration import ShortSellingIntegration
integration = ShortSellingIntegration()
print(f'Using remote: {integration.use_remote}')
"
```

### Test 3: Data Freshness
```bash
# Check when data was last updated
cat portfolio/remote_cache/short_positions_meta.json
```

### Test 4: Update Function
```python
# Test update
python3 -c "
from short_selling_integration import ShortSellingIntegration
integration = ShortSellingIntegration()
result = integration.update_short_data()
print(f'Success: {result[\"success\"]}')
print(f'Message: {result[\"message\"]}')
"
```

---

## Adding Historical Graphs (Menu Option 5)

Once integrated, add historical visualization to `short_selling_menu.py`:

### In the trends menu option:

```python
def _show_trends(self):
    """Show short interest trends."""
    
    # Show menu of stocks with historical data
    available_stocks = self._get_stocks_with_history()
    
    if not available_stocks:
        self.stdscr.addstr(2, 2, "No historical data available yet")
        self.stdscr.addstr(3, 2, "Run updates for a few days to build history")
        self.stdscr.addstr(5, 2, "Press any key to continue...")
        self.stdscr.getch()
        return
    
    # Let user select a stock
    selected = self._select_stock_for_trend(available_stocks)
    
    if selected:
        self._display_trend_graph(selected)

def _get_stocks_with_history(self) -> List[str]:
    """Get stocks with historical data."""
    try:
        from short_selling_integration import ShortSellingIntegration
        integration = ShortSellingIntegration()
        
        if hasattr(integration, 'remote_fetcher'):
            success, data = integration.remote_fetcher.fetch_data()
            if success and data and 'historical' in data:
                return list(data['historical'].keys())
    except:
        pass
    
    return []

def _display_trend_graph(self, stock: str):
    """Display trend graph for a stock."""
    from short_selling_integration import ShortSellingIntegration
    integration = ShortSellingIntegration()
    
    # Get 30 days of history
    history = integration.get_short_history(stock, days=30)
    
    if not history or not history.get('history'):
        self.stdscr.addstr(2, 2, "No history available for this stock")
        self.stdscr.getch()
        return
    
    # Display
    self.stdscr.clear()
    self.stdscr.addstr(0, 2, f"Short Interest Trend: {stock}")
    self.stdscr.addstr(1, 2, "=" * 70)
    
    # Sort dates
    dates = sorted(history['history'].keys())
    percentages = [history['history'][d]['percentage'] for d in dates]
    
    # Display as sparkline
    line = 3
    self.stdscr.addstr(line, 2, "Percentage:")
    line += 1
    
    for date, pct in zip(dates, percentages):
        self.stdscr.addstr(line, 4, f"{date}: {pct:5.2f}%")
        
        # Add visual bar
        bar_length = int(pct * 2)  # Scale for display
        self.stdscr.addstr(line, 30, "█" * bar_length)
        
        line += 1
    
    # Stats
    line += 1
    self.stdscr.addstr(line, 2, f"Average: {sum(percentages)/len(percentages):.2f}%")
    line += 1
    self.stdscr.addstr(line, 2, f"Min: {min(percentages):.2f}%")
    line += 1
    self.stdscr.addstr(line, 2, f"Max: {max(percentages):.2f}%")
    line += 1
    
    # Trend indicator
    if len(percentages) >= 2:
        trend = "↑ Increasing" if percentages[-1] > percentages[0] else "↓ Decreasing"
        self.stdscr.addstr(line, 2, f"Trend: {trend}")
    
    line += 2
    self.stdscr.addstr(line, 2, "Press any key to continue...")
    self.stdscr.getch()
```

---

## Rollback Plan

If something goes wrong:

### For Option 1 (Drop-in):
```python
# Simply revert the import in short_selling_integration.py:
from short_selling_tracker import ShortSellingTracker  # Back to original
```

### For Option 2 (Gradual):
```bash
# Use git to revert changes:
git checkout short_selling_integration.py
```

### Data Preservation:
Your local short_positions.json is never modified by the remote system, so your existing data is always safe.

---

## Monitoring After Integration

### Check Remote Status:
```python
python3 -c "
from short_selling_integration import ShortSellingIntegration
integration = ShortSellingIntegration()
if hasattr(integration, 'remote_fetcher'):
    status = integration.remote_fetcher.get_status()
    import json
    print(json.dumps(status, indent=2))
"
```

### View Logs:
```bash
# Server logs
tail -f /tmp/yspy_shorts_update.log

# Client logs (if you have logging enabled)
grep "remote" yspy.log
```

---

## Summary

**Option 1 (Recommended)**:
- Change 1 line in short_selling_integration.py
- 5 minutes
- Fully compatible
- Easy rollback

**Option 2 (Advanced)**:
- More control
- 30 minutes
- Add historical support
- Manual integration

Both options are **backward compatible** - if remote data is unavailable, the system automatically falls back to local operation.

---

## Need Help?

- See `REMOTE_SETUP.md` for server setup
- See `QUICK_REFERENCE.txt` for quick commands
- Run `./test_remote_setup.py` to verify setup
- Check logs for errors

The system is designed to fail gracefully - if anything goes wrong, it falls back to the existing local tracker.
