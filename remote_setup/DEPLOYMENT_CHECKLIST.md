# Remote Short Data Setup Checklist

Use this checklist to deploy the remote short data system to your Ubuntu server.

---

## Pre-Deployment Checklist

- [ ] **Ubuntu server running** (version 18.04+)
- [ ] **Python 3.6+** installed on server
- [ ] **yspy repository** cloned on server
- [ ] **Network connectivity** between server and client
- [ ] **Storage space** available (~100 MB for data)
- [ ] **Cron daemon** running on server

---

## Server Setup Checklist

### 1. Prepare Server

- [ ] SSH into your Ubuntu server
- [ ] Navigate to yspy directory: `cd /path/to/yspy`
- [ ] Verify Python: `python3 --version`
- [ ] Install dependencies: `pip3 install -r requirements.txt`
- [ ] Test dependencies: `python3 -c "import pandas, requests"`

### 2. Run Setup Script

- [ ] Make script executable: `chmod +x setup_remote_shorts.sh`
- [ ] Run setup: `./setup_remote_shorts.sh`
- [ ] Provide output directory path (e.g., `/shared/yspy_data`)
- [ ] Choose update time (e.g., `9:00 AM`)
- [ ] Confirm cron job installation

### 3. Verify Server Installation

- [ ] Check cron job: `crontab -l | grep update_shorts`
- [ ] Test update manually: `python3 update_shorts_cron.py --output /shared/yspy_data --verbose`
- [ ] Verify files created:
  - [ ] `short_positions_current.json` exists
  - [ ] `short_positions_historical.json` exists
  - [ ] `short_positions_meta.json` exists
- [ ] Check file sizes are reasonable (~500 KB for current)
- [ ] Review logs: `cat /tmp/yspy_shorts_update.log`

### 4. Set Up Data Access (Choose ONE)

#### Option A: NFS Mount
- [ ] Install NFS server: `sudo apt install nfs-kernel-server`
- [ ] Configure exports: `sudo nano /etc/exports`
- [ ] Add line: `/shared/yspy_data *(ro,sync,no_subtree_check)`
- [ ] Apply changes: `sudo exportfs -ra`
- [ ] Verify: `sudo exportfs -v`
- [ ] Open firewall: `sudo ufw allow from CLIENT_IP to any port 2049`

#### Option B: HTTP Server
- [ ] Install nginx: `sudo apt install nginx`
- [ ] Create config: `sudo nano /etc/nginx/sites-available/yspy`
- [ ] Configure location block (see REMOTE_SETUP.md)
- [ ] Enable site: `sudo ln -s /etc/nginx/sites-available/yspy /etc/nginx/sites-enabled/`
- [ ] Test config: `sudo nginx -t`
- [ ] Reload nginx: `sudo systemctl reload nginx`
- [ ] Test access: `curl http://localhost/yspy_data/short_positions_meta.json`
- [ ] (Optional) Set up HTTPS with certbot

#### Option C: SSH Access
- [ ] Verify SSH server running: `sudo systemctl status ssh`
- [ ] Test SSH access from client: `ssh user@server`
- [ ] Set up key authentication (if not done)
- [ ] Verify file access: `ssh user@server "ls /shared/yspy_data"`

---

## Client Setup Checklist

### 1. Install Client Files (if needed)

- [ ] Copy yspy repository to client machine
- [ ] Verify new files exist:
  - [ ] `remote_short_data.py`
  - [ ] `remote_integration_helper.py`
  - [ ] `remote_config.example.json`

### 2. Configure Access Method (Choose ONE)

#### Option A: NFS Mount
- [ ] Create mount point: `sudo mkdir -p /mnt/yspy_data`
- [ ] Test mount: `sudo mount SERVER_IP:/shared/yspy_data /mnt/yspy_data`
- [ ] Verify: `ls /mnt/yspy_data`
- [ ] Make permanent: Add to `/etc/fstab`:
  ```
  SERVER_IP:/shared/yspy_data /mnt/yspy_data nfs ro,soft,intr 0 0
  ```
