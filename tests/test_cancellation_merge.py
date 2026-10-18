from datetime import datetime

import pytest
from google.transit import gtfs_realtime_pb2 as pb

from gtfs_core.transport_api import TransportAPI


def make_api():
    api = object.__new__(TransportAPI)
    api._now = lambda: datetime(2026, 10, 18, 15, 20)
    api.stop_info_lookup = {}
    api.stop_times_by_stop = {'target': [{'trip_id': 'trip', 'stop_sequence': '18'}]}
    api.get_departures_for_stops = lambda *args, **kwargs: []
    api.get_scheduled_times_for_route_stop = lambda **kwargs: [
        {'trip_id': 'trip', 'route_id': 's2', 'route_short_name': 'S2',
         'arrival_time': '15:48:15', 'departure_time': '15:48:15',
         'seconds_until': 1695},
        {'trip_id': 'following', 'route_id': 's2', 'route_short_name': 'S2',
         'arrival_time': '16:08:45', 'departure_time': '16:08:45',
         'seconds_until': 2925},
    ]
    api.filter_schedule_by_time_window = lambda schedule, **kwargs: schedule
    feed = pb.FeedMessage()
    feed.header.gtfs_realtime_version = '2.0'
    entity = feed.entity.add()
    entity.id = 'cancelled'
    entity.trip_update.trip.trip_id = 'trip'
    api._trip_updates_cache = feed
    return api, entity.trip_update


@pytest.mark.parametrize('whole_trip', [False, True])
def test_cancelled_departure_does_not_return_as_schedule_only(whole_trip):
    api, update = make_api()
    if whole_trip:
        update.trip.schedule_relationship = pb.TripDescriptor.CANCELED
    else:
        stop = update.stop_time_update.add()
        stop.stop_id = 'target'
        stop.stop_sequence = 18
        stop.schedule_relationship = pb.TripUpdate.StopTimeUpdate.SKIPPED
    rows = api.get_combined_departures_and_schedule(['target'])['live']
    assert rows[0]['timing_status'] == 'cancelled'
    assert rows[0]['cancelled'] is True
    assert rows[0]['expected_departure_time'] is None
    assert rows[0]['time_left'] == 1695
    assert rows[1]['timing_status'] == 'schedule_only'


def test_skipped_different_stop_does_not_cancel_target():
    api, update = make_api()
    stop = update.stop_time_update.add()
    stop.stop_id = 'other'
    stop.schedule_relationship = pb.TripUpdate.StopTimeUpdate.SKIPPED
    assert api.get_combined_departures_and_schedule(['target'])['live'][0]['timing_status'] == 'schedule_only'


def test_sequence_only_skipped_update_matches_target():
    api, update = make_api()
    stop = update.stop_time_update.add()
    stop.stop_sequence = 18
    stop.schedule_relationship = pb.TripUpdate.StopTimeUpdate.SKIPPED
    assert api.get_combined_departures_and_schedule(['target'])['live'][0]['timing_status'] == 'cancelled'


def test_no_data_does_not_mean_cancelled():
    api, update = make_api()
    stop = update.stop_time_update.add()
    stop.stop_id = 'target'
    stop.schedule_relationship = pb.TripUpdate.StopTimeUpdate.NO_DATA
    assert api.get_combined_departures_and_schedule(['target'])['live'][0]['timing_status'] == 'schedule_only'
