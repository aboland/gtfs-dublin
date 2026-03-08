# GTFS Dublin Simplification Plan

## Current Project Status
The GTFS Dublin project is functional and well-structured, providing real-time and scheduled Dublin transport data via FastAPI REST API and MCP server interfaces. It uses UV for dependency management, has no compilation errors, and includes Docker support. Key components include GTFS data loading, API queries, and update scripts. However, there is code duplication (e.g., GTFS scripts and data storage), a large monolithic TransportAPI class (~500 lines), and legacy files that add unnecessary complexity.

## Short-Term Development Plan (Simplification Focus)
Prioritize quick wins to reduce duplication and improve maintainability. Estimated effort: 1-2 weeks for core changes.

1. **Remove Legacy Files (1-2 hours)**: ✅ Completed
   - Deleted `ignore/` folder (outdated code copy).
   - Removed `requirements.txt` (superseded by UV/pyproject.toml).

2. **Consolidate GTFS Update Logic (2-4 hours)**: ✅ Completed
   - Moved `scripts/update_gtfs.py` to root-level `update_gtfs.py`.
   - Removed duplicate `mcp-server/update_gtfs.py` and `mcp-server/GTFS_Realtime/` directory.
   - Updated `mcp-server/test_setup.py` to use correct GTFS path (`../GTFS_Realtime`).
   - MCP server now references root GTFS data via workspace dependency.

3. **Extract Cache Helper in TransportAPI (1-2 hours)**: ✅ Completed
   - Added reusable `_cached_fetch()` method with 20-second max age caching.
   - Refactored `_fetch_vehicle_positions()` and `_fetch_trip_updates()` to use the helper, eliminating duplicated error-handling logic.

4. **Split TransportAPI Class (4-6 hours)**: ✅ Completed
   - Created `VehicleDataFetcher` class for GTFS Realtime data fetching and caching.
   - Created `GTFSQueries` class for static GTFS data queries (structure in place).
   - Created `DepartureService` class for combined queries (structure in place).
   - Updated `TransportAPI` to compose these classes and delegate calls accordingly.

5. **Add Basic Integration Tests (2-4 hours)**: ✅ Completed
   - Expanded `mcp-server/test_setup.py` with integration tests for key TransportAPI methods (get_vehicles_near_location, get_departures_for_stops, get_scheduled_times_for_route_stop).
   - Tests validate that methods execute without errors and return expected data structures.

6. **Validation & Documentation (1-2 hours)**: ✅ Completed
   - Ran linting with `uv run ruff check` — all checks passed.
   - Updated README.md to reflect simplified structure, UV-only installation, and recent changes.
   - Verified project builds and runs correctly after all simplifications.

This plan reduces code by ~20-30% while maintaining functionality. Start with removals, then refactoring. If issues arise, iterate on fixes.