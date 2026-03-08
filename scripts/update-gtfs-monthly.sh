#!/bin/bash
#
# GTFS Monthly Update Script
# Updates GTFS data and restarts Docker containers
# Intended to be run via cron monthly
#

set -e

# Configuration
PROJECT_DIR="$HOME/gtfs-dublin"
LOG_FILE="$PROJECT_DIR/gtfs-update.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Logging function
log() {
    echo "[$TIMESTAMP] $1" >> "$LOG_FILE"
}

# Error handling
on_error() {
    ERROR_MSG="GTFS update failed at line $1"
    log "❌ $ERROR_MSG"
    # Optional: Send notification (e.g., via email or webhook)
    exit 1
}

trap 'on_error $LINENO' ERR

# Start update
log "🔄 Starting GTFS update..."

# Navigate to project directory
cd "$PROJECT_DIR"

# Update GTFS data
log "📥 Downloading latest GTFS data..."
python3 update_gtfs.py >> "$LOG_FILE" 2>&1

log "✅ GTFS data updated successfully"

# Restart containers to load new data
log "🔄 Restarting Docker containers..."
docker-compose restart transport-api >> "$LOG_FILE" 2>&1

log "✅ Containers restarted successfully"
log "✅ GTFS update complete!"

exit 0
