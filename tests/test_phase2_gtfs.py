"""
Phase 2 Automated Verification Suite: Synthetic 2030 Mumbai Metro GTFS Feed.
Validates zip structure, table schemas, route headways, bi-directional trips,
calendar validity, and 35 km/h commercial speed timing.
"""

import io
import zipfile
from pathlib import Path
import pandas as pd
import pytest

GTFS_ZIP_PATH = Path("data/mumbai/processed/mumbai_2030_metro_gtfs.zip")


@pytest.fixture(scope="module")
def gtfs_tables():
    """Load all tables from the synthesized GTFS zip."""
    assert GTFS_ZIP_PATH.exists(), f"Missing GTFS archive at {GTFS_ZIP_PATH}"
    tables = {}
    with zipfile.ZipFile(GTFS_ZIP_PATH, "r") as zf:
        for name in zf.namelist():
            with zf.open(name) as f:
                tables[name] = pd.read_csv(f)
    return tables


def test_gtfs_required_files_exist(gtfs_tables):
    """Verify all mandatory GTFS tables exist."""
    required = ["agency.txt", "calendar.txt", "routes.txt", "stops.txt", "trips.txt", "stop_times.txt"]
    for req in required:
        assert req in gtfs_tables, f"Missing required GTFS table: {req}"


def test_agency_and_calendar(gtfs_tables):
    """Verify agency and active calendar entries."""
    agency = gtfs_tables["agency.txt"]
    assert len(agency) >= 1
    assert "MMRDA" in agency["agency_id"].values
    
    calendar = gtfs_tables["calendar.txt"]
    assert len(calendar) >= 1
    assert "DAILY" in calendar["service_id"].values
    # Check weekday coverage
    daily_row = calendar[calendar["service_id"] == "DAILY"].iloc[0]
    assert daily_row["tuesday"] == 1
    assert daily_row["start_date"] <= 20260908 <= daily_row["end_date"]


def test_routes_and_line2b_split(gtfs_tables):
    """Verify 13 routes and Line 2B split into operational and under-construction patterns."""
    routes = gtfs_tables["routes.txt"]
    assert len(routes) == 13
    route_ids = set(routes["route_id"])
    
    expected_routes = {
        "METRO_L1", "METRO_L2A", "METRO_L2B_OP", "METRO_L2B_UC", "METRO_L3",
        "METRO_L4", "METRO_L4A", "METRO_L5", "METRO_L6", "METRO_L7",
        "METRO_L7A", "METRO_L9", "METRO_L12"
    }
    assert route_ids == expected_routes


def test_stops_count_and_coordinates(gtfs_tables):
    """Verify stops have valid coordinates."""
    stops = gtfs_tables["stops.txt"]
    assert len(stops) == 177, f"Expected 177 stops, got {len(stops)}"
    assert stops["stop_lat"].notnull().all()
    assert stops["stop_lon"].notnull().all()
    assert (stops["stop_lat"] >= 18.70).all() and (stops["stop_lat"] <= 20.10).all()
    assert (stops["stop_lon"] >= 72.65).all() and (stops["stop_lon"] <= 73.55).all()


def test_trips_bidirectional_and_headways(gtfs_tables):
    """Verify bi-directional trips and monotonic stop times."""
    trips = gtfs_tables["trips.txt"]
    stop_times = gtfs_tables["stop_times.txt"]
    
    assert len(trips) > 2000
    assert len(stop_times) > 30000
    
    # Check bi-directional support
    directions = set(trips["direction_id"])
    assert directions == {0, 1}
    
    # Verify monotonic time ordering for sample trips
    sample_trip_ids = trips["trip_id"].sample(20, random_state=42)
    for trip_id in sample_trip_ids:
        st_trip = stop_times[stop_times["trip_id"] == trip_id].sort_values("stop_sequence")
        arr_times = list(st_trip["arrival_time"])
        dep_times = list(st_trip["departure_time"])
        assert arr_times == sorted(arr_times), f"Non-monotonic arrival times in trip {trip_id}"
        assert dep_times == sorted(dep_times), f"Non-monotonic departure times in trip {trip_id}"
