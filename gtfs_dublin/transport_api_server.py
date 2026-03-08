import os

from fastapi import FastAPI, HTTPException, Query

from gtfs_core import TransportAPI

app = FastAPI()


# Read stops from environment variable (comma-separated)
def get_env_stops() -> list[str]:
    stops = os.getenv("STOPS", "")
    return [s.strip() for s in stops.split(",") if s.strip()]


# Read API key from environment variable
API_KEY = os.getenv("TRANSPORT_API_KEY", "")

# Create TransportAPI instance with focus_stops from env
api = TransportAPI(api_key=API_KEY, focus_stops=get_env_stops())


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
    days: int = Query(default=7, ge=1, le=90, description="Number of days to look back"),
    limit: int = Query(default=500, ge=1, le=5000, description="Max records"),
):
    """Get historical delay records for tracked stops/routes."""
    if not hasattr(api, "_delay_db_path"):
        raise HTTPException(status_code=404, detail="Delay tracking not enabled")
    return api.get_delay_history(stop_id=stop_id, route_id=route_id, days=days, limit=limit)


@app.get("/delays/summary")
def delay_summary(
    stop_id: str | None = Query(default=None, description="Filter by stop ID"),
    route_id: str | None = Query(default=None, description="Filter by route ID"),
    days: int = Query(default=7, ge=1, le=90, description="Number of days"),
):
    """Get average/max delay statistics for tracked stops/routes."""
    if not hasattr(api, "_delay_db_path"):
        raise HTTPException(status_code=404, detail="Delay tracking not enabled")
    return api.get_delay_summary(stop_id=stop_id, route_id=route_id, days=days)
