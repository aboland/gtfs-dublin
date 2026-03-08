# gtfs-dublin

A Python package providing both a REST API and MCP server for working with Dublin GTFS and GTFS-RT data.

## Recent Changes
- **Simplified project structure**: Removed legacy files, consolidated GTFS update logic, and split the monolithic TransportAPI class into smaller, focused components.
- **Improved caching**: Data fetching now uses time-based caching (max 20 seconds) for better performance and reduced API load.
- **UV-only installation**: Dropped outdated requirements.txt in favor of modern UV workspace management.

## Requirements
- Python 3.12+
- [UV](https://github.com/astral-sh/uv) for dependency and workspace management
- Docker (optional, for containerized deployment)

## Installation & Setup

### 1. Install UV
```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone the repository
```sh
git clone https://github.com/aboland/gtfs-dublin.git
cd gtfs-dublin
```

### 3. Install dependencies
```sh
uv sync
```

### 4. Set up environment variables
```sh
# Copy and edit the environment file
cp .env.example .env
# Edit .env with your Transport for Ireland API key
```

### 5. Download the latest GTFS data
```sh
uv run python update_gtfs.py
```

Or from Python:
```python
from gtfs_core.gtfs_loader import download_latest_gtfs
download_latest_gtfs()
```
```

## Usage

### Run the API server (locally)
```sh
uv run python -m gtfs_dublin
```

### Run the MCP server (locally)
```sh
uv run --project mcp-server python mcp-server/main.py --transport stdio
```

### Run with Docker
Build and run the container:
```sh
make build
make run
```
Or use Docker Compose:
```sh
make up          # Run both API server and MCP server
make up-api      # Run only the API server
make up-mcp      # Run only the MCP server
```

Docker Compose now manages GTFS data inside a Docker volume. You do not need `uv` or `git lfs` installed on the host machine for the normal compose workflow.

If the GTFS data volume is empty, invalid, or contains Git LFS pointer files, the `gtfs-data-init` container downloads fresh GTFS files before the API services start.

To force a GTFS refresh on the next startup:
```sh
GTFS_REFRESH_ON_START=1 docker compose up --build
```

To remove the persisted GTFS data volume and start clean:
```sh
docker compose down -v
docker compose up --build
```

### Docker Services
- **GTFS Data Init**: One-shot init container that validates/downloads GTFS files into a shared Docker volume
- **API Server** (port 8000): FastAPI REST API for transport data
- **MCP Server** (port 8001): Model Context Protocol server for AI integration

### API Endpoints
- `/departures?stops=STOP_ID1,STOP_ID2` — Get combined real-time and scheduled departures for given stop IDs
- `/departures?stops=1234,5678&use_stop_code=true` — Same, but using the 4-digit codes displayed at physical bus stops
- `/departures/route/{route_short_name}?stop=STOP_ID` — Get departures for a specific route (e.g. `15`, `16A`) at a stop
- `/alerts` — Get active service alerts (disruptions, cancellations, detours)
- `/alerts?route=15` — Alerts filtered by route short name
- `/stops/search?q=parnell` — Search stops by name, code, or ID
- `/delays/history?stop_id=...&route_id=...&days=7` — Historical delay records (requires delay tracking enabled)
- `/delays/summary?stop_id=...&days=7` — Average/max delay statistics
- `/health` — Health check endpoint

### MCP Server
The MCP server provides AI-accessible tools for transport data:
- `get_vehicles_near_location` — Find vehicles near coordinates
- `get_vehicles_near_stop` — Find vehicles near stops
- `get_departures_for_stops` — Get real-time departures
- `get_scheduled_times_for_route_stop` — Get scheduled times
- `get_combined_departures_and_schedule` — Combined real-time + scheduled data
- `get_service_alerts` — Get active service alerts
- `search_stops` — Search stops by name, code, or ID

### Environment Variables
- `TRANSPORT_API_KEY` — Your API key for the National Transport API (required)
- `STOPS` — Comma-separated list of stop IDs to focus on (optional)
- `GTFS_DIR` — Directory for GTFS files (default: `GTFS_Realtime`)
- `DELAY_DB_PATH` — Path to SQLite database for delay tracking (default: `delay_history.db`)
- `GTFS_SERVICE_ALERTS_URL` — Override the NTA service alerts endpoint (optional)

## Development

### Code Quality
This project uses modern Python tooling for code quality:

- **Ruff**: Fast Python linter and code formatter
- **MyPy**: Static type checking
- **Pre-commit**: Git hooks for automated quality checks

### Running Code Quality Checks
```sh
# Format code
make format

# Lint code
make lint

# Fix linting issues automatically
make lint-fix

# Type checking
make type-check

# Run all checks
make check
```

## Project Structure
```
gtfs_core/             # Shared core functionality
    __init__.py
    formatting.py      # Output formatting utilities
    gtfs_loader.py     # GTFS data loader and downloader
    transport_api.py   # Main transport API logic

gtfs_dublin/           # FastAPI server package
    __init__.py
    __main__.py        # Entrypoint for API server
    transport_api_server.py  # FastAPI application

mcp-server/            # MCP server for AI integration
    main.py            # MCP server implementation
    test_setup.py      # Test script
    update_gtfs.py     # GTFS update script for MCP

scripts/               # Utility scripts
    update-gtfs-monthly.sh  # Monthly GTFS cron script

GTFS_Realtime/         # GTFS data files (auto-downloaded)
Makefile               # Development and deployment tasks
docker-compose.yml     # Multi-service Docker setup
pyproject.toml         # UV workspace configuration
```

## Updating GTFS Data
To download the latest GTFS data files:
```python
from gtfs_core.gtfs_loader import download_latest_gtfs
download_latest_gtfs()
```
This will back up existing files as `.bak` if present.

## License
MIT
