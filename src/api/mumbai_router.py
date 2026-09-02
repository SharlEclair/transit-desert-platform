"""
FastAPI Router for Mumbai Multimodal Transit Equity, Desert Analytics & 3-Stage Evaluation.
Serves:
- H3 Resolution-9 3D hexagon GeoJSON payloads with 5-stage Scenario switching:
  1. `legacy`: Legacy Network (Without Metro)
  2. `current_metro`: Current Network (Active Metro - 79 Stns)
  3. `future_2030`: 2030 Network (Full Expansion - 178 Stns)
  4. `delta_active`: Impact of Active Metro (TDI_legacy - TDI_current)
  5. `delta_future`: Impact of Future Expansion (TDI_current - TDI_2030)
- 3-Stage chronological comparison statistics and delta distributions
- High-fidelity Metro track alignments (MMRDA official colors) and Suburban Rail (#546E7A)
- Slum Cluster 2D polygon overlays and BMC Ward boundaries
"""

import os
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
import duckdb
import h3

MUMBAI_DB_PATH = "data/mumbai/processed/mumbai_equity.db"
METRO_STATIONS_GEOJSON_PATH = "data/mumbai/processed/mumbai_metro_stations_resolved.geojson"
METRO_TRACKS_STYLED_PATH = "data/mumbai/processed/mumbai_metro_tracks_styled.geojson"
SUBURBAN_RAIL_STYLED_PATH = "data/mumbai/processed/mumbai_suburban_rail_styled.geojson"
TRANSIT_LINES_GEOJSON_PATH = "data/mumbai/processed/mumbai_transit_lines.geojson"

router = APIRouter(prefix="/api/v1/mumbai", tags=["Mumbai Transit Equity & 3-Stage Evaluation"])


def get_mumbai_db():
    """Establish a thread-safe read-only connection to Mumbai DuckDB."""
    if not os.path.exists(MUMBAI_DB_PATH):
        raise HTTPException(
            status_code=503,
            detail=f"Mumbai database not found at '{MUMBAI_DB_PATH}'. Please run Mumbai pipeline first."
        )
    con = duckdb.connect(MUMBAI_DB_PATH, read_only=True)
    con.execute("LOAD spatial;")
    return con


# --- Pydantic Models ---

class MumbaiHealthResponse(BaseModel):
    status: str
    city: str = "Mumbai"
    database: str
    h3_total_cells: int
    slum_cluster_polygons: int
    travel_matrix_pairs: int
    travel_matrix_pairs_current: int
    travel_matrix_pairs_2030: int
    equity_scored_cells: int
    severe_transit_deserts: int
    timestamp: float


class MumbaiPOIModel(BaseModel):
    id: str
    name: str
    category: str
    lat: float
    lon: float
    reachable_h3_count: int
    reachable_h3_current: int
    reachable_h3_2030: int
    avg_travel_time_p50: float
    avg_travel_time_current: float
    avg_travel_time_2030: float
    avg_time_saved: float


class MumbaiDesertSummary(BaseModel):
    h3_index: str
    lat: float
    lon: float
    is_slum_cluster: int
    vulnerability_score: float
    accessibility_score: float
    tdi_score: float
    time_bkc: float
    time_kem: float
    time_iit: float
    time_pal: float


class MetricDistribution(BaseModel):
    metric: str
    min_val: float
    p25: float
    median: float
    mean: float
    p75: float
    p90: float
    max_val: float


class MumbaiStatsResponse(BaseModel):
    city: str = "Mumbai"
    total_h3_cells: int
    slum_cluster_cells: int
    severe_desert_cells: int
    avg_accessibility: float
    avg_tdi: float
    distributions: List[MetricDistribution]


