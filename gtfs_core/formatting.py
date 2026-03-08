class DeparturesFormatter:
    @staticmethod
    def print_combined_schedule(combined):
        """
        Pretty-print the combined departures and schedule dict from get_combined_departures_and_schedule.
        Handles both the old (dict of stop_id -> list) and new (dict with 'timestamp' and 'live') formats.
        Safely handles None values for all fields.
        """
        # Detect new format (timestamp + live)
        if "live" in combined:
            entries = combined["live"]
            print(f"Timestamp: {combined.get('timestamp', '')}")
        else:
            # Old format: flatten all entries
            entries = []
            for stop_id in combined:
                entries.extend(combined[stop_id])
        if not entries:
            print("No departures found.")
            return
        # Group by stop for pretty output
        from collections import defaultdict

        grouped = defaultdict(list)
        for entry in entries:
            stop_name = entry.get("stop_name", "Unknown Stop")
            grouped[stop_name].append(entry)
        for stop_name in sorted(grouped.keys()):
            stop_entries = grouped[stop_name]
            stop_id = stop_entries[0].get("stop_id", "")
            stop_code = stop_entries[0].get("stop_code", "")
            print(f"\n=== {stop_name} (ID: {stop_id}, Code: {stop_code}) ===")
            sorted_entries = sorted(
                stop_entries,
                key=lambda d: (
                    d.get("time_left") is None,
                    d.get("time_left", float("inf")),
                ),
            )
            print(
                f"{'Type':<10} {'Bus (trip_id)':<20} {'Headsign':<25} {'Route':<8} {'Scheduled':<10} {'Live':<10} {'In (min:sec)':<12} {'Distance':<10} {'Last Update':<20}"
            )
            print("-" * 135)
            for entry in sorted_entries:
                src = str(entry.get("source", "") or "")
                bus_id = str(entry.get("vehicle_id", "") or "")
                trip_id = str(entry.get("trip_id", "") or "")
                bus_trip = f"{bus_id} ({trip_id})" if bus_id else trip_id
                headsign = str(entry.get("trip_headsign", "") or "")
                route_short = str(entry.get("route_short_name", "") or "")
                scheduled = entry.get("scheduled_departure_time", "")
                live = entry.get("expected_departure_time", "")
                # For scheduled-only rows, show arrival_time in Scheduled column if scheduled_departure_time is empty
                if not scheduled:
                    scheduled = entry.get("arrival_time", "")
                time_left = entry.get("time_left")
                if time_left is not None:
                    minsec = f"{abs(time_left)//60}:{abs(time_left)%60:02d}"
                    if time_left < 0:
                        minsec = f"-{minsec}"
                else:
                    minsec = "N/A"
                # Vehicle distance
                vehicle_distance = entry.get("vehicle_distance_to_stop_m")
                if vehicle_distance is not None:
                    distance_str = f"{vehicle_distance:.0f}m"
                else:
                    distance_str = ""
                # Last update
                last_update = entry.get("vehicle_timestamp")
                if (
                    last_update is None
                    and entry.get("vehicle")
                    and entry["vehicle"].get("timestamp")
                ):
                    last_update = entry["vehicle"]["timestamp"]
                if last_update is not None:
                    try:
                        from datetime import datetime

                        last_update_str = datetime.fromtimestamp(
                            float(last_update)
                        ).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        last_update_str = str(last_update)
                else:
                    last_update_str = ""
                print(
                    f"{src:<10} {bus_trip:<20} {headsign:<25} {route_short:<8} {scheduled:<10} {live:<10} {minsec:<12} {distance_str:<10} {last_update_str:<20}"
                )

    @staticmethod
    def format_departures_output(json_output):
        """
        Takes the JSON output from get_departures_for_stops and prints a formatted summary.
        Groups by stop name, sorts by time_left ascending.
        """
        import json
        from collections import defaultdict

        departures = json.loads(json_output)
        grouped = defaultdict(list)
        for dep in departures:
            stop_name = dep.get("stop_name", "Unknown Stop")
            grouped[stop_name].append(dep)
        for stop in sorted(grouped.keys()):
            print(f"\n=== {stop} ===")
            # Sort by time_left (None last)
            sorted_deps = sorted(
                grouped[stop],
                key=lambda d: (
                    d["time_left"] is None,
                    d["time_left"] if d["time_left"] is not None else float("inf"),
                ),
            )
            for dep in sorted_deps:
                route = dep.get("route_short_name", "")
                time_left = dep.get("time_left")
                if time_left is not None:
                    minsec = f"{abs(time_left)//60}:{abs(time_left)%60:02d}"
                    if time_left < 0:
                        minsec = f"-{minsec}"
                else:
                    minsec = "N/A"
                scheduled_departure = dep.get("scheduled_departure_time", "N/A")
                expected_departure = dep.get("expected_departure_time", "N/A")
                vehicle_distance = dep.get("vehicle_distance_to_stop_m")
                vehicle_distance_str = (
                    f"{vehicle_distance:.0f}m"
                    if vehicle_distance is not None
                    else "N/A"
                )
                vehicle_updated = None
                if dep.get("vehicle") and dep["vehicle"].get("timestamp"):
                    from datetime import datetime

                    ts = dep["vehicle"]["timestamp"]
                    vehicle_updated = datetime.fromtimestamp(ts).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                else:
                    vehicle_updated = "N/A"
                print(
                    f"Route: {route} | Time Left: {minsec} | Scheduled: {scheduled_departure} | Expected: {expected_departure} | Vehicle Distance: {vehicle_distance_str} | Vehicle Updated: {vehicle_updated}"
                )

    @staticmethod
    def print_tidy_schedule(filtered_schedule):
        print(
            f"{'Bus':<10} {'Headsign':<25} {'No.':<10} {'Arrival':<10} {'Departure':<10} {'In (min:sec)':<12} {'Trip ID':<15} {'Route ID':<10} {'Service ID':<10}"
        )
        print("-" * 120)
        for entry in filtered_schedule:
            bus = entry.get("trip_id", "")
            headsign = entry.get("trip_headsign", "")
            route_short = entry.get("route_short_name", "")
            arrival = entry.get("arrival_time", "")
            departure = entry.get("departure_time", "")
            seconds_until = entry.get("seconds_until")
            trip_id = entry.get("trip_id", "")
            route_id = entry.get("route_id", "")
            service_id = entry.get("service_id", "")
            if seconds_until is not None:
                minsec = f"{abs(seconds_until)//60}:{abs(seconds_until)%60:02d}"
                if seconds_until < 0:
                    minsec = f"-{minsec}"
            else:
                minsec = "N/A"
            print(
                f"{bus:<10} {headsign:<25} {route_short:<10} {arrival:<10} {departure:<10} {minsec:<12} {trip_id:<15} {route_id:<10} {service_id:<10}"
            )
