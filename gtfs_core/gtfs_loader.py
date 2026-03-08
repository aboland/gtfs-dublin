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
        self.focus_stops = set(focus_stops) if focus_stops else None
        self.trip_headsign_lookup = {}
        self.trip_service_lookup = {}
        self.route_short_name_lookup = {}
        self.stop_info_lookup = {}
        self.stop_times_by_stop = {}
        self.departure_lookup = {}
        self.stop_code_to_id = {}  # New: map stop_code to stop_id
        self.trip_info_lookup = {}  # trip_id -> {route_id, service_id, trip_headsign, trip_short_name}
        self.calendar_lookup = {}  # service_id -> calendar row
        self.focus_trip_ids = set()
        self._loaded = False
        self._load_all()

    def _load_all(self):
        try:
            self._load_trips()
            self._load_routes()
            self._load_stops()
            self._load_stop_times()
            self._load_calendar()
            self._prune_to_focus_trips()
        except Exception as e:
            raise GTFSDataError(f"Failed to load GTFS data: {e}") from e
        self._loaded = True

    def _prune_to_focus_trips(self):
        if self.focus_stops is None:
            return

        relevant_trip_ids = self.focus_trip_ids
        self.trip_info_lookup = {
            trip_id: info
            for trip_id, info in self.trip_info_lookup.items()
            if trip_id in relevant_trip_ids
        }
        self.trip_headsign_lookup = {
            key: headsign
            for key, headsign in self.trip_headsign_lookup.items()
            if key[0] in relevant_trip_ids
        }
        self.trip_service_lookup = {
            key: service_id
            for key, service_id in self.trip_service_lookup.items()
            if key[0] in relevant_trip_ids
        }

        relevant_service_ids = {
            info["service_id"]
            for info in self.trip_info_lookup.values()
            if info.get("service_id")
        }
        self.calendar_lookup = {
            service_id: row
            for service_id, row in self.calendar_lookup.items()
            if service_id in relevant_service_ids
        }

    def _open_csv_reader(self, path, required_columns):
        if not os.path.exists(path):
            raise GTFSDataError(f"Missing file: {path}")

        csv_file = open(path, newline="", encoding="utf-8-sig")
        reader = csv.DictReader(csv_file)
        fieldnames = reader.fieldnames or []

        if fieldnames and fieldnames[0] == "version https://git-lfs.github.com/spec/v1":
            csv_file.close()
            raise GTFSDataError(
                f"{path} is a Git LFS pointer, not GTFS data. Run 'git lfs pull' or refresh the GTFS files with update_gtfs.py."
            )

        missing_columns = [column for column in required_columns if column not in fieldnames]
        if missing_columns:
            csv_file.close()
            raise GTFSDataError(
                f"{path} is missing expected GTFS columns {missing_columns}. Found columns: {fieldnames}"
            )

        return csv_file, reader

    def _load_trips(self):
        path = os.path.join(self.gtfs_dir, "trips.txt")
        required_columns = ["route_id", "service_id", "trip_id"]
        trips_file, reader = self._open_csv_reader(path, required_columns)
        try:
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
        finally:
            trips_file.close()

    def _load_routes(self):
        path = os.path.join(self.gtfs_dir, "routes.txt")
        required_columns = ["route_id", "route_short_name"]
        routes_file, reader = self._open_csv_reader(path, required_columns)
        try:
            for row in reader:
                self.route_short_name_lookup[row["route_id"]] = row["route_short_name"]
        finally:
            routes_file.close()

    def _load_stops(self):
        path = os.path.join(self.gtfs_dir, "stops.txt")
        required_columns = ["stop_id", "stop_name", "stop_lat", "stop_lon"]
        stops_file, reader = self._open_csv_reader(path, required_columns)
        try:
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
        finally:
            stops_file.close()

    def _load_stop_times(self):
        path = os.path.join(self.gtfs_dir, "stop_times.txt")
        required_columns = ["trip_id", "stop_id", "departure_time", "arrival_time"]
        stop_times_file, reader = self._open_csv_reader(path, required_columns)
        try:
            for row in reader:
                if self.focus_stops is None or row["stop_id"] in self.focus_stops:
                    self.stop_times_by_stop.setdefault(row["stop_id"], []).append(row)
                    self.focus_trip_ids.add(row["trip_id"])
                    key = (row["trip_id"], row["stop_id"])
                    self.departure_lookup[key] = row["departure_time"]
        finally:
            stop_times_file.close()

    def _load_calendar(self):
        path = os.path.join(self.gtfs_dir, "calendar.txt")
        required_columns = ["service_id", "start_date", "end_date"]
        cal_file, reader = self._open_csv_reader(path, required_columns)
        try:
            for row in reader:
                self.calendar_lookup[row["service_id"]] = row
        finally:
            cal_file.close()


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
