"""
Phase 3 Automated Verification Suite: 2030 R5 Matrix, Equity Materialization & Comparison API.
Validates DuckDB 2030 tables, v_mumbai_equity_comparison view, delta_tdi calculations,
and FastAPI 2030 scenario endpoints.
"""

from pathlib import Path
import duckdb
import pytest
from fastapi.testclient import TestClient
from src.api.main import app

DB_PATH = Path("data/mumbai/processed/mumbai_equity.db")
client = TestClient(app)


def test_mumbai_2030_tables_and_view_exist():
    """Verify DuckDB 3-stage tables and master comparison view exist."""
    assert DB_PATH.exists(), f"Database not found at {DB_PATH}"
    con = duckdb.connect(str(DB_PATH), read_only=True)
    con.execute("LOAD spatial;")
    
    tables = [t[0] for t in con.execute("SHOW TABLES;").fetchall()]
    assert "mumbai_travel_matrix" in tables
    assert "mumbai_travel_matrix_current_metro" in tables
    assert "mumbai_travel_matrix_2030" in tables
    assert "mumbai_equity_legacy" in tables
    assert "mumbai_equity_current" in tables
    assert "mumbai_equity_2030" in tables
    assert "v_mumbai_equity_master" in tables
    assert "v_mumbai_equity_comparison" in tables
    con.close()


def test_mumbai_equity_2030_materialization():
    """Verify mumbai_equity_2030 table counts and valid value distributions."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    
    count_2030 = con.execute("SELECT COUNT(*) FROM mumbai_equity_2030;").fetchone()[0]
    assert count_2030 == 10891, f"Expected 10,891 cells, got {count_2030}"
    
    stats = con.execute("""
        SELECT 
            MIN(tdi_score), MAX(tdi_score), AVG(tdi_score),
            MIN(accessibility_score), MAX(accessibility_score), AVG(accessibility_score)
        FROM mumbai_equity_2030;
    """).fetchone()
    
    min_tdi, max_tdi, avg_tdi, min_acc, max_acc, avg_acc = stats
    assert 0.0 <= min_tdi <= max_tdi <= 1.0
    assert 0.0 <= min_acc <= max_acc <= 1.0
    assert avg_acc > 0.0
    con.close()


def test_comparison_view_delta_reduction():
    """Verify v_mumbai_equity_master demonstrates progressive TDI reduction across stages."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    
    comp_stats = con.execute("""
        SELECT 
            AVG(legacy_tdi),
            AVG(current_tdi),
            AVG(future_tdi),
            AVG(delta_active_metro),
            AVG(delta_future_expansion),
            AVG(delta_total_metro),
            MAX(delta_total_metro)
        FROM v_mumbai_equity_master;
    """).fetchone()
    
    leg_tdi, cur_tdi, fut_tdi, d_act, d_fut, d_tot, max_d = comp_stats
    
    # Mathematical progression assertions
    assert cur_tdi <= leg_tdi, f"Expected active metro TDI ({cur_tdi}) <= legacy ({leg_tdi})"
    assert fut_tdi <= cur_tdi, f"Expected 2030 TDI ({fut_tdi}) <= active ({cur_tdi})"
    assert d_act >= 0.0, f"Expected positive delta active metro, got {d_act}"
    assert d_fut >= 0.0, f"Expected positive delta future expansion, got {d_fut}"
    assert d_tot >= 0.0, f"Expected positive total delta, got {d_tot}"
    assert max_d > 0.01, f"Expected significant max total delta, got {max_d}"
    con.close()


def test_api_mumbai_scenarios():
    """Verify FastAPI /api/v1/mumbai/transit-deserts for all 5 chronological scenarios."""
    scenarios = ["legacy", "current_metro", "future_2030", "delta_active", "delta_future"]
    for scenario in scenarios:
        res = client.get(f"/api/v1/mumbai/transit-deserts?scenario={scenario}&limit=100")
        assert res.status_code == 200, f"Scenario {scenario} returned {res.status_code}"
        data = res.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) > 0
        props = data["features"][0]["properties"]
        assert "h3_index" in props
        assert "tdi" in props
        assert "legacy_tdi" in props
        assert "current_tdi" in props
        assert "future_tdi" in props
        assert "delta_active_metro" in props
        assert "delta_future_expansion" in props


def test_api_mumbai_comparison_stats():
    """Verify /api/v1/mumbai/comparison-stats endpoint with 3-stage metrics."""
    res = client.get("/api/v1/mumbai/comparison-stats")
    assert res.status_code == 200
    data = res.json()
    assert data["city"] == "Mumbai"
    assert data["total_cells"] == 10891
    assert data["avg_delta_tdi_reduction"] >= 0.0
    assert data["avg_delta_active_metro"] >= 0.0
    assert data["avg_delta_future_expansion"] >= 0.0
    assert data["pct_cells_improved"] > 0.0


def test_api_mumbai_metro_layers():
    """Verify /api/v1/mumbai/metro-lines, /suburban-rail, and /metro-stations endpoints."""
    res_lines = client.get("/api/v1/mumbai/metro-lines")
    assert res_lines.status_code == 200
    data_lines = res_lines.json()
    assert data_lines["type"] == "FeatureCollection"
    assert len(data_lines["features"]) > 0
    
    res_rail = client.get("/api/v1/mumbai/suburban-rail")
    assert res_rail.status_code == 200
    data_rail = res_rail.json()
    assert data_rail["type"] == "FeatureCollection"
    assert len(data_rail["features"]) > 0
    
    res_stations = client.get("/api/v1/mumbai/metro-stations")
    assert res_stations.status_code == 200
    data_stations = res_stations.json()
    assert data_stations["type"] == "FeatureCollection"
    assert len(data_stations["features"]) == 177