class MumbaiComparisonStats(BaseModel):
    city: str = "Mumbai"
    total_cells: int
    slum_cells: int
    
    # 3-Stage Means
    baseline_mean_tdi: float          # Legacy (No Metro)
    current_metro_mean_tdi: float     # Active Metro (79 stns)
    future_2030_mean_tdi: float       # Full Expansion (178 stns)
    
    baseline_mean_accessibility: float
    current_metro_mean_accessibility: float
    future_2030_mean_accessibility: float
    
    # Deltas
    avg_delta_tdi_reduction: float     # Total reduction (legacy -> 2030)
    max_delta_tdi_reduction: float
    avg_delta_active_metro: float     # Stage 1 -> 2
    max_delta_active_metro: float
    avg_delta_future_expansion: float # Stage 2 -> 3
    max_delta_future_expansion: float
    
    avg_accessibility_gain: float     # Total gain
    avg_accessibility_gain_active: float
    avg_accessibility_gain_future: float
    
    # Slum Metrics
    slum_mean_tdi_current: float
    slum_mean_tdi_2030: float
    slum_mean_tdi_reduction: float
    slum_mean_tdi_active_reduction: float
    slum_mean_tdi_future_reduction: float
    
    pct_cells_improved: float
    pct_cells_improved_active: float
    pct_cells_improved_future: float


def unwrap_param(val, default=None):
    """Unwrap FastAPI Query object if function is invoked directly."""
    if hasattr(val, "default"):
        res = val.default
        return default if res is None or res is ... else res
    return val if val is not None else default


# --- Endpoints ---

@router.get("/health", response_model=MumbaiHealthResponse)
def health_check():
    """Verify Mumbai DuckDB database connectivity and scenario table inventory."""
    con = get_mumbai_db()
    try:
        tables = [t[0] for t in con.execute("SHOW TABLES;").fetchall()]
        
        h3_cnt = con.execute("SELECT COUNT(*) FROM mumbai_h3_grid;").fetchone()[0] if "mumbai_h3_grid" in tables else 0
        slum_cnt = con.execute("SELECT COUNT(*) FROM mumbai_slums;").fetchone()[0] if "mumbai_slums" in tables else 0
        mat_cnt = con.execute("SELECT COUNT(*) FROM mumbai_travel_matrix;").fetchone()[0] if "mumbai_travel_matrix" in tables else 0
        mat_cur_cnt = con.execute("SELECT COUNT(*) FROM mumbai_travel_matrix_current_metro;").fetchone()[0] if "mumbai_travel_matrix_current_metro" in tables else mat_cnt
        mat_2030_cnt = con.execute("SELECT COUNT(*) FROM mumbai_travel_matrix_2030;").fetchone()[0] if "mumbai_travel_matrix_2030" in tables else mat_cnt
        eq_cnt = con.execute("SELECT COUNT(*) FROM mumbai_equity_scores;").fetchone()[0] if "mumbai_equity_scores" in tables else 0
        des_cnt = con.execute("SELECT COUNT(*) FROM v_mumbai_transit_deserts;").fetchone()[0] if "v_mumbai_transit_deserts" in tables else 0
        
        return MumbaiHealthResponse(
            status="healthy",
            city="Mumbai",
            database=MUMBAI_DB_PATH,
            h3_total_cells=h3_cnt,
            slum_cluster_polygons=slum_cnt,
            travel_matrix_pairs=mat_cnt,
            travel_matrix_pairs_current=mat_cur_cnt,
            travel_matrix_pairs_2030=mat_2030_cnt,
            equity_scored_cells=eq_cnt,
            severe_transit_deserts=des_cnt,
            timestamp=time.time()
        )
    finally:
        con.close()


