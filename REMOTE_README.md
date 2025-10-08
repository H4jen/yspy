# Remote Short Selling Data Updates - Quick Start

This setup allows you to run daily short selling data updates on a remote server, with your local yspy client fetching the data automatically.

## What Was Created

### Server Components (Run on Ubuntu Server)

1. **`update_shorts_cron.py`** - Standalone cron script
   - Fetches short selling data from regulatory sources
   - Saves current snapshot + historical data
   - Logs updates and errors
   - Exit codes for cron monitoring

2. **`setup_remote_shorts.sh`** - Automated setup script
   - Creates output directory
   - Tests the update script
   - Installs cron job
   - Creates client configuration

### Client Components (Run on Your Computer)

3. **`remote_short_data.py`** - Data fetcher module
   - Supports multiple protocols: file (NFS), HTTP, SSH, S3
   - Local caching (6-hour TTL)
   - Automatic fallback to cache on errors
   - Data freshness monitoring

4. **`remote_config.json`** - Client configuration
   - Defines how to connect to server
   - Protocol-specific settings
   - Cache configuration

### Documentation & Testing

5. **`REMOTE_SETUP.md`** - Complete documentation
   - Architecture diagrams
   - Step-by-step setup for all protocols
   - Troubleshooting guide
   - Security best practices

6. **`test_remote_setup.py`** - Test script
   - Tests server script
   - Tests client fetcher
   - Tests configuration loading
   - Validates complete setup

7. **`remote_config.example.json`** - Example configurations
   - File/NFS protocol
   - HTTP protocol
   - SSH protocol
   - Copy to `remote_config.json` and customize

## Quick Setup

### On Your Ubuntu Server

```bash
# 1. Navigate to yspy directory
cd /path/to/yspy

# 2. Run setup script
./setup_remote_shorts.sh

# 3. Follow the prompts
#    - Output directory: /shared/yspy_data (or your choice)
#    - Schedule: 9:00 AM daily
#    - Install cron: yes

# 4. Verify
crontab -l
cat /shared/yspy_data/short_positions_meta.json
```

### On Your Computer

Choose ONE method:

#### Option A: Mounted Network Share (Recommended)

```bash
# Mount server directory
sudo mkdir -p /mnt/yspy_data
sudo mount server-ip:/shared/yspy_data /mnt/yspy_data

# Configure yspy
cat > remote_config.json << 'EOF'
{
  "protocol": "file",
  "location": "/mnt/yspy_data",
  "cache_ttl_hours": 6
}
EOF
```

#### Option B: HTTP Server

```bash
# (Server needs nginx/apache serving the directory)

# Configure yspy
cat > remote_config.json << 'EOF'
{
  "protocol": "http",
  "location": "https://your-server.com/yspy_data",
  "cache_ttl_hours": 6
}
EOF
```

#### Option C: SSH/SFTP

```bash
# Install paramiko
pip3 install paramiko

# Configure yspy
cat > remote_config.json << 'EOF'
{
  "protocol": "ssh",
  "location": "user@server:/shared/yspy_data",
  "ssh_key_path": "/home/user/.ssh/id_rsa",
  "cache_ttl_hours": 6
}
EOF
```

## Testing

```bash
# Test complete setup
./test_remote_setup.py

# Test connection to your server
python3 -c "
from remote_short_data import *
config = load_remote_config()
fetcher = RemoteShortDataFetcher(config)
success, data = fetcher.fetch_data(force_refresh=True)
print(f'Success: {success}')
if data:
    print(f'Positions: {len(data[\"positions\"])}')
    print(f'Last updated: {data[\"last_updated\"]}')
"
```

## How It Works

```
Server (Ubuntu)          Client (Your Computer)
===============          ======================

09:00 - Cron runs        
   ↓                     
Fetch FI data            
   ↓                     
Save to                  
/shared/yspy_data/       
   ↓                     
   ├─ current.json       ←── When you run yspy
   ├─ historical.json   ←── Fetch via NFS/HTTP/SSH
   └─ meta.json              ↓
                             Cache locally (6hr)
                             ↓
                             Use in yspy app
```

## Benefits

✅ **Always Fresh Data** - Daily automated updates
✅ **No Manual Updates** - Set and forget
✅ **Historical Tracking** - Build trend data over time
✅ **Efficient** - Client uses cached data (6hr TTL)
✅ **Resilient** - Fallback to cache if server unreachable
✅ **Secure** - Multiple protocol options
✅ **Lightweight** - Minimal server resources

## Data Files

The server creates 3 files daily:

1. **short_positions_current.json** (~500 KB)
   - Complete snapshot of all short positions
   - Includes individual holder details
   - Last updated timestamp

2. **short_positions_historical.json** (~50 MB after 1 year)
   - Daily snapshots for trend analysis
   - Automatically purges data >365 days
   - Used for graphing in yspy

3. **short_positions_meta.json** (~2 KB)
   - Update status and statistics
   - Used to check data freshness
   - Error messages if update failed

## Monitoring

```bash
# Check server logs
tail -f /tmp/yspy_shorts_update.log

# Check data freshness
cat /shared/yspy_data/short_positions_meta.json

# Check cron status
crontab -l
grep update_shorts_cron /var/log/syslog
```

## Troubleshooting

**Server not updating?**
```bash
# Test manually
python3 update_shorts_cron.py --output /shared/yspy_data --verbose

# Check cron logs
grep CRON /var/log/syslog
```

**Client can't connect?**
```bash
# File protocol:
ls /mnt/yspy_data

# HTTP protocol:
curl https://your-server.com/yspy_data/short_positions_meta.json

# SSH protocol:
ssh user@server "ls /shared/yspy_data"
```

**Data is stale?**
```bash
# Clear cache and force refresh
rm -rf portfolio/remote_cache/*
python3 -c "from remote_short_data import *; ..."
```

## Next Steps

1. ✅ Server setup complete
2. ✅ Client configured
3. ✅ Test connection successful
4. 🔄 **Integrate with yspy** - Modify short_selling_integration.py to use remote data
5. 📊 **Enable historical graphs** - Use historical data for trend visualization

## Full Documentation

See **`REMOTE_SETUP.md`** for complete documentation including:
- Detailed architecture
- All protocol options
- Security best practices
- Advanced configuration
- FAQ

## File Summary

| File | Purpose | Location |
|------|---------|----------|
| update_shorts_cron.py | Server update script | Server |
| setup_remote_shorts.sh | Setup automation | Server |
| remote_short_data.py | Client fetcher | Client |
| remote_config.json | Client config | Client |
| REMOTE_SETUP.md | Full docs | Both |
| test_remote_setup.py | Test suite | Both |

---

**Need help?** Check REMOTE_SETUP.md or run `./test_remote_setup.py`
