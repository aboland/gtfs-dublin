# Home Assistant Integration

This guide explains how to add Dublin bus stop departure data to Home Assistant using the REST API.

## Prerequisites

- The `transport-api` service running and accessible from your Home Assistant instance
- Your stop IDs (find them at [Transport for Ireland](https://www.transportforireland.ie/) or in the GTFS `stops.txt` file)

## Setup

### 1. Deploy the API

Run the API server using Docker Compose on your network:

```sh
# Set your environment variables
export TRANSPORT_API_KEY=your-api-key
export STOPS=8220DB002437,8220DB002438

docker compose up -d transport-api
```

The API will be available at `http://<your-server-ip>:8000`.

### 2. Add REST Sensor to Home Assistant

Add the following to your `configuration.yaml` (or in a `sensor:` package file):

```yaml
rest:
  - resource: http://<your-server-ip>:8000/departures?stops=8220DB002437,8220DB002438
    scan_interval: 60
    sensor:
      - name: "Bus Departures"
        value_template: "{{ value_json.live | length }}"
        unit_of_measurement: "departures"
        json_attributes_path: "$"
        json_attributes:
          - timestamp
          - live
```

Replace `<your-server-ip>` with the IP/hostname of the machine running the API, and update the stop IDs to your own.

### 3. Create Template Sensors for Individual Stops

To break out departures per stop, add template sensors:

```yaml
template:
  - sensor:
      - name: "Next Bus - Main Street"
        state: >
          {% set deps = state_attr('sensor.bus_departures', 'live') %}
          {% if deps %}
            {% set stop = deps | selectattr('stop_id', 'eq', '8220DB002437') | sort(attribute='time_left') | list %}
            {% if stop %}
              {{ (stop[0].time_left / 60) | round(0) }}
            {% else %}
              No data
            {% endif %}
          {% else %}
            Unavailable
          {% endif %}
        unit_of_measurement: "min"
        icon: mdi:bus-clock
        attributes:
          route: >
            {% set deps = state_attr('sensor.bus_departures', 'live') %}
            {% if deps %}
              {% set stop = deps | selectattr('stop_id', 'eq', '8220DB002437') | sort(attribute='time_left') | list %}
              {{ stop[0].route_short_name if stop else 'N/A' }}
            {% endif %}
          headsign: >
            {% set deps = state_attr('sensor.bus_departures', 'live') %}
            {% if deps %}
              {% set stop = deps | selectattr('stop_id', 'eq', '8220DB002437') | sort(attribute='time_left') | list %}
              {{ stop[0].trip_headsign if stop else 'N/A' }}
            {% endif %}
          expected: >
            {% set deps = state_attr('sensor.bus_departures', 'live') %}
            {% if deps %}
              {% set stop = deps | selectattr('stop_id', 'eq', '8220DB002437') | sort(attribute='time_left') | list %}
              {{ stop[0].expected_departure_time if stop else 'N/A' }}
            {% endif %}
```

### 4. Next N Departures for a Stop

To show the next 3 upcoming buses at a stop:

```yaml
template:
  - sensor:
      - name: "Upcoming Buses - Main Street"
        state: >
          {% set deps = state_attr('sensor.bus_departures', 'live') %}
          {% if deps %}
            {% set stop = deps | selectattr('stop_id', 'eq', '8220DB002437') | selectattr('time_left', 'defined') | sort(attribute='time_left') | list %}
            {% if stop %}
              {% for d in stop[:3] %}
                {{ d.route_short_name }} in {{ (d.time_left / 60) | round(0) }}min{{ ', ' if not loop.last }}
              {% endfor %}
            {% else %}
              No buses
            {% endif %}
          {% else %}
            Unavailable
          {% endif %}
        icon: mdi:bus-multiple
```

### 5. Filter by Route

To track a specific route (e.g. route `15`):

```yaml
template:
  - sensor:
      - name: "Next 15 Bus"
        state: >
          {% set deps = state_attr('sensor.bus_departures', 'live') %}
          {% if deps %}
            {% set buses = deps | selectattr('stop_id', 'eq', '8220DB002437') | selectattr('route_short_name', 'eq', '15') | sort(attribute='time_left') | list %}
            {% if buses %}
              {{ (buses[0].time_left / 60) | round(0) }}
            {% else %}
              No buses
            {% endif %}
          {% else %}
            Unavailable
          {% endif %}
        unit_of_measurement: "min"
        icon: mdi:bus
```

## Dashboard Card

A simple entities card showing your bus sensors:

```yaml
type: entities
title: Bus Departures
entities:
  - entity: sensor.next_bus_main_street
    name: Next Bus
  - entity: sensor.next_15_bus
    name: Next 15
  - entity: sensor.upcoming_buses_main_street
    name: Upcoming
```

For a richer display, consider the [flex-table-card](https://github.com/custom-cards/flex-table-card) from HACS:

```yaml
type: custom:flex-table-card
title: Bus Departures
entities:
  include: sensor.bus_departures
columns:
  - name: Route
    data: live
    modify: x.route_short_name
  - name: Headsign
    data: live
    modify: x.trip_headsign
  - name: In (min)
    data: live
    modify: Math.round(x.time_left / 60)
  - name: Expected
    data: live
    modify: x.expected_departure_time || 'Scheduled'
  - name: Source
    data: live
    modify: x.source
```

## Automation Example

Trigger an automation when your bus is approaching:

```yaml
automation:
  - alias: "Bus Arriving Soon"
    trigger:
      - platform: numeric_state
        entity_id: sensor.next_bus_main_street
        below: 5
    condition:
      - condition: time
        after: "07:00:00"
        before: "09:00:00"
        weekday:
          - mon
          - tue
          - wed
          - thu
          - fri
    action:
      - service: notify.mobile_app
        data:
          title: "Bus Alert"
          message: >
            {{ state_attr('sensor.next_bus_main_street', 'route') }} bus
            to {{ state_attr('sensor.next_bus_main_street', 'headsign') }}
            arriving in {{ states('sensor.next_bus_main_street') }} minutes
```

## Troubleshooting

- **Sensor shows "Unavailable"**: Check that the API is reachable from HA (`curl http://<ip>:8000/health`)
- **Empty departures**: Verify your stop IDs are correct and that there are active services at the current time
- **Stale data**: The REST sensor polls every 60 seconds by default. The API caches upstream GTFS-RT data for 20 seconds.

## Finding Stop IDs

1. Visit [Transport for Ireland](https://www.transportforireland.ie/) and search for your stop
2. The stop ID is in the URL or stop details page
3. Alternatively, check `GTFS_Realtime/stops.txt` for stop IDs and codes
4. You can use stop codes instead of stop IDs by adding `&use_stop_code=true` to the API URL
5. To get departures for a single route: `http://<ip>:8000/departures/route/15?stop=8220DB002437`