@router.get("/transit-deserts")
def get_mumbai_transit_deserts(
    scenario: str = Query("legacy", description="Scenario: 'legacy', 'current_metro', 'future_2030', 'delta_active', or 'delta_future'"),
    min_tdi: float = Query(0.0, ge=0.0, le=1.0, description="Minimum Transit Desert Index filter"),
    only_slums: bool = Query(False, description="Filter for Informal Settlement slum clusters only"),
    only_deserts: bool = Query(False, description="Filter for severe transit deserts (TDI >= 0.5)"),
    limit: int = Query(12000, ge=1, le=15000, description="Maximum number of hexagon records to return"),
    format: str = Query("geojson", description="Response format: 'geojson' or 'json'")
):
    """
    Retrieve H3 Resolution-9 hexagon polygons with Transit Desert Index and 3-Stage Multimodal Accessibility.
    Scenarios:
    - 'legacy': Legacy Network (Without Metro)
    - 'current_metro' / 'current': Current Network (Active Metro - 79 Stns)
    - 'future_2030' / '2030': 2030 Network (Full Expansion - 178 Stns)
    - 'delta_active' / 'delta_active_metro': Impact of Active Metro (TDI_legacy - TDI_current)
    - 'delta_future' / 'delta_future_expansion': Impact of Future Expansion (TDI_current - TDI_2030)
    - 'delta' / 'delta_total': Total Metro Impact (TDI_legacy - TDI_2030)
    """
    scenario_val = str(unwrap_param(scenario, "legacy")).lower()
    min_tdi_val = float(unwrap_param(min_tdi, 0.0))
    only_slums_val = bool(unwrap_param(only_slums, False))
    only_deserts_val = bool(unwrap_param(only_deserts, False))
    limit_val = int(unwrap_param(limit, 12000))
    format_val = str(unwrap_param(format, "geojson")).lower()

    con = get_mumbai_db()
    try:
        tables = [t[0] for t in con.execute("SHOW TABLES;").fetchall()]
        has_master = "v_mumbai_equity_master" in tables
        
        where_clauses = []
        params = []
        
        if only_slums_val:
            where_clauses.append("is_slum_cluster = 1")
            
        if only_deserts_val:
            if scenario_val in ("future_2030", "2030"):
                where_clauses.append("future_tdi >= 0.5")
            elif scenario_val in ("current_metro", "current"):
                where_clauses.append("current_tdi >= 0.5")
            else:
                where_clauses.append("legacy_tdi >= 0.5")
                
        if min_tdi_val > 0.0:
            if scenario_val in ("future_2030", "2030"):
                where_clauses.append("future_tdi >= ?")
                params.append(min_tdi_val)
            elif scenario_val in ("current_metro", "current"):
                where_clauses.append("current_tdi >= ?")
                params.append(min_tdi_val)
            else:
                where_clauses.append("legacy_tdi >= ?")
                params.append(min_tdi_val)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        
        # Determine order by based on scenario
        if scenario_val in ("delta_active", "delta_active_metro"):
            order_by_sql = "ORDER BY delta_active_metro DESC"
        elif scenario_val in ("delta_future", "delta_future_expansion"):
            order_by_sql = "ORDER BY delta_future_expansion DESC"
        elif scenario_val in ("delta", "delta_total"):
            order_by_sql = "ORDER BY delta_total_metro DESC"
        elif scenario_val in ("future_2030", "2030"):
            order_by_sql = "ORDER BY future_tdi DESC"
        elif scenario_val in ("current_metro", "current"):
            order_by_sql = "ORDER BY current_tdi DESC"
        else:
            order_by_sql = "ORDER BY legacy_tdi DESC"

        query = f"""
            SELECT 
                h3_index, centroid_lat, centroid_lng, is_slum_cluster, vulnerability_score,
                
                -- 3-Stage TDI
                legacy_tdi,
                current_tdi,
                future_tdi,
                
                -- 3-Stage Accessibility
                legacy_accessibility,
                current_accessibility,
                future_accessibility,
                
                -- Deltas
                delta_active_metro,
                delta_future_expansion,
                delta_total_metro,
                delta_accessibility_active,
                delta_accessibility_future,
                delta_accessibility_total,
                
                -- 3-Stage Travel Times
                legacy_time_bkc, current_time_bkc, future_time_bkc, time_saved_active_bkc, time_saved_future_bkc, time_saved_total_bkc,
                legacy_time_kem, current_time_kem, future_time_kem, time_saved_active_kem, time_saved_future_kem, time_saved_total_kem,
                legacy_time_iit, current_time_iit, future_time_iit, time_saved_active_iit, time_saved_future_iit, time_saved_total_iit,
                legacy_time_pal, current_time_pal, future_time_pal, time_saved_active_pal, time_saved_future_pal, time_saved_total_pal
            FROM v_mumbai_equity_master
            {where_sql}
            {order_by_sql}
            LIMIT {limit_val};
        """
        
        df = con.execute(query, params).fetchdf() if params else con.execute(query).fetchdf()
        
        if format_val == "json":
            return df.to_dict(orient="records")
            
        features = []
        for row in df.itertuples(index=False):
            lat_lng_boundary = h3.cell_to_boundary(row.h3_index)
            ring = [[lng, lat] for lat, lng in lat_lng_boundary]
            ring.append(ring[0])
            
            # Select primary display metrics for active scenario
            if scenario_val in ("future_2030", "2030"):
                disp_tdi = float(row.future_tdi)
                disp_acc = float(row.future_accessibility)
                disp_delta = float(row.delta_future_expansion)
                disp_tbkc = float(row.future_time_bkc)
                disp_tkem = float(row.future_time_kem)
                disp_tiit = float(row.future_time_iit)
                disp_tpal = float(row.future_time_pal)
            elif scenario_val in ("current_metro", "current"):
                disp_tdi = float(row.current_tdi)
                disp_acc = float(row.current_accessibility)
                disp_delta = float(row.delta_active_metro)
                disp_tbkc = float(row.current_time_bkc)
                disp_tkem = float(row.current_time_kem)
                disp_tiit = float(row.current_time_iit)
                disp_tpal = float(row.current_time_pal)
            elif scenario_val in ("delta_active", "delta_active_metro"):
                disp_tdi = float(row.current_tdi)
                disp_acc = float(row.current_accessibility)
                disp_delta = float(row.delta_active_metro)
                disp_tbkc = float(row.current_time_bkc)
                disp_tkem = float(row.current_time_kem)
                disp_tiit = float(row.current_time_iit)
                disp_tpal = float(row.current_time_pal)
            elif scenario_val in ("delta_future", "delta_future_expansion"):
                disp_tdi = float(row.future_tdi)
                disp_acc = float(row.future_accessibility)
                disp_delta = float(row.delta_future_expansion)
                disp_tbkc = float(row.future_time_bkc)
                disp_tkem = float(row.future_time_kem)
                disp_tiit = float(row.future_time_iit)
                disp_tpal = float(row.future_time_pal)
            elif scenario_val in ("delta", "delta_total"):
                disp_tdi = float(row.future_tdi)
                disp_acc = float(row.future_accessibility)
                disp_delta = float(row.delta_total_metro)
                disp_tbkc = float(row.future_time_bkc)
                disp_tkem = float(row.future_time_kem)
                disp_tiit = float(row.future_time_iit)
                disp_tpal = float(row.future_time_pal)
            else:
                # legacy
                disp_tdi = float(row.legacy_tdi)
                disp_acc = float(row.legacy_accessibility)
                disp_delta = 0.0
                disp_tbkc = float(row.legacy_time_bkc)
                disp_tkem = float(row.legacy_time_kem)
                disp_tiit = float(row.legacy_time_iit)
                disp_tpal = float(row.legacy_time_pal)

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [ring]
                },
                "properties": {
                    "h3_index": row.h3_index,
                    "centroid_lat": float(row.centroid_lat),
                    "centroid_lng": float(row.centroid_lng),
                    "is_slum": int(row.is_slum_cluster),
                    "vulnerability": float(row.vulnerability_score),
                    
                    # Display metrics (for current view)
                    "tdi": disp_tdi,
                    "accessibility": disp_acc,
                    "delta_tdi": disp_delta,
                    "tt_bkc": disp_tbkc,
                    "tt_kem": disp_tkem,
                    "tt_iit": disp_tiit,
                    "tt_pal": disp_tpal,
                    
                    # 3-Stage Comprehensive Metrics for Inspector
                    "legacy_tdi": float(row.legacy_tdi),
                    "current_tdi": float(row.current_tdi),
                    "future_tdi": float(row.future_tdi),
                    
                    "legacy_accessibility": float(row.legacy_accessibility),
                    "current_accessibility": float(row.current_accessibility),
                    "future_accessibility": float(row.future_accessibility),
                    
                    "delta_active_metro": float(row.delta_active_metro),
                    "delta_future_expansion": float(row.delta_future_expansion),
                    "delta_total_metro": float(row.delta_total_metro),
                    
                    "legacy_time_bkc": float(row.legacy_time_bkc),
                    "current_time_bkc": float(row.current_time_bkc),
                    "future_time_bkc": float(row.future_time_bkc),
                    "time_saved_active_bkc": float(row.time_saved_active_bkc),
                    "time_saved_future_bkc": float(row.time_saved_future_bkc),
                    
                    "legacy_time_kem": float(row.legacy_time_kem),
                    "current_time_kem": float(row.current_time_kem),
                    "future_time_kem": float(row.future_time_kem),
                    "time_saved_active_kem": float(row.time_saved_active_kem),
                    "time_saved_future_kem": float(row.time_saved_future_kem),
                    
                    "legacy_time_iit": float(row.legacy_time_iit),
                    "current_time_iit": float(row.current_time_iit),
                    "future_time_iit": float(row.future_time_iit),
                    "time_saved_active_iit": float(row.time_saved_active_iit),
                    "time_saved_future_iit": float(row.time_saved_future_iit),
                    
                    "legacy_time_pal": float(row.legacy_time_pal),
                    "current_time_pal": float(row.current_time_pal),
                    "future_time_pal": float(row.future_time_pal),
                    "time_saved_active_pal": float(row.time_saved_active_pal),
                    "time_saved_future_pal": float(row.time_saved_future_pal)
                }
            })
            
        return {
            "type": "FeatureCollection",
            "metadata": {
                "city": "Mumbai",
                "scenario": scenario_val,
                "count": len(features),
                "min_tdi": min_tdi_val,
                "only_slums": only_slums_val,
                "only_deserts": only_deserts_val
            },
            "features": features
        }
    finally:
        con.close()


