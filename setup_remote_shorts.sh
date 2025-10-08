#!/bin/bash
# Setup script for remote short selling data updates via cron

set -e

echo "========================================"
echo "yspy Remote Short Data Update Setup"
echo "========================================"
echo ""

# Configuration
DEFAULT_OUTPUT_DIR="/shared/yspy_data"
DEFAULT_CRON_HOUR=9
DEFAULT_CRON_MINUTE=0

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "This script will set up automated short selling data updates"
echo "that run daily via cron on your server."
echo ""

# Ask for output directory
read -p "Output directory for data files [$DEFAULT_OUTPUT_DIR]: " OUTPUT_DIR
OUTPUT_DIR="${OUTPUT_DIR:-$DEFAULT_OUTPUT_DIR}"

# Create output directory
echo ""
echo "Creating output directory: $OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

if [ -w "$OUTPUT_DIR" ]; then
    echo -e "${GREEN}✓${NC} Directory created and writable"
else
    echo -e "${RED}✗${NC} Directory not writable! You may need sudo."
    exit 1
fi

# Ask for cron schedule
echo ""
echo "Cron schedule (when to run daily update):"
read -p "Hour (0-23) [$DEFAULT_CRON_HOUR]: " CRON_HOUR
CRON_HOUR="${CRON_HOUR:-$DEFAULT_CRON_HOUR}"

read -p "Minute (0-59) [$DEFAULT_CRON_MINUTE]: " CRON_MINUTE
CRON_MINUTE="${CRON_MINUTE:-$DEFAULT_CRON_MINUTE}"

# Find Python
PYTHON_PATH=$(which python3)
if [ -z "$PYTHON_PATH" ]; then
    echo -e "${RED}✗${NC} Python 3 not found!"
    exit 1
fi
echo -e "${GREEN}✓${NC} Found Python: $PYTHON_PATH"

# Check for virtual environment
if [ -d "$SCRIPT_DIR/.venv" ]; then
    PYTHON_PATH="$SCRIPT_DIR/.venv/bin/python3"
    echo -e "${GREEN}✓${NC} Using virtual environment: $PYTHON_PATH"
fi

# Test the update script
echo ""
echo "Testing update script..."
$PYTHON_PATH "$SCRIPT_DIR/update_shorts_cron.py" --output "$OUTPUT_DIR" --verbose

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Update script test successful!"
else
    echo -e "${RED}✗${NC} Update script test failed!"
    exit 1
fi

# Create cron job entry
CRON_CMD="$CRON_MINUTE $CRON_HOUR * * * $PYTHON_PATH $SCRIPT_DIR/update_shorts_cron.py --output $OUTPUT_DIR >> /tmp/yspy_shorts_update.log 2>&1"

echo ""
echo "Cron job to add:"
echo "$CRON_CMD"
echo ""

# Ask to install cron job
read -p "Add this cron job? (y/n): " ADD_CRON

if [ "$ADD_CRON" = "y" ] || [ "$ADD_CRON" = "Y" ]; then
    # Check if cron job already exists
    if crontab -l 2>/dev/null | grep -q "update_shorts_cron.py"; then
        echo -e "${YELLOW}⚠${NC}  Cron job already exists. Removing old version..."
        crontab -l 2>/dev/null | grep -v "update_shorts_cron.py" | crontab -
    fi
    
    # Add new cron job
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    
    echo -e "${GREEN}✓${NC} Cron job added successfully!"
    echo ""
    echo "Current crontab:"
    crontab -l | grep "update_shorts_cron.py"
else
    echo ""
    echo "Cron job not added. You can add it manually with:"
    echo "  crontab -e"
    echo ""
    echo "And add this line:"
    echo "  $CRON_CMD"
fi

# Create remote config for client
echo ""
echo "Creating client configuration..."

CLIENT_CONFIG="$SCRIPT_DIR/remote_config.json"
cat > "$CLIENT_CONFIG" << EOF
{
  "protocol": "file",
  "location": "$OUTPUT_DIR",
  "cache_ttl_hours": 6,
  "cache_dir": "portfolio/remote_cache"
}
EOF

echo -e "${GREEN}✓${NC} Created $CLIENT_CONFIG"

# Print summary
echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Configuration:"
echo "  Output directory: $OUTPUT_DIR"
echo "  Schedule: Daily at $(printf '%02d:%02d' $CRON_HOUR $CRON_MINUTE)"
echo "  Python: $PYTHON_PATH"
echo "  Log file: /tmp/yspy_shorts_update.log"
echo ""
echo "Next steps:"
echo ""
echo "1. If running on a server, ensure yspy can access:"
echo "   $OUTPUT_DIR"
echo ""
echo "2. For remote access, choose one of these:"
echo ""
echo "   A) Mount the directory via NFS/Samba on your client:"
echo "      - Mount $OUTPUT_DIR to /mnt/yspy_data on your machine"
echo "      - Update remote_config.json: \"location\": \"/mnt/yspy_data\""
echo ""
echo "   B) Serve via HTTP:"
echo "      - Install nginx/apache"
echo "      - Serve $OUTPUT_DIR as static files"
echo "      - Update remote_config.json:"
echo "        \"protocol\": \"http\","
echo "        \"location\": \"https://your-server.com/yspy_data\""
echo ""
echo "   C) Use SSH/SFTP:"
echo "      - Update remote_config.json:"
echo "        \"protocol\": \"ssh\","
echo "        \"location\": \"user@server:$OUTPUT_DIR\","
echo "        \"ssh_key_path\": \"/home/user/.ssh/id_rsa\""
echo ""
echo "3. Test the client connection:"
echo "   python3 -c 'from remote_short_data import *; config = load_remote_config(); fetcher = RemoteShortDataFetcher(config); print(fetcher.get_status())'"
echo ""
echo "========================================"
echo ""
echo -e "${GREEN}Done!${NC} Your server will now update short data daily."
echo ""
