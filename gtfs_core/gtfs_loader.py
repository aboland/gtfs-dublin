import csv
import os
import zipfile
from io import BytesIO

import requests


class GTFSDataError(Exception):
    pass


class GTFSDataLoader:
    def __init__(self, gtfs_dir="GTFS_Realtime", focus_stops=None):
        self.gtfs_dir = gtfs_dir
        self.focus_stops = focus_stops
        self.trip_headsign_lookup = {}
        self.trip_service_lookup = {}
        self.route_short_name_lookup = {}
        self.stop_info_lookup = {}
        self.stop_times_by_stop = {}
        self.departure_lookup = {}
        self.stop_code_to_id = {}  # New: map stop_code to stop_id
        self.trip_info_lookup = {}  # trip_id -> {route_id, service_id, trip_headsign, trip_short_name}
        self.calendar_lookup = {}  # service_id -> calendar row
        self._loaded = False
        self._load_all()

    def _load_all(self):
        try:
            self._load_trips()
            self._load_routes()
            self._load_stops()
            self._load_stop_times()
            self._load_calendar()
        except Exception as e:
            raise GTFSDataError(f"Failed to load GTFS data: {e}") from e
        self._loaded = True

    def _load_trips(self):
        path = os.path.join(self.gtfs_dir, "trips.txt")
        if not os.path.exists(path):
            raise GTFSDataError(f"Missing file: {path}")
        with open(path, newline="") as trips_file:
            reader = csv.DictReader(trips_file)
            for row in reader:
                key = (row["trip_id"], row["route_id"])
                self.trip_headsign_lookup[key] = row["trip_headsign"]
                self.trip_service_lookup[key] = row["service_id"]
                self.trip_info_lookup[row["trip_id"]] = {
                    "route_id": row["route_id"],
                    "service_id": row["service_id"],
                    "trip_headsign": row.get("trip_headsign", ""),
                    "trip_short_name": row.get("trip_short_name", ""),
                }

    def _load_routes(self):
        path = os.path.join(self.gtfs_dir, "routes.txt")
        if not os.path.exists(path):
            raise GTFSDataError(f"Missing file: {path}")
        with open(path, newline="") as routes_file:
            reader = csv.DictReader(routes_file)
            for row in reader:
                self.route_short_name_lookup[row["route_id"]] = row["route_short_name"]

    def _load_stops(self):
        path = os.path.join(self.gtfs_dir, "stops.txt")
        if not os.path.exists(path):
            raise GTFSDataError(f"Missing file: {path}")
        with open(path, newline="") as stops_file:
            reader = csv.DictReader(stops_file)
            for row in reader:
                # Always store stop_code in stop_info_lookup for later reference
                self.stop_info_lookup[row["stop_id"]] = {
                    "stop_name": row.get("stop_name", ""),
                    "stop_lat": row.get("stop_lat", ""),
                    "stop_lon": row.get("stop_lon", ""),
                    "stop_code": row.get("stop_code", ""),
                }
                # Map stop_code to stop_id if present and not blank
                stop_code = row.get("stop_code", "")
                stop_id = row.get("stop_id", "")
                if stop_code and stop_id:
                    self.stop_code_to_id[stop_code] = stop_id

    def _load_stop_times(self):
        path = os.path.join(self.gtfs_dir, "stop_times.txt")
        if not os.path.exists(path):
            raise GTFSDataError(f"Missing file: {path}")
        with open(path, newline="") as stop_times_file:
            reader = csv.DictReader(stop_times_file)
            for row in reader:
                if self.focus_stops is None or row["stop_id"] in self.focus_stops:
                    self.stop_times_by_stop.setdefault(row["stop_id"], []).append(row)
                    key = (row["trip_id"], row["stop_id"])
                    self.departure_lookup[key] = row["departure_time"]

    def _load_calendar(self):
        path = os.path.join(self.gtfs_dir, "calendar.txt")
        if not os.path.exists(path):
            raise GTFSDataError(f"Missing file: {path}")
        with open(path, newline="") as cal_file:
            reader = csv.DictReader(cal_file)
            for row in reader:
                self.calendar_lookup[row["service_id"]] = row


def download_latest_gtfs(
    gtfs_dir="GTFS_Realtime",
    url="https://www.transportforireland.ie/transitData/Data/GTFS_Realtime.zip",
    keep_existing=True,
):
    """
    Downloads and extracts the latest GTFS files to the specified directory.
    If keep_existing is True, existing files are preserved as .bak copies.
    """
    os.makedirs(gtfs_dir, exist_ok=True)
    response = requests.get(url)
    response.raise_for_status()
    with zipfile.ZipFile(BytesIO(response.content)) as z:
        for member in z.namelist():
            filename = os.path.join(gtfs_dir, os.path.basename(member))
            if keep_existing and os.path.exists(filename):
                os.rename(filename, filename + ".bak")
            with open(filename, "wb") as f:
                f.write(z.read(member))
