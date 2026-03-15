#!/bin/bash
set -e

# Create config directory if it doesn't exist
mkdir -p /config

# Remove default nginx site if present
rm -f /etc/nginx/sites-enabled/default

echo "Starting DeDuparr v2..."
exec "$@"
