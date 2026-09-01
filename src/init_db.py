"""
DuckDB Database Initializer for Transit Equity Platform.
Installs and loads the spatial extension, creating the target schema.
"""

import os
import duckdb
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s - %(message)s')
logger = logging.getLogger("DBInit")

DB_PATH = "data/processed/transit_equity.db"

def init_database(db_path=DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    logger.info("Connecting to DuckDB database at: %s", db_path)
    
    con = duckdb.connect(db_path)
    
    # Install and load spatial extension
    logger.info("Installing and loading DuckDB spatial extension...")
    con.execute("INSTALL spatial;")
    con.execute("LOAD spatial;")
    
    # Table 1: Melbourne Demographics (SA1 Level)
    logger.info("Creating table schemas...")
    con.execute("""
        CREATE TABLE IF NOT EXISTS melb_demographics (
            sa1_code VARCHAR PRIMARY KEY,
            sa2_code VARCHAR,
            sa2_name VARCHAR,
            gccsa_code VARCHAR,
            gccsa_name VARCHAR,
            area_sqkm DOUBLE,
            population INTEGER,
            pop_density DOUBLE,
            seifa_irsd_score DOUBLE,
            seifa_irsd_decile INTEGER,
            seifa_irsad_score DOUBLE,
            seifa_irsad_decile INTEGER,
            geom GEOMETRY
        );
    """)
    
    # Table 2: Melbourne H3 Grid (Resolution 9)
    con.execute("""
        CREATE TABLE IF NOT EXISTS melb_h3_grid (
            h3_index VARCHAR PRIMARY KEY,
            centroid_lat DOUBLE,
            centroid_lng DOUBLE,
            centroid_geom GEOMETRY
        );
    """)
    
    # Table 3: Travel Time Matrix (Origins to POIs)
    con.execute("""
        CREATE TABLE IF NOT EXISTS melb_travel_matrix (
            origin_h3 VARCHAR,
            destination_id VARCHAR,
            travel_time_p50 DOUBLE,
            travel_time_p90 DOUBLE,
            PRIMARY KEY (origin_h3, destination_id)
        );
    """)
    
    tables = con.execute("SHOW TABLES;").fetchall()
    logger.info("Database initialized successfully with tables: %s", [t[0] for t in tables])
    con.close()

if __name__ == "__main__":
    init_database()
