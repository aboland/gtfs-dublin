#!/bin/bash
#
# GTFS Monthly Update Script
# Updates GTFS data and restarts Docker containers
# Intended to be run via cron monthly
#

set -e

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

# Run update in a temporary container with write access to GTFS data
if docker-compose ps transport-api | grep -q "Up"; then
    # If container is running, use its image
    IMAGE_NAME=$(docker inspect $(docker-compose ps -q transport-api) --format='{{.Config.Image}}')
else
    # If container is not running, build it first
    log "🏗️ Building transport-api container..."
    docker-compose build transport-api >> "$LOG_FILE" 2>&1
    IMAGE_NAME="gtfs-dublin_transport-api"
fi

docker run --rm \
  -v "$PROJECT_DIR:/app" \
  -w /app \
  -e TRANSPORT_API_KEY="${TRANSPORT_API_KEY:-}" \
  --entrypoint python3 \
  "$IMAGE_NAME" \
  update_gtfs.py >> "$LOG_FILE" 2>&1

log "✅ GTFS data updated successfully"

# Restart containers to load new data
log "🔄 Restarting Docker containers..."
docker-compose restart transport-api >> "$LOG_FILE" 2>&1

log "✅ Containers restarted successfully"
log "✅ GTFS update complete!"

exit 0
