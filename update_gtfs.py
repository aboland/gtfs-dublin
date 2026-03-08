#!/usr/bin/env python3
"""
GTFS Data Update Script
Downloads the latest GTFS data from Transport for Ireland
"""

import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from gtfs_core.gtfs_loader import download_latest_gtfs  # noqa: E402


def main():
    """Download and update GTFS data"""
    print("🔄 Downloading latest GTFS data...")

    try:
        download_latest_gtfs()
        print("✅ GTFS data updated successfully!")
        print("📁 Files updated in GTFS_Realtime/ directory")
    except Exception as e:
        print(f"❌ Error updating GTFS data: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
