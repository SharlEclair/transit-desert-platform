"""
Demographic Ingestion for Greater Melbourne (ABS SEIFA SA1).
Adheres strictly to geospatial-audit rules:
- Transforms input from EPSG:7844 to EPSG:4326 using GeoPandas.
- Asserts gdf.crs.to_epsg() == 4326 prior to DuckDB insertion.
- Merges SEIFA socio-economic disadvantage indexes and resident population.
"""

import os
import duckdb
import geopandas as gpd
import pandas as pd
import logging
from shapely import wkt

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s - %(message)s')
logger = logging.getLogger("DemographicsIngestion")

GPKG_PATH = "data/raw/ASGS_2021_Main_Structure_GDA2020.gpkg"
SEIFA_EXCEL_PATH = "data/raw/Statistical Area Level 1, Indexes, SEIFA 2021.xlsx"
DB_PATH = "data/processed/transit_equity.db"

def ingest_demographics(gpkg_path=GPKG_PATH, seifa_excel_path=SEIFA_EXCEL_PATH, db_path=DB_PATH):
    logger.info("Reading SA1 geometries for Greater Melbourne from %s...", gpkg_path)
    
    # Read SA1 layer
    gdf_sa1 = gpd.read_file(gpkg_path, layer='SA1_2021_AUST_GDA2020', where="GCCSA_NAME_2021 = 'Greater Melbourne'")
    logger.info("Found %d SA1 polygons in Greater Melbourne (Source CRS: %s)", len(gdf_sa1), gdf_sa1.crs)
    
    # Transform CRS explicitly to WGS84 EPSG:4326
    logger.info("Transforming CRS from %s to EPSG:4326...", gdf_sa1.crs)
    gdf_sa1 = gdf_sa1.to_crs(epsg=4326)
    
    # STRICT PYTHON ASSERTION (as mandated to avoid DuckDB ST_SRID bug)
    assert gdf_sa1.crs.to_epsg() == 4326, f"CRS transformation failed! Target must be 4326, got: {gdf_sa1.crs}"
    logger.info("[AUDIT PASSED] GeoDataFrame CRS successfully validated as EPSG:4326.")
    
    # Read SEIFA Table 1 (IRSD and IRSAD)
    logger.info("Reading SEIFA index metrics from %s...", seifa_excel_path)
    df_seifa_raw = pd.read_excel(seifa_excel_path, sheet_name='Table 1', skiprows=4)
    
    # Map SEIFA columns:
    # Col 0: SA1 Code
    # Col 1: IRSD Score
    # Col 2: IRSD Decile
    # Col 3: IRSAD Score
    # Col 4: IRSAD Decile
    # Col 9: Usual Resident Population
    seifa_clean = pd.DataFrame({
        'sa1_code': df_seifa_raw.iloc[1:, 0].astype(str).str.strip(),
        'seifa_irsd_score': pd.to_numeric(df_seifa_raw.iloc[1:, 1], errors='coerce'),
        'seifa_irsd_decile': pd.to_numeric(df_seifa_raw.iloc[1:, 2], errors='coerce'),
        'seifa_irsad_score': pd.to_numeric(df_seifa_raw.iloc[1:, 3], errors='coerce'),
        'seifa_irsad_decile': pd.to_numeric(df_seifa_raw.iloc[1:, 4], errors='coerce'),
        'population': pd.to_numeric(df_seifa_raw.iloc[1:, 9], errors='coerce').fillna(0).astype(int)
    })
    
    # Prepare SA1 geodataframe fields
    gdf_sa1['sa1_code'] = gdf_sa1['SA1_CODE_2021'].astype(str).str.strip()
    gdf_sa1['sa2_code'] = gdf_sa1['SA2_CODE_2021'].astype(str)
    gdf_sa1['sa2_name'] = gdf_sa1['SA2_NAME_2021'].astype(str)
    gdf_sa1['gccsa_code'] = gdf_sa1['GCCSA_CODE_2021'].astype(str)
    gdf_sa1['gccsa_name'] = gdf_sa1['GCCSA_NAME_2021'].astype(str)
    gdf_sa1['area_sqkm'] = pd.to_numeric(gdf_sa1['AREA_ALBERS_SQKM'], errors='coerce')
    
    # Merge geometries with SEIFA data
    logger.info("Merging spatial polygons with SEIFA index attributes...")
    merged = gdf_sa1.merge(seifa_clean, on='sa1_code', how='left')
    
    # Compute population density (people per sq km)
    merged['pop_density'] = merged['population'] / merged['area_sqkm'].replace(0, pd.NA)
    merged['pop_density'] = merged['pop_density'].fillna(0.0)
    
    # Convert geometry to WKT for clean DuckDB spatial ingestion
    merged['geom_wkt'] = merged['geometry'].apply(lambda g: g.wkt if g is not None else None)
    
    df_to_insert = merged[[
        'sa1_code', 'sa2_code', 'sa2_name', 'gccsa_code', 'gccsa_name',
        'area_sqkm', 'population', 'pop_density',
        'seifa_irsd_score', 'seifa_irsd_decile', 'seifa_irsad_score', 'seifa_irsad_decile',
        'geom_wkt'
    ]]
    
    logger.info("Writing %d demographic records into DuckDB table 'melb_demographics'...", len(df_to_insert))
    con = duckdb.connect(db_path)
    con.execute("LOAD spatial;")
    
    # Register dataframe and insert with ST_GeomFromText
    con.register("df_temp", df_to_insert)
    con.execute("DELETE FROM melb_demographics;")
    con.execute("""
        INSERT INTO melb_demographics
        SELECT 
            sa1_code, sa2_code, sa2_name, gccsa_code, gccsa_name,
            area_sqkm, population, pop_density,
            seifa_irsd_score, seifa_irsd_decile, seifa_irsad_score, seifa_irsad_decile,
            ST_GeomFromText(geom_wkt) AS geom
        FROM df_temp;
    """)
    con.unregister("df_temp")
    
    count = con.execute("SELECT COUNT(*) FROM melb_demographics;").fetchone()[0]
    sample = con.execute("SELECT sa1_code, sa2_name, population, pop_density, seifa_irsd_decile, ST_AsText(geom) FROM melb_demographics LIMIT 1;").fetchone()
    
    logger.info("[AUDIT SUCCESS] Ingested %d SA1 polygons into DuckDB.", count)
    logger.info("Sample record: SA1=%s, SA2=%s, Pop=%s, Density=%.1f/km2, SEIFA Decile=%s", sample[0], sample[1], sample[2], sample[3], sample[4])
    con.close()

if __name__ == "__main__":
    ingest_demographics()