@router.get("/deserts/top", response_model=List[MumbaiDesertSummary])
def get_mumbai_top_deserts(
    limit: int = Query(15, ge=1, le=100, description="Number of top priority desert cells to return"),
    only_slums: bool = Query(False, description="Filter for slum clusters only")
):
    """Retrieve top-ranked priority transit desert cells in Mumbai."""
    limit_val = int(unwrap_param(limit, 15))
    only_slums_val = bool(unwrap_param(only_slums, False))
    
    con = get_mumbai_db()
    try:
        where_sql = "WHERE is_slum_cluster = 1" if only_slums_val else ""
        query = f"""
            SELECT 
                h3_index,
                centroid_lat AS lat,
                centroid_lng AS lon,
                is_slum_cluster,
                vulnerability_score,
                legacy_accessibility AS accessibility_score,
                legacy_tdi AS tdi_score,
                legacy_time_bkc AS time_bkc,
                legacy_time_kem AS time_kem,
                legacy_time_iit AS time_iit,
                legacy_time_pal AS time_pal
            FROM v_mumbai_equity_master
            {where_sql}
            ORDER BY legacy_tdi DESC, legacy_accessibility ASC
            LIMIT ?;
        """
        df = con.execute(query, [limit_val]).fetchdf()
        return df.to_dict(orient="records")
    finally:
        con.close()


