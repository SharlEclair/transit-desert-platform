"""
FastAPI Backend for Multimodal Transit Desert & Equity Platform (Melbourne).
Connects to DuckDB (`data/processed/transit_equity.db`) in read-only mode to serve:
- GeoJSON 3D H3 Hexagon features for Transit Deserts
- Aggregated Suburb Priority Leaderboards
- Statistical Distributions & System Inventory
- Strategic POIs Metadata
- Static web client hosting
"""

import os
import time
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
import duckdb
import h3

DB_PATH = "data/processed/transit_equity.db"
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")

app = FastAPI(
    title="Multimodal Transit Desert Platform API",
    description="Spatial transit equity and accessibility analytics for Greater Melbourne using DuckDB, Uber H3, and r5py.",
    version="1.0.0"
)

# Enable CORS for local development and client consumption
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    """Establish a thread-safe read-only connection to DuckDB."""
    if not os.path.exists(DB_PATH):
        raise HTTPException(
            status_code=503,
            detail=f"Database file not found at '{DB_PATH}'. Please run pipeline stages 1-3 first."
        )
    con = duckdb.connect(DB_PATH, read_only=True)
    con.execute("LOAD spatial;")
    return con


# --- Pydantic Response Models ---

class HealthResponse(BaseModel):
    status: str
    database: str
    h3_total_cells: int
    demographic_polygons: int
    travel_matrix_pairs: int
    equity_scored_cells: int
    transit_desert_cells: int
    timestamp: float


class POIModel(BaseModel):
    id: str
    name: str
    category: str
    lat: float
    lon: float
    reachable_h3_count: int
    avg_travel_time_p50: float


class SuburbSummary(BaseModel):
    suburb_name: str
    desert_hex_count: int
    total_hex_count: int
    estimated_resident_pop: int
    avg_density_sqkm: float
    avg_seifa_decile: float
    avg_access_score: float
    avg_vuln_score: float
    avg_desert_index: float
    centroid_lat: float
    centroid_lng: float


class MetricDistribution(BaseModel):
    metric: str
    min_val: float
    p25: float
    median: float
    mean: float
    p75: float
    p90: float
    max_val: float


class StatsResponse(BaseModel):
    total_h3_cells: int
    populated_cells: int
    transit_desert_cells_p80: int
    p80_tdi_threshold: float
    total_analyzed_population: int
    deserts_affected_population: int
    distributions: List[MetricDistribution]


# --- API Routes ---

