"""Tests for TransportAPI utility methods and schedule filtering."""

from datetime import datetime, timedelta


def _make_api():
    """Create a minimal TransportAPI-like object with just the utility methods."""
    from gtfs_core.transport_api import TransportAPI

    # We only need the utility methods, so we avoid full __init__
    api = object.__new__(TransportAPI)
    return api


class TestHaversineDistance:
    def setup_method(self):
        self.api = _make_api()

    def test_same_point_is_zero(self):
        assert self.api._haversine_distance(53.3498, -6.2603, 53.3498, -6.2603) == 0.0

    def test_known_distance(self):
        # Dublin Spire to O'Connell Bridge ~250m
        dist = self.api._haversine_distance(53.3498, -6.2603, 53.3474, -6.2591)
        assert 200 < dist < 400

    def test_symmetric(self):
        d1 = self.api._haversine_distance(53.0, -6.0, 54.0, -7.0)
        d2 = self.api._haversine_distance(54.0, -7.0, 53.0, -6.0)
        assert abs(d1 - d2) < 0.01

    def test_large_distance(self):
        # Dublin to London ~464 km
        dist = self.api._haversine_distance(53.3498, -6.2603, 51.5074, -0.1278)
        assert 450_000 < dist < 480_000


class TestAddDelayToTime:
    def setup_method(self):
        self.api = _make_api()

    def test_no_delay(self):
        time_str, dt = self.api._add_delay_to_time("10:00:00", 0)
        assert time_str == "10:00:00"

    def test_positive_delay(self):
        time_str, dt = self.api._add_delay_to_time("10:00:00", 120)
        assert time_str == "10:02:00"

    def test_negative_delay(self):
        time_str, dt = self.api._add_delay_to_time("10:00:00", -60)
        assert time_str == "09:59:00"

    def test_crosses_hour(self):
        time_str, dt = self.api._add_delay_to_time("09:59:00", 120)
        assert time_str == "10:01:00"


class TestSecondsUntilDeparture:
    def setup_method(self):
        self.api = _make_api()

    def test_future_departure(self):
        future = datetime.now() + timedelta(minutes=5)
        result = self.api._seconds_until_departure(future)
        assert 290 <= result <= 310

    def test_past_departure(self):
        past = datetime.now() - timedelta(minutes=5)
        result = self.api._seconds_until_departure(past)
        assert -310 <= result <= -290


class TestFormatSecondsToMinSec:
    def setup_method(self):
        self.api = _make_api()

    def test_positive(self):
        assert self.api._format_seconds_to_min_sec(125) == "2:05"

    def test_zero(self):
        assert self.api._format_seconds_to_min_sec(0) == "0:00"

    def test_negative(self):
        assert self.api._format_seconds_to_min_sec(-65) == "-1:05"

    def test_exact_minute(self):
        assert self.api._format_seconds_to_min_sec(60) == "1:00"


