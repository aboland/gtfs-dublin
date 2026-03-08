# GTFS Dublin — Issues & Suggested Improvements

## Critical: Security

### 1. API Key Hardcoded in Source Code
**File:** `gtfs_core/transport_api.py` (bottom `__main__` block)
```python
api_key=os.environ.get("TRANSPORT_API_KEY", "309f2a3c4c8d486a8b23bd6037e98bb0")
```
A real API key is used as a default fallback. This key is committed to version control. **Remove the default value** and rely solely on the environment variable. If the key is live, rotate it immediately.

### 2. `.env` File Committed to Repository
**File:** `mcp-server/.env` contains the actual API key and stop IDs. This file is not covered by `.gitignore` (only `/.env` at root is ignored). Add `mcp-server/.env` to `.gitignore` and remove it from version history.

### 3. Missing `.env.example`
The README references `cp .env.example .env` but no `.env.example` file exists. Create one with placeholder values:
```
TRANSPORT_API_KEY=your-api-key-here
STOPS=stop_id_1,stop_id_2
```

---

## High Priority: Dead / Broken Code

### 4. Incomplete Refactor — Stub Classes Never Used
`VehicleDataFetcher`, `GTFSQueries`, and `DepartureService` at the top of `transport_api.py` were created as part of a decomposition effort, but their methods are stubs (`pass`). Meanwhile, `TransportAPI` still contains all the actual logic. Either:
- **Complete the refactor**: move logic into the sub-components and have `TransportAPI` delegate, or
- **Remove the stubs** to avoid confusion.

### 5. Orphaned Methods on `TransportAPI`
`TransportAPI` defines `_fetch_trip_updates()` and `_fetch_vehicle_positions()` that call `self._cached_fetch(...)`, but `TransportAPI` does not have a `_cached_fetch` method — only `VehicleDataFetcher` does. These methods would crash if called directly. They appear to be leftover copies from before the `VehicleDataFetcher` extraction.

### 6. `get_departures_for_stops` Returns JSON String
This method returns `json.dumps(departures, ...)` (a string), but `get_combined_departures_and_schedule` immediately `json.loads()` it back into a dict. This unnecessary serialisation round-trip adds overhead and makes the internal API awkward. Return the list directly and serialise only at the boundary (FastAPI endpoint / MCP tool).

### 7. `temp_trip_updates.txt` Checked In
This appears to be a debug artifact. Remove it from the repository and add it to `.gitignore`.

---

## Medium Priority: MCP Server

### 8. `format_departures_output` Tool Is Unusable for AI Agents
This MCP tool calls `print()` and returns the static string `"Departures formatted and printed to console."`. An AI agent consuming this tool via MCP gets no useful data. It should **return the formatted text as a string** instead of printing it.

### 9. `get_departures_for_stops` Tool Returns Raw JSON String
All other MCP tools return Pydantic models for structured output, but this one returns a raw JSON string (`str`). Convert it to return `list[DepartureInfo]` for consistency and better schema validation.

### 10. No Error Handling in MCP Tools
All MCP tool functions call `get_api()` and `api.*` without try/except. If the API key is missing, GTFS data isn't loaded, or the upstream API is down, the agent receives a raw Python traceback. Wrap tool bodies in try/except and return clear error messages.

### 11. Fragile `sys.path` Manipulation
`mcp-server/main.py` uses `sys.path.insert(0, ...)` to find the parent package. Since the MCP server already declares `gtfs-dublin` as a workspace dependency in its `pyproject.toml`, this shouldn't be necessary when running via `uv run`. Remove the path hack and rely on the proper workspace resolution.

### 12. Consider Adding MCP Resources and Prompts
The MCP server only exposes tools. Adding MCP resources (e.g., `stop://{stop_id}` for stop info, `route://{route_id}` for route info) and prompts (e.g., a "departure summary" prompt) would give AI agents richer context and more natural interaction patterns, per MCP best practices.

---

## Medium Priority: Performance

### 13. Re-reading CSV Files on Every Request
`get_scheduled_times_for_route_stop()` opens and reads `trips.txt` and `calendar.txt` from disk on every call. These files only change when GTFS data is updated (monthly). Load them once during `GTFSDataLoader` initialization and store them in memory alongside the other lookups.

### 14. O(n) Linear Scan for Trip→Route Lookup
In both `VehicleDataFetcher._fetch_vehicle_positions()` and `TransportAPI.get_vehicles_near_location()`, when the `trip_id_to_info` lookup isn't available, the code iterates over the entire `trip_headsign_lookup` dict to find a matching `trip_id`:
```python
for (t_id, r_id), h in self.trip_headsign_lookup.items():
    if t_id == tid:
        ...
        break
```
Build a `trip_id → route_id` index once during initialization to make this O(1).