@app.get("/api/v1/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """Verify database connectivity, spatial extensions, and table counts."""
    con = get_db()
    try:
        h3_cnt = con.execute("SELECT COUNT(*) FROM melb_h3_grid;").fetchone()[0]
        demo_cnt = con.execute("SELECT COUNT(*) FROM melb_demographics;").fetchone()[0]
        mat_cnt = con.execute("SELECT COUNT(*) FROM melb_travel_matrix;").fetchone()[0]
        eq_cnt = con.execute("SELECT COUNT(*) FROM melb_equity_scores;").fetchone()[0]
        des_cnt = con.execute("SELECT COUNT(*) FROM v_transit_deserts;").fetchone()[0]
        
        return HealthResponse(
            status="healthy",
            database=DB_PATH,
            h3_total_cells=h3_cnt,
            demographic_polygons=demo_cnt,
            travel_matrix_pairs=mat_cnt,
            equity_scored_cells=eq_cnt,
            transit_desert_cells=des_cnt,
            timestamp=time.time()
        )
    finally:
        con.close()


def unwrap_param(val, default=None):
    """Unwrap FastAPI Query object if function is called directly in Python tests."""
    if hasattr(val, "default"):
        res = val.default
        return default if res is None or res is ... else res
    return val if val is not None else default


@app.get("/api/v1/transit-deserts", tags=["Geospatial Data"])
def get_transit_deserts(
    min_tdi: float = Query(0.0, ge=0.0, le=1.0, description="Minimum Transit Desert Index filter"),
    suburb: Optional[str] = Query(None, description="Filter by SA2 Suburb name (case-insensitive substring)"),
    only_deserts: bool = Query(True, description="If true, query from v_transit_deserts; if false, query from melb_equity_scores"),
    limit: int = Query(20000, ge=1, le=50000, description="Maximum number of features returned"),
    format: str = Query("geojson", pattern="^(geojson|json)$", description="Response format ('geojson' or 'json')")
):
    """
    Serve H3 Resolution-9 hexagon polygons enriched with TDI, accessibility, vulnerability,
    and demographic attributes as standard GeoJSON FeatureCollection for MapLibre GL JS 3D rendering.
    """
    con = get_db()
    try:
        min_tdi_val = float(unwrap_param(min_tdi, 0.0))
        suburb_val = unwrap_param(suburb, None)
        only_deserts_val = bool(unwrap_param(only_deserts, True))
        limit_val = int(unwrap_param(limit, 20000))
        format_val = str(unwrap_param(format, "geojson"))

        table_source = "v_transit_deserts" if only_deserts_val else "melb_equity_scores"
        where_clauses = ["population > 0"]
        params = []
        
        if min_tdi_val > 0:
            where_clauses.append("transit_desert_index >= ?")
            params.append(min_tdi_val)
            
        if suburb_val:
            where_clauses.append("LOWER(sa2_name) LIKE ?")
            params.append(f"%{suburb_val.lower()}%")
            
        where_sql = " AND ".join(where_clauses)
        query = f"""
            SELECT 
                h3_index,
                centroid_lat,
                centroid_lng,
                sa1_code,
                sa2_name AS suburb_name,
                population,
                ROUND(pop_density, 1) AS pop_density,
                ROUND(seifa_irsd_score, 1) AS seifa_irsd_score,
                seifa_irsd_decile,
                travel_time_rmh_p50,
                travel_time_monash_p50,
                travel_time_chadstone_p50,
                score_rmh,
                score_monash,
                score_chadstone,
                accessibility_score AS accessibility,
                vulnerability_score AS vulnerability,
                transit_desert_index AS tdi
            FROM {table_source}
            WHERE {where_sql}
            ORDER BY transit_desert_index DESC
            LIMIT {limit_val};
        """
        
        df = con.execute(query, params).fetchdf() if params else con.execute(query).fetchdf()
        
        if format_val == "json":
            return df.to_dict(orient="records")
            
        # Build GeoJSON FeatureCollection
        features = []
        for row in df.itertuples(index=False):
            # Compute exact hexagon polygon ring from H3 index
            lat_lng_boundary = h3.cell_to_boundary(row.h3_index)
            # GeoJSON coordinates: [[lng, lat], ...]
            ring = [[lng, lat] for lat, lng in lat_lng_boundary]
            ring.append(ring[0])  # Close polygon ring
            
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [ring]
                },
                "properties": {
                    "h3_index": row.h3_index,
                    "centroid_lat": row.centroid_lat,
                    "centroid_lng": row.centroid_lng,
                    "suburb_name": row.suburb_name,
                    "sa1_code": row.sa1_code,
                    "population": int(row.population),
                    "pop_density": float(row.pop_density),
                    "seifa_irsd_score": float(row.seifa_irsd_score) if row.seifa_irsd_score is not None else None,
                    "seifa_irsd_decile": int(row.seifa_irsd_decile) if row.seifa_irsd_decile is not None else None,
                    "tt_rmh": float(row.travel_time_rmh_p50),
                    "tt_monash": float(row.travel_time_monash_p50),
                    "tt_chadstone": float(row.travel_time_chadstone_p50),
                    "score_rmh": float(row.score_rmh),
                    "score_monash": float(row.score_monash),
                    "score_chadstone": float(row.score_chadstone),
                    "accessibility": float(row.accessibility),
                    "vulnerability": float(row.vulnerability),
                    "tdi": float(row.tdi)
                }
            })
            
        return {
            "type": "FeatureCollection",
            "metadata": {
                "count": len(features),
                "min_tdi": min_tdi_val,
                "suburb_filter": suburb_val,
                "only_deserts": only_deserts_val
            },
            "features": features
        }
    finally:
        con.close()


@app.get("/api/v1/suburbs/top", response_model=List[SuburbSummary], tags=["Analytics"])
def get_top_suburbs(
    limit: int = Query(15, ge=1, le=100, description="Number of top suburbs to return"),
    min_pop: int = Query(500, ge=0, description="Minimum estimated resident population")
):
    """Retrieve top-ranked priority transit desert suburbs aggregated across H3 hexagons."""
    limit_val = int(unwrap_param(limit, 15))
    min_pop_val = int(unwrap_param(min_pop, 500))
    
    con = get_db()
    try:
        query = """
            SELECT 
                sa2_name AS suburb_name,
                COUNT(CASE WHEN transit_desert_index >= 0.3447 THEN 1 END) AS desert_hex_count,
                COUNT(*) AS total_hex_count,
                CAST(SUM(population) AS INTEGER) AS estimated_resident_pop,
                ROUND(AVG(pop_density), 1) AS avg_density_sqkm,
                ROUND(AVG(seifa_irsd_decile), 1) AS avg_seifa_decile,
                ROUND(AVG(accessibility_score), 4) AS avg_access_score,
                ROUND(AVG(vulnerability_score), 4) AS avg_vuln_score,
                ROUND(AVG(transit_desert_index), 4) AS avg_desert_index,
                ROUND(AVG(centroid_lat), 5) AS centroid_lat,
                ROUND(AVG(centroid_lng), 5) AS centroid_lng
            FROM melb_equity_scores
            WHERE population > 0 AND sa2_name IS NOT NULL
            GROUP BY sa2_name
            HAVING SUM(population) >= ?
            ORDER BY avg_desert_index DESC, desert_hex_count DESC
            LIMIT ?;
        """
        df = con.execute(query, [min_pop_val, limit_val]).fetchdf()
        return df.to_dict(orient="records")
    finally:
        con.close()


@app.get("/api/v1/stats", response_model=StatsResponse, tags=["Analytics"])
def get_system_stats():
    """Retrieve statistical distribution percentiles and summary totals across Greater Melbourne."""
    con = get_db()
    try:
        # Totals
        totals = con.execute("""
            SELECT 
                COUNT(*) AS total_h3,
                COUNT(CASE WHEN population > 0 THEN 1 END) AS populated_h3,
                COUNT(CASE WHEN transit_desert_index >= 0.3447 AND population > 0 THEN 1 END) AS desert_h3,
                SUM(population) AS total_pop,
                SUM(CASE WHEN transit_desert_index >= 0.3447 THEN population ELSE 0 END) AS desert_pop
            FROM melb_equity_scores;
        """).fetchone()
        
        # P80 cutoff
        p80_cutoff = con.execute("""
            SELECT ROUND(PERCENTILE_CONT(0.80) WITHIN GROUP (ORDER BY transit_desert_index), 4)
            FROM melb_equity_scores WHERE population > 0;
        """).fetchone()[0]
        
        # Distributions
        dist_df = con.execute("""
            SELECT 
                'Transit Desert Index' AS metric,
                ROUND(MIN(transit_desert_index), 4) AS min_val,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY transit_desert_index), 4) AS p25,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY transit_desert_index), 4) AS median,
                ROUND(AVG(transit_desert_index), 4) AS mean,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY transit_desert_index), 4) AS p75,
                ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY transit_desert_index), 4) AS p90,
                ROUND(MAX(transit_desert_index), 4) AS max_val
            FROM melb_equity_scores WHERE population > 0
            UNION ALL
            SELECT 
                'Accessibility Score' AS metric,
                ROUND(MIN(accessibility_score), 4) AS min_val,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY accessibility_score), 4) AS p25,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY accessibility_score), 4) AS median,
                ROUND(AVG(accessibility_score), 4) AS mean,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY accessibility_score), 4) AS p75,
                ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY accessibility_score), 4) AS p90,
                ROUND(MAX(accessibility_score), 4) AS max_val
            FROM melb_equity_scores WHERE population > 0
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
            FROM melb_equity_scores WHERE population > 0;
        """).fetchdf()
        
        return StatsResponse(
            total_h3_cells=totals[0],
            populated_cells=totals[1],
            transit_desert_cells_p80=totals[2],
            p80_tdi_threshold=float(p80_cutoff),
            total_analyzed_population=int(totals[3] or 0),
            deserts_affected_population=int(totals[4] or 0),
            distributions=dist_df.to_dict(orient="records")
        )
    finally:
        con.close()


@app.get("/api/v1/pois", response_model=List[POIModel], tags=["Geospatial Data"])
def get_pois():
    """Retrieve strategic Points of Interest (POIs) metadata and reachability summary."""
    pois_def = [
        {"id": "RMH", "name": "Royal Melbourne Hospital", "category": "Healthcare", "lat": -37.7990, "lon": 144.9560},
        {"id": "MONASH_CLAYTON", "name": "Monash University Clayton", "category": "Education", "lat": -37.9150, "lon": 145.1300},
        {"id": "CHADSTONE", "name": "Chadstone Shopping Centre", "category": "Commercial", "lat": -37.8860, "lon": 145.0830}
    ]
    con = get_db()
    try:
        results = []
        for p in pois_def:
            stats = con.execute("""
                SELECT 
                    COUNT(*) AS count_val,
                    ROUND(AVG(travel_time_p50), 1) AS avg_time
                FROM melb_travel_matrix
                WHERE destination_id = ?;
            """, [p["id"]]).fetchone()
            
            results.append(POIModel(
                id=p["id"],
                name=p["name"],
                category=p["category"],
                lat=p["lat"],
                lon=p["lon"],
                reachable_h3_count=stats[0] if stats else 0,
                avg_travel_time_p50=float(stats[1]) if stats and stats[1] is not None else 0.0
            ))
        return results
    finally:
        con.close()


# --- Static Frontend Serving ---

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return JSONResponse({"message": "Frontend index.html not found"}, status_code=404)
