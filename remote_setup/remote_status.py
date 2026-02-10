#!/usr/bin/env python3
"""
Check status of the remote short selling data server.

Usage:
    ./remote_status.py                  # Check status
    ./remote_status.py --update         # Force update on remote
    ./remote_status.py --logs           # Show recent logs
    ./remote_status.py --fetch          # Fetch latest data to local
    ./remote_status.py --version        # Check local and remote versions
"""

__version__ = "1.2.0"  # 2026-02-02: Background updates, version checking

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Remote server configuration
REMOTE_HOST = "barbapappa@192.168.66.1"
REMOTE_PATH = "/home/barbapappa/projects/yspy_data"
REMOTE_VENV_PYTHON = f"{REMOTE_PATH}/venv/bin/python"
SSH_KEY = "~/.ssh/id_rsa"

# Local paths
LOCAL_CONFIG = Path(__file__).parent.parent / "remote_config.json"


def run_ssh_command(command: str, timeout: int = 30) -> tuple:
    """Run command on remote server via SSH."""
    ssh_cmd = [
        "ssh",
        "-i", SSH_KEY,
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=no",
        REMOTE_HOST,
        command
    ]
    
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Connection timed out"
    except Exception as e:
        return False, "", str(e)


def check_status():
    """Check status of remote data."""
    print("=" * 60)
    print("Remote Short Selling Data Server Status")
    print("=" * 60)
    print(f"Host: {REMOTE_HOST}")
    print(f"Path: {REMOTE_PATH}")
    print()
    
    # Check if server is reachable
    print("Checking connection...", end=" ")
    success, _, err = run_ssh_command("echo OK")
    if not success:
        print(f"❌ FAILED: {err}")
        return False
    print("✓ Connected")
    
    # Get metadata
    print("Fetching status...", end=" ")
    success, output, err = run_ssh_command(f"cat {REMOTE_PATH}/short_positions_meta.json 2>/dev/null")
    
    if not success or not output.strip():
        print("❌ No metadata found")
        return False
    
    print("✓ OK")
    print()
    
    try:
        meta = json.loads(output)
        
        # Parse last update
        last_update = meta.get('last_update', 'Unknown')
        if last_update != 'Unknown':
            try:
                dt = datetime.fromisoformat(last_update)
                age = datetime.now() - dt
                age_str = f"{age.total_seconds() / 3600:.1f} hours ago"
            except:
                age_str = "Unknown"
        else:
            age_str = "Unknown"
        
        status = meta.get('status', 'Unknown')
        status_icon = "✓" if status == 'success' else "❌" if status in ['error', 'validation_failed'] else "?"
        
        print(f"Last Update:      {last_update}")
        print(f"Age:              {age_str}")
        print(f"Status:           {status_icon} {status}")
        print(f"Total Positions:  {meta.get('total_positions', 'N/A')}")
        print(f"With Holders:     {meta.get('positions_with_holders', 'N/A')}")
        print(f"Markets:          {', '.join(meta.get('markets', []))}")
        
        # Show validation info if present
        validation = meta.get('validation', {})
        if validation:
            print()
            print("Validation:")
            print(f"  Passed:         {'✓' if validation.get('passed') else '❌'}")
            print(f"  Warnings:       {validation.get('warnings_count', 0)}")
            if validation.get('warnings'):
                for w in validation['warnings'][:3]:
                    print(f"    - {w}")
        
        # Show errors if any
        if meta.get('validation_errors'):
            print()
            print("❌ Validation Errors:")
            for e in meta['validation_errors'][:5]:
                print(f"  - {e}")
        
    except json.JSONDecodeError:
        print(f"❌ Could not parse metadata: {output[:100]}")
        return False
    
    print()
    
    # Check data file
    success, output, _ = run_ssh_command(f"wc -l {REMOTE_PATH}/short_positions_current.json 2>/dev/null | cut -d' ' -f1")
    if success and output.strip():
        print(f"Data File:        {output.strip()} lines")
    
    # Check log file
    success, output, _ = run_ssh_command("tail -1 /tmp/yspy_shorts_update.log 2>/dev/null")
    if success and output.strip():
        print(f"Last Log Entry:   {output.strip()[:60]}...")
    
    # Check cron job
    print()
    success, output, _ = run_ssh_command("crontab -l 2>/dev/null | grep update_shorts")
    if success and output.strip():
        print(f"Cron Job:         ✓ Configured")
        print(f"  {output.strip()}")
    else:
        print("Cron Job:         ❌ Not configured")
    
    print()
    print("=" * 60)
    return True