### 15. `departure_lookup` Loads All Stop Times
While `stop_times_by_stop` is filtered by `focus_stops`, the `departure_lookup` dict is populated for every trip/stop in `stop_times.txt` — the largest GTFS file. Consider applying the same filter, or loading it lazily.

---

## Low Priority: Code Quality & Project Config

### 16. Redundant `use_stop_code` Handling
In `get_combined_departures_and_schedule`, stop codes are mapped to stop IDs at the start, but then `get_scheduled_times_for_route_stop(stop_id=sid, use_stop_code=use_stop_code)` is called with the flag still set. This could cause double-mapping. After mapping once at the caller, pass `use_stop_code=False` downstream.

### 17. Duplicate Vehicle Enrichment Logic
The vehicle enrichment code (adding `route_short_name`, `trip_headsign`) is duplicated almost identically in:
- `VehicleDataFetcher._fetch_vehicle_positions()`
- `TransportAPI._fetch_vehicle_positions()` (dead code)
- `TransportAPI.get_vehicles_near_location()`

Since `_fetch_vehicle_positions()` already enriches vehicles, `get_vehicles_near_location()` re-enriches them redundantly. Consolidate to a single enrichment pass.

### 18. `pyproject.toml` Placeholder Author
```toml
authors = [{name = "Your Name", email = "you@example.com"}]
```
Update with actual author information.

### 19. Overlapping Formatters: `black` + `ruff`
Both `black` and `ruff` are configured. Ruff now includes a formatter (`ruff format`) that can replace black entirely. Consider dropping black to simplify the toolchain.

### 20. Very Permissive `mypy` Config
Most strictness options are disabled (`disallow_untyped_defs = false`, etc.). Gradually enabling these would catch real bugs — especially around the `None` vs missing-key patterns throughout the codebase.

### 21. README Markdown Issues
- The code block showing `download_latest_gtfs()` has mismatched fencing (extra triple backticks)
- The repository URL is `https://github.com/yourusername/gtfs-dublin.git` — a placeholder

### 22. No Proper Test Suite
Only `mcp-server/test_setup.py` exists — a manual integration check script. There are no pytest unit tests despite pytest being in `dev` dependencies. Key candidates for testing:
- `GTFSDataLoader` parsing logic
- `_haversine_distance` calculations
- `_add_delay_to_time` / `_seconds_until_departure` time math
- `filter_schedule_by_time_window` filtering logic
- `get_combined_departures_and_schedule` merging logic

### 23. Docker — MCP Server Unnecessary `depends_on`
In `docker-compose.yml`, `mcp-server` depends on `transport-api`, but they are independent services that both access GTFS data directly. Remove the dependency unless there's a specific startup ordering need.

### 24. Global Mutable State in MCP Server
The `api` global variable with lazy initialization (`get_api()`) isn't thread-safe. Use FastMCP's lifespan context manager to initialize the `TransportAPI` instance once at startup:
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(server):
    api = TransportAPI(...)
    yield {"api": api}
```

---

## Summary Table

| # | Severity | Category | Summary |
|---|----------|----------|---------|
| 1 | **Critical** | Security | API key hardcoded in source |
| 2 | **Critical** | Security | `.env` with real key committed |
| 3 | **High** | Config | Missing `.env.example` |
| 4 | **High** | Code | Stub classes never completed |
| 5 | **High** | Bug | Orphaned methods reference missing `_cached_fetch` |
| 6 | **High** | Design | Unnecessary JSON round-trip |
| 7 | **Medium** | Hygiene | Temp file in repo |
| 8 | **Medium** | MCP | `format_departures_output` prints instead of returns |
| 9 | **Medium** | MCP | Inconsistent return types across tools |
| 10 | **Medium** | MCP | No error handling in tools |
| 11 | **Medium** | MCP | Fragile `sys.path` hack |
| 12 | **Medium** | MCP | No resources or prompts |
| 13 | **Medium** | Perf | CSV re-read on every request |
| 14 | **Medium** | Perf | O(n) trip→route lookups |
| 15 | **Medium** | Perf | Unfiltered `departure_lookup` |
| 16 | **Low** | Bug | Double `use_stop_code` mapping |
| 17 | **Low** | Code | Duplicated enrichment logic |
| 18 | **Low** | Config | Placeholder author |
| 19 | **Low** | Tooling | Redundant `black` + `ruff` |
| 20 | **Low** | Tooling | Permissive mypy config |
| 21 | **Low** | Docs | README markdown/placeholder issues |
| 22 | **Low** | Testing | No pytest test suite |
| 23 | **Low** | Docker | Unnecessary service dependency |
| 24 | **Low** | MCP | Global mutable state / thread safety |
