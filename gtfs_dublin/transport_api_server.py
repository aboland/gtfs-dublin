import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException, Query

from gtfs_core import TransportAPI

logger = logging.getLogger(__name__)


# Read stops from environment variable (comma-separated)
def get_env_stops() -> list[str]:
    stops = os.getenv("STOPS", "")
    return [s.strip() for s in stops.split(",") if s.strip()]


def get_env_list(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def is_delay_tracking_enabled() -> bool:
    return os.getenv("DELAY_TRACKING_ENABLED", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# Read API key from environment variable
API_KEY = os.getenv("TRANSPORT_API_KEY", "")

# Create TransportAPI instance with focus_stops from env
api = TransportAPI(api_key=API_KEY, focus_stops=get_env_stops())


def resolve_route_id(route_id: str | None = None, route: str | None = None) -> str | None:
    if route_id:
        return route_id
    if route is None:
        return None
    for rid, name in api.route_short_name_lookup.items():
        if name.lower() == route.lower():
            return rid
    raise HTTPException(status_code=404, detail=f"Route '{route}' not found")


def resolve_tracked_routes(values: list[str]) -> list[str]:
    resolved: list[str] = []
    for value in values:
        if value in api.route_short_name_lookup:
            resolved.append(value)
            continue
        matched = next(
            (rid for rid, name in api.route_short_name_lookup.items() if name.lower() == value.lower()),
            None,
        )
        if matched:
            resolved.append(matched)
        else:
            logger.warning("Ignoring unknown tracked route '%s'", value)
    return resolved


async def delay_record_loop(interval_seconds: int):
    while True:
        try:
            count = api.record_delays()
            logger.info("Recorded %d delay entries", count)
        except Exception:
            logger.exception("Error recording delays")
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task: asyncio.Task | None = None
    if is_delay_tracking_enabled():
        tracked_stops = get_env_list("DELAY_TRACKED_STOPS", os.getenv("STOPS", ""))
        tracked_routes = resolve_tracked_routes(get_env_list("DELAY_TRACKED_ROUTES"))
        if tracked_stops:
            api.init_delay_tracking(
                db_path=os.getenv("DELAY_DB_PATH", "/app/data/delay_history.db"),
                tracked_stops=tracked_stops,
                tracked_routes=tracked_routes or None,
            )
            keep_days = int(os.getenv("DELAY_KEEP_DAYS", "90"))
            api.purge_old_delays(keep_days=keep_days)
            interval_seconds = int(os.getenv("DELAY_RECORD_INTERVAL", "300"))
            if interval_seconds > 0:
                task = asyncio.create_task(delay_record_loop(interval_seconds))
        else:
            logger.warning(
                "Delay tracking was enabled but no tracked stops were configured"
            )
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(lifespan=lifespan)


@app.get("/departures")
def departures(
    stops: str | None = None,
    use_stop_code: bool = Query(
        default=False,
        description="If true, treat stop values as stop codes (displayed at physical stops) instead of GTFS stop IDs",
    ),
):
    """
    Returns combined departures for the given stops (comma-separated), or the env stops if not provided.
    Set use_stop_code=true to pass the 4-digit codes shown at bus stops instead of GTFS stop IDs.
    """
    stop_ids = [
        s.strip()
        for s in (stops or os.getenv("STOPS", "") or "").split(",")
        if s.strip()
    ]
    if not stop_ids:
        raise HTTPException(status_code=400, detail="No stop IDs provided")
    try:
        result = api.get_combined_departures_and_schedule(
            stop_ids, use_stop_code=use_stop_code
        )
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/departures/route/{route_short_name}")
def departures_by_route(
    route_short_name: str,
    stop: str = Query(description="Stop ID (or stop code if use_stop_code=true)"),
    use_stop_code: bool = Query(default=False, description="Treat stop as a stop code"),
):
    """
    Get scheduled and real-time departures for a specific route at a stop.
    Use the route's short name (e.g. '15', '16A') as shown on the bus.
    """
    # Resolve route short name to route_id
    route_id = None
    for rid, name in api.route_short_name_lookup.items():
        if name.lower() == route_short_name.lower():
            route_id = rid
            break
    if route_id is None:
        raise HTTPException(status_code=404, detail=f"Route '{route_short_name}' not found")

    try:
        combined = api.get_combined_departures_and_schedule(
            [stop], use_stop_code=use_stop_code
        )
        filtered = [
            dep for dep in combined.get("live", [])
            if dep.get("route_id") == route_id
               or dep.get("route_short_name", "").lower() == route_short_name.lower()
        ]
        return {"timestamp": combined["timestamp"], "live": filtered}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/alerts")
def service_alerts(
    route: str | None = Query(default=None, description="Filter by route short name"),
    stop_id: str | None = Query(default=None, description="Filter by stop ID"),
):
    """Get active service alerts, optionally filtered by route or stop."""
    route_id = None
    if route:
        for rid, name in api.route_short_name_lookup.items():
            if name.lower() == route.lower():
                route_id = rid
                break
        if route_id is None:
            raise HTTPException(status_code=404, detail=f"Route '{route}' not found")
    try:
        return api.get_service_alerts(route_id=route_id, stop_id=stop_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/stops/search")
def search_stops(
    q: str = Query(description="Search query (stop name, code, or ID)"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
):
    """Search for stops by name, stop code, or stop ID."""
    return api.search_stops(q, limit=limit)


@app.get("/delays/history")
def delay_history(
    stop_id: str | None = Query(default=None, description="Filter by stop ID"),
    route_id: str | None = Query(default=None, description="Filter by route ID"),
    route: str | None = Query(default=None, description="Filter by route short name"),
    days: int = Query(default=7, ge=1, le=90, description="Number of days to look back"),
    limit: int = Query(default=500, ge=1, le=5000, description="Max records"),
):
    """Get historical delay records for tracked stops/routes."""
    if not hasattr(api, "_delay_db_path"):
        raise HTTPException(status_code=404, detail="Delay tracking not enabled")
    resolved_route_id = resolve_route_id(route_id=route_id, route=route)
    return api.get_delay_history(
        stop_id=stop_id, route_id=resolved_route_id, days=days, limit=limit
    )


@app.get("/delays/summary")
def delay_summary(
    stop_id: str | None = Query(default=None, description="Filter by stop ID"),
    route_id: str | None = Query(default=None, description="Filter by route ID"),
    route: str | None = Query(default=None, description="Filter by route short name"),
    days: int = Query(default=7, ge=1, le=90, description="Number of days"),
):
    """Get average/max delay statistics for tracked stops/routes."""
    if not hasattr(api, "_delay_db_path"):
        raise HTTPException(status_code=404, detail="Delay tracking not enabled")
    resolved_route_id = resolve_route_id(route_id=route_id, route=route)
    return api.get_delay_summary(stop_id=stop_id, route_id=resolved_route_id, days=days)


@app.get("/delays/patterns")
def delay_patterns(
    stop_id: str | None = Query(default=None, description="Filter by stop ID"),
    route_id: str | None = Query(default=None, description="Filter by route ID"),
    route: str | None = Query(default=None, description="Filter by route short name"),
    days: int = Query(default=30, ge=1, le=365, description="Number of days"),
    weekday: int | None = Query(default=None, ge=0, le=6, description="Weekday, Monday=0"),
    hour: int | None = Query(default=None, ge=0, le=23, description="Hour of day (24h)"),
):
    """Get historical delay summaries bucketed by weekday and hour."""
    if not hasattr(api, "_delay_db_path"):
        raise HTTPException(status_code=404, detail="Delay tracking not enabled")
    resolved_route_id = resolve_route_id(route_id=route_id, route=route)
    return api.get_delay_pattern_summary(
        stop_id=stop_id,
        route_id=resolved_route_id,
        days=days,
        weekday=weekday,
        hour=hour,
    )


@app.get("/delays/estimate")
def delay_estimate(
    stop_id: str = Query(description="Filter by stop ID"),
    route_id: str | None = Query(default=None, description="Filter by route ID"),
    route: str | None = Query(default=None, description="Route short name"),
    days: int = Query(default=90, ge=1, le=365, description="Number of days"),
    weekday: int | None = Query(default=None, ge=0, le=6, description="Weekday, Monday=0"),
    hour: int | None = Query(default=None, ge=0, le=23, description="Hour of day (24h)"),
    min_samples: int = Query(default=5, ge=1, le=100, description="Minimum samples before fallback"),
):
    """Estimate expected delay using weekday/hour history with fallback."""
    if not hasattr(api, "_delay_db_path"):
        raise HTTPException(status_code=404, detail="Delay tracking not enabled")
    resolved_route_id = resolve_route_id(route_id=route_id, route=route)
    if resolved_route_id is None:
        raise HTTPException(status_code=400, detail="route or route_id is required")
    result = api.get_delay_estimate(
        stop_id=stop_id,
        route_id=resolved_route_id,
        days=days,
        weekday=weekday,
        hour=hour,
        min_samples=min_samples,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No historical delay data found")
    return result