def force_update():
    """Force an update on the remote server (runs in background)."""
    print("Triggering remote update in background...")
    print()
    
    # Run in background with nohup, redirect output to log
    cmd = f"nohup {REMOTE_VENV_PYTHON} {REMOTE_PATH}/update_shorts_cron.py --output {REMOTE_PATH} --verbose >> /tmp/yspy_shorts_update.log 2>&1 &"
    
    success, output, err = run_ssh_command(cmd, timeout=10)
    
    if success:
        print("✓ Update started in background")
        print()
        print("Check progress with:")
        print("  python3 remote_setup/remote_status.py --logs")
    else:
        print("❌ Failed to start update")
        if err:
            print(err)
    
    return success


def show_logs(lines: int = 50):
    """Show recent log entries."""
    print(f"Last {lines} log entries:")
    print("-" * 60)
    
    success, output, err = run_ssh_command(f"tail -n {lines} /tmp/yspy_shorts_update.log 2>/dev/null")
    
    if success:
        print(output)
    else:
        print(f"❌ Could not fetch logs: {err}")


def show_history():
    """Show history of update runs with their status."""
    print("Update History (recent runs):")
    print("-" * 70)
    
    # Get log entries for starts and completions
    cmd = """grep -E '(Starting short selling|completed successfully|validation FAILED|Error updating|Total positions:)' /tmp/yspy_shorts_update.log 2>/dev/null | tail -40"""
    
    success, output, err = run_ssh_command(cmd)
    
    if not success or not output.strip():
        print("No history found in logs")
        return
    
    lines = output.strip().split('\n')
    
    runs = []
    current_run = None
    
    for line in lines:
        if 'Starting short selling' in line:
            # New run started
            timestamp = line.split(' - ')[0] if ' - ' in line else 'Unknown'
            current_run = {'start': timestamp, 'status': 'running', 'positions': '?'}
        elif 'completed successfully' in line and current_run:
            current_run['status'] = '✓ SUCCESS'
            runs.append(current_run)
            current_run = None
        elif 'validation FAILED' in line and current_run:
            current_run['status'] = '❌ VALIDATION FAILED'
            runs.append(current_run)
            current_run = None
        elif 'Error updating' in line and current_run:
            current_run['status'] = '❌ ERROR'
            runs.append(current_run)
            current_run = None
        elif 'Total positions:' in line and current_run:
            # Extract position count
            try:
                count = line.split('Total positions:')[1].strip().split()[0]
                current_run['positions'] = count
            except:
                pass
    
    # Add any in-progress run
    if current_run:
        current_run['status'] = '⏳ IN PROGRESS'
        runs.append(current_run)
    
    if not runs:
        print("No completed runs found")
        return
    
    # Display runs (most recent first)
    print(f"{'Timestamp':<25} {'Status':<22} {'Positions'}")
    print("-" * 70)
    for run in reversed(runs[-15:]):  # Last 15 runs
        print(f"{run['start']:<25} {run['status']:<22} {run['positions']}")
    
    print()
    print(f"Total runs shown: {len(runs[-15:])}")