class TestFilterScheduleByTimeWindow:
    def setup_method(self):
        self.api = _make_api()

    def _make_entry(self, arrival_time, service_id="S1"):
        return {
            "arrival_time": arrival_time,
            "service_id": service_id,
            "calendar": {
                "monday": "1",
                "tuesday": "1",
                "wednesday": "1",
                "thursday": "1",
                "friday": "1",
                "saturday": "1",
                "sunday": "1",
                "start_date": "20240101",
                "end_date": "20261231",
            },
        }

    def test_includes_upcoming(self):
        now = datetime.now()
        future_time = (now + timedelta(minutes=10)).strftime("%H:%M:%S")
        entries = [self._make_entry(future_time)]
        result = self.api.filter_schedule_by_time_window(
            entries, window_past=60, window_future=3600, reference_time=now
        )
        assert len(result) == 1
        assert "seconds_until" in result[0]

    def test_excludes_far_future(self):
        now = datetime.now()
        far_future = (now + timedelta(hours=3)).strftime("%H:%M:%S")
        entries = [self._make_entry(far_future)]
        result = self.api.filter_schedule_by_time_window(
            entries, window_past=60, window_future=3600, reference_time=now
        )
        assert len(result) == 0

    def test_excludes_far_past(self):
        now = datetime.now()
        far_past = (now - timedelta(hours=1)).strftime("%H:%M:%S")
        entries = [self._make_entry(far_past)]
        result = self.api.filter_schedule_by_time_window(
            entries, window_past=600, window_future=3600, reference_time=now
        )
        assert len(result) == 0

    def test_includes_recent_past(self):
        now = datetime.now()
        recent_past = (now - timedelta(minutes=3)).strftime("%H:%M:%S")
        entries = [self._make_entry(recent_past)]
        result = self.api.filter_schedule_by_time_window(
            entries, window_past=600, window_future=3600, reference_time=now
        )
        assert len(result) == 1
        assert result[0]["seconds_until"] < 0

    def test_sorted_by_seconds_until(self):
        now = datetime.now()
        t1 = (now + timedelta(minutes=30)).strftime("%H:%M:%S")
        t2 = (now + timedelta(minutes=5)).strftime("%H:%M:%S")
        t3 = (now + timedelta(minutes=15)).strftime("%H:%M:%S")
        entries = [self._make_entry(t1), self._make_entry(t2), self._make_entry(t3)]
        result = self.api.filter_schedule_by_time_window(
            entries, window_past=60, window_future=3600, reference_time=now
        )
        assert len(result) == 3
        assert result[0]["seconds_until"] <= result[1]["seconds_until"] <= result[2]["seconds_until"]

    def test_inactive_service_excluded(self):
        now = datetime.now()
        t = (now + timedelta(minutes=5)).strftime("%H:%M:%S")
        entry = self._make_entry(t)
        # Disable all days
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            entry["calendar"][day] = "0"
        result = self.api.filter_schedule_by_time_window(
            [entry], window_past=60, window_future=3600, reference_time=now
        )
        assert len(result) == 0

    def test_expired_service_excluded(self):
        now = datetime.now()
        t = (now + timedelta(minutes=5)).strftime("%H:%M:%S")
        entry = self._make_entry(t)
        entry["calendar"]["start_date"] = "20200101"
        entry["calendar"]["end_date"] = "20200201"
        result = self.api.filter_schedule_by_time_window(
            [entry], window_past=60, window_future=3600, reference_time=now
        )
        assert len(result) == 0

    def test_handles_25_hour_time(self):
        """GTFS allows times >24:00:00 for trips running past midnight."""
        now = datetime.now().replace(hour=23, minute=50, second=0, microsecond=0)
        entries = [self._make_entry("25:10:00")]
        result = self.api.filter_schedule_by_time_window(
            entries, window_past=600, window_future=7200, reference_time=now
        )
        assert len(result) == 1
        assert result[0]["seconds_until"] > 0


class TestRealtimeWindowFiltering:
    def setup_method(self):
        self.api = _make_api()
        self.api.stop_info_lookup = {
            "S1": {"stop_code": "1234", "stop_name": "Main Street"}
        }

    def test_excludes_stale_realtime_departure(self):
        self.api.get_departures_for_stops = lambda stop_ids, use_stop_code=False: [
            {
                "trip_id": "T1",
                "stop_id": "S1",
                "route_id": "R1",
                "route_short_name": "15",
                "time_left": -25 * 60,
                "expected_departure_time": "10:00:00",
            }
        ]
        self.api.get_scheduled_times_for_route_stop = (
            lambda stop_id, use_stop_code=False: []
        )

        result = self.api.get_combined_departures_and_schedule(["S1"])

        assert result["live"] == []

    def test_keeps_recent_realtime_departure_in_grace_window(self):
        self.api.get_departures_for_stops = lambda stop_ids, use_stop_code=False: [
            {
                "trip_id": "T1",
                "stop_id": "S1",
                "route_id": "R1",
                "route_short_name": "15",
                "time_left": -2 * 60,
                "expected_departure_time": "10:00:00",
            }
        ]
        self.api.get_scheduled_times_for_route_stop = (
            lambda stop_id, use_stop_code=False: []
        )

        result = self.api.get_combined_departures_and_schedule(["S1"])

        assert len(result["live"]) == 1
        assert result["live"][0]["time_left"] == -2 * 60
        assert result["live"][0]["timing_status"] == "live"


