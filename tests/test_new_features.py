"""Tests for stop search and delay tracking."""

import sqlite3

import pytest


@pytest.fixture
def gtfs_dir(tmp_path):
    """Create minimal GTFS files."""
    (tmp_path / "trips.txt").write_text(
        "route_id,service_id,trip_id,trip_headsign,trip_short_name\n"
        "R1,S1,T1,City Centre,15\n"
    )
    (tmp_path / "routes.txt").write_text(
        "route_id,route_short_name,route_long_name\n"
        "R1,15,Route 15\n"
    )
    (tmp_path / "stops.txt").write_text(
        "stop_id,stop_code,stop_name,stop_lat,stop_lon\n"
        "S100,1234,Main Street,53.3498,-6.2603\n"
        "S200,5678,Parnell Square,53.3532,-6.2633\n"
        "S300,9012,Airport Terminal,53.4264,-6.2499\n"
    )
    (tmp_path / "stop_times.txt").write_text(
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,08:00:00,08:00:00,S100,1\n"
    )
    (tmp_path / "calendar.txt").write_text(
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "S1,1,1,1,1,1,0,0,20240101,20261231\n"
    )
    return str(tmp_path)


@pytest.fixture
def api(gtfs_dir, monkeypatch):
    """Create a TransportAPI with test GTFS data."""
    monkeypatch.setenv("TRANSPORT_API_KEY", "test-key")
    from gtfs_core.transport_api import TransportAPI

    return TransportAPI(api_key="test-key", gtfs_dir=gtfs_dir)


class TestSearchStops:
    def test_search_by_name(self, api):
        results = api.search_stops("Main")
        assert len(results) == 1
        assert results[0]["stop_id"] == "S100"
        assert results[0]["stop_name"] == "Main Street"

    def test_search_by_code(self, api):
        results = api.search_stops("5678")
        assert len(results) == 1
        assert results[0]["stop_id"] == "S200"

    def test_search_by_stop_id(self, api):
        results = api.search_stops("S300")
        assert len(results) == 1
        assert results[0]["stop_name"] == "Airport Terminal"

    def test_search_case_insensitive(self, api):
        results = api.search_stops("main street")
        assert len(results) == 1

    def test_search_partial(self, api):
        results = api.search_stops("arn")  # matches "Parnell"
        assert len(results) == 1
        assert results[0]["stop_name"] == "Parnell Square"

    def test_search_multiple_matches(self, api):
        results = api.search_stops("S")  # All 3 stops match (name or stop_id contains 's')
        assert len(results) == 3

    def test_search_no_results(self, api):
        results = api.search_stops("zzznomatch")
        assert len(results) == 0

    def test_search_limit(self, api):
        results = api.search_stops("S", limit=1)  # All stop_ids start with S
        assert len(results) == 1

    def test_search_empty_query(self, api):
        # Empty string matches everything
        results = api.search_stops("", limit=100)
        assert len(results) == 3


class TestDelayTracking:
    def test_init_creates_db(self, api, tmp_path):
        db_path = str(tmp_path / "test_delays.db")
        api.init_delay_tracking(db_path=db_path, tracked_stops=["S100"])
        conn = sqlite3.connect(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        assert ("delay_records",) in tables

    def test_record_and_query(self, api, tmp_path):
        db_path = str(tmp_path / "test_delays.db")
        api.init_delay_tracking(db_path=db_path, tracked_stops=["S100"])
        # Manually insert a record to test querying
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO delay_records (recorded_at, stop_id, route_id, route_short_name, trip_id, scheduled_time, delay_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026-03-08 10:00:00", "S100", "R1", "15", "T1", "10:00:00", 120),
        )
        conn.commit()
        conn.close()
        history = api.get_delay_history(stop_id="S100", days=30)
        assert len(history) == 1
        assert history[0]["delay_seconds"] == 120

    def test_delay_summary(self, api, tmp_path):
        db_path = str(tmp_path / "test_delays.db")
        api.init_delay_tracking(db_path=db_path, tracked_stops=["S100"])
        conn = sqlite3.connect(db_path)
        conn.executemany(
            "INSERT INTO delay_records (recorded_at, stop_id, route_id, route_short_name, trip_id, scheduled_time, delay_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("2026-03-08 10:00:00", "S100", "R1", "15", "T1", "10:00:00", 60),
                ("2026-03-08 10:05:00", "S100", "R1", "15", "T2", "10:05:00", 180),
            ],
        )
        conn.commit()
        conn.close()
        summary = api.get_delay_summary(stop_id="S100", days=30)
        assert len(summary) == 1
        assert summary[0]["sample_count"] == 2
        assert summary[0]["avg_delay"] == 120.0
        assert summary[0]["max_delay"] == 180

    def test_purge_old(self, api, tmp_path):
        db_path = str(tmp_path / "test_delays.db")
        api.init_delay_tracking(db_path=db_path, tracked_stops=["S100"])
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO delay_records (recorded_at, stop_id, route_id, route_short_name, trip_id, scheduled_time, delay_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2020-01-01 10:00:00", "S100", "R1", "15", "T1", "10:00:00", 60),
        )
        conn.commit()
        conn.close()
        deleted = api.purge_old_delays(keep_days=30)
        assert deleted == 1
        history = api.get_delay_history(days=9999)
        assert len(history) == 0

    def test_filter_by_route(self, api, tmp_path):
        db_path = str(tmp_path / "test_delays.db")
        api.init_delay_tracking(db_path=db_path, tracked_stops=["S100"])
        conn = sqlite3.connect(db_path)
        conn.executemany(
            "INSERT INTO delay_records (recorded_at, stop_id, route_id, route_short_name, trip_id, scheduled_time, delay_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("2026-03-08 10:00:00", "S100", "R1", "15", "T1", "10:00:00", 60),
                ("2026-03-08 10:00:00", "S100", "R2", "16A", "T2", "10:00:00", 90),
            ],
        )
        conn.commit()
        conn.close()
        history = api.get_delay_history(route_id="R1", days=30)
        assert len(history) == 1
        assert history[0]["route_id"] == "R1"


class TestGetTranslatedText:
    def test_returns_none_for_empty(self, api):
        assert api._get_translated_text(None) is None

    def test_returns_english_text(self, api):
        from google.transit import gtfs_realtime_pb2

        ts = gtfs_realtime_pb2.TranslatedString()
        t = ts.translation.add()
        t.language = "en"
        t.text = "Hello"
        t2 = ts.translation.add()
        t2.language = "ga"
        t2.text = "Dia duit"
        assert api._get_translated_text(ts) == "Hello"
