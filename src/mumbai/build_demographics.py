"""
Spatial Demographics & Vulnerability Proxy Builder for Mumbai.
- Initializes DuckDB database: data/mumbai/processed/mumbai_equity.db
- Generates H3 Resolution 9 grid across Greater Mumbai bounding box
- Flattens 3D KML slum clusters into 2D geometries (EPSG:4326) and ingests into DuckDB
- Computes baseline vulnerability scores using spatial ST_Intersects joins
- Ingests 2011 Ward-wise Census demographic data and BMC administrative boundaries
"""

import os
import logging
import duckdb
import h3
import shapely
import geopandas as gpd
import pandas as pd
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s - %(message)s')
logger = logging.getLogger("MumbaiDemographicsBuilder")

# Paths
DB_PATH = Path("data/mumbai/processed/mumbai_equity.db")
KML_PATH = Path("data/mumbai/raw/5d6f72ed-a290-4931-821f-5476c148407b.kml")
CENSUS_PATH = Path("data/mumbai/raw/95e22d97-7f59-4214-b244-2abbf52e6027.csv")
WARDS_GEOJSON_PATH = Path("data/mumbai/raw/BMC_Wards.geojson")

# Bounding box for Greater Mumbai Metropolitan limits
BBOX = {
    'lng_min': 72.77,
    'lat_min': 18.89,
    'lng_max': 73.00,
    'lat_max': 19.28
}
H3_RESOLUTION = 9

def initialize_database(con):
    """Install and load DuckDB spatial extension."""
    logger.info("Initializing DuckDB spatial extension...")
    con.execute("INSTALL spatial;")
    con.execute("LOAD spatial;")

def build_h3_grid(con, bbox=BBOX, resolution=H3_RESOLUTION):
    """Generate H3 Res-9 grid and store centroids in mumbai_h3_grid."""
    logger.info("Generating H3 Resolution %d grid for bbox: %s", resolution, bbox)
    
    poly_coords = [
        (bbox['lat_min'], bbox['lng_min']),
        (bbox['lat_min'], bbox['lng_max']),
        (bbox['lat_max'], bbox['lng_max']),
        (bbox['lat_max'], bbox['lng_min']),
        (bbox['lat_min'], bbox['lng_min'])
    ]
    lat_lng_poly = h3.LatLngPoly(poly_coords)
    cells = h3.polygon_to_cells(lat_lng_poly, resolution)
    logger.info("Generated %d H3 hexagons", len(cells))
    
    records = []
    for cell in cells:
        lat, lng = h3.cell_to_latlng(cell)
        records.append({
            'h3_index': str(cell),
            'centroid_lat': float(lat),
            'centroid_lng': float(lng)
        })
        
    df_grid = pd.DataFrame(records)
    con.register("df_grid_temp", df_grid)
    con.execute("""
        CREATE OR REPLACE TABLE mumbai_h3_grid AS
        SELECT 
            h3_index,
            centroid_lat,
            centroid_lng,
            ST_Point(centroid_lng, centroid_lat) AS centroid_geom
        FROM df_grid_temp;
    """)
    con.unregister("df_grid_temp")
    
    count = con.execute("SELECT COUNT(*) FROM mumbai_h3_grid;").fetchone()[0]
    logger.info("Created table 'mumbai_h3_grid' with %d cells.", count)
    return count

def ingest_slums(con, kml_path=KML_PATH):
    """Ingest slum cluster KML, flatten 3D coordinates to 2D EPSG:4326, and save to mumbai_slums."""
    logger.info("Reading Slum Cluster KML from %s...", kml_path)
    gdf_slums = gpd.read_file(kml_path, engine='pyogrio')
    logger.info("Loaded %d slum cluster polygons. Flattening 3D geometries to 2D...", len(gdf_slums))
    
    # Force 2D geometry and ensure EPSG:4326
    gdf_slums['geometry'] = shapely.force_2d(gdf_slums.geometry)
    if gdf_slums.crs is None or gdf_slums.crs.to_epsg() != 4326:
        gdf_slums = gdf_slums.set_crs(epsg=4326, allow_override=True)
        
    gdf_slums['wkt'] = gdf_slums.geometry.apply(lambda g: g.wkt)
    slum_df = gdf_slums[['polyno', 'wkt']].copy()
    
    con.register("df_slums_temp", slum_df)
    con.execute("""
        CREATE OR REPLACE TABLE mumbai_slums AS
        SELECT 
            CAST(polyno AS INTEGER) AS polyno,
            ST_GeomFromText(wkt) AS geom
        FROM df_slums_temp;
    """)
    con.unregister("df_slums_temp")
    
    count = con.execute("SELECT COUNT(*) FROM mumbai_slums;").fetchone()[0]
    logger.info("Created table 'mumbai_slums' with %d flattened 2D polygons.", count)
    return count

def compute_vulnerability(con):
    """Execute spatial join between H3 centroids and slums to compute baseline vulnerability scores."""
    logger.info("Executing DuckDB spatial ST_Intersects join to compute vulnerability proxy...")
    
    con.execute("""
        CREATE OR REPLACE TABLE mumbai_demographics AS
        WITH slum_intersections AS (
            SELECT DISTINCT g.h3_index
            FROM mumbai_h3_grid g
            JOIN mumbai_slums s ON ST_Intersects(g.centroid_geom, s.geom)
        )
        SELECT 
            g.h3_index,
            g.centroid_lat,
            g.centroid_lng,
            g.centroid_geom,
            CASE WHEN si.h3_index IS NOT NULL THEN 1 ELSE 0 END AS is_slum_cluster,
            CASE WHEN si.h3_index IS NOT NULL THEN 1.0 ELSE 0.2 END AS vulnerability_score
        FROM mumbai_h3_grid g
        LEFT JOIN slum_intersections si ON g.h3_index = si.h3_index;
    """)
    
    total_cells = con.execute("SELECT COUNT(*) FROM mumbai_demographics;").fetchone()[0]
    slum_cells = con.execute("SELECT COUNT(*) FROM mumbai_demographics WHERE is_slum_cluster = 1;").fetchone()[0]
    baseline_cells = con.execute("SELECT COUNT(*) FROM mumbai_demographics WHERE is_slum_cluster = 0;").fetchone()[0]
    
    logger.info("Materialized 'mumbai_demographics' table:")
    logger.info("  • Total Grid Cells:        %d", total_cells)
    logger.info("  • Slum Cluster Cells (1.0): %d (%.2f%%)", slum_cells, (slum_cells / total_cells) * 100)
    logger.info("  • Baseline Cells (0.2):     %d (%.2f%%)", baseline_cells, (baseline_cells / total_cells) * 100)
    return total_cells, slum_cells

def ingest_census_and_wards(con, census_path=CENSUS_PATH, wards_path=WARDS_GEOJSON_PATH):
    """Ingest 2011 Census demographics and administrative BMC ward boundaries."""
    logger.info("Ingesting 2011 Ward Census from %s...", census_path)
    df_census = pd.read_csv(census_path)
    df_census.columns = [c.strip().lower().replace(' ', '_').replace('/', '_') for c in df_census.columns]
    
    con.register("df_census_temp", df_census)
    con.execute("""
        CREATE OR REPLACE TABLE mumbai_ward_census AS
        SELECT * FROM df_census_temp;
    """)
    con.unregister("df_census_temp")
    census_count = con.execute("SELECT COUNT(*) FROM mumbai_ward_census;").fetchone()[0]
    logger.info("Created table 'mumbai_ward_census' with %d ward records.", census_count)
    
    if wards_path.exists():
        logger.info("Ingesting BMC Administrative Ward boundaries from %s...", wards_path)
        gdf_wards = gpd.read_file(wards_path)
        gdf_wards['wkt'] = gdf_wards.geometry.apply(lambda g: g.wkt)
        con.register("df_wards_temp", gdf_wards[['gid', 'name', 'wkt']])
        con.execute("""
            CREATE OR REPLACE TABLE mumbai_bmc_wards AS
            SELECT 
                gid,
                name AS ward_name,
                ST_GeomFromText(wkt) AS geom
            FROM df_wards_temp;
        """)
        con.unregister("df_wards_temp")
        wards_count = con.execute("SELECT COUNT(*) FROM mumbai_bmc_wards;").fetchone()[0]
        logger.info("Created table 'mumbai_bmc_wards' with %d municipal ward polygons.", wards_count)

def run_pipeline():
    """Execute complete demographic and grid pipeline for Mumbai."""
    print("=" * 70)
    print("MUMBAI SPATIAL DEMOGRAPHICS & VULNERABILITY PIPELINE")
    print("=" * 70)
    
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    
    initialize_database(con)
    build_h3_grid(con)
    ingest_slums(con)
    compute_vulnerability(con)
    ingest_census_and_wards(con)
    
    # Audit summary
    tables = con.execute("SHOW TABLES;").fetchall()
    table_names = [t[0] for t in tables]
    
    print("\n" + "=" * 70)
    print("MUMBAI DEMOGRAPHICS INGESTION SUMMARY:")
    print(f"  • Database: {DB_PATH}")
    print(f"  • Tables Populated: {table_names}")
    for tbl in table_names:
        cnt = con.execute(f"SELECT COUNT(*) FROM {tbl};").fetchone()[0]
        print(f"    - {tbl:<22}: {cnt:>8,} records")
    print("=" * 70)
    
    con.close()

if __name__ == "__main__":
    run_pipeline()
