#!/usr/bin/env python3
"""
MCP Server for GTFS Dublin Transport API
"""

import os
import sys
from pathlib import Path
from typing import Any, cast

# Add parent directory to path to import gtfs_dublin
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()

# All imports after environment setup
from mcp.server.fastmcp import FastMCP  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from gtfs_core import TransportAPI  # noqa: E402


# Pydantic models for structured output
class VehicleInfo(BaseModel):
    trip_id: str
    vehicle_id: str
    position: dict[str, float]
    timestamp: int
    schedule_relationship: str
    distance_to_point_m: float | None = None
    route_short_name: str | None = None
    trip_headsign: str | None = None


class DepartureInfo(BaseModel):
    route_id: str
    route_short_name: str
    trip_id: str
    trip_headsign: str
    service_id: str
    stop_id: str
    stop_sequence: int
    stop_name: str
    stop_lat: str
    stop_lon: str
    scheduled_departure_time: str | None = None
    delay: int | None = None
    expected_departure_time: str | None = None
    time_left: int | None = None
    start_time: str
    start_date: str
    schedule_relationship: str
    arrival_str: str
    vehicle: VehicleInfo | None = None
    vehicle_distance_to_stop_m: float | None = None
    vehicle_seconds_since_update: int | None = None


class ScheduleEntry(BaseModel):
    route_id: str
    service_id: str
    trip_headsign: str
    trip_short_name: str
    trip_id: str
    arrival_time: str
    departure_time: str
    stop_sequence: int
    route_short_name: str
    calendar: dict[str, Any]


class CombinedDeparture(BaseModel):
    route_id: str
    route_short_name: str
    trip_id: str
    trip_headsign: str
    service_id: str
    stop_id: str
    stop_sequence: int
    stop_name: str
    stop_lat: str
    stop_lon: str
    scheduled_departure_time: str | None = None
    delay: int | None = None
    expected_departure_time: str | None = None
    time_left: int | None = None
    start_time: str
    start_date: str
    schedule_relationship: str
    arrival_str: str
    source: str
    used_scheduled_time: bool
    vehicle: VehicleInfo | None = None
    vehicle_distance_to_stop_m: float | None = None
    vehicle_seconds_since_update: int | None = None


class CombinedScheduleResponse(BaseModel):
    timestamp: str
    live: list[CombinedDeparture]


# Global API instance
api: TransportAPI | None = None


def get_api() -> TransportAPI:
    """Get or create TransportAPI instance"""
    global api
    if api is None:
        api_key = os.environ.get("TRANSPORT_API_KEY")
        if not api_key:
            raise ValueError("TRANSPORT_API_KEY environment variable is required")
        gtfs_dir = os.environ.get("GTFS_DIR", "../GTFS_Realtime")
        api = TransportAPI(api_key=api_key, gtfs_dir=gtfs_dir)
    return api


# Create MCP server
mcp = FastMCP("GTFS Dublin Transport API", host="0.0.0.0", port=8001)


@mcp.tool()
def get_vehicles_near_location(
    lat: float = Field(description="Latitude of the location"),
    lon: float = Field(description="Longitude of the location"),
    radius_m: int = Field(default=100, description="Search radius in meters"),
) -> list[VehicleInfo]:
    """
    Get vehicles within a specified radius of a geographic location.
    Returns vehicle information including position, route, and trip details.
    """
    api = get_api()
    vehicles = api.get_vehicles_near_location(lat, lon, radius_m)
    return [VehicleInfo(**v) for v in vehicles]


@mcp.tool()
def get_vehicles_near_stop(
    stop_id: str = Field(description="GTFS stop ID"),
    radius_m: int = Field(default=100, description="Search radius in meters"),
) -> list[VehicleInfo]:
    """
    Get vehicles within a specified radius of a GTFS stop.
    Returns vehicle information including position, route, and trip details.
    """
    api = get_api()
    vehicles = api.get_vehicles_near_stop(stop_id, radius_m)
    return [VehicleInfo(**v) for v in vehicles]


@mcp.tool()
def get_departures_for_stops(
    stop_ids: list[str] = Field(description="List of GTFS stop IDs"),
    use_stop_code: bool = Field(
        default=False, description="Whether stop_ids are stop codes instead of stop IDs"
    ),
) -> str:
    """
    Get real-time departures for specified stops.
    Returns JSON string with detailed departure information including delays and vehicle positions.
    """
    api = get_api()
    return cast(str, api.get_departures_for_stops(stop_ids, use_stop_code))


@mcp.tool()
def get_scheduled_times_for_route_stop(
    route_id: str | None = Field(
        default=None,
        description="GTFS route ID (optional, returns all routes if not specified)",
    ),
    stop_id: str = Field(description="GTFS stop ID"),
    use_stop_code: bool = Field(
        default=False, description="Whether stop_id is a stop code instead of stop ID"
    ),
) -> list[ScheduleEntry]:
    """
    Get scheduled departure times for a specific route and stop.
    Returns schedule entries with trip, route, and calendar information.
    """
    api = get_api()
    schedule = api.get_scheduled_times_for_route_stop(route_id, stop_id, use_stop_code)
    return [ScheduleEntry(**entry) for entry in schedule]


@mcp.tool()
def get_combined_departures_and_schedule(
    stop_ids: list[str] = Field(description="List of GTFS stop IDs"),
    window_future: int = Field(
        default=3600, description="Future time window in seconds (default 1 hour)"
    ),
    use_stop_code: bool = Field(
        default=False, description="Whether stop_ids are stop codes instead of stop IDs"
    ),
) -> CombinedScheduleResponse:
    """
    Get combined real-time and scheduled departures for specified stops.
    Merges live data with scheduled data for a comprehensive view.
    """
    api = get_api()
    result = api.get_combined_departures_and_schedule(
        stop_ids, window_future, use_stop_code
    )
    return CombinedScheduleResponse(**result)


@mcp.tool()
def format_departures_output(
    json_output: str = Field(description="JSON output from get_departures_for_stops"),
) -> str:
    """
    Format raw departure JSON output into a human-readable format.
    Note: This function prints formatted output to console and returns a summary.
    """
    api = get_api()
    api.format_departures_output(json_output)
    return "Departures formatted and printed to console. Check the output above."


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GTFS Dublin MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport type (default: stdio)",
    )

    args = parser.parse_args()

    if args.transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