def fetch_data():
    """Fetch latest data from remote to local cache."""
    print("Fetching data from remote server...")
    
    # Use the existing remote_short_data module
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / 'short_selling'))
        from remote_short_data import RemoteShortDataFetcher, load_remote_config
        
        config = load_remote_config(str(LOCAL_CONFIG))
        fetcher = RemoteShortDataFetcher(config)
        
        success, data = fetcher.fetch_data(force_refresh=True)
        
        if success and data:
            print(f"✓ Fetched {len(data.get('positions', []))} positions")
            print(f"  Last updated: {data.get('last_updated', 'Unknown')}")
            
            status = fetcher.get_status()
            print(f"  Cache valid: {status.get('cache_valid', False)}")
            print(f"  Validation: {'enabled' if status.get('validation_enabled') else 'disabled'}")
        else:
            print("❌ Failed to fetch data")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True


def check_versions():
    """Check local and remote script versions."""
    print("Version Check")
    print("=" * 60)
    print()
    
    # Local versions
    print("Local versions:")
    try:
        # Import local modules
        sys.path.insert(0, str(Path(__file__).parent.parent / 'short_selling'))
        from short_selling_tracker import __version__ as tracker_version
        print(f"  short_selling_tracker.py: {tracker_version}")
    except (ImportError, AttributeError):
        print("  short_selling_tracker.py: (no version)")
    
    try:
        # Check update_shorts_cron.py
        cron_file = Path(__file__).parent / 'update_shorts_cron.py'
        if cron_file.exists():
            with open(cron_file) as f:
                for line in f:
                    if line.startswith('__version__'):
                        version = line.split('=')[1].strip().strip('"\'').split('#')[0].strip().strip('"\'')
                        print(f"  update_shorts_cron.py:    {version}")
                        break
                else:
                    print("  update_shorts_cron.py:    (no version)")
    except Exception:
        print("  update_shorts_cron.py:    (error reading)")
    
    print(f"  remote_status.py:         {__version__}")
    
    print()
    print("Remote versions:")
    
    # Remote short_selling_tracker.py
    success, output, _ = run_ssh_command(f"grep '__version__' {REMOTE_PATH}/short_selling_tracker.py 2>/dev/null | head -1")
    if success and output.strip():
        version = output.split('=')[1].strip().split('#')[0].strip().strip('"\'')
        print(f"  short_selling_tracker.py: {version}")
    else:
        print("  short_selling_tracker.py: (no version or not found)")
    
    # Remote update_shorts_cron.py
    success, output, _ = run_ssh_command(f"grep '__version__' {REMOTE_PATH}/update_shorts_cron.py 2>/dev/null | head -1")
    if success and output.strip():
        version = output.split('=')[1].strip().split('#')[0].strip().strip('"\'')
        print(f"  update_shorts_cron.py:    {version}")
    else:
        print("  update_shorts_cron.py:    (no version or not found)")
    
    print()
    print("=" * 60)
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Check status of remote short selling data server'
    )
    parser.add_argument(
        '--update', '-u',
        action='store_true',
        help='Force an update on the remote server'
    )
    parser.add_argument(
        '--logs', '-l',
        nargs='?',
        const=50,
        type=int,
        metavar='LINES',
        help='Show recent log entries (default: 50 lines)'
    )
    parser.add_argument(
        '--fetch', '-f',
        action='store_true',
        help='Fetch latest data to local cache'
    )
    parser.add_argument(
        '--history', '-H',
        action='store_true',
        help='Show history of update runs with status'
    )
    parser.add_argument(
        '--host',
        type=str,
        help='Override remote host (user@host)'
    )
    parser.add_argument(
        '--version', '-v',
        action='store_true',
        help='Check local and remote script versions'
    )
    
    args = parser.parse_args()
    
    # Override host if specified
    global REMOTE_HOST
    if args.host:
        REMOTE_HOST = args.host
    
    if args.version:
        success = check_versions()
    elif args.update:
        success = force_update()
    elif args.logs is not None:
        show_logs(args.logs)
        success = True
    elif args.history:
        show_history()
        success = True
    elif args.fetch:
        success = fetch_data()
    else:
        success = check_status()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
