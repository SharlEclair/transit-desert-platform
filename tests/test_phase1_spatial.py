"""
Phase 1 Automated Verification Suite: Spatial Geometry & Metro Station Interpolation.
Validates Overpass track extraction, unified station count (178 stations), UTM 43N coordinate snapping,
and WGS84 bounds integrity.
"""

import json
from pathlib import Path
import geopandas as gpd
import pytest

TRANSIT_LINES_PATH = Path("data/mumbai/processed/mumbai_transit_lines.geojson")
STATIONS_RAW_PATH = Path("data/mumbai/raw/metro_network/mumbai_metro_stations.json")
STATIONS_GEOJSON_PATH = Path("data/mumbai/processed/mumbai_metro_stations_resolved.geojson")

BBOX = (72.65, 18.70, 73.55, 20.10)  # [min_lon, min_lat, max_lon, max_lat]


def test_transit_lines_geojson_exists_and_valid():
    """Verify extracted transit lines file and styled vector tracks."""
    assert TRANSIT_LINES_PATH.exists(), f"Missing {TRANSIT_LINES_PATH}"
    gdf = gpd.read_file(str(TRANSIT_LINES_PATH))
    assert len(gdf) > 0, f"Expected features, got {len(gdf)}"
    assert gdf.crs.to_epsg() == 4326, f"Expected EPSG:4326, got {gdf.crs}"
    
    # Verify styled layers exist
    assert Path("data/mumbai/processed/mumbai_metro_tracks_styled.geojson").exists()
    assert Path("data/mumbai/processed/mumbai_suburban_rail_styled.geojson").exists()


def test_unified_raw_metro_stations_count():
    """Verify raw parsed station JSON has exactly 178 records (79 operational + 99 under construction)."""
    assert STATIONS_RAW_PATH.exists(), f"Missing {STATIONS_RAW_PATH}"
    with open(STATIONS_RAW_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    meta = data["metadata"]
    assert meta["total_stations"] == 178
    assert meta["operational_stations"] == 79
    assert meta["under_construction_stations"] == 99
    assert len(data["stations"]) == 178


def test_resolved_metro_stations_interpolation_and_bounds():
    """Verify all 177 stations in resolved GeoJSON have non-null WGS84 coordinates in bounds."""
    assert STATIONS_GEOJSON_PATH.exists(), f"Missing {STATIONS_GEOJSON_PATH}"
    with open(STATIONS_GEOJSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    features = data["features"]
    assert len(features) == 177
    
    # Check lines present
    expected_lines = {"1", "2A", "2B", "3", "4", "4A", "5", "6", "7", "7A", "9", "12"}
    actual_lines = set(f["properties"]["line_id"] for f in features)
    assert actual_lines == expected_lines, f"Line mismatch: {actual_lines ^ expected_lines}"
    
    for f in features:
        lon, lat = f["geometry"]["coordinates"]
        name = f["properties"]["station_name"]
        assert lat is not None and lon is not None, f"Station {name} has null coords"
        assert BBOX[1] <= lat <= BBOX[3], f"Station {name} lat {lat} outside Mumbai bounds"
        assert BBOX[0] <= lon <= BBOX[2], f"Station {name} lon {lon} outside Mumbai bounds"


def test_resolved_stations_geojson():
    """Verify resolved GeoJSON FeatureCollection."""
    assert STATIONS_GEOJSON_PATH.exists(), f"Missing {STATIONS_GEOJSON_PATH}"
    gdf = gpd.read_file(str(STATIONS_GEOJSON_PATH))
    assert len(gdf) == 177
    assert gdf.crs.to_epsg() == 4326
    assert (gdf.geometry.geom_type == "Point").all()
