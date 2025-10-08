# Remote Setup Directory

This directory contains all files needed to set up and manage the remote short selling data system.

## 📁 Contents

### Server Setup Files
- **`update_shorts_cron.py`** - Cron script that runs on your server to fetch data daily
- **`setup_remote_shorts.sh`** - Interactive setup wizard for server configuration

### Documentation
- **`REMOTE_README.md`** - Quick start guide (read this first!)
- **`REMOTE_SETUP.md`** - Complete setup documentation for all protocols
- **`MIGRATION_GUIDE.md`** - How to integrate with existing yspy code
- **`DEPLOYMENT_CHECKLIST.md`** - Step-by-step deployment checklist
- **`IMPLEMENTATION_SUMMARY.md`** - Technical implementation details
- **`QUICK_REFERENCE.txt`** - One-page command reference

### Configuration & Testing
- **`remote_config.example.json`** - Example configurations for all protocols
- **`test_remote_setup.py`** - Test suite to verify setup

## 🚀 Quick Start

### 1. Server Setup (Ubuntu Server)

```bash
# Copy files to your server
scp update_shorts_cron.py setup_remote_shorts.sh user@server:/path/to/yspy/

# SSH to server and run setup
ssh user@server
cd /path/to/yspy
./setup_remote_shorts.sh
```

### 2. Client Setup (Your Computer)

```bash
# Copy example config to main directory
cp remote_setup/remote_config.example.json ../remote_config.json

# Edit with your settings
nano ../remote_config.json

# Test connection
cd ..
python3 -c "from remote_short_data import *; ..."
```

## 📖 Documentation

Start with **`REMOTE_README.md`** for a quick overview, then:
- For detailed setup: **`REMOTE_SETUP.md`**
- For integration: **`MIGRATION_GUIDE.md`**
- For deployment: **`DEPLOYMENT_CHECKLIST.md`**

## ⚙️ Files NOT in This Directory

These files are in the main yspy directory because they're needed at runtime:

- **`remote_short_data.py`** - Client fetcher library (imported by app)
- **`remote_integration_helper.py`** - Optional integration helper
- **`remote_config.json`** - Your actual configuration (not tracked in git)

## 🔄 Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Server Setup (one-time)                                 │
│    → Use: setup_remote_shorts.sh                           │
│    → Installs: update_shorts_cron.py as cron job          │
├─────────────────────────────────────────────────────────────┤
│ 2. Client Setup (one-time)                                 │
│    → Copy: remote_config.example.json → ../remote_config.json │
│    → Configure with your server details                    │
├─────────────────────────────────────────────────────────────┤
│ 3. Daily Operation (automatic)                             │
│    → Server: Cron fetches data at 9 AM                    │
│    → Client: App fetches from server when needed          │
└─────────────────────────────────────────────────────────────┘
```

## 🧪 Testing

```bash
# Test server script
python3 update_shorts_cron.py --output /tmp/test --verbose

# Test client connection
python3 test_remote_setup.py

# Test full integration
cd ..
./yspy.py  # Should use remote data automatically
```

## 📝 Notes

- All files in this directory are for **setup and documentation only**
- The main yspy application only needs `remote_short_data.py` and `remote_config.json`
- Server runs independently - no yspy app needed on server
- Historical data accumulates automatically

## 🆘 Help

- **Quick reference**: `QUICK_REFERENCE.txt`
- **Troubleshooting**: See `REMOTE_SETUP.md` section
- **Test connection**: `test_remote_setup.py`

---

**Status**: Remote data system is operational
**Your config**: `../remote_config.json` (in main directory)
**Server script**: `update_shorts_cron.py` (deploy to server)