@router.get("/stats", response_model=MumbaiStatsResponse)
def get_mumbai_stats():
    """Retrieve statistical distribution percentiles and totals for Mumbai."""
    con = get_mumbai_db()
    try:
        totals = con.execute("""
            SELECT 
                COUNT(*) AS total_cells,
                SUM(CASE WHEN is_slum_cluster = 1 THEN 1 ELSE 0 END) AS slum_cells,
                SUM(CASE WHEN legacy_tdi >= 0.5 THEN 1 ELSE 0 END) AS severe_deserts,
                ROUND(AVG(legacy_accessibility), 4) AS avg_acc,
                ROUND(AVG(legacy_tdi), 4) AS avg_tdi
            FROM v_mumbai_equity_master;
        """).fetchone()
        
        dist_df = con.execute("""
            SELECT 
                'Transit Desert Index' AS metric,
                ROUND(MIN(legacy_tdi), 4) AS min_val,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY legacy_tdi), 4) AS p25,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY legacy_tdi), 4) AS median,
                ROUND(AVG(legacy_tdi), 4) AS mean,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY legacy_tdi), 4) AS p75,
                ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY legacy_tdi), 4) AS p90,
                ROUND(MAX(legacy_tdi), 4) AS max_val
            FROM v_mumbai_equity_master
            UNION ALL
            SELECT 
                'Accessibility Score' AS metric,
                ROUND(MIN(legacy_accessibility), 4) AS min_val,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY legacy_accessibility), 4) AS p25,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY legacy_accessibility), 4) AS median,
                ROUND(AVG(legacy_accessibility), 4) AS mean,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY legacy_accessibility), 4) AS p75,
                ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY legacy_accessibility), 4) AS p90,
                ROUND(MAX(legacy_accessibility), 4) AS max_val
            FROM v_mumbai_equity_master
            UNION ALL
            SELECT 
                'Vulnerability Score' AS metric,
                ROUND(MIN(vulnerability_score), 4) AS min_val,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY vulnerability_score), 4) AS p25,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY vulnerability_score), 4) AS median,
                ROUND(AVG(vulnerability_score), 4) AS mean,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY vulnerability_score), 4) AS p75,
                ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY vulnerability_score), 4) AS p90,
                ROUND(MAX(vulnerability_score), 4) AS max_val
            FROM v_mumbai_equity_master;
        """).fetchdf()
        
        return MumbaiStatsResponse(
            city="Mumbai",
            total_h3_cells=int(totals[0]),
            slum_cluster_cells=int(totals[1]),
            severe_desert_cells=int(totals[2]),
            avg_accessibility=float(totals[3]),
            avg_tdi=float(totals[4]),
            distributions=dist_df.to_dict(orient="records")
        )
    finally:
        con.close()


