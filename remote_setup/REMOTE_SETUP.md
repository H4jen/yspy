# Remote Short Selling Data Updates

This guide explains how to set up automated short selling data updates on a remote server, with your local yspy client fetching the data.

## Architecture

```
┌─────────────────────────┐
│   Ubuntu Server         │
│                         │
│  ┌──────────────────┐  │
│  │ Cron Job (9 AM)  │  │
│  │ Daily Updates    │  │
│  └────────┬─────────┘  │
│           │             │
│           ▼             │
│  ┌──────────────────┐  │
│  │ update_shorts_   │  │
│  │   cron.py        │  │
│  └────────┬─────────┘  │
│           │             │
│           ▼             │
│  ┌──────────────────┐  │
│  │ /shared/         │  │
│  │   yspy_data/     │  │
│  │ • current.json   │  │
│  │ • historical.json│  │
│  │ • meta.json      │  │
│  └──────────────────┘  │
└───────────┬─────────────┘
            │
            │ NFS/HTTP/SSH
            │
┌───────────▼─────────────┐
│   Your Computer         │
│                         │
│  ┌──────────────────┐  │
│  │ yspy.py          │  │
│  │ (client)         │  │
│  └────────┬─────────┘  │
│           │             │
│           ▼             │
│  ┌──────────────────┐  │
│  │ remote_short_    │  │
│  │   data.py        │  │
│  └────────┬─────────┘  │
│           │             │
│           ▼             │
│  ┌──────────────────┐  │
│  │ Local Cache      │  │
│  │ (6hr TTL)        │  │
│  └──────────────────┘  │
└─────────────────────────┘
```

## Quick Start

### Server Setup (Ubuntu)

1. **Install yspy on server:**
   ```bash
   cd /home/user
   git clone <your-repo> yspy
   cd yspy
   pip3 install -r requirements.txt
   ```

2. **Run setup script:**
   ```bash
   chmod +x setup_remote_shorts.sh
   ./setup_remote_shorts.sh
   ```

3. **Follow the prompts:**
   - Output directory: `/shared/yspy_data` (or your choice)
   - Schedule: `9:00` (or your preferred time)
   - Confirm cron job installation

4. **Verify cron job:**
   ```bash
   crontab -l
   # Should show: 0 9 * * * python3 /path/to/update_shorts_cron.py ...
   ```

### Client Setup (Your Computer)

Choose **ONE** of these methods:

#### Option A: Mounted Network Share (Easiest)

**On Server:**
```bash
# Install NFS server
sudo apt install nfs-kernel-server

# Export directory
sudo echo "/shared/yspy_data *(ro,sync,no_subtree_check)" >> /etc/exports
sudo exportfs -ra
```

**On Your Computer:**
```bash
# Mount the share
sudo mkdir -p /mnt/yspy_data
sudo mount server-ip:/shared/yspy_data /mnt/yspy_data

# Make permanent (add to /etc/fstab):
echo "server-ip:/shared/yspy_data /mnt/yspy_data nfs ro,soft,intr 0 0" | sudo tee -a /etc/fstab
```

**Configure yspy:**
```json
// remote_config.json
{
  "protocol": "file",
  "location": "/mnt/yspy_data",
  "cache_ttl_hours": 6
}
```

#### Option B: HTTP Server (Simple)

**On Server:**
```bash
# Install nginx
sudo apt install nginx

# Create config
sudo cat > /etc/nginx/sites-available/yspy << 'EOF'
server {
    listen 80;
    server_name your-server.com;
    
    location /yspy_data/ {
        alias /shared/yspy_data/;
        autoindex off;
        
        # Allow JSON files only
        location ~ \.json$ {
            add_header Access-Control-Allow-Origin *;
            add_header Cache-Control "no-cache";
        }
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/yspy /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Optional: Add HTTPS with Let's Encrypt
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-server.com
```

**Configure yspy:**
```json
// remote_config.json
{
  "protocol": "http",
  "location": "https://your-server.com/yspy_data",
  "http_timeout": 30,
  "http_verify_ssl": true,
  "cache_ttl_hours": 6
}
```

#### Option C: SSH/SFTP (Most Secure)

**On Server:**
```bash
# Ensure SSH server is running
sudo systemctl enable ssh
sudo systemctl start ssh
```

**On Your Computer:**
```bash
# Set up SSH key (if not already done)
ssh-keygen -t rsa -b 4096
ssh-copy-id user@server

# Test connection
ssh user@server "ls /shared/yspy_data"
```

**Install paramiko:**
```bash
pip3 install paramiko
```

**Configure yspy:**
```json
// remote_config.json
{
  "protocol": "ssh",
  "location": "user@server:/shared/yspy_data",
  "ssh_key_path": "/home/user/.ssh/id_rsa",
  "cache_ttl_hours": 6
}
```

## Configuration

### remote_config.json

Located in the yspy project root. Controls how the client fetches data.

**Complete Options:**
```json
{
  // Protocol: "file", "http", "ssh", or "s3"
  "protocol": "file",
  
  // Location (format depends on protocol)
  "location": "/mnt/yspy_data",
  
  // Cache settings
  "cache_dir": "portfolio/remote_cache",
  "cache_ttl_hours": 6,
  
  // HTTP-specific (if protocol="http")
  "http_timeout": 30,
  "http_verify_ssl": true,
  
  // SSH-specific (if protocol="ssh")
  "ssh_key_path": "/home/user/.ssh/id_rsa"
}
```

## Testing

### Test Server Update
```bash
# On server
cd /path/to/yspy
python3 update_shorts_cron.py --output /shared/yspy_data --verbose

# Check output
ls -lh /shared/yspy_data/
cat /shared/yspy_data/short_positions_meta.json
```

### Test Client Fetch
```bash
# On your computer
cd /path/to/yspy
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

### Check Status
```bash
python3 -c "
from remote_short_data import *
config = load_remote_config()
fetcher = RemoteShortDataFetcher(config)
status = fetcher.get_status()
import json
print(json.dumps(status, indent=2))
"
```

## Monitoring

### Check Cron Logs
```bash
# On server
tail -f /tmp/yspy_shorts_update.log

# Or system cron log
grep CRON /var/log/syslog | tail -20
```

### Monitor Data Freshness
The metadata file contains update information:
```bash
cat /shared/yspy_data/short_positions_meta.json
```

```json
{
  "last_update": "2025-10-08T09:00:15.123456",
  "next_update": "daily_9am",
  "total_positions": 323,
  "positions_with_holders": 93,
  "markets": ["SE", "FI"],
  "status": "success"
}
```

## Troubleshooting

### Server Issues

**Cron job not running:**
```bash
# Check if cron is running
sudo systemctl status cron

# Check cron logs
grep update_shorts_cron /var/log/syslog

# Test manually
/usr/bin/python3 /path/to/update_shorts_cron.py --output /shared/yspy_data
```

**Permission errors:**
```bash
# Ensure output directory is writable
chmod 755 /shared/yspy_data
chown user:user /shared/yspy_data
```

**Missing dependencies:**
```bash
# Install requirements
pip3 install -r requirements.txt

# Or individually
pip3 install pandas requests odfpy
```

### Client Issues

**Cannot connect to server:**
```bash
# Test network connectivity
ping server-ip

# Test protocol-specific
# File:
ls /mnt/yspy_data

# HTTP:
curl https://your-server.com/yspy_data/short_positions_meta.json

