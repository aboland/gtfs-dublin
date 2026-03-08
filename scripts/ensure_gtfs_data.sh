#!/bin/sh
set -eu

cd /app

GTFS_DIR="${GTFS_DIR:-/app/GTFS_Realtime}"
REFRESH_ON_START="${GTFS_REFRESH_ON_START:-0}"

is_lfs_pointer() {
    file_path="$1"
    [ -f "$file_path" ] && head -n 1 "$file_path" | grep -q '^version https://git-lfs.github.com/spec/v1$'
}

has_expected_header_prefix() {
    file_path="$1"
    header_prefix="$2"
    [ -f "$file_path" ] || return 1
    header_line="$(head -n 1 "$file_path" 2>/dev/null || true)"
    case "$header_line" in
        "$header_prefix"*) return 0 ;;
        *) return 1 ;;
    esac
}

needs_refresh=0

if [ "$REFRESH_ON_START" = "1" ]; then
    needs_refresh=1
fi

mkdir -p "$GTFS_DIR"

if [ ! -f "$GTFS_DIR/trips.txt" ] || ! has_expected_header_prefix "$GTFS_DIR/trips.txt" 'route_id,service_id,trip_id,'; then
    needs_refresh=1
fi

if [ ! -f "$GTFS_DIR/routes.txt" ] || ! has_expected_header_prefix "$GTFS_DIR/routes.txt" 'route_id,route_short_name,'; then
    needs_refresh=1
fi

if [ ! -f "$GTFS_DIR/stops.txt" ] || ! has_expected_header_prefix "$GTFS_DIR/stops.txt" 'stop_id,stop_code,stop_name,'; then
    needs_refresh=1
fi

if [ ! -f "$GTFS_DIR/stop_times.txt" ] || ! has_expected_header_prefix "$GTFS_DIR/stop_times.txt" 'trip_id,arrival_time,departure_time,'; then
    needs_refresh=1
fi

if [ ! -f "$GTFS_DIR/calendar.txt" ] || ! has_expected_header_prefix "$GTFS_DIR/calendar.txt" 'service_id,'; then
    needs_refresh=1
fi

for gtfs_file in trips.txt routes.txt stops.txt stop_times.txt calendar.txt; do
    if is_lfs_pointer "$GTFS_DIR/$gtfs_file"; then
        needs_refresh=1
        break
    fi
done

if [ "$needs_refresh" = "1" ]; then
    echo "Refreshing GTFS data in $GTFS_DIR"
    uv run python update_gtfs.py
else
    echo "Using existing GTFS data in $GTFS_DIR"
fi

echo "GTFS data is ready"