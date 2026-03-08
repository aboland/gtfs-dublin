import os

from fastapi import FastAPI, HTTPException

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
def departures(stops: str | None = None):
    """
    Returns combined departures for the given stops (comma-separated), or the env stops if not provided.
    """
    stop_ids = [
        s.strip()
        for s in (stops or os.getenv("STOPS", "") or "").split(",")
        if s.strip()
    ]
    if not stop_ids:
        # No stops provided and no default in env
        raise HTTPException(status_code=400, detail="No stop IDs provided")
    try:
        result = api.get_combined_departures_and_schedule(stop_ids)
        return result
    except RuntimeError as e:
        # Upstream fetch failure or other runtime issue
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/health")
def health():
    return {"status": "ok"}
