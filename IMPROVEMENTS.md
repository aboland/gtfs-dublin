# GTFS Dublin — Delay Tracking Implementation Plan

This document describes how to set up and operationalise historical delay tracking for Dublin bus stops. The tracking system uses a lightweight SQLite database, scoped to specific stops and routes to control storage size.

---

## Overview

The delay tracking system periodically snapshots real-time delay data from the NTA GTFS-RT feed and stores it in SQLite. This enables:
- Historical delay analysis per route and stop
- Delay analysis by weekday and hour of day
- Average/max delay statistics over configurable time windows
- Trend detection for commute planning
- Data for Home Assistant sensors showing delay patterns

**Storage is bounded by design:**
- Only tracks delays at stops/routes you configure
- Automatic purge of records older than N days
- Estimated ~2-3 MB/month for 2 stops, all routes, sampled every 5 minutes

---

## 1. Configuration

### Environment Variables

Add these to your `.env` file (all optional):

```env
# Path to the SQLite database (default: delay_history.db)
DELAY_DB_PATH=/app/data/delay_history.db

# Stops to track delays for (reuses STOPS if not set)
DELAY_TRACKED_STOPS=8220DB002437,8220DB002438

# Routes to track (optional — if unset, tracks all routes at tracked stops)
DELAY_TRACKED_ROUTES=

# How often to record delays in seconds (default: 300 = 5 minutes)
DELAY_RECORD_INTERVAL=300

# How many days of history to keep (default: 90)
DELAY_KEEP_DAYS=90
```

### Docker Volume

To persist the database across container restarts, mount a volume in `docker-compose.yml`:

```yaml
services:
  transport-api:
    volumes:
      - ./GTFS_Realtime:/app/GTFS_Realtime:ro
      - ./data:/app/data  # Persistent storage for delay database
```

---

## 2. API Methods

The `TransportAPI` class provides these methods:

### Initialisation
```python
api.init_delay_tracking(
    db_path="/app/data/delay_history.db",
    tracked_stops=["8220DB002437", "8220DB002438"],
    tracked_routes=None,  # None = all routes at tracked stops
)
```

### Recording (call periodically)
```python
count = api.record_delays()  # Returns number of records inserted
```

### Querying
```python
# Raw history (last 7 days, up to 500 records)
history = api.get_delay_history(stop_id="8220DB002437", route_id=None, days=7, limit=500)

# Aggregated stats
summary = api.get_delay_summary(stop_id="8220DB002437", days=7)
# Returns: [{"route_id": "...", "route_short_name": "15", "stop_id": "...",
#            "sample_count": 42, "avg_delay": 85.3, "max_delay": 300, "min_delay": -10}]
```

### Cleanup
```python
deleted = api.purge_old_delays(keep_days=30)
```

---

## 3. REST API Endpoints

Once tracking is enabled:

| Endpoint | Description |
|---|---|
| `GET /delays/history?stop_id=...&route_id=...&days=7&limit=500` | Raw delay records |
| `GET /delays/summary?stop_id=...&route_id=...&days=7` | Aggregated delay stats |
| `GET /delays/patterns?stop_id=...&route=15&days=90` | Delay stats bucketed by weekday and hour |
| `GET /delays/estimate?stop_id=...&route=15` | Historical delay estimate with weekday/hour fallback |

---

## 4. Implementation Steps

### Step 1: Add Background Recording to the API Server

Update `gtfs_dublin/transport_api_server.py` to call `record_delays()` periodically using a FastAPI background task:

```python
import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise delay tracking on startup
    tracked_stops = os.getenv("DELAY_TRACKED_STOPS", os.getenv("STOPS", ""))
    stops = [s.strip() for s in tracked_stops.split(",") if s.strip()]
    tracked_routes_env = os.getenv("DELAY_TRACKED_ROUTES", "")
    routes = [r.strip() for r in tracked_routes_env.split(",") if r.strip()] or None

    if stops:
        api.init_delay_tracking(
            db_path=os.getenv("DELAY_DB_PATH", "delay_history.db"),
            tracked_stops=stops,
            tracked_routes=routes,
        )
        # Start background recording loop
        task = asyncio.create_task(_record_loop())
    yield
    if stops:
        task.cancel()

async def _record_loop():
    interval = int(os.getenv("DELAY_RECORD_INTERVAL", "300"))
    while True:
        try:
            count = api.record_delays()
            logger.info("Recorded %d delay entries", count)
        except Exception:
            logger.exception("Error recording delays")
        await asyncio.sleep(interval)

app = FastAPI(lifespan=lifespan)
```

### Step 2: Add Periodic Purge (cron or startup)

Option A — Run purge on startup (simplest):
```python
# Inside lifespan, after init_delay_tracking:
keep_days = int(os.getenv("DELAY_KEEP_DAYS", "30"))
api.purge_old_delays(keep_days=keep_days)
```

Option B — Cron job on the host:
```sh
# /etc/cron.d/gtfs-purge-delays
0 3 * * 0 curl -s http://localhost:8000/delays/purge > /dev/null
```

### Step 3: Mount Persistent Volume

In `docker-compose.yml`, add the data volume so the SQLite DB survives container restarts:
```yaml
volumes:
  - ./data:/app/data
```

Create the directory on the host:
```sh
mkdir -p data
```

### Step 4: Deploy

```sh
git pull origin main
docker compose build
docker compose up -d
```

---

## 5. Home Assistant Integration

### Average Delay Sensor

```yaml
rest:
  - resource: http://<server-ip>:8000/delays/summary?stop_id=8220DB002437&days=7
    scan_interval: 3600  # Update hourly
    sensor:
      - name: "Bus Delay Stats"
        value_template: "{{ value_json | length }}"
        json_attributes_path: "$[0]"
        json_attributes:
          - route_short_name
          - avg_delay
          - max_delay
          - sample_count
```

### Template Sensor for Display

```yaml
template:
  - sensor:
      - name: "Avg Bus Delay - Main Street"
        state: >
          {% set avg = state_attr('sensor.bus_delay_stats', 'avg_delay') %}
          {% if avg is not none %}
            {{ (avg / 60) | round(1) }}
          {% else %}
            Unknown
          {% endif %}
        unit_of_measurement: "min"
        icon: mdi:clock-alert-outline
```

---

## 6. Storage Estimates

| Stops | Sample Interval | Routes | Days Kept | Est. Rows | Est. Size |
|-------|----------------|--------|-----------|-----------|-----------|
| 2     | 5 min          | All    | 30        | ~29,000   | ~2-3 MB   |
| 2     | 5 min          | 3      | 30        | ~8,000    | ~1 MB     |
| 5     | 5 min          | All    | 30        | ~72,000   | ~6-7 MB   |
| 2     | 5 min          | All    | 90        | ~87,000   | ~8 MB     |

Storage is dominated by the number of tracked stops. Limiting `tracked_routes` is the most effective way to reduce size.

---

## 7. Database Schema

```sql
CREATE TABLE delay_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,      -- ISO timestamp
    stop_id TEXT NOT NULL,
    route_id TEXT NOT NULL,
    route_short_name TEXT,
    trip_id TEXT NOT NULL,
    scheduled_time TEXT,
    delay_seconds INTEGER,         -- Positive = late, negative = early
    UNIQUE(recorded_at, stop_id, trip_id)
);

CREATE INDEX idx_delay_stop_route ON delay_records(stop_id, route_id, recorded_at);
```

The `UNIQUE` constraint prevents duplicate entries if `record_delays()` is called more frequently than departures change.