# SSH:
ssh user@server "ls /shared/yspy_data"
```

**Stale cache:**
```bash
# Clear cache
rm -rf portfolio/remote_cache/*

# Force refresh
python3 -c "
from remote_short_data import *
config = load_remote_config()
fetcher = RemoteShortDataFetcher(config)
success, data = fetcher.fetch_data(force_refresh=True)
print(f'Refreshed: {success}')
"
```

**Import errors:**
```bash
# Install optional dependencies
pip3 install requests  # For HTTP
pip3 install paramiko  # For SSH
pip3 install boto3     # For S3
```

## Advanced Configuration

### Multiple Markets

To fetch data for multiple markets, modify the cron script:
```bash
# Finnish market
0 9 * * * python3 update_shorts_cron.py --output /shared/yspy_data_fi --portfolio /path/to/finnish_portfolio

# Swedish market
0 9 * * * python3 update_shorts_cron.py --output /shared/yspy_data_se --portfolio /path/to/swedish_portfolio
```

### S3 Storage (AWS/MinIO)

**Server setup:**
```bash
pip3 install boto3

# Configure AWS credentials
aws configure
# Or use MinIO
export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
export AWS_ENDPOINT_URL=http://minio-server:9000
```

**Modify cron script to upload to S3:**
```bash
0 9 * * * python3 update_shorts_cron.py --output /tmp/yspy_data && \
  aws s3 sync /tmp/yspy_data s3://my-bucket/yspy_data/
```

**Client config:**
```json
{
  "protocol": "s3",
  "location": "s3://my-bucket/yspy_data"
}
```

### Backup Strategy

**Daily backups:**
```bash
# Add to cron after update
5 9 * * * tar czf /backups/yspy_data_$(date +\%Y\%m\%d).tar.gz /shared/yspy_data
```

**Retention:**
```bash
# Keep last 30 days
10 9 * * * find /backups/yspy_data_*.tar.gz -mtime +30 -delete
```

## Performance

### Data Sizes
- **Current snapshot:** ~500 KB (323 positions)
- **Historical (1 year):** ~50 MB (estimated)
- **Metadata:** ~2 KB

### Bandwidth Usage
- **Daily update:** ~500 KB download
- **Client fetch:** ~500 KB every 6 hours (configurable)
- **Monthly:** ~15 MB total

### Cache Strategy
- Client caches data for 6 hours by default
- Prevents unnecessary fetches during active use
- Configurable via `cache_ttl_hours`

## Security

### Best Practices

1. **Use HTTPS** for HTTP protocol
2. **Use SSH keys** (not passwords) for SSH protocol
3. **Restrict NFS exports** to specific IPs
4. **Run cron as non-root user**
5. **Validate JSON** before loading (built-in)
6. **Limit file permissions** (644 for data files)

### Firewall Rules

**NFS (port 2049):**
```bash
sudo ufw allow from client-ip to any port 2049
```

**HTTP (port 80/443):**
```bash
sudo ufw allow 80
sudo ufw allow 443
```

**SSH (port 22):**
```bash
sudo ufw allow from client-ip to any port 22
```

## FAQ

**Q: What happens if the server is down?**
A: Client uses cached data (up to 6 hours old by default)

**Q: Can multiple clients use the same server?**
A: Yes, data is read-only for clients

**Q: How much server resources does this use?**
A: Minimal - ~30 seconds CPU time per day, ~50 MB disk space

**Q: Can I run this on Windows Server?**
A: Yes, use Windows Task Scheduler instead of cron

**Q: Does this work with VPN?**
A: Yes, any protocol that works over VPN will work

**Q: Can I use this with cloud storage (Dropbox/Google Drive)?**
A: Yes, use the `file` protocol with the sync folder path

## Support

For issues or questions:
1. Check logs: `/tmp/yspy_shorts_update.log`
2. Test connection manually (see Testing section)
3. Verify configuration files
4. Check firewall/network settings

## See Also

- [short_selling_tracker.py](short_selling_tracker.py) - Core tracker
- [remote_short_data.py](remote_short_data.py) - Client fetcher
- [update_shorts_cron.py](update_shorts_cron.py) - Cron script
