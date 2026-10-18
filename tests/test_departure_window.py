from datetime import datetime

import pytest

from gtfs_core.transport_api import TransportAPI


@pytest.mark.parametrize("window, expected", [(None, ["soon", "later"]), (3600, ["soon"])])
def test_combined_departures_default_covers_two_hours(window, expected):
    api = object.__new__(TransportAPI)
    api._now = lambda: datetime(2026, 10, 18, 21, 45)
    api.stop_info_lookup = {}
    api.get_departures_for_stops = lambda *args, **kwargs: []
    api.get_scheduled_times_for_route_stop = lambda **kwargs: [
        {
            "trip_id": trip,
            "arrival_time": departure,
            "departure_time": departure,
            "calendar": {
                "start_date": "20261018", "end_date": "20261018", "sunday": "1"
            },
        }
        for trip, departure in [("soon", "22:20:45"), ("later", "22:50:45"), ("outside", "23:45:01")]
    ]
    kwargs = {} if window is None else {"window_future": window}
    rows = api.get_combined_departures_and_schedule(["stop"], **kwargs)["live"]
    assert [row["trip_id"] for row in rows] == expected
    assert all(row["timing_status"] == "schedule_only" for row in rows)
    assert all(row["used_scheduled_time"] for row in rows)
