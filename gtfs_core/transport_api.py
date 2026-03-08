import csv
import json
import os
from datetime import datetime, timedelta

import requests
from google.transit import gtfs_realtime_pb2

from .formatting import DeparturesFormatter
from .gtfs_loader import GTFSDataError, GTFSDataLoader


class VehicleDataFetcher:
    """Handles fetching and caching of GTFS Realtime data."""

    def __init__(self, session, headers, request_timeout, trip_headsign_lookup, route_short_name_lookup, gtfs):
        self.session = session
        self.headers = headers
        self.request_timeout = request_timeout
        self.trip_headsign_lookup = trip_headsign_lookup
        self.route_short_name_lookup = route_short_name_lookup
        self.gtfs = gtfs

    def _cached_fetch(self, cache_attr, fetch_func, max_age_seconds=20):
        """
        Fetches data with time-based caching. Returns cached data if fresh (< max_age_seconds).
        On fetch failure, returns cached data if available as fallback.
        """
        import logging
        from datetime import datetime

        now = datetime.now()
        cache = getattr(self, cache_attr, None)
        cache_time = getattr(self, f"{cache_attr}_time", None)

        if cache is not None and cache_time is not None:
            age = (now - cache_time).total_seconds()
            if age < max_age_seconds:
                return cache

        # Fetch fresh data
        try:
            data = fetch_func()
            setattr(self, cache_attr, data)
            setattr(self, f"{cache_attr}_time", now)
            return data
        except requests.exceptions.HTTPError as e:
            status_code = getattr(e.response, "status_code", None)
            logging.error(f"Cached fetch failed: {e}")
            if status_code == 429 and cache is not None:
                logging.warning("Returning cached data due to rate limiting (429).")
                return cache
            if cache is not None:
                logging.warning("Returning cached data due to fetch failure.")
                return cache
            raise RuntimeError(f"Fetch failed: {e}") from e
        except Exception as e:
            logging.error(f"Cached fetch failed: {e}")
            if cache is not None:
                logging.warning("Returning cached data due to fetch failure.")
                return cache
            raise RuntimeError(f"Fetch failed: {e}") from e

    def _fetch_trip_updates(self):
        def fetch_func():
            feed = gtfs_realtime_pb2.FeedMessage()
            url = os.environ.get(
                "GTFS_TRIP_UPDATES_URL", "https://api.nationaltransport.ie/gtfsr/v2/gtfsr"
            )
            response = self.session.get(url, headers=self.headers, timeout=self.request_timeout)
            response.raise_for_status()
            feed.ParseFromString(response.content)
            return feed

        return self._cached_fetch("_trip_updates_cache", fetch_func, max_age_seconds=20)

    def _fetch_vehicle_positions(self):
        def fetch_func():
            vfeed = gtfs_realtime_pb2.FeedMessage()
            url = os.environ.get(
                "GTFS_VEHICLE_POSITIONS_URL",
                "https://api.nationaltransport.ie/gtfsr/v2/Vehicles",
            )
            vresponse = self.session.get(url, headers=self.headers, timeout=self.request_timeout)
            vresponse.raise_for_status()
            vfeed.ParseFromString(vresponse.content)
            vehicle_lookup = {}
            for entity in vfeed.entity:
                if entity.HasField("vehicle"):
                    trip_id = entity.vehicle.trip.trip_id
                    vehicle_lookup[trip_id] = {
                        "trip_id": trip_id,
                        "vehicle_id": entity.vehicle.vehicle.id,
                        "position": {
                            "lat": entity.vehicle.position.latitude,
                            "lon": entity.vehicle.position.longitude,
                        },
                        "timestamp": entity.vehicle.timestamp,
                        "schedule_relationship": gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Name(
                            entity.vehicle.trip.schedule_relationship
                        ),
                    }
            # Enrich vehicle entries with static GTFS info when available
            for tid, v in list(vehicle_lookup.items()):
                try:
                    route_id = None
                    headsign = None
                    # Prefer trip->route mapping if GTFS loader provides it
                    if hasattr(self.gtfs, "trip_id_to_info"):
                        tinfo = self.gtfs.trip_id_to_info.get(tid)
                        if tinfo:
                            route_id = tinfo.get("route_id")
                            headsign = tinfo.get("trip_headsign") or tinfo.get("trip_headsign", None)
                    # Fallback: use trip_headsign_lookup which maps (trip_id, route_id) -> headsign
                    if not headsign:
                        for (t_id, r_id), h in self.trip_headsign_lookup.items():
                            if t_id == tid:
                                route_id = route_id or r_id
                                headsign = h
                                break
                    if route_id:
                        v["route_short_name"] = self.route_short_name_lookup.get(route_id, "")
                        # trip_short_name is sometimes used as a vehicle-facing number
                        # attempt to read it from trip data if available
                        if hasattr(self.gtfs, "trip_id_to_info") and tinfo:
                            tsn = tinfo.get("trip_short_name") or tinfo.get("trip_short_name", None)
                            if tsn:
                                v["trip_short_name"] = tsn
                    if headsign:
                        v["trip_headsign"] = headsign
                except Exception:
                    # Don't fail vehicle parsing for enrichment errors
                    continue
            return vehicle_lookup

        return self._cached_fetch("_vehicle_positions_cache", fetch_func, max_age_seconds=20)