@router.get("/comparison-stats", response_model=MumbaiComparisonStats)
def get_mumbai_comparison_stats():
    """Retrieve statistical distribution of 3-Stage evaluations and delta equity gains."""
    con = get_mumbai_db()
    try:
        tables = [t[0] for t in con.execute("SHOW TABLES;").fetchall()]
        if "v_mumbai_equity_master" not in tables:
            raise HTTPException(status_code=404, detail="Master view `v_mumbai_equity_master` not materialized.")
            
        row = con.execute("""
            SELECT 
                COUNT(*) AS total_cells,
                SUM(CASE WHEN is_slum_cluster = 1 THEN 1 ELSE 0 END) AS slum_cells,
                
                -- Means
                ROUND(AVG(legacy_tdi), 4) AS base_tdi,
                ROUND(AVG(current_tdi), 4) AS cur_tdi,
                ROUND(AVG(future_tdi), 4) AS fut_tdi,
                
                ROUND(AVG(legacy_accessibility), 4) AS base_acc,
                ROUND(AVG(current_accessibility), 4) AS cur_acc,
                ROUND(AVG(future_accessibility), 4) AS fut_acc,
                
                -- Total Deltas (Legacy -> 2030)
                ROUND(AVG(delta_total_metro), 4) AS avg_delta_total,
                ROUND(MAX(delta_total_metro), 4) AS max_delta_total,
                
                -- Active Metro Deltas (Stage 1 -> 2)
                ROUND(AVG(delta_active_metro), 4) AS avg_delta_act,
                ROUND(MAX(delta_active_metro), 4) AS max_delta_act,
                
                -- Future Expansion Deltas (Stage 2 -> 3)
                ROUND(AVG(delta_future_expansion), 4) AS avg_delta_fut,
                ROUND(MAX(delta_future_expansion), 4) AS max_delta_fut,
                
                -- Accessibility Gains
                ROUND(AVG(delta_accessibility_total), 4) AS avg_acc_gain_tot,
                ROUND(AVG(delta_accessibility_active), 4) AS avg_acc_gain_act,
                ROUND(AVG(delta_accessibility_future), 4) AS avg_acc_gain_fut,
                
                -- Slum TDI Means
                ROUND(AVG(CASE WHEN is_slum_cluster = 1 THEN current_tdi ELSE NULL END), 4) AS slum_cur_tdi,
                ROUND(AVG(CASE WHEN is_slum_cluster = 1 THEN future_tdi ELSE NULL END), 4) AS slum_fut_tdi,
                ROUND(AVG(CASE WHEN is_slum_cluster = 1 THEN delta_total_metro ELSE NULL END), 4) AS slum_tot_red,
                ROUND(AVG(CASE WHEN is_slum_cluster = 1 THEN delta_active_metro ELSE NULL END), 4) AS slum_act_red,
                ROUND(AVG(CASE WHEN is_slum_cluster = 1 THEN delta_future_expansion ELSE NULL END), 4) AS slum_fut_red,
                
                -- Percentage Improved
                ROUND(SUM(CASE WHEN delta_total_metro > 0.0001 THEN 1.0 ELSE 0.0 END) / COUNT(*) * 100.0, 1) AS pct_tot,
                ROUND(SUM(CASE WHEN delta_active_metro > 0.0001 THEN 1.0 ELSE 0.0 END) / COUNT(*) * 100.0, 1) AS pct_act,
                ROUND(SUM(CASE WHEN delta_future_expansion > 0.0001 THEN 1.0 ELSE 0.0 END) / COUNT(*) * 100.0, 1) AS pct_fut
            FROM v_mumbai_equity_master;
        """).fetchone()
        
        return MumbaiComparisonStats(
            city="Mumbai",
            total_cells=int(row[0]),
            slum_cells=int(row[1]),
            
            baseline_mean_tdi=float(row[2]),
            current_metro_mean_tdi=float(row[3]),
            future_2030_mean_tdi=float(row[4]),
            
            baseline_mean_accessibility=float(row[5]),
            current_metro_mean_accessibility=float(row[6]),
            future_2030_mean_accessibility=float(row[7]),
            
            avg_delta_tdi_reduction=float(row[8]),
            max_delta_tdi_reduction=float(row[9]),
            avg_delta_active_metro=float(row[10]),
            max_delta_active_metro=float(row[11]),
            avg_delta_future_expansion=float(row[12]),
            max_delta_future_expansion=float(row[13]),
            
            avg_accessibility_gain=float(row[14]),
            avg_accessibility_gain_active=float(row[15]),
            avg_accessibility_gain_future=float(row[16]),
            
            slum_mean_tdi_current=float(row[17]),
            slum_mean_tdi_2030=float(row[18]),
            slum_mean_tdi_reduction=float(row[19]),
            slum_mean_tdi_active_reduction=float(row[20]),
            slum_mean_tdi_future_reduction=float(row[21]),
            
            pct_cells_improved=float(row[22]),
            pct_cells_improved_active=float(row[23]),
            pct_cells_improved_future=float(row[24])
        )
    finally:
        con.close()


