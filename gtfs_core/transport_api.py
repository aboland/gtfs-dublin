import logging
import os
import sqlite3
from datetime import datetime, timedelta

import requests
from google.transit import gtfs_realtime_pb2

from .formatting import DeparturesFormatter
from .gtfs_loader import GTFSDataError, GTFSDataLoader

logger = logging.getLogger(__name__)


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

    # --- GTFS Realtime Data Fetchers (with caching) ---
    def _cached_fetch(self, cache_attr, fetch_func, max_age_seconds=20):
        """Fetch data with time-based caching. Returns cached data if fresh (< max_age_seconds)."""
        now = datetime.now()
        cache = getattr(self, cache_attr, None)
        cache_time = getattr(self, f"{cache_attr}_time", None)

        if cache is not None and cache_time is not None:
            age = (now - cache_time).total_seconds()
            if age < max_age_seconds:
                return cache

        try:
            data = fetch_func()
            setattr(self, cache_attr, data)
            setattr(self, f"{cache_attr}_time", now)
            return data
        except requests.exceptions.HTTPError as e:
            status_code = getattr(e.response, "status_code", None)
            logger.error("Cached fetch failed: %s", e)
            if status_code == 429 and cache is not None:
                logger.warning("Returning cached data due to rate limiting (429).")
                return cache
            if cache is not None:
                logger.warning("Returning cached data due to fetch failure.")
                return cache
            raise RuntimeError(f"Fetch failed: {e}") from e
        except Exception as e:
            logger.error("Cached fetch failed: %s", e)
            if cache is not None:
                logger.warning("Returning cached data due to fetch failure.")
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
                    tinfo = self.gtfs.trip_info_lookup.get(tid)
                    route_id = tinfo["route_id"] if tinfo else None
                    headsign = tinfo["trip_headsign"] if tinfo else None
                    if not headsign:
                        for (t_id, r_id), h in self.trip_headsign_lookup.items():
                            if t_id == tid:
                                route_id = route_id or r_id
                                headsign = h
                                break
                    if route_id:
                        v["route_short_name"] = self.route_short_name_lookup.get(route_id, "")
                        if tinfo:
                            tsn = tinfo.get("trip_short_name")
                            if tsn:
                                v["trip_short_name"] = tsn
                    if headsign:
                        v["trip_headsign"] = headsign
                except Exception:
                    continue
            return vehicle_lookup

        return self._cached_fetch("_vehicle_positions_cache", fetch_func, max_age_seconds=20)

    def _fetch_service_alerts(self):
        def fetch_func():
            feed = gtfs_realtime_pb2.FeedMessage()
            url = os.environ.get(
                "GTFS_SERVICE_ALERTS_URL",
                "https://api.nationaltransport.ie/gtfsr/v2/ServiceAlerts",
            )
            response = self.session.get(url, headers=self.headers, timeout=self.request_timeout)
            response.raise_for_status()
            feed.ParseFromString(response.content)
            alerts = []
            for entity in feed.entity:
                if entity.HasField("alert"):
                    alert = entity.alert
                    # Extract translated text (prefer English, fall back to first)
                    header = self._get_translated_text(alert.header_text)
                    description = self._get_translated_text(alert.description_text)
                    url_text = self._get_translated_text(alert.url) if alert.HasField("url") else None
                    # Active periods
                    active_periods = []
                    for period in alert.active_period:
                        active_periods.append({
                            "start": period.start if period.start else None,
                            "end": period.end if period.end else None,
                        })
                    # Informed entities (affected routes/stops/agencies)
                    informed = []
                    for ie in alert.informed_entity:
                        entry = {}
                        if ie.agency_id:
                            entry["agency_id"] = ie.agency_id
                        if ie.route_id:
                            entry["route_id"] = ie.route_id
                            entry["route_short_name"] = self.route_short_name_lookup.get(ie.route_id, "")
                        if ie.stop_id:
                            entry["stop_id"] = ie.stop_id
                            stop = self.stop_info_lookup.get(ie.stop_id, {})
                            entry["stop_name"] = stop.get("stop_name", "")
                        if ie.HasField("trip"):
                            entry["trip_id"] = ie.trip.trip_id
                        informed.append(entry)
                    alerts.append({
                        "id": entity.id,
                        "header": header,
                        "description": description,
                        "url": url_text,
                        "cause": gtfs_realtime_pb2.Alert.Cause.Name(alert.cause),
                        "effect": gtfs_realtime_pb2.Alert.Effect.Name(alert.effect),
                        "active_periods": active_periods,
                        "informed_entities": informed,
                    })
            return alerts

        return self._cached_fetch("_service_alerts_cache", fetch_func, max_age_seconds=120)

    @staticmethod
    def _get_translated_text(translated_string):
        """Extract text from a GTFS-RT TranslatedString, preferring English."""
        if not translated_string or not translated_string.translation:
            return None
        for t in translated_string.translation:
            if t.language in ("en", "EN", ""):
                return t.text
        return translated_string.translation[0].text

    # --- Service Alerts ---
    def get_service_alerts(self, route_id=None, stop_id=None):
        """
        Get active service alerts. Optionally filter by route_id or stop_id.
        Returns a list of alert dicts.
        """
        alerts = self._fetch_service_alerts()
        if route_id is None and stop_id is None:
            return alerts
        filtered = []
        for alert in alerts:
            for ie in alert["informed_entities"]:
                if route_id and ie.get("route_id") == route_id:
                    filtered.append(alert)
                    break
                if stop_id and ie.get("stop_id") == stop_id:
                    filtered.append(alert)
                    break
        return filtered

    # --- Vehicle Proximity Queries ---
    def get_vehicles_near_location(self, lat, lon, radius_m=100):
        """
        Returns a list of vehicles within `radius_m` metres of the given (lat, lon).
        Adds route_short_name and trip_headsign if available.
        """
        vehicle_lookup = self._fetch_vehicle_positions()
        nearby = []
        for v in vehicle_lookup.values():
            vlat = v["position"]["lat"]
            vlon = v["position"]["lon"]
            dist = self._haversine_distance(lat, lon, vlat, vlon)
            if dist <= radius_m:
                v_copy = v.copy()
                v_copy["distance_to_point_m"] = dist
                # Vehicles are already enriched with route/headsign from _fetch_vehicle_positions
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

    # --- Stop Search ---
    def search_stops(self, query, limit=20):
        """
        Search stops by name or stop code (case-insensitive substring match).
        Returns a list of matching stop dicts with stop_id, stop_name, stop_code, stop_lat, stop_lon.
        """
        query_lower = query.lower()
        results = []
        for stop_id, info in self.stop_info_lookup.items():
            name = info.get("stop_name", "").lower()
            code = info.get("stop_code", "").lower()
            if query_lower in name or query_lower in code or query_lower in stop_id.lower():
                results.append({
                    "stop_id": stop_id,
                    "stop_name": info.get("stop_name", ""),
                    "stop_code": info.get("stop_code", ""),
                    "stop_lat": info.get("stop_lat", ""),
                    "stop_lon": info.get("stop_lon", ""),
                })
                if len(results) >= limit:
                    break
        return results

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
        feed = self._fetch_trip_updates()
        vehicle_lookup = self._fetch_vehicle_positions()
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
        return departures

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

        results = []
        stop_ids = [sid] if sid is not None else list(self.stop_times_by_stop.keys())
        for sid in stop_ids:
            for row in self.stop_times_by_stop.get(sid, []):
                trip = self.gtfs.trip_info_lookup.get(row["trip_id"])
                if not trip:
                    continue
                if route_id is not None and trip["route_id"] != route_id:
                    continue
                route_id_val = trip["route_id"]
                route_short_name = self.route_short_name_lookup.get(route_id_val, "")
                result = trip.copy()
                result["trip_id"] = row["trip_id"]
                result["arrival_time"] = row["arrival_time"]
                result["departure_time"] = row["departure_time"]
                result["stop_sequence"] = row["stop_sequence"]
                result["route_short_name"] = route_short_name
                cal = self.gtfs.calendar_lookup.get(result["service_id"], {})
                result["calendar"] = cal
                results.append(result)
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
        from copy import deepcopy

        # Map stop_codes to stop_ids if needed
        if use_stop_code:
            stop_ids = [self.gtfs.stop_code_to_id.get(code, code) for code in stop_ids]
        else:
            stop_ids = stop_ids

        now = datetime.now()
        realtime = self.get_departures_for_stops(stop_ids, use_stop_code=False)
        rt_index = {(d["trip_id"], d["stop_id"]): d for d in realtime}
        all_entries = []
        for sid in stop_ids:
            schedule = self.get_scheduled_times_for_route_stop(
                stop_id=sid, use_stop_code=False
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

    # --- Historical Delay Tracking ---
    def init_delay_tracking(self, db_path=None, tracked_stops=None, tracked_routes=None):
        """
        Initialize SQLite-based delay tracking.
        Only records delays for the specified stops and/or routes to control storage size.
        If tracked_stops/tracked_routes are None, uses focus_stops and tracks all routes at those stops.
        """
        self._delay_db_path = db_path or os.environ.get("DELAY_DB_PATH", "delay_history.db")
        self._tracked_stops = set(tracked_stops or self.gtfs.focus_stops or [])
        self._tracked_routes = set(tracked_routes) if tracked_routes else None
        conn = sqlite3.connect(self._delay_db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS delay_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                stop_id TEXT NOT NULL,
                route_id TEXT NOT NULL,
                route_short_name TEXT,
                trip_id TEXT NOT NULL,
                scheduled_time TEXT,
                delay_seconds INTEGER,
                UNIQUE(recorded_at, stop_id, trip_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_delay_stop_route
            ON delay_records(stop_id, route_id, recorded_at)
        """)
        conn.commit()
        conn.close()
        logger.info(
            "Delay tracking initialized: db=%s, stops=%s, routes=%s",
            self._delay_db_path, self._tracked_stops, self._tracked_routes,
        )

    def record_delays(self):
        """
        Snapshot current delays for tracked stops/routes and store in SQLite.
        Call this periodically (e.g. every few minutes) from a background task or cron.
        """
        if not hasattr(self, "_delay_db_path"):
            raise RuntimeError("Call init_delay_tracking() first")
        if not self._tracked_stops:
            return 0
        departures = self.get_departures_for_stops(list(self._tracked_stops))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        records = []
        for dep in departures:
            if dep.get("delay") is None:
                continue
            route_id = dep.get("route_id", "")
            if self._tracked_routes and route_id not in self._tracked_routes:
                continue
            records.append((
                now_str,
                dep.get("stop_id", ""),
                route_id,
                dep.get("route_short_name", ""),
                dep.get("trip_id", ""),
                dep.get("scheduled_departure_time"),
                dep.get("delay"),
            ))
        if not records:
            return 0
        conn = sqlite3.connect(self._delay_db_path)
        conn.executemany(
            "INSERT OR IGNORE INTO delay_records "
            "(recorded_at, stop_id, route_id, route_short_name, trip_id, scheduled_time, delay_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            records,
        )
        conn.commit()
        conn.close()
        return len(records)

    def get_delay_history(self, stop_id=None, route_id=None, days=7, limit=500):
        """
        Query historical delay records. Filter by stop_id and/or route_id.
        Returns records from the last `days` days, up to `limit` rows.
        """
        if not hasattr(self, "_delay_db_path"):
            raise RuntimeError("Call init_delay_tracking() first")
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        query = "SELECT recorded_at, stop_id, route_id, route_short_name, trip_id, scheduled_time, delay_seconds FROM delay_records WHERE recorded_at >= ?"
        params: list = [since]
        if stop_id:
            query += " AND stop_id = ?"
            params.append(stop_id)
        if route_id:
            query += " AND route_id = ?"
            params.append(route_id)
        query += " ORDER BY recorded_at DESC LIMIT ?"
        params.append(limit)
        conn = sqlite3.connect(self._delay_db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_delay_summary(self, stop_id=None, route_id=None, days=7):
        """
        Get average and max delay stats for the given stop/route over the last N days.
        """
        if not hasattr(self, "_delay_db_path"):
            raise RuntimeError("Call init_delay_tracking() first")
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        query = """
            SELECT route_id, route_short_name, stop_id,
                   COUNT(*) as sample_count,
                   ROUND(AVG(delay_seconds), 1) as avg_delay,
                   MAX(delay_seconds) as max_delay,
                   MIN(delay_seconds) as min_delay
            FROM delay_records
            WHERE recorded_at >= ?
        """
        params: list = [since]
        if stop_id:
            query += " AND stop_id = ?"
            params.append(stop_id)
        if route_id:
            query += " AND route_id = ?"
            params.append(route_id)
        query += " GROUP BY route_id, stop_id ORDER BY avg_delay DESC"
        conn = sqlite3.connect(self._delay_db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def purge_old_delays(self, keep_days=30):
        """Remove delay records older than keep_days to control storage size."""
        if not hasattr(self, "_delay_db_path"):
            raise RuntimeError("Call init_delay_tracking() first")
        cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(self._delay_db_path)
        cursor = conn.execute("DELETE FROM delay_records WHERE recorded_at < ?", (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        # VACUUM must run outside a transaction
        conn = sqlite3.connect(self._delay_db_path, isolation_level=None)
        conn.execute("VACUUM")
        conn.close()
        logger.info("Purged %d delay records older than %d days", deleted, keep_days)
        return deleted


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    api = TransportAPI(
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
