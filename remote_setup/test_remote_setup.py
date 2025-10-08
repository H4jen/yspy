#!/usr/bin/env python3
"""
Quick test script for remote short selling data setup.

Tests both server (cron script) and client (fetcher) components.
"""

import sys
import json
import tempfile
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from remote_short_data import RemoteDataConfig, RemoteShortDataFetcher


def test_server_script():
    """Test the server cron script."""
    print("=" * 70)
    print("TEST 1: Server Cron Script")
    print("=" * 70)
    
    try:
        from update_shorts_cron import update_short_data
        
        # Use temp directory for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            
            print(f"\nTest output directory: {test_dir}")
            print("\nRunning update_short_data()...")
            
            success = update_short_data(test_dir)
            
            if success:
                print("\n✅ Server script test PASSED")
                
                # Check files
                files = list(test_dir.glob("*.json"))
                print(f"\nGenerated files ({len(files)}):")
                for f in files:
                    size = f.stat().st_size
                    print(f"  - {f.name}: {size:,} bytes")
                
                # Check metadata
                meta_file = test_dir / "short_positions_meta.json"
                if meta_file.exists():
                    with open(meta_file) as f:
                        meta = json.load(f)
                    print(f"\nMetadata:")
                    print(f"  Status: {meta.get('status')}")
                    print(f"  Total positions: {meta.get('total_positions')}")
                    print(f"  Last update: {meta.get('last_update')}")
                
                return True
            else:
                print("\n❌ Server script test FAILED")
                return False
                
    except Exception as e:
        print(f"\n❌ Server script test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_client_fetcher():
    """Test the client fetcher."""
    print("\n" + "=" * 70)
    print("TEST 2: Client Fetcher")
    print("=" * 70)
    
    try:
        # Create test configuration
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            data_dir = test_dir / "data"
            cache_dir = test_dir / "cache"
            
            data_dir.mkdir()
            cache_dir.mkdir()
            
            # Create test data
            print(f"\nCreating test data in: {data_dir}")
            
            from datetime import datetime
            test_data = {
                'last_updated': datetime.now().isoformat(),
                'update_source': 'test',
                'positions': [
                    {
                        'ticker': 'TEST.ST',
                        'company_name': 'Test Company',
                        'position_holder': 'Aggregated',
                        'position_percentage': 5.5,
                        'position_date': '2025-10-08',
                        'market': 'SE',
                        'threshold_crossed': None,
                        'individual_holders': []
                    }
                ]
            }
            
            current_file = data_dir / "short_positions_current.json"
            with open(current_file, 'w') as f:
                json.dump(test_data, f)
            
            meta_file = data_dir / "short_positions_meta.json"
            with open(meta_file, 'w') as f:
                json.dump({
                    'last_update': datetime.now().isoformat(),
                    'status': 'success',
                    'total_positions': 1
                }, f)
            
            # Test fetcher
            print("\nTesting RemoteShortDataFetcher...")
            
            config = RemoteDataConfig(
                protocol='file',
                location=str(data_dir),
                cache_dir=cache_dir,
                cache_ttl_hours=1
            )
            
            fetcher = RemoteShortDataFetcher(config)
            
            # Test fetch
            print("Fetching data...")
            success, data = fetcher.fetch_data(force_refresh=True)
            
            if success and data:
                print("\n✅ Client fetcher test PASSED")
                print(f"\nFetched data:")
                print(f"  Positions: {len(data['positions'])}")
                print(f"  Last updated: {data['last_updated']}")
                print(f"  Source: {data['update_source']}")
                
                # Test status
                print("\nFetcher status:")
                status = fetcher.get_status()
                for key, value in status.items():
                    if key != 'metadata':
                        print(f"  {key}: {value}")
                
                # Test cache
                print("\nTesting cache...")
                success2, data2 = fetcher.fetch_data(force_refresh=False)
                if success2:
                    print("  ✓ Cache working")
                
                return True
            else:
                print("\n❌ Client fetcher test FAILED: No data returned")
                return False
                
    except Exception as e:
        print(f"\n❌ Client fetcher test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_configuration():
    """Test configuration loading."""
    print("\n" + "=" * 70)
    print("TEST 3: Configuration")
    print("=" * 70)
    
    try:
        from remote_short_data import load_remote_config
        
        print("\nTesting configuration loading...")
        
        # Test with non-existent file (should return default)
        config = load_remote_config('nonexistent.json')
        print(f"\nDefault config:")
        print(f"  Protocol: {config.protocol}")
        print(f"  Location: {config.location}")
        print(f"  Cache TTL: {config.cache_ttl_hours} hours")
        
        print("\n✅ Configuration test PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ Configuration test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "Remote Short Data Setup Tests" + " " * 24 + "║")
    print("╚" + "=" * 68 + "╝")
    print()
    
    results = []
    
    # Run tests
    results.append(("Server Script", test_server_script()))
    results.append(("Client Fetcher", test_client_fetcher()))
    results.append(("Configuration", test_configuration()))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name:.<50} {status}")
    
    print("=" * 70)
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n🎉 All tests passed!")
        print("\nNext steps:")
        print("1. Run ./setup_remote_shorts.sh on your server")
        print("2. Configure remote_config.json on your client")
        print("3. Test connection with your actual setup")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