class GTFSQueries:
    """Handles static GTFS data queries."""

    def __init__(self, gtfs):
        self.gtfs = gtfs
        self.trip_headsign_lookup = gtfs.trip_headsign_lookup
        self.trip_service_lookup = gtfs.trip_service_lookup
        self.route_short_name_lookup = gtfs.route_short_name_lookup
        self.stop_info_lookup = gtfs.stop_info_lookup
        self.stop_times_by_stop = gtfs.stop_times_by_stop
        self.departure_lookup = gtfs.departure_lookup

    def get_scheduled_times_for_route_stop(self, route_id, stop_id, direction_id=None, max_departures=5):
        """Get scheduled departure times for a specific route and stop."""
        # Implementation from TransportAPI
        # (copy the method body)
        pass  # I'll fill this later

    # Add other static query methods


class DepartureService:
    """Handles combined departure queries using realtime and static data."""

    def __init__(self, data_fetcher, gtfs_queries):
        self.data_fetcher = data_fetcher
        self.gtfs_queries = gtfs_queries

    def get_combined_departures_and_schedule(self, stops, max_departures=5, include_vehicles=True):
        """Get combined realtime and scheduled departures."""
        # Implementation
        pass


class TransportAPI:
    # --- Initialization and Configuration ---
    def __init__(self, api_key=None, gtfs_dir=None, focus_stops=None):
        # Configuration from env vars or parameters
        self.api_key = api_key or os.environ.get("TRANSPORT_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key must be provided via argument or TRANSPORT_API_KEY env var."
            )
        self.headers = {
            "x-api-key": self.api_key,
            "Cache-Control": "no-cache",
        }
        self.gtfs_dir = gtfs_dir or os.environ.get("GTFS_DIR", "GTFS_Realtime")
        try:
            self.gtfs = GTFSDataLoader(self.gtfs_dir, focus_stops=focus_stops)
        except GTFSDataError as e:
            raise RuntimeError(f"Failed to load GTFS data: {e}") from e
        # Use loader's lookups
        self.trip_headsign_lookup = self.gtfs.trip_headsign_lookup
        self.trip_service_lookup = self.gtfs.trip_service_lookup
        self.route_short_name_lookup = self.gtfs.route_short_name_lookup
        self.stop_info_lookup = self.gtfs.stop_info_lookup
        self.stop_times_by_stop = self.gtfs.stop_times_by_stop
        self.departure_lookup = self.gtfs.departure_lookup
        # HTTP session with sensible defaults: timeouts and retries
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        self.request_timeout = int(os.environ.get("GTFS_REQUEST_TIMEOUT", 5))
        session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        self.session = session

        # Compose with sub-components
        self.data_fetcher = VehicleDataFetcher(self.session, self.headers, self.request_timeout, self.trip_headsign_lookup, self.route_short_name_lookup, self.gtfs)
        self.gtfs_queries = GTFSQueries(self.gtfs)
        self.departure_service = DepartureService(self.data_fetcher, self.gtfs_queries)

    # --- Utility Methods ---
    def _add_delay_to_time(self, time_str, delay_seconds):
        t = datetime.strptime(time_str, "%H:%M:%S").time()
        today = datetime.today().date()
        dt = datetime.combine(today, t)
        new_time = dt + timedelta(seconds=delay_seconds)
        return new_time.strftime("%H:%M:%S"), new_time

    def _seconds_until_departure(self, expected_departure_dt):
        now = datetime.now().replace(microsecond=0)
        delta = expected_departure_dt - now
        return int(delta.total_seconds())

    def _format_seconds_to_min_sec(self, seconds):
        minutes, secs = divmod(abs(seconds), 60)
        sign = "-" if seconds < 0 else ""
        return f"{sign}{minutes}:{secs:02d}"

    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calculate the great-circle distance between two points on the Earth (in meters)."""
        from math import atan2, cos, radians, sin, sqrt

        R = 6371000  # Earth radius in meters
        phi1, phi2 = radians(lat1), radians(lat2)
        dphi = radians(lat2 - lat1)
        dlambda = radians(lon2 - lon1)
        a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    # --- GTFS Realtime Fetchers ---
    def _fetch_trip_updates(self):
        def fetch_func():
            feed = gtfs_realtime_pb2.FeedMessage()
            url = os.environ.get(
                "GTFS_TRIP_UPDATES_URL", "https://api.nationaltransport.ie/gtfsr/v2/gtfsr"
            )
            response = self.session.get(url, headers=self.headers, timeout=self.request_timeout)
            response.raise_for_status()
            feed.ParseFromString(response.content)
            return feed

        return self._cached_fetch("_trip_updates_cache", fetch_func, max_age_seconds=20)

    def _fetch_vehicle_positions(self):
        def fetch_func():
            vfeed = gtfs_realtime_pb2.FeedMessage()
            url = os.environ.get(
                "GTFS_VEHICLE_POSITIONS_URL",
                "https://api.nationaltransport.ie/gtfsr/v2/Vehicles",
            )
            vresponse = self.session.get(url, headers=self.headers, timeout=self.request_timeout)
            vresponse.raise_for_status()
            vfeed.ParseFromString(vresponse.content)
            vehicle_lookup = {}
            for entity in vfeed.entity:
                if entity.HasField("vehicle"):
                    trip_id = entity.vehicle.trip.trip_id
                    vehicle_lookup[trip_id] = {
                        "trip_id": trip_id,
                        "vehicle_id": entity.vehicle.vehicle.id,
                        "position": {
                            "lat": entity.vehicle.position.latitude,
                            "lon": entity.vehicle.position.longitude,
                        },
                        "timestamp": entity.vehicle.timestamp,
                        "schedule_relationship": gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Name(
                            entity.vehicle.trip.schedule_relationship
                        ),
                    }
            # Enrich vehicle entries with static GTFS info when available
            for tid, v in list(vehicle_lookup.items()):
                try:
                    route_id = None
                    headsign = None
                    # Prefer trip->route mapping if GTFS loader provides it
                    if hasattr(self.gtfs, "trip_id_to_info"):
                        tinfo = self.gtfs.trip_id_to_info.get(tid)
                        if tinfo:
                            route_id = tinfo.get("route_id")
                            headsign = tinfo.get("trip_headsign") or tinfo.get("trip_headsign", None)
                    # Fallback: use trip_headsign_lookup which maps (trip_id, route_id) -> headsign
                    if not headsign:
                        for (t_id, r_id), h in self.trip_headsign_lookup.items():
                            if t_id == tid:
                                route_id = route_id or r_id
                                headsign = h
                                break
                    if route_id:
                        v["route_short_name"] = self.route_short_name_lookup.get(route_id, "")
                        # trip_short_name is sometimes used as a vehicle-facing number
                        # attempt to read it from trip data if available
                        if hasattr(self.gtfs, "trip_id_to_info") and tinfo:
                            tsn = tinfo.get("trip_short_name") or tinfo.get("trip_short_name", None)
                            if tsn:
                                v["trip_short_name"] = tsn
                    if headsign:
                        v["trip_headsign"] = headsign
                except Exception:
                    # Don't fail vehicle parsing for enrichment errors
                    continue
            return vehicle_lookup

        return self._cached_fetch("_vehicle_positions_cache", fetch_func, max_age_seconds=20)

    # --- Vehicle Proximity Queries ---
    def get_vehicles_near_location(self, lat, lon, radius_m=100):
        """
        Returns a list of vehicles within `radius_m` metres of the given (lat, lon).
        Adds route_short_name and trip_headsign if available.
        """
        vehicle_lookup = self.data_fetcher._fetch_vehicle_positions()
        nearby = []
        for v in vehicle_lookup.values():
            vlat = v["position"]["lat"]
            vlon = v["position"]["lon"]
            dist = self._haversine_distance(lat, lon, vlat, vlon)
            if dist <= radius_m:
                v_copy = v.copy()
                v_copy["distance_to_point_m"] = dist
                # Try to add route_short_name and trip_headsign if trip_id is available
                trip_id = v.get("trip_id")
                route_id = None
                headsign = None
                if trip_id:
                    # Find route_id from trip_id using GTFS static data
                    if hasattr(self.gtfs, "trip_id_to_info"):
                        t_info = self.gtfs.trip_id_to_info.get(trip_id)
                        if t_info:
                            route_id = t_info.get("route_id")
                    if not route_id:
                        # Fallback: try to get from trip_headsign_lookup
                        for (t_id, r_id), h in self.trip_headsign_lookup.items():
                            if t_id == trip_id:
                                route_id = r_id
                                headsign = h
                                break
                    if route_id:
                        v_copy["route_short_name"] = self.route_short_name_lookup.get(
                            route_id, ""
                        )
                    # Add headsign if available
                    if headsign is None:
                        # Try to get headsign from trip_headsign_lookup
                        for (t_id, _r_id), h in self.trip_headsign_lookup.items():
                            if t_id == trip_id:
                                headsign = h
                                break
                    if headsign:
                        v_copy["trip_headsign"] = headsign
                nearby.append(v_copy)
        return nearby

    def get_vehicles_near_stop(self, stop_id, radius_m=100):
        """
        Returns a list of vehicles within `radius_m` metres of the stop with stop_id.
        """
        stop = self.stop_info_lookup.get(stop_id)
        if not stop:
            raise ValueError(f"Stop ID {stop_id} not found.")
        lat = float(stop["stop_lat"])
        lon = float(stop["stop_lon"])
        return self.get_vehicles_near_location(lat, lon, radius_m)

    def get_departures_for_stops(self, stop_ids, use_stop_code=False):
        """
        Get departures for a list of stop_ids or stop_codes.
        If use_stop_code is True, will map stop_codes to stop_ids using GTFS static data.
        """
        # Map stop_codes to stop_ids if needed
        if use_stop_code:
            stop_ids = [self.gtfs.stop_code_to_id.get(code, code) for code in stop_ids]
        else:
            stop_ids = stop_ids
        feed = self.data_fetcher._fetch_trip_updates()
        vehicle_lookup = self.data_fetcher._fetch_vehicle_positions()
        departures = []
        for entity in feed.entity:
            if entity.HasField("trip_update"):
                for stu in entity.trip_update.stop_time_update:
                    if stu.stop_id in stop_ids:
                        trip = entity.trip_update.trip
                        key = (trip.trip_id, trip.route_id)
                        dept_key = (trip.trip_id, stu.stop_id)
                        scheduled_departure_time = self.departure_lookup.get(
                            dept_key, ""
                        )
                        delay = (
                            stu.departure.delay
                            if stu.departure.HasField("delay")
                            else None
                        )
                        # Parse start_date and start_time
                        start_date = str(trip.start_date)
                        start_time_str = str(trip.start_time)
                        if start_date and start_time_str:
                            dt_str = start_date + " " + start_time_str
                            try:
                                arrival_dt = datetime.strptime(
                                    dt_str, "%Y%m%d %H:%M:%S"
                                )
                                arrival_str = arrival_dt.strftime("%Y-%m-%d %H:%M:%S")
                            except Exception:
                                arrival_str = f"{start_date} {start_time_str}"
                        else:
                            arrival_str = "N/A"
                        if delay is not None and scheduled_departure_time:
                            expected_departure_str, expected_departure_dt = (
                                self._add_delay_to_time(scheduled_departure_time, delay)
                            )
                            seconds_left = self._seconds_until_departure(
                                expected_departure_dt
                            )
                        else:
                            expected_departure_str = None
                            seconds_left = None
                        dep = {
                            "route_id": trip.route_id,
                            "route_short_name": self.route_short_name_lookup.get(
                                trip.route_id, ""
                            ),
                            "trip_id": trip.trip_id,
                            "trip_headsign": self.trip_headsign_lookup.get(key, ""),
                            "service_id": self.trip_service_lookup.get(key, ""),
                            "stop_id": stu.stop_id,
                            "stop_sequence": stu.stop_sequence,
                            "stop_name": self.stop_info_lookup.get(stu.stop_id, {}).get(
                                "stop_name", ""
                            ),
                            "stop_lat": self.stop_info_lookup.get(stu.stop_id, {}).get(
                                "stop_lat", ""
                            ),
                            "stop_lon": self.stop_info_lookup.get(stu.stop_id, {}).get(
                                "stop_lon", ""
                            ),
                            "scheduled_departure_time": scheduled_departure_time,
                            "delay": delay,
                            "expected_departure_time": expected_departure_str,
                            "time_left": seconds_left,
                            "start_time": trip.start_time,
                            "start_date": trip.start_date,
                            "schedule_relationship": gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.ScheduleRelationship.Name(
                                stu.schedule_relationship
                            ),
                            "arrival_str": arrival_str,
                        }
                        # Add vehicle info if available
                        vehicle_info = vehicle_lookup.get(trip.trip_id)
                        if vehicle_info:
                            dep["vehicle"] = vehicle_info
                            # Calculate distance if both stop and vehicle have valid lat/lon
                            try:
                                stop_lat = float(dep["stop_lat"])
                                stop_lon = float(dep["stop_lon"])
                                veh_lat = float(vehicle_info["position"]["lat"])
                                veh_lon = float(vehicle_info["position"]["lon"])
                                dep["vehicle_distance_to_stop_m"] = round(
                                    self._haversine_distance(
                                        stop_lat, stop_lon, veh_lat, veh_lon
                                    ),
                                    1,
                                )
                            except Exception:
                                dep["vehicle_distance_to_stop_m"] = None
                            # Add seconds since vehicle updated
                            try:
                                now = datetime.now().timestamp()
                                vehicle_ts = vehicle_info["timestamp"]
                                dep["vehicle_seconds_since_update"] = int(
                                    now - vehicle_ts
                                )
                            except Exception:
                                dep["vehicle_seconds_since_update"] = None
                        departures.append(dep)
        return json.dumps(departures, indent=2, default=str)

    def format_departures_output(self, json_output):
        return DeparturesFormatter.format_departures_output(json_output)

    def print_tidy_schedule(self, filtered_schedule):
        return DeparturesFormatter.print_tidy_schedule(filtered_schedule)

    def print_combined_schedule(self, combined_output):
        return DeparturesFormatter.print_combined_schedule(combined_output)

    def get_scheduled_times_for_route_stop(
        self, route_id=None, stop_id=None, use_stop_code=False
    ):
        """
        Returns a list of scheduled times for a given stop_id or stop_code (and optionally route_id), including trip, route, and calendar info.
        If route_id is None, returns all routes for the stop.
        Adds route_id and route_short_name to each result.
        Uses in-memory index if available.
        If use_stop_code is True, stop_id is interpreted as a stop_code and mapped to stop_id.
        """

        # Map stop_code to stop_id if needed
        sid = stop_id
        if use_stop_code and stop_id is not None:
            sid = self.gtfs.stop_code_to_id.get(stop_id, stop_id)

        # 1. Build trip lookup: trip_id -> (route_id, service_id, trip_headsign, trip_short_name)
        trip_lookup = {}
        with open(f"{self.gtfs_dir}/trips.txt", newline="") as trips_file:
            reader = csv.DictReader(trips_file)
            for row in reader:
                if route_id is None or row["route_id"] == route_id:
                    trip_lookup[row["trip_id"]] = {
                        "route_id": row["route_id"],
                        "service_id": row["service_id"],
                        "trip_headsign": row.get("trip_headsign", ""),
                        "trip_short_name": row.get("trip_short_name", ""),
                    }
        # 2. Use in-memory index if available
        results = []
        stop_ids = [sid] if sid is not None else list(self.stop_times_by_stop.keys())
        for sid in stop_ids:
            for row in self.stop_times_by_stop.get(sid, []):
                trip = trip_lookup.get(row["trip_id"])
                if not trip:
                    continue
                route_id_val = trip["route_id"]
                route_short_name = self.route_short_name_lookup.get(route_id_val, "")
                result = trip.copy()
                result["trip_id"] = row["trip_id"]  # Ensure trip_id is present
                result["arrival_time"] = row["arrival_time"]
                result["departure_time"] = row["departure_time"]
                result["stop_sequence"] = row["stop_sequence"]
                result["route_short_name"] = route_short_name
                results.append(result)
        # 3. For each result, get calendar info for service_id
        calendar_lookup = {}
        with open(f"{self.gtfs_dir}/calendar.txt", newline="") as cal_file:
            reader = csv.DictReader(cal_file)
            for row in reader:
                calendar_lookup[row["service_id"]] = row
        for result in results:
            cal = calendar_lookup.get(result["service_id"], {})
            result["calendar"] = cal
        return results

    def filter_schedule_by_time_window(
        self, schedule, window_past=10 * 60, window_future=60 * 60, reference_time=None
    ):
        """
        Filters a stop schedule for arrivals in the last `window_past` seconds and next `window_future` seconds.
        Only includes trips whose service is active for the current day of the week.
        By default, shows arrivals from 10 minutes ago to 60 minutes ahead.
        `reference_time` can be set for testing, otherwise uses now.
        Returns a list of dicts with an added 'seconds_until' field.
        """
        from datetime import datetime, timedelta

        now = reference_time or datetime.now()
        today = now.date()
        weekday = now.strftime("%A").lower()  # e.g. 'monday'
        filtered = []
        for entry in schedule:
            arr_time_str = entry.get("arrival_time")
            cal = entry.get("calendar", {})
            # Check if service is active for today
            if not cal or cal.get(weekday, "0") != "1":
                continue
            # Check if today is within start_date and end_date
            try:
                start_date = datetime.strptime(
                    cal.get("start_date", "19000101"), "%Y%m%d"
                ).date()
                end_date = datetime.strptime(
                    cal.get("end_date", "21000101"), "%Y%m%d"
                ).date()
                if not (start_date <= today <= end_date):
                    continue
            except Exception:
                continue
            if not arr_time_str:
                continue
            # Handle times >24:00:00 (next day)
            h, m, s = map(int, arr_time_str.split(":"))
            if h >= 24:
                arr_time = datetime.combine(
                    today + timedelta(days=1), datetime.min.time()
                ) + timedelta(hours=h - 24, minutes=m, seconds=s)
            else:
                arr_time = datetime.combine(today, datetime.min.time()) + timedelta(
                    hours=h, minutes=m, seconds=s
                )
            seconds_until = int((arr_time - now).total_seconds())
            if -window_past <= seconds_until <= window_future:
                entry = entry.copy()
                entry["seconds_until"] = seconds_until
                filtered.append(entry)
        # Sort by time until
        filtered.sort(key=lambda x: x["seconds_until"])
        return filtered

    def get_combined_departures_and_schedule(
        self, stop_ids, window_future=60 * 60, use_stop_code=False
    ):
        """
        Returns a dict with the current timestamp and a 'live' key containing a flat list of all departures (with all info in each entry).
        """
        import json
        from copy import deepcopy

        # Map stop_codes to stop_ids if needed
        if use_stop_code:
            stop_ids = [self.gtfs.stop_code_to_id.get(code, code) for code in stop_ids]
        else:
            stop_ids = stop_ids

        now = datetime.now()
        realtime_json = self.get_departures_for_stops(stop_ids, use_stop_code=False)
        realtime = json.loads(realtime_json)
        rt_index = {(d["trip_id"], d["stop_id"]): d for d in realtime}
        all_entries = []
        for sid in stop_ids:
            schedule = self.get_scheduled_times_for_route_stop(
                stop_id=sid, use_stop_code=use_stop_code
            )
            filtered = self.filter_schedule_by_time_window(
                schedule,
                window_past=5 * 60,
                window_future=window_future,
                reference_time=now,
            )
            stop_info = self.stop_info_lookup.get(sid, {})
            stop_code = stop_info.get("stop_code", "")
            stop_name = stop_info.get("stop_name", "")
            for entry in filtered:
                if "trip_id" not in entry:
                    continue  # Skip malformed schedule entries
                key = (entry["trip_id"], sid)
                entry["stop_id"] = sid
                entry["stop_code"] = stop_code
                entry["stop_name"] = stop_name
                if key in rt_index:
                    rt_index[key]["stop_id"] = sid
                    rt_index[key]["stop_code"] = stop_code
                    rt_index[key]["stop_name"] = stop_name
                    dep = deepcopy(rt_index[key])
                    if dep.get("expected_departure_time") is None and entry.get(
                        "arrival_time"
                    ):
                        dep["expected_departure_time"] = entry.get("arrival_time")
                        dep["used_scheduled_time"] = True
                        arr_time_str = entry.get("arrival_time")
                        h, m, s = map(int, arr_time_str.split(":"))
                        arr_time = now.replace(
                            hour=0, minute=0, second=0, microsecond=0
                        ) + timedelta(hours=h, minutes=m, seconds=s)
                        dep["time_left"] = int((arr_time - now).total_seconds())
                    else:
                        dep["used_scheduled_time"] = False
                    dep["source"] = "realtime"
                    if "vehicle_distance_to_stop_m" not in dep:
                        dep["vehicle_distance_to_stop_m"] = None
                    if "vehicle_seconds_since_update" not in dep:
                        dep["vehicle_seconds_since_update"] = None
                    all_entries.append(dep)
                else:
                    dep = deepcopy(entry)
                    dep["source"] = "schedule"
                    dep["time_left"] = dep.get("seconds_until")
                    dep["used_scheduled_time"] = True
                    dep["vehicle_distance_to_stop_m"] = None
                    dep["vehicle_seconds_since_update"] = None
                    all_entries.append(dep)
            # Add any real-time departures not in schedule (e.g. unscheduled extras)
            for key, dep in rt_index.items():
                if key[1] == sid and not any(
                    e.get("trip_id") == dep.get("trip_id")
                    for e in all_entries
                    if e.get("stop_id") == sid
                ):
                    dep2 = deepcopy(dep)
                    dep2["source"] = "realtime"
                    if dep2.get("expected_departure_time") is None:
                        dep2["used_scheduled_time"] = True
                    else:
                        dep2["used_scheduled_time"] = False
                    all_entries.append(dep2)
        # Sort all entries by time_left
        all_entries.sort(
            key=lambda d: (d.get("time_left") is None, d.get("time_left", float("inf")))
        )
        return {"timestamp": now.isoformat(), "live": all_entries}


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    api = TransportAPI(
        api_key=os.environ.get("TRANSPORT_API_KEY", "309f2a3c4c8d486a8b23bd6037e98bb0"),
        focus_stops=["8220DB002437", "8220DB002438"],
    )
    # Combined real-time and scheduled departures for the next hour for two stops
    combined = api.get_combined_departures_and_schedule(
        ["8220DB002437", "8220DB002438"]
    )
    for stop_id, departures in combined.items():
        print(f"\nDepartures for stop {stop_id}:")
        for dep in departures:
            src = dep.get("source", "")
            route = dep.get("route_short_name", "")
            trip = dep.get("trip_id", "")
            headsign = dep.get("trip_headsign", "")
            # Prefer expected_departure_time, then arrival_time, then scheduled_departure_time, then 'N/A'
            arr = (
                dep.get("expected_departure_time")
                or dep.get("arrival_time")
                or dep.get("scheduled_departure_time")
                or "N/A"
            )
            mins = dep.get("time_left")
            if mins is not None:
                minsec = f"{abs(mins)//60}:{abs(mins)%60:02d}"
                if mins < 0:
                    minsec = f"-{minsec}"
            else:
                minsec = "N/A"
            print(
                f"  [{src}] Route: {route} | Trip: {trip} | Headsign: {headsign} | Arrival: {arr} | In: {minsec}"
            )
