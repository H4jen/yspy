#!/bin/bash
# YSpy Remote Access Setup Helper
# This script helps you configure remote access for short selling data

echo "╔════════════════════════════════════════════════════════════╗"
echo "║         YSpy Remote Access Setup Helper                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

CONFIG_FILE="remote_config.json"

# Check if config exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "⚠️  Configuration file not found: $CONFIG_FILE"
    echo "Creating from example..."
    cp remote_setup/remote_config.example.json "$CONFIG_FILE"
fi

echo "Current configuration:"
echo "────────────────────────────────────────────────────────────"
cat "$CONFIG_FILE"
echo "────────────────────────────────────────────────────────────"
echo ""

# Menu
echo "Select your remote access method:"
echo ""
echo "1) SSH/SFTP (Secure, requires SSH server)"
echo "2) NFS/Network Mount (Easy, requires mounted share)"
echo "3) HTTP (Simple, requires web server)"
echo "4) S3 (Cloud storage, requires AWS/MinIO)"
echo "5) Test current configuration"
echo "6) View documentation"
echo "7) Exit"
echo ""

read -p "Enter your choice (1-7): " choice

case $choice in
    1)
        echo ""
        echo "SSH/SFTP Configuration"
        echo "────────────────────────────────────────────────────────────"
        read -p "Enter server address (user@hostname): " server
        read -p "Enter remote path: " remote_path
        read -p "Enter SSH key path [~/.ssh/id_rsa]: " key_path
        key_path=${key_path:-~/.ssh/id_rsa}
        
        cat > "$CONFIG_FILE" <<EOF
{
  "protocol": "ssh",
  "location": "${server}:${remote_path}",
  "ssh_key_path": "${key_path}",
  "cache_ttl_hours": 6,
  "cache_dir": "portfolio/remote_cache"
}
EOF
        echo "✓ Configuration saved!"
        echo ""
        echo "Next: Test connection with 'python3 -c \"from short_selling.remote_short_data import *; print(load_remote_config())\"'"
        ;;
        
    2)
        echo ""
        echo "NFS/Network Mount Configuration"
        echo "────────────────────────────────────────────────────────────"
        read -p "Enter mount point path: " mount_path
        
        cat > "$CONFIG_FILE" <<EOF
{
  "protocol": "file",
  "location": "${mount_path}",
  "cache_ttl_hours": 6,
  "cache_dir": "portfolio/remote_cache"
}
EOF
        echo "✓ Configuration saved!"
        echo ""
        echo "Make sure the directory is mounted and accessible!"
        ;;
        
    3)
        echo ""
        echo "HTTP Configuration"
        echo "────────────────────────────────────────────────────────────"
        read -p "Enter server URL (https://example.com/yspy_data): " url
        
        cat > "$CONFIG_FILE" <<EOF
{
  "protocol": "http",
  "location": "${url}",
  "http_timeout": 30,
  "http_verify_ssl": true,
  "cache_ttl_hours": 6,
  "cache_dir": "portfolio/remote_cache"
}
EOF
        echo "✓ Configuration saved!"
        ;;
        
    4)
        echo ""
        echo "S3 Configuration"
        echo "────────────────────────────────────────────────────────────"
        read -p "Enter S3 bucket path (s3://bucket/path): " s3_path
        
        cat > "$CONFIG_FILE" <<EOF
{
  "protocol": "s3",
  "location": "${s3_path}",
  "cache_ttl_hours": 6,
  "cache_dir": "portfolio/remote_cache"
}
EOF
        echo "✓ Configuration saved!"
        echo ""
        echo "Make sure AWS credentials are configured (aws configure)"
        ;;
        
    5)
        echo ""
        echo "Testing current configuration..."
        echo "────────────────────────────────────────────────────────────"
        python3 -c "
import sys
sys.path.insert(0, 'short_selling')
from remote_short_data import load_remote_config, RemoteShortDataFetcher

config = load_remote_config()
print(f'Protocol: {config.protocol}')
print(f'Location: {config.location}')
print(f'Cache TTL: {config.cache_ttl_hours} hours')
print(f'Cache dir: {config.cache_dir}')

print('\nTesting connection...')
fetcher = RemoteShortDataFetcher(config)
success, data = fetcher.fetch_data(force_refresh=True)

if success and data:
    print(f'✓ Connection successful!')
    print(f'  Positions: {len(data.get(\"positions\", []))}')
    print(f'  Last updated: {data.get(\"last_updated\")}')
else:
    print('✗ Connection failed!')
    print('  Check your configuration and server status.')
"
        ;;
        
    6)
        echo ""
        echo "Opening documentation..."
        if command -v less &> /dev/null; then
            less remote_setup/QUICK_REFERENCE.txt
        else
            cat remote_setup/QUICK_REFERENCE.txt
        fi
        ;;
        
    7)
        echo "Goodbye!"
        exit 0
        ;;
        
    *)
        echo "Invalid choice!"
        exit 1
        ;;
esac

echo ""
echo "────────────────────────────────────────────────────────────"
echo "Setup complete! Run this script again to make changes."
echo "────────────────────────────────────────────────────────────"
