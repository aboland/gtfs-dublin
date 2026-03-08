"""Tests for DeparturesFormatter."""

import json

from gtfs_core.formatting import DeparturesFormatter


class TestFormatDeparturesOutput:
    def _make_departure(self, stop_name="Test Stop", route="15", time_left=300):
        return {
            "stop_name": stop_name,
            "route_short_name": route,
            "time_left": time_left,
            "scheduled_departure_time": "10:00:00",
            "expected_departure_time": "10:05:00",
            "vehicle": None,
            "vehicle_distance_to_stop_m": None,
        }

    def test_accepts_list(self, capsys):
        deps = [self._make_departure()]
        DeparturesFormatter.format_departures_output(deps)
        output = capsys.readouterr().out
        assert "Test Stop" in output
        assert "Route: 15" in output

    def test_accepts_json_string(self, capsys):
        deps = [self._make_departure()]
        DeparturesFormatter.format_departures_output(json.dumps(deps))
        output = capsys.readouterr().out
        assert "Test Stop" in output

    def test_groups_by_stop(self, capsys):
        deps = [
            self._make_departure(stop_name="Stop A", route="15"),
            self._make_departure(stop_name="Stop B", route="16A"),
        ]
        DeparturesFormatter.format_departures_output(deps)
        output = capsys.readouterr().out
        assert "Stop A" in output
        assert "Stop B" in output

    def test_sorted_by_time_left(self, capsys):
        deps = [
            self._make_departure(time_left=600, route="16A"),
            self._make_departure(time_left=120, route="15"),
        ]
        DeparturesFormatter.format_departures_output(deps)
        output = capsys.readouterr().out
        lines = [line for line in output.strip().split("\n") if line.startswith("Route:")]
        assert "15" in lines[0]
        assert "16A" in lines[1]

    def test_none_time_left(self, capsys):
        deps = [self._make_departure(time_left=None)]
        DeparturesFormatter.format_departures_output(deps)
        output = capsys.readouterr().out
        assert "N/A" in output

    def test_negative_time_left(self, capsys):
        deps = [self._make_departure(time_left=-90)]
        DeparturesFormatter.format_departures_output(deps)
        output = capsys.readouterr().out
        assert "-1:30" in output