class TestTimingStatus:
    def setup_method(self):
        self.api = _make_api()
        self.api.stop_info_lookup = {
            "S1": {"stop_code": "1234", "stop_name": "Main Street"}
        }

    def test_helper_returns_live_for_realtime_predictions(self):
        assert self.api._get_timing_status("realtime", False) == "live"

    def test_helper_returns_scheduled_fallback_for_realtime_without_eta(self):
        assert self.api._get_timing_status("realtime", True) == "scheduled_fallback"

    def test_helper_returns_schedule_only_for_timetable_entries(self):
        assert self.api._get_timing_status("schedule", True) == "schedule_only"

    def test_marks_schedule_only_entries_in_combined_output(self):
        self.api.get_departures_for_stops = lambda stop_ids, use_stop_code=False: []
        self.api.get_scheduled_times_for_route_stop = (
            lambda stop_id, use_stop_code=False: [
                {
                    "trip_id": "T1",
                    "route_id": "R1",
                    "route_short_name": "15",
                    "service_id": "SVC1",
                    "trip_headsign": "City Centre",
                    "trip_short_name": "15",
                    "arrival_time": (datetime.now() + timedelta(minutes=5)).strftime("%H:%M:%S"),
                    "departure_time": (datetime.now() + timedelta(minutes=5)).strftime("%H:%M:%S"),
                    "stop_sequence": 1,
                    "calendar": {
                        "monday": "1",
                        "tuesday": "1",
                        "wednesday": "1",
                        "thursday": "1",
                        "friday": "1",
                        "saturday": "1",
                        "sunday": "1",
                        "start_date": "20240101",
                        "end_date": "20261231",
                    },
                }
            ]
        )

        result = self.api.get_combined_departures_and_schedule(["S1"])

        assert len(result["live"]) == 1
        assert result["live"][0]["source"] == "schedule"
        assert result["live"][0]["timing_status"] == "schedule_only"

    def test_marks_scheduled_fallback_for_realtime_trip_without_prediction(self):
        self.api.get_departures_for_stops = lambda stop_ids, use_stop_code=False: [
            {
                "trip_id": "T1",
                "stop_id": "S1",
                "route_id": "R1",
                "route_short_name": "15",
                "trip_headsign": "City Centre",
                "service_id": "SVC1",
                "stop_sequence": 1,
                "stop_name": "Main Street",
                "stop_lat": "53.3498",
                "stop_lon": "-6.2603",
                "scheduled_departure_time": "",
                "delay": None,
                "expected_departure_time": None,
                "time_left": None,
                "start_time": "10:00:00",
                "start_date": "20260308",
                "schedule_relationship": "SCHEDULED",
                "arrival_str": "2026-03-08 10:00:00",
            }
        ]
        self.api.get_scheduled_times_for_route_stop = (
            lambda stop_id, use_stop_code=False: [
                {
                    "trip_id": "T1",
                    "route_id": "R1",
                    "route_short_name": "15",
                    "service_id": "SVC1",
                    "trip_headsign": "City Centre",
                    "trip_short_name": "15",
                    "arrival_time": (datetime.now() + timedelta(minutes=5)).strftime("%H:%M:%S"),
                    "departure_time": (datetime.now() + timedelta(minutes=5)).strftime("%H:%M:%S"),
                    "stop_sequence": 1,
                    "calendar": {
                        "monday": "1",
                        "tuesday": "1",
                        "wednesday": "1",
                        "thursday": "1",
                        "friday": "1",
                        "saturday": "1",
                        "sunday": "1",
                        "start_date": "20240101",
                        "end_date": "20261231",
                    },
                }
            ]
        )

        result = self.api.get_combined_departures_and_schedule(["S1"])

        assert len(result["live"]) == 1
        assert result["live"][0]["source"] == "realtime"
        assert result["live"][0]["used_scheduled_time"] is True
        assert result["live"][0]["timing_status"] == "scheduled_fallback"
