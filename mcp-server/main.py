#!/usr/bin/env python3
"""
MCP Server for GTFS Dublin Transport API
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()

# All imports after environment setup
from mcp.server.fastmcp import FastMCP  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from gtfs_core import TransportAPI  # noqa: E402

logger = logging.getLogger(__name__)


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
    timing_status: str
    vehicle: VehicleInfo | None = None
    vehicle_distance_to_stop_m: float | None = None
    vehicle_seconds_since_update: int | None = None


class CombinedScheduleResponse(BaseModel):
    timestamp: str
    live: list[CombinedDeparture]


# Module-level API reference, set during lifespan
_api: TransportAPI | None = None


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """Initialize TransportAPI once at startup."""
    global _api
    api_key = os.environ.get("TRANSPORT_API_KEY")
    if not api_key:
        raise ValueError("TRANSPORT_API_KEY environment variable is required")
    gtfs_dir = os.environ.get("GTFS_DIR", "../GTFS_Realtime")
    _api = TransportAPI(api_key=api_key, gtfs_dir=gtfs_dir)
    logger.info("TransportAPI initialized successfully")
    yield {"api": _api}
    _api = None


def get_api() -> TransportAPI:
    """Get the TransportAPI instance initialized at startup."""
    if _api is None:
        raise RuntimeError(
            "TransportAPI not initialized. Server may still be starting up."
        )
    return _api


# Create MCP server
mcp = FastMCP(
    "GTFS Dublin Transport API",
    host="0.0.0.0",
    port=8001,
    lifespan=app_lifespan,
)


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
    try:
        api = get_api()
        vehicles = api.get_vehicles_near_location(lat, lon, radius_m)
        return [VehicleInfo(**v) for v in vehicles]
    except Exception as e:
        logger.exception("Error in get_vehicles_near_location")
        raise RuntimeError(f"Failed to get vehicles near location: {e}") from e


@mcp.tool()
def get_vehicles_near_stop(
    stop_id: str = Field(description="GTFS stop ID"),
    radius_m: int = Field(default=100, description="Search radius in meters"),
) -> list[VehicleInfo]:
    """
    Get vehicles within a specified radius of a GTFS stop.
    Returns vehicle information including position, route, and trip details.
    """
    try:
        api = get_api()
        vehicles = api.get_vehicles_near_stop(stop_id, radius_m)
        return [VehicleInfo(**v) for v in vehicles]
    except ValueError as e:
        raise RuntimeError(f"Stop not found: {e}") from e
    except Exception as e:
        logger.exception("Error in get_vehicles_near_stop")
        raise RuntimeError(f"Failed to get vehicles near stop: {e}") from e


@mcp.tool()
def get_departures_for_stops(
    stop_ids: list[str] = Field(description="List of GTFS stop IDs"),
    use_stop_code: bool = Field(
        default=False, description="Whether stop_ids are stop codes instead of stop IDs"
    ),
) -> list[DepartureInfo]:
    """
    Get real-time departures for specified stops.
    Returns detailed departure information including delays and vehicle positions.
    """
    try:
        api = get_api()
        departures = api.get_departures_for_stops(stop_ids, use_stop_code)
        return [DepartureInfo(**d) for d in departures]
    except Exception as e:
        logger.exception("Error in get_departures_for_stops")
        raise RuntimeError(f"Failed to get departures: {e}") from e


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
    try:
        api = get_api()
        schedule = api.get_scheduled_times_for_route_stop(route_id, stop_id, use_stop_code)
        return [ScheduleEntry(**entry) for entry in schedule]
    except Exception as e:
        logger.exception("Error in get_scheduled_times_for_route_stop")
        raise RuntimeError(f"Failed to get schedule: {e}") from e


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
    try:
        api = get_api()
        result = api.get_combined_departures_and_schedule(
            stop_ids, window_future, use_stop_code
        )
        return CombinedScheduleResponse(**result)
    except Exception as e:
        logger.exception("Error in get_combined_departures_and_schedule")
        raise RuntimeError(f"Failed to get combined departures: {e}") from e


@mcp.tool()
def format_departures_output(
    json_output: str = Field(description="JSON output from get_departures_for_stops"),
) -> str:
    """
    Format raw departure JSON output into a human-readable summary.
    Returns a formatted text string with departure information grouped by stop.
    """
    import json
    from collections import defaultdict

    departures = json.loads(json_output)
    grouped: dict[str, list] = defaultdict(list)
    for dep in departures:
        stop_name = dep.get("stop_name", "Unknown Stop")
        grouped[stop_name].append(dep)

    lines = []
    for stop in sorted(grouped.keys()):
        lines.append(f"\n=== {stop} ===")
        sorted_deps = sorted(
            grouped[stop],
            key=lambda d: (
                d["time_left"] is None,
                d["time_left"] if d["time_left"] is not None else float("inf"),
            ),
        )
        for dep in sorted_deps:
            route = dep.get("route_short_name", "")
            time_left = dep.get("time_left")
            if time_left is not None:
                minsec = f"{abs(time_left)//60}:{abs(time_left)%60:02d}"
                if time_left < 0:
                    minsec = f"-{minsec}"
            else:
                minsec = "N/A"
            scheduled = dep.get("scheduled_departure_time", "N/A")
            expected = dep.get("expected_departure_time", "N/A")
            lines.append(
                f"Route: {route} | Time Left: {minsec} | Scheduled: {scheduled} | Expected: {expected}"
            )
    return "\n".join(lines) if lines else "No departures found."


@mcp.tool()
def get_service_alerts(
    route: str | None = Field(default=None, description="Route short name to filter by (e.g. '15', '16A')"),
    stop_id: str | None = Field(default=None, description="Stop ID to filter by"),
) -> list[dict]:
    """
    Get active service alerts (disruptions, cancellations, detours).
    Optionally filter by route short name or stop ID.
    """
    try:
        api = get_api()
        route_id = None
        if route:
            for rid, name in api.route_short_name_lookup.items():
                if name.lower() == route.lower():
                    route_id = rid
                    break
        return api.get_service_alerts(route_id=route_id, stop_id=stop_id)
    except Exception as e:
        logger.exception("Error in get_service_alerts")
        raise RuntimeError(f"Failed to get service alerts: {e}") from e


@mcp.tool()
def search_stops(
    query: str = Field(description="Search query (stop name, code, or ID)"),
    limit: int = Field(default=20, description="Maximum number of results"),
) -> list[dict]:
    """
    Search for stops by name, stop code, or stop ID.
    Returns matching stops with their IDs, names, codes, and coordinates.
    """
    try:
        api = get_api()
        return api.search_stops(query, limit=limit)
    except Exception as e:
        logger.exception("Error in search_stops")
        raise RuntimeError(f"Failed to search stops: {e}") from e


# --- MCP Resources ---


@mcp.resource("stop://{stop_id}")
def get_stop_info(stop_id: str) -> str:
    """Get information about a specific GTFS stop including name, location, and stop code."""
    try:
        api = get_api()
        stop = api.stop_info_lookup.get(stop_id)
        if not stop:
            return f"Stop {stop_id} not found"
        return (
            f"Stop ID: {stop_id}\n"
            f"Name: {stop.get('stop_name', 'Unknown')}\n"
            f"Code: {stop.get('stop_code', 'N/A')}\n"
            f"Location: {stop.get('stop_lat', '?')}, {stop.get('stop_lon', '?')}"
        )
    except Exception as e:
        return f"Error looking up stop {stop_id}: {e}"


@mcp.resource("route://{route_id}")
def get_route_info(route_id: str) -> str:
    """Get the short name for a GTFS route."""
    try:
        api = get_api()
        short_name = api.route_short_name_lookup.get(route_id)
        if not short_name:
            return f"Route {route_id} not found"
        return f"Route ID: {route_id}\nShort Name: {short_name}"
    except Exception as e:
        return f"Error looking up route {route_id}: {e}"


# --- MCP Prompts ---


@mcp.prompt()
def departure_summary(stop_ids: str) -> str:
    """Generate a prompt asking for a departure summary for comma-separated stop IDs."""
    ids = [s.strip() for s in stop_ids.split(",") if s.strip()]
    stop_list = ", ".join(ids)
    return (
        f"Please get the combined real-time and scheduled departures for stops: {stop_list}. "
        "Summarize the upcoming departures, highlighting any delays. "
        "Group by stop and sort by soonest departure."
    )


@mcp.prompt()
def nearby_vehicles(lat: str, lon: str, radius_m: str = "500") -> str:
    """Generate a prompt asking about vehicles near a location."""
    return (
        f"Please find all vehicles within {radius_m} meters of latitude {lat}, longitude {lon}. "
        "List each vehicle with its route, headsign, and distance from the point."
    )


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