@router.get("/pois", response_model=List[MumbaiPOIModel])
def get_mumbai_pois():
    """Retrieve reachability and commute times for Strategic Mega-Hubs across scenarios."""
    pois_def = [
        {"id": "BKC", "name": "Bandra Kurla Complex (BKC)", "category": "Employment", "lat": 19.0657, "lon": 72.8682},
        {"id": "KEM_HOSPITAL", "name": "KEM Hospital Parel", "category": "Healthcare", "lat": 19.0028, "lon": 72.8415},
        {"id": "IIT_BOMBAY", "name": "IIT Bombay Powai", "category": "Education", "lat": 19.1334, "lon": 72.9133},
        {"id": "PALLADIUM", "name": "Palladium Lower Parel", "category": "Commercial", "lat": 18.9940, "lon": 72.8248}
    ]
    con = get_mumbai_db()
    try:
        tables = [t[0] for t in con.execute("SHOW TABLES;").fetchall()]
        results = []
        for p in pois_def:
            leg_stats = con.execute("""
                SELECT COUNT(*), ROUND(AVG(travel_time_p50), 1)
                FROM mumbai_travel_matrix WHERE destination_id = ?;
            """, [p["id"]]).fetchone() if "mumbai_travel_matrix" in tables else (0, 0.0)
            
            cur_stats = con.execute("""
                SELECT COUNT(*), ROUND(AVG(travel_time_p50), 1)
                FROM mumbai_travel_matrix_current_metro WHERE destination_id = ?;
            """, [p["id"]]).fetchone() if "mumbai_travel_matrix_current_metro" in tables else leg_stats
            
            fut_stats = con.execute("""
                SELECT COUNT(*), ROUND(AVG(travel_time_p50), 1)
                FROM mumbai_travel_matrix_2030 WHERE destination_id = ?;
            """, [p["id"]]).fetchone() if "mumbai_travel_matrix_2030" in tables else cur_stats
            
            l_cnt = leg_stats[0] if leg_stats else 0
            c_cnt = cur_stats[0] if cur_stats else l_cnt
            f_cnt = fut_stats[0] if fut_stats else c_cnt
            
            l_time = float(leg_stats[1]) if leg_stats and leg_stats[1] is not None else 0.0
            c_time = float(cur_stats[1]) if cur_stats and cur_stats[1] is not None else l_time
            f_time = float(fut_stats[1]) if fut_stats and fut_stats[1] is not None else c_time
            saved = round(l_time - f_time, 1) if (l_time > 0 and f_time > 0) else 0.0
            
            results.append(MumbaiPOIModel(
                id=p["id"],
                name=p["name"],
                category=p["category"],
                lat=p["lat"],
                lon=p["lon"],
                reachable_h3_count=l_cnt,
                reachable_h3_current=c_cnt,
                reachable_h3_2030=f_cnt,
                avg_travel_time_p50=l_time,
                avg_travel_time_current=c_time,
                avg_travel_time_2030=f_time,
                avg_time_saved=saved
            ))
        return results
    finally:
        con.close()


