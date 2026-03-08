"""Tests for GTFSDataLoader parsing logic."""

import pytest

from gtfs_core.gtfs_loader import GTFSDataError, GTFSDataLoader


@pytest.fixture
def gtfs_dir(tmp_path):
    """Create a minimal set of GTFS files for testing."""
    # trips.txt
    (tmp_path / "trips.txt").write_text(
        "route_id,service_id,trip_id,trip_headsign,trip_short_name\n"
        "R1,S1,T1,City Centre,15\n"
        "R2,S1,T2,Airport,16A\n"
        "R1,S1,T3,Northbound,15\n"
    )
    # routes.txt
    (tmp_path / "routes.txt").write_text(
        "route_id,route_short_name,route_long_name\n"
        "R1,15,Route 15\n"
        "R2,16A,Route 16A\n"
    )
    # stops.txt
    (tmp_path / "stops.txt").write_text(
        "stop_id,stop_code,stop_name,stop_lat,stop_lon\n"
        "S100,1234,Main Street,53.3498,-6.2603\n"
        "S200,5678,Airport Terminal,53.4264,-6.2499\n"
    )
    # stop_times.txt
    (tmp_path / "stop_times.txt").write_text(
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,08:00:00,08:00:00,S100,1\n"
        "T1,08:15:00,08:15:00,S200,2\n"
        "T2,09:00:00,09:00:00,S100,1\n"
        "T3,10:00:00,10:00:00,S100,1\n"
    )
    # calendar.txt
    (tmp_path / "calendar.txt").write_text(
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "S1,1,1,1,1,1,0,0,20240101,20261231\n"
    )
    return str(tmp_path)


class TestGTFSDataLoaderParsing:
    def test_loads_successfully(self, gtfs_dir):
        loader = GTFSDataLoader(gtfs_dir)
        assert loader._loaded

    def test_trip_info_lookup(self, gtfs_dir):
        loader = GTFSDataLoader(gtfs_dir)
        assert "T1" in loader.trip_info_lookup
        assert loader.trip_info_lookup["T1"]["route_id"] == "R1"
        assert loader.trip_info_lookup["T1"]["service_id"] == "S1"
        assert loader.trip_info_lookup["T1"]["trip_headsign"] == "City Centre"
        assert loader.trip_info_lookup["T2"]["route_id"] == "R2"

    def test_trip_headsign_lookup(self, gtfs_dir):
        loader = GTFSDataLoader(gtfs_dir)
        assert loader.trip_headsign_lookup[("T1", "R1")] == "City Centre"
        assert loader.trip_headsign_lookup[("T2", "R2")] == "Airport"

    def test_route_short_name_lookup(self, gtfs_dir):
        loader = GTFSDataLoader(gtfs_dir)
        assert loader.route_short_name_lookup["R1"] == "15"
        assert loader.route_short_name_lookup["R2"] == "16A"

    def test_stop_info_lookup(self, gtfs_dir):
        loader = GTFSDataLoader(gtfs_dir)
        assert "S100" in loader.stop_info_lookup
        assert loader.stop_info_lookup["S100"]["stop_name"] == "Main Street"
        assert loader.stop_info_lookup["S100"]["stop_code"] == "1234"

    def test_stop_code_to_id(self, gtfs_dir):
        loader = GTFSDataLoader(gtfs_dir)
        assert loader.stop_code_to_id["1234"] == "S100"
        assert loader.stop_code_to_id["5678"] == "S200"

    def test_stop_times_by_stop(self, gtfs_dir):
        loader = GTFSDataLoader(gtfs_dir)
        assert "S100" in loader.stop_times_by_stop
        # T1, T2, and T3 all stop at S100
        assert len(loader.stop_times_by_stop["S100"]) == 3
        assert "S200" in loader.stop_times_by_stop
        assert len(loader.stop_times_by_stop["S200"]) == 1

    def test_departure_lookup(self, gtfs_dir):
        loader = GTFSDataLoader(gtfs_dir)
        assert loader.departure_lookup[("T1", "S100")] == "08:00:00"
        assert loader.departure_lookup[("T1", "S200")] == "08:15:00"

    def test_calendar_lookup(self, gtfs_dir):
        loader = GTFSDataLoader(gtfs_dir)
        assert "S1" in loader.calendar_lookup
        assert loader.calendar_lookup["S1"]["monday"] == "1"
        assert loader.calendar_lookup["S1"]["saturday"] == "0"

    def test_focus_stops_filters(self, gtfs_dir):
        loader = GTFSDataLoader(gtfs_dir, focus_stops=["S100"])
        # Only S100 stop_times should be loaded
        assert "S100" in loader.stop_times_by_stop
        assert "S200" not in loader.stop_times_by_stop
        # departure_lookup should only have S100 entries
        assert ("T1", "S100") in loader.departure_lookup
        assert ("T1", "S200") not in loader.departure_lookup

    def test_missing_file_raises(self, tmp_path):
        # Empty directory — no GTFS files
        with pytest.raises(GTFSDataError):
            GTFSDataLoader(str(tmp_path))


class TestGTFSDataLoaderEdgeCases:
    def test_empty_trip_headsign(self, tmp_path):
        (tmp_path / "trips.txt").write_text(
            "route_id,service_id,trip_id,trip_headsign,trip_short_name\n"
            "R1,S1,T1,,\n"
        )
        (tmp_path / "routes.txt").write_text(
            "route_id,route_short_name,route_long_name\n"
            "R1,15,Route 15\n"
        )
        (tmp_path / "stops.txt").write_text(
            "stop_id,stop_code,stop_name,stop_lat,stop_lon\n"
        )
        (tmp_path / "stop_times.txt").write_text(
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        )
        (tmp_path / "calendar.txt").write_text(
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "S1,1,1,1,1,1,0,0,20240101,20261231\n"
        )
        loader = GTFSDataLoader(str(tmp_path))
        assert loader.trip_info_lookup["T1"]["trip_headsign"] == ""
