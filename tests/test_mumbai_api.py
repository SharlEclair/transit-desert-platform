"""
Integration & Unit Test Suite for Mumbai Transit Equity API Endpoints.
Validates:
- /api/v1/cities: Discovery endpoint listing both Melbourne and Mumbai
- /api/v1/mumbai/health: Table inventories and health status
- /api/v1/mumbai/transit-deserts: GeoJSON FeatureCollection generation with 3D polygon rings and properties
- /api/v1/mumbai/deserts/top: Top-priority desert ranking
- /api/v1/mumbai/stats: Metric distributions and percentiles
- /api/v1/mumbai/pois: Strategic Mega-Hubs metadata
- /api/v1/mumbai/slums: Slum cluster 2D boundary polygons
- /api/v1/mumbai/wards: BMC administrative ward boundaries
"""

import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_cities_endpoint():
    """Verify city discovery endpoint lists Melbourne and Mumbai with correct metadata."""
    response = client.get("/api/v1/cities")
    assert response.status_code == 200
    data = response.json()
    assert "cities" in data
    city_ids = [c["id"] for c in data["cities"]]
    assert "melbourne" in city_ids
    assert "mumbai" in city_ids
    
    mumbai_meta = next(c for c in data["cities"] if c["id"] == "mumbai")
    assert mumbai_meta["name"] == "Greater Mumbai"
    assert mumbai_meta["total_h3_cells"] == 10891
    assert mumbai_meta["cutoff_time_min"] == 90

def test_mumbai_health():
    """Verify Mumbai health check endpoint returns 200 with populated database stats."""
    response = client.get("/api/v1/mumbai/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["city"] == "Mumbai"
    assert data["h3_total_cells"] == 10891
    assert data["slum_cluster_polygons"] == 2542
    assert data["travel_matrix_pairs"] >= 20000
    assert data["equity_scored_cells"] == 10891
    assert data["severe_transit_deserts"] >= 150

def test_mumbai_transit_deserts_geojson():
    """Verify GeoJSON FeatureCollection generation for Mumbai."""
    response = client.get("/api/v1/mumbai/transit-deserts?limit=50")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert "metadata" in data
    assert len(data["features"]) == 50
    
    # Validate feature schema
    feat = data["features"][0]
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "Polygon"
    assert len(feat["geometry"]["coordinates"][0]) == 7  # H3 hexagon closed ring (6 vertices + 1 closed)
    
    props = feat["properties"]
    assert "h3_index" in props
    assert "accessibility" in props
    assert "vulnerability" in props
    assert "tdi" in props
    assert "tt_bkc" in props
    assert "tt_kem" in props
    assert "tt_iit" in props
    assert "tt_pal" in props

def test_mumbai_transit_deserts_filtering():
    """Verify filtering parameters: min_tdi, only_slums, only_deserts."""
    # Only slums
    resp_slums = client.get("/api/v1/mumbai/transit-deserts?only_slums=true&limit=1000")
    assert resp_slums.status_code == 200
    slums_data = resp_slums.json()
    assert all(f["properties"]["is_slum"] == 1 for f in slums_data["features"])
    assert len(slums_data["features"]) == 360  # Total slum cells in Mumbai
    
    # Only severe deserts (TDI >= 0.5)
    resp_deserts = client.get("/api/v1/mumbai/transit-deserts?only_deserts=true&limit=1000")
    assert resp_deserts.status_code == 200
    deserts_data = resp_deserts.json()
    assert all(f["properties"]["tdi"] >= 0.5 for f in deserts_data["features"])
    assert len(deserts_data["features"]) >= 150

def test_mumbai_top_deserts():
    """Verify Top Deserts leaderboard endpoint."""
    response = client.get("/api/v1/mumbai/deserts/top?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10
    # Must be sorted descending by TDI
    tdi_values = [d["tdi_score"] for d in data]
    assert tdi_values == sorted(tdi_values, reverse=True)
    assert tdi_values[0] >= 0.90

def test_mumbai_stats():
    """Verify Mumbai statistical distributions endpoint."""
    response = client.get("/api/v1/mumbai/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_h3_cells"] == 10891
    assert data["slum_cluster_cells"] == 360
    assert data["severe_desert_cells"] >= 150
    assert len(data["distributions"]) == 3
    assert len(data["distributions"]) == 3
    
    metrics = [d["metric"] for d in data["distributions"]]
    assert "Transit Desert Index" in metrics
    assert "Accessibility Score" in metrics
    assert "Vulnerability Score" in metrics

def test_mumbai_pois():
    """Verify Strategic Mega-Hubs endpoint."""
    response = client.get("/api/v1/mumbai/pois")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4
    poi_ids = [p["id"] for p in data]
    assert "BKC" in poi_ids
    assert "KEM_HOSPITAL" in poi_ids
    assert "IIT_BOMBAY" in poi_ids
    assert "PALLADIUM" in poi_ids
    
    for p in data:
        assert p["reachable_h3_count"] > 5000
        assert p["avg_travel_time_p50"] > 0

def test_mumbai_slums_geojson():
    """Verify slum polygon overlay endpoint."""
    response = client.get("/api/v1/mumbai/slums?limit=100")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 100
    assert data["features"][0]["geometry"]["type"] in ["Polygon", "MultiPolygon"]

def test_mumbai_wards_geojson():
    """Verify BMC administrative ward boundary polygons endpoint."""
    response = client.get("/api/v1/mumbai/wards")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 24
    ward_names = [f["properties"]["ward_name"] for f in data["features"]]
    assert "A" in ward_names
    assert "H/E" in ward_names