@router.get("/metro-lines")
def get_mumbai_metro_lines_geojson():
    """Serve Mumbai Metro corridor physical track geometries with MMRDA colors."""
    if os.path.exists(METRO_TRACKS_STYLED_PATH):
        with open(METRO_TRACKS_STYLED_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    elif os.path.exists(TRANSIT_LINES_GEOJSON_PATH):
        with open(TRANSIT_LINES_GEOJSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        metro_features = [feat for feat in data.get("features", []) if feat.get("properties", {}).get("transit_type") == "metro"]
        return {"type": "FeatureCollection", "features": metro_features}
    else:
        raise HTTPException(status_code=404, detail="Metro tracks geojson not found.")


@router.get("/suburban-rail")
def get_mumbai_suburban_rail_geojson():
    """Serve Mumbai Suburban Rail physical track geometries styled with #546E7A Dark Slate."""
    if os.path.exists(SUBURBAN_RAIL_STYLED_PATH):
        with open(SUBURBAN_RAIL_STYLED_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        raise HTTPException(status_code=404, detail="Suburban rail tracks geojson not found.")


@router.get("/transit-lines")
def get_mumbai_transit_lines_geojson():
    """Serve Mumbai Combined Transit Network (Metro + Suburban Rail) physical geometries."""
    if os.path.exists(TRANSIT_LINES_GEOJSON_PATH):
        with open(TRANSIT_LINES_GEOJSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        raise HTTPException(status_code=404, detail="Combined transit lines geojson not found.")


@router.get("/metro-stations")
def get_mumbai_metro_stations_geojson():
    """Serve all 178 resolved 2030 Mumbai Metro stations as GeoJSON."""
    if not os.path.exists(METRO_STATIONS_GEOJSON_PATH):
        raise HTTPException(status_code=404, detail="Metro stations geojson not found.")
    with open(METRO_STATIONS_GEOJSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/slums")
def get_mumbai_slums_geojson(limit: int = Query(3000, ge=1, le=5000)):
    """Serve flattened 2D slum cluster boundary polygons as standard GeoJSON."""
    con = get_mumbai_db()
    try:
        limit_val = int(unwrap_param(limit, 3000))
        query = f"""
            SELECT polyno, ST_AsGeoJSON(geom) AS geojson_geom
            FROM mumbai_slums
            LIMIT {limit_val};
        """
        df = con.execute(query).fetchdf()
        
        features = []
        for row in df.itertuples(index=False):
            features.append({
                "type": "Feature",
                "geometry": json.loads(row.geojson_geom),
                "properties": {
                    "polyno": int(row.polyno),
                    "type": "Informal Settlement"
                }
            })
            
        return {
            "type": "FeatureCollection",
            "metadata": {"count": len(features)},
            "features": features
        }
    finally:
        con.close()


@router.get("/wards")
def get_mumbai_wards_geojson():
    """Serve BMC administrative ward polygons as standard GeoJSON."""
    con = get_mumbai_db()
    try:
        query = """
            SELECT gid, ward_name, ST_AsGeoJSON(geom) AS geojson_geom
            FROM mumbai_bmc_wards;
        """
        df = con.execute(query).fetchdf()
        
        features = []
        for row in df.itertuples(index=False):
            features.append({
                "type": "Feature",
                "geometry": json.loads(row.geojson_geom),
                "properties": {
                    "gid": int(row.gid),
                    "ward_name": row.ward_name
                }
            })
            
        return {
            "type": "FeatureCollection",
            "metadata": {"count": len(features)},
            "features": features
        }
    finally:
        con.close()