- [ ] Test fstab: `sudo mount -a`

#### Option B: HTTP Access
- [ ] Test HTTP access: `curl http://SERVER/yspy_data/short_positions_meta.json`
- [ ] (If HTTPS) Verify certificate works

#### Option C: SSH Access
- [ ] Install paramiko: `pip3 install paramiko`
- [ ] Test SSH key: `ssh user@server "echo test"`
- [ ] Verify non-interactive: No password prompt

### 3. Create Configuration

- [ ] Copy example: `cp remote_config.example.json remote_config.json`
- [ ] Edit `remote_config.json` with your settings:
  - [ ] Set `protocol` (file/http/ssh)
  - [ ] Set `location` (path/URL)
  - [ ] Adjust `cache_ttl_hours` if needed
  - [ ] (SSH only) Set `ssh_key_path`
  - [ ] (HTTP only) Set `http_verify_ssl`

### 4. Test Client Connection

- [ ] Run test script: `./test_remote_setup.py`
- [ ] All tests pass: ✅
- [ ] Test manual fetch:
  ```bash
  python3 -c "
  from remote_short_data import *
  config = load_remote_config()
  fetcher = RemoteShortDataFetcher(config)
  success, data = fetcher.fetch_data(force_refresh=True)
  print(f'Success: {success}')
  print(f'Positions: {len(data[\"positions\"]) if data else 0}')
  "
  ```
- [ ] Verify cache created: `ls -lh portfolio/remote_cache/`
- [ ] Check cache contents: `cat portfolio/remote_cache/short_positions_meta.json`

---

## Integration Checklist

### Option 1: Drop-in Replacement (Recommended)

- [ ] Backup `short_selling_integration.py`:
  ```bash
  cp short_selling_integration.py short_selling_integration.py.backup
  ```
- [ ] Edit `short_selling_integration.py`
- [ ] Find line: `from short_selling_tracker import ShortSellingTracker`
- [ ] Replace with: `from remote_integration_helper import RemoteShortSellingTracker as ShortSellingTracker`
- [ ] Save file
- [ ] Test integration:
  ```bash
  python3 -c "from short_selling_integration import ShortSellingIntegration; i = ShortSellingIntegration(); print('OK')"
  ```

### Option 2: Gradual Integration (Advanced)

- [ ] Follow MIGRATION_GUIDE.md steps
- [ ] Add imports
- [ ] Initialize remote fetcher
- [ ] Modify update method
- [ ] Modify data retrieval methods
- [ ] Test each change

---

## Testing Checklist

### Functional Tests

- [ ] **Basic startup**: `./yspy.py` starts without errors
- [ ] **Short selling menu**: Accessible from main menu
- [ ] **View portfolio shorts**: Option 1 shows data
- [ ] **Individual stock data**: Option 2 works
- [ ] **Update function**: Option 3 updates successfully
- [ ] **High interest alerts**: Option 4 displays stocks
- [ ] **Position holders**: Option 6 shows holders
- [ ] **All stocks view**: Option 7 displays all stocks
- [ ] **Watch screen**: Short% column displays correctly

### Remote Connection Tests

- [ ] **Fresh data**: First fetch downloads from server
- [ ] **Cached data**: Second fetch uses cache (within 6 hours)
- [ ] **Force refresh**: Update option fetches fresh data
- [ ] **Fallback**: Client works when server temporarily unreachable
- [ ] **Error handling**: No crashes on network errors

### Performance Tests

- [ ] Startup time acceptable (< 5 seconds)
- [ ] Data fetch time acceptable (< 10 seconds first time)
- [ ] Cache access fast (< 1 second)
- [ ] No memory leaks during extended use

---

## Monitoring Checklist

### Initial Monitoring (First Week)

- [ ] **Day 1**: Check server log after first cron run
- [ ] **Day 1**: Verify files updated
- [ ] **Day 2**: Confirm daily updates working
- [ ] **Day 3**: Check historical data growing
- [ ] **Day 7**: Verify weekly data accumulation

