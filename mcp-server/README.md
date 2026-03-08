# GTFS Dublin MCP Server

A Model Context Protocol (MCP) server that provides access to Dublin's public transport data through the GTFS Dublin API.

## Features

This MCP server exposes the following tools for accessing Dublin transport data:

- **get_vehicles_near_location**: Find vehicles within a radius of a geographic location
- **get_vehicles_near_stop**: Find vehicles near a specific GTFS stop
- **get_departures_for_stops**: Get real-time departures for specified stops
- **get_scheduled_times_for_route_stop**: Get scheduled departure times for routes and stops
- **get_combined_departures_and_schedule**: Get combined real-time and scheduled departures
- **format_departures_output**: Format raw departure data into human-readable format

## Setup

1. Ensure you have a valid Transport API key from the National Transport Authority
2. Set the `TRANSPORT_API_KEY` environment variable in the `.env` file
3. Update the GTFS data: `python update_gtfs.py` (copies from parent project)
4. The GTFS data directory should be available (automatically copied from parent project)

## Environment Variables

- `TRANSPORT_API_KEY`: Your API key for accessing transport data
- `GTFS_DIR`: Path to GTFS data directory (defaults to `./GTFS_Realtime`)

## Running the Server

### Development Mode
```bash
uv run mcp dev main.py
```

### As stdio Server
```bash
python main.py
```

### As HTTP Server
```bash
uv run python main.py --transport streamable-http
```

## Installation in Claude Desktop

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "gtfs-dublin": {
      "command": "uv",
      "args": ["run", "python", "/path/to/mcp-server/main.py"],
      "env": {
        "TRANSPORT_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## API Key

To get an API key, visit the [National Transport Authority Developer Portal](https://developer.nationaltransport.ie/).</content>
<parameter name="filePath">/Users/aidanboland/git/gtfs-dublin/mcp-server/README.md
