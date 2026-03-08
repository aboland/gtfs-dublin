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
git clone https://github.com/yourusername/gtfs-dublin.git
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
```
```python
from gtfs_dublin.gtfs_loader import download_latest_gtfs
download_latest_gtfs()
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

### Docker Services
- **API Server** (port 8000): FastAPI REST API for transport data
- **MCP Server** (port 8001): Model Context Protocol server for AI integration

### API Endpoints
- `/departures?stops=STOP_ID1,STOP_ID2` — Get combined real-time and scheduled departures for given stop IDs
- `/health` — Health check endpoint

### MCP Server
The MCP server provides AI-accessible tools for transport data:
- `get_vehicles_near_location` — Find vehicles near coordinates
- `get_vehicles_near_stop` — Find vehicles near stops
- `get_departures_for_stops` — Get real-time departures
- `get_scheduled_times_for_route_stop` — Get scheduled times
- `get_combined_departures_and_schedule` — Combined real-time + scheduled data

### Environment Variables
- `TRANSPORT_API_KEY` — Your API key for the National Transport API (required)
- `STOPS` — Comma-separated list of stop IDs to focus on (optional)
- `GTFS_DIR` — Directory for GTFS files (default: `GTFS_Realtime`)

## Development

### Code Quality
This project uses modern Python tooling for code quality:

- **Black**: Code formatting (88 character line length)
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

# Install pre-commit hooks
make pre-commit-install

# Run pre-commit on all files
make pre-commit-run
```

- Format code: `make format` (uses Black via UV)
- Run linter: `make lint` (uses Ruff via UV)
- Type check: `make type-check` (uses MyPy via UV)
- Run tests: `make test` (uses pytest via UV)
- Clean build/test artifacts: `make clean`

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
    update_gtfs.py     # GTFS data download script

GTFS_Realtime/         # GTFS data files (auto-downloaded)
Makefile               # Development and deployment tasks
docker-compose.yml     # Multi-service Docker setup
pyproject.toml         # UV workspace configuration
```
    transport_api_server.py # FastAPI server
mcp-server/            # MCP server for AI integration
    main.py            # MCP server entrypoint
    pyproject.toml     # MCP server dependencies
    README.md          # MCP server documentation
GTFS_Realtime/         # GTFS data files (updated periodically)
Makefile               # Common tasks (build, test, format, Docker)
pyproject.toml         # UV / build configuration (project + workspace)
uv.lock                # UV workspace lockfile
requirements.txt       # (legacy, for Docker)
README.md
```

## Updating GTFS Data
To download the latest GTFS data files:
```python
from gtfs_dublin.gtfs_loader import download_latest_gtfs
download_latest_gtfs()
```
This will back up existing files as `.bak` if present.

## License
MIT