### Daily Checks

- [ ] Monitor disk space: `df -h /shared/yspy_data`
- [ ] Check log file size: `ls -lh /tmp/yspy_shorts_update.log`
- [ ] Verify last update time: `cat /shared/yspy_data/short_positions_meta.json | grep last_update`

### Weekly Checks

- [ ] Review logs for errors: `grep ERROR /tmp/yspy_shorts_update.log`
- [ ] Check data freshness on client
- [ ] Verify historical data growing: `du -h /shared/yspy_data/short_positions_historical.json`

---

## Troubleshooting Checklist

### If Server Not Updating

- [ ] Check cron is running: `sudo systemctl status cron`
- [ ] Check cron logs: `grep CRON /var/log/syslog | tail -20`
- [ ] Test manual update: `python3 update_shorts_cron.py --output /shared/yspy_data --verbose`
- [ ] Check permissions: `ls -la /shared/yspy_data`
- [ ] Review error log: `cat /tmp/yspy_shorts_update.log`
- [ ] Verify network connectivity: `ping www.fi.se`

### If Client Can't Connect

- [ ] Test protocol-specific connection (see checklist above)
- [ ] Check firewall rules
- [ ] Verify remote_config.json syntax: `python3 -c "import json; json.load(open('remote_config.json'))"`
- [ ] Check file permissions on server
- [ ] Test with manual commands (see REMOTE_SETUP.md)
- [ ] Clear cache and retry: `rm -rf portfolio/remote_cache/*`

### If Data Is Stale

- [ ] Check server last update: `cat /shared/yspy_data/short_positions_meta.json`
- [ ] Force server update: Run cron script manually
- [ ] Check client cache: `ls -lh portfolio/remote_cache/`
- [ ] Force client refresh: `rm -rf portfolio/remote_cache/*`
- [ ] Verify cache TTL setting in remote_config.json

---

## Rollback Checklist (If Needed)

- [ ] Stop using remote data:
  - Option 1: `cp short_selling_integration.py.backup short_selling_integration.py`
  - Option 2: `git checkout short_selling_integration.py`
- [ ] Remove remote config: `rm remote_config.json`
- [ ] Clear cache: `rm -rf portfolio/remote_cache/`
- [ ] (Optional) Disable cron: `crontab -e` and comment out line
- [ ] Test yspy works with local data: `./yspy.py`

---

## Completion Checklist

✅ **Deployment Complete When:**

- [ ] Server cron running and updating daily
- [ ] Client can fetch data successfully
- [ ] yspy application uses remote data
- [ ] All menu options functional
- [ ] Tests passing
- [ ] Monitoring in place
- [ ] Documentation reviewed
- [ ] Backup strategy defined

---

## Documentation Reference

- [ ] Read `REMOTE_README.md` - Quick start
- [ ] Read `REMOTE_SETUP.md` - Complete guide
- [ ] Read `MIGRATION_GUIDE.md` - Integration steps
- [ ] Read `QUICK_REFERENCE.txt` - Command reference
- [ ] Bookmark for future reference

---

## Maintenance Schedule

### Daily (Automated)
- Server updates data via cron

### Weekly (2 minutes)
- Review logs for errors
- Check data freshness
- Monitor disk usage

### Monthly (5 minutes)
- Review historical data growth
- Update documentation if needed
- Consider adjusting cache TTL

### Yearly (10 minutes)
- Review and adjust data retention (365 days default)
- Update server dependencies: `pip3 install -U -r requirements.txt`
- Test backup/restore procedures

---

## Support Resources

If you encounter issues:

1. Check logs first: `/tmp/yspy_shorts_update.log`
2. Run test script: `./test_remote_setup.py`
3. Review troubleshooting section in `REMOTE_SETUP.md`
4. Test with verbose mode: `--verbose` flag
5. Check firewall and network connectivity

---

**Status**: Ready for deployment ✅

**Next Step**: Start with "Server Setup Checklist" above
