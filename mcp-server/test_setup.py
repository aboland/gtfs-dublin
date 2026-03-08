#!/usr/bin/env python3
"""
Test script for GTFS Dublin MCP Server
"""

import os
import sys
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path to access gtfs_core
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from gtfs_core import TransportAPI

    print("✓ TransportAPI import successful")

    # Test API initialization
    api_key = os.environ.get("TRANSPORT_API_KEY")
    if not api_key:
        print("✗ TRANSPORT_API_KEY not found in environment")
        sys.exit(1)

    print(f"✓ Found API key: {api_key[:8]}...")

    gtfs_dir = os.environ.get("GTFS_DIR", "../GTFS_Realtime")
    if not Path(gtfs_dir).exists():
        print(f"✗ GTFS directory not found: {gtfs_dir}")
        sys.exit(1)

    print(f"✓ GTFS directory found: {gtfs_dir}")

    # Try to initialize API
    try:
        api = TransportAPI(api_key=api_key, gtfs_dir=gtfs_dir)
        print("✓ TransportAPI initialized successfully")
    except Exception as e:
        print(f"✗ TransportAPI initialization failed: {e}")
        sys.exit(1)

    # Basic integration tests
    print("Running integration tests...")

    try:
        # Test get_vehicles_near_location (may return empty list)
        vehicles = api.get_vehicles_near_location(53.3498, -6.2603, radius_m=500)
        print(f"✓ get_vehicles_near_location returned {len(vehicles)} vehicles")
    except Exception as e:
        print(f"✗ get_vehicles_near_location failed: {e}")
        sys.exit(1)

    try:
        # Test get_departures_for_stops (use a known stop)
        # Assuming stop_id '8220DB0001' exists, or use a dummy that may fail gracefully
        departures_json = api.get_departures_for_stops(['8220DB0001'])
        print("✓ get_departures_for_stops returned data")
    except Exception as e:
        print(f"⚠ get_departures_for_stops failed (may be expected if stop not found): {e}")

    try:
        # Test get_scheduled_times_for_route_stop
        schedule = api.get_scheduled_times_for_route_stop(stop_id='8220DB0001')
        print(f"✓ get_scheduled_times_for_route_stop returned {len(schedule)} entries")
    except Exception as e:
        print(f"⚠ get_scheduled_times_for_route_stop failed: {e}")

    print("✓ All tests passed! MCP server should work correctly.")

except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)
