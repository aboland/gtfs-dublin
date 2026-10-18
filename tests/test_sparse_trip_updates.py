from datetime import datetime
from types import SimpleNamespace

import pytest
from google.transit import gtfs_realtime_pb2 as pb

from gtfs_core.transport_api import TransportAPI


def make_api():
    api = object.__new__(TransportAPI)
    api.stop_times_by_stop = {'target': [{'trip_id': 'trip', 'stop_sequence': '11'}]}
    api.departure_lookup = {('trip', 'target'): '15:09:15'}
    return api


def trip_update():
    update = pb.TripUpdate()
    update.trip.trip_id = 'trip'
    update.trip.route_id = 'route'
    update.trip.start_date = '20261018'
    return update


def add(update, sequence, delay=None, relationship=None):
    stop = update.stop_time_update.add()
    stop.stop_sequence = sequence
    stop.stop_id = f'stop-{sequence}'
    if delay is not None:
        stop.departure.delay = delay
    if relationship is not None:
        stop.schedule_relationship = relationship
    return stop


def test_15a_sparse_update_reaches_stop_11():
    api, update = make_api(), trip_update()
    add(update, 1, 0)
    add(update, 2, 65)
    results = list(api._updates_for_requested_stops(update, ['target']))
    assert len(results) == 1
    stop, propagated = results[0]
    assert stop.stop_id == 'target'
    assert stop.departure.delay == 65
    assert propagated is True


def test_zero_delay_is_still_a_live_prediction():
    api, update = make_api(), trip_update()
    add(update, 1, 0)
    add(update, 8, -1)
    add(update, 9, 0)
    add(update, 22, -1)
    assert list(api._updates_for_requested_stops(update, ['target']))[0][0].departure.delay == 0


@pytest.mark.parametrize('relationship', [pb.TripUpdate.StopTimeUpdate.NO_DATA, pb.TripUpdate.StopTimeUpdate.SCHEDULED])
def test_no_data_or_empty_scheduled_update_clears_previous_delay(relationship):
    api, update = make_api(), trip_update()
    add(update, 1, 65)
    add(update, 8, relationship=relationship)
    assert list(api._updates_for_requested_stops(update, ['target'])) == []


def test_skipped_intermediate_stop_preserves_delay():
    api, update = make_api(), trip_update()
    add(update, 1, 65)
    add(update, 8, relationship=pb.TripUpdate.StopTimeUpdate.SKIPPED)
    assert list(api._updates_for_requested_stops(update, ['target']))[0][0].departure.delay == 65


def test_later_update_does_not_predict_earlier_stop():
    api, update = make_api(), trip_update()
    add(update, 22, 65)
    assert list(api._updates_for_requested_stops(update, ['target'])) == []


def test_arrival_delay_and_trip_delay_are_supported():
    api, update = make_api(), trip_update()
    update.delay = 30
    assert list(api._updates_for_requested_stops(update, ['target']))[0][0].departure.delay == 30
    add(update, 2).arrival.delay = 65
    assert list(api._updates_for_requested_stops(update, ['target']))[0][0].departure.delay == 65


def test_explicit_stop_update_wins_and_sequence_only_updates_match():
    api, update = make_api(), trip_update()
    add(update, 1, 65)
    target = add(update, 11, 120)
    target.ClearField('stop_id')
    results = list(api._updates_for_requested_stops(update, ['target']))
    assert len(results) == 1
    assert results[0][0].departure.delay == 120
    assert results[0][1] is False


def test_propagated_delay_produces_real_departure_prediction():
    api, update = make_api(), trip_update()
    add(update, 2, 65)
    feed = pb.FeedMessage()
    feed.header.gtfs_realtime_version = '2.0'
    entity = feed.entity.add()
    entity.id = 'test'
    entity.trip_update.CopyFrom(update)
    api._fetch_trip_updates = lambda: feed
    api._fetch_vehicle_positions = lambda: {}
    api.route_short_name_lookup = {'route': '15A'}
    api.trip_headsign_lookup = {}
    api.trip_service_lookup = {}
    api.stop_info_lookup = {}
    api._now = lambda: datetime(2026, 10, 18, 15, 3)
    result = api.get_departures_for_stops(['target'])[0]
    assert result['expected_departure_time'] == '15:10:20'
    assert result['time_left'] == 440
    assert result['prediction_source'] == 'propagated_delay'
