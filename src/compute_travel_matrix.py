"""
Travel Time Matrix Computation for Multimodal Transit Desert Platform.
Utilizes r5py.TransportNetwork and TravelTimeMatrix (R5 FastRaptor engine)
to compute multimodal transit + walking travel times from Greater Melbourne
H3 Resolution-9 grid centroids to key Points of Interest (POIs).

Adheres to:
- 12GB+ JVM Memory allocation (OpenJDK 21)
- WGS84 (EPSG:4326) CRS spatial standard
- Tuesday morning peak departure (2026-09-08 08:00 AM)
- 45-minute max travel time cutoff
- Memory-safe origin chunking (20,000 cells/batch) with garbage collection
- Filtering out unreachable / NaN routes prior to DuckDB insertion
"""

import os
import sys
import gc
import glob
import time
import logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import duckdb

# Ensure Java 21 is configured before importing r5py
DEFAULT_JDK_PATH = r"C:\Users\91704\.jdk\jdk-21.0.6+7"
if os.path.exists(DEFAULT_JDK_PATH) and "JAVA_HOME" not in os.environ:
    os.environ["JAVA_HOME"] = DEFAULT_JDK_PATH

import r5py
from r5py import TransportMode, TransportNetwork, TravelTimeMatrix

# Alias TravelTimeMatrixComputer for API consistency
TravelTimeMatrixComputer = getattr(r5py, "TravelTimeMatrixComputer", TravelTimeMatrix)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("MatrixComputation")

# Database and file path configuration
DB_PATH = "data/processed/transit_equity.db"
OSM_PBF_PATHS = [
    "data/raw/osm/victoria-latest.osm.pbf",
    "data/raw/victoria-260831.osm.pbf"
]
GTFS_DIR = "data/processed/gtfs_feeds"

# Target POIs (EPSG:4326)
POIS = [
    {
        "id": "RMH",
        "name": "Royal Melbourne Hospital",
        "lat": -37.7990,
        "lon": 144.9560,
        "category": "Healthcare"
    },
    {
        "id": "MONASH_CLAYTON",
        "name": "Monash University Clayton",
        "lat": -37.9150,
        "lon": 145.1300,
        "category": "Education"
    },
    {
        "id": "CHADSTONE",
        "name": "Chadstone Shopping Centre",
        "lat": -37.8860,
        "lon": 145.0830,
        "category": "Commercial"
    }
]

# Routing Parameters
DEPARTURE_DATETIME = datetime(2026, 9, 8, 8, 0, 0)  # Tuesday 08:00 AM
MAX_TIME_MINUTES = 45
MAX_TIME = timedelta(minutes=MAX_TIME_MINUTES)
PERCENTILES = [50, 90]
CHUNK_SIZE = 20000


def resolve_osm_path():
    """Find the valid OSM PBF extract path."""
    for path in OSM_PBF_PATHS:
        if os.path.exists(path):
            logger.info("Found OSM PBF extract at: %s (%.1f MB)", path, os.path.getsize(path) / (1024 * 1024))
            return path
    raise FileNotFoundError(f"No OSM PBF file found in {OSM_PBF_PATHS}")


def get_gtfs_feeds():
    """Collect all cleaned GTFS feeds."""
    feed_files = sorted(glob.glob(os.path.join(GTFS_DIR, "*.zip")))
    if not feed_files:
        raise FileNotFoundError(f"No GTFS feed archives found in {GTFS_DIR}")
    logger.info("Found %d GTFS feed archives in %s:", len(feed_files), GTFS_DIR)
    for f in feed_files:
        logger.info("  - %s (%.2f MB)", os.path.basename(f), os.path.getsize(f) / (1024 * 1024))
    return feed_files


def create_destinations_gdf():
    """Create destinations GeoDataFrame in EPSG:4326."""
    gdf = gpd.GeoDataFrame(
        POIS,
        geometry=[Point(p["lon"], p["lat"]) for p in POIS],
        crs="EPSG:4326"
    )
    logger.info("Initialized %d destination POIs (EPSG:4326):", len(gdf))
    for idx, row in gdf.iterrows():
        logger.info("  [%s] %s @ (%.4f, %.4f)", row["id"], row["name"], row["lat"], row["lon"])
    return gdf


def load_origins_gdf(db_path=DB_PATH):
    """Load H3 grid centroids from DuckDB into a GeoDataFrame (EPSG:4326)."""
    logger.info("Connecting to DuckDB at: %s", db_path)
    con = duckdb.connect(db_path, read_only=True)
    con.execute("LOAD spatial;")
    
    query = "SELECT h3_index AS id, centroid_lng, centroid_lat FROM melb_h3_grid ORDER BY h3_index;"
    df = con.execute(query).fetchdf()
    con.close()
    
    logger.info("Loaded %d H3 centroids from DuckDB `melb_h3_grid`", len(df))
    
    gdf = gpd.GeoDataFrame(
        df[["id"]],
        geometry=gpd.points_from_xy(df.centroid_lng, df.centroid_lat),
        crs="EPSG:4326"
    )
    return gdf


def to_minutes_float(val):
    """Convert timedelta or numeric to float minutes, returning np.nan for invalid/null."""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (timedelta, pd.Timedelta)):
        return float(val.total_seconds() / 60.0)
    try:
        f_val = float(val)
        return f_val if f_val >= 0 else np.nan
    except (ValueError, TypeError):
        return np.nan


def compute_and_store_matrix():
    """Build transport network and compute batched travel time matrix."""
    start_total_time = time.time()
    logger.info("=" * 70)
    logger.info("STARTING MULTIMODAL TRAVEL TIME MATRIX COMPUTATION")
    logger.info("=" * 70)
    
    # 1. Resolve inputs
    osm_path = resolve_osm_path()
    gtfs_feeds = get_gtfs_feeds()
    
    # 2. Build destinations and origins
    destinations_gdf = create_destinations_gdf()
    origins_gdf = load_origins_gdf(DB_PATH)
    total_origins = len(origins_gdf)
    
    # 3. Instantiate TransportNetwork
    logger.info("-" * 70)
    logger.info("INITIALIZING R5 TRANSPORT NETWORK GRAPH...")
    logger.info("Note: Building street & transit topological index may take several minutes on first run.")
    net_start_time = time.time()
    
    # Clean stale unfinalized mapdb files if any
    cache_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "r5py")
    if os.path.exists(cache_dir):
        for f in glob.glob(os.path.join(cache_dir, "*.mapdb*")):
            try:
                os.remove(f)
                logger.info("Removed stale MapDB cache file: %s", os.path.basename(f))
            except Exception:
                pass

    transport_network = TransportNetwork(
        osm_pbf=osm_path,
        gtfs=gtfs_feeds
    )
    logger.info("Transport network initialized successfully in %.1f seconds!", time.time() - net_start_time)
    logger.info("-" * 70)
    
    # 4. Prepare DuckDB connection
    con = duckdb.connect(DB_PATH)
    con.execute("LOAD spatial;")
    
    # Clear existing travel matrix before fresh insertion
    con.execute("DELETE FROM melb_travel_matrix;")
    logger.info("Cleared existing records in `melb_travel_matrix`")
    
    # 5. Compute in memory-safe chunks
    num_chunks = int(np.ceil(total_origins / CHUNK_SIZE))
    logger.info("Starting computation for %d origins across %d batches (Batch size: %d)", total_origins, num_chunks, CHUNK_SIZE)
    
    total_valid_records = 0
    transport_modes = [TransportMode.TRANSIT, TransportMode.WALK]
    
    for chunk_idx in range(num_chunks):
        chunk_start = chunk_idx * CHUNK_SIZE
        chunk_end = min((chunk_idx + 1) * CHUNK_SIZE, total_origins)
        chunk_origins = origins_gdf.iloc[chunk_start:chunk_end].copy()
        
        logger.info(
            ">>> Processing Batch %d/%d (Origins %d to %d / %d) [%.1f%%]...",
            chunk_idx + 1, num_chunks, chunk_start + 1, chunk_end, total_origins,
            (chunk_start / total_origins) * 100
        )
        
        batch_start_time = time.time()
        
        # Execute TravelTimeMatrix for chunk
        ttm = TravelTimeMatrixComputer(
            transport_network=transport_network,
            origins=chunk_origins,
            destinations=destinations_gdf,
            departure=DEPARTURE_DATETIME,
            max_time=MAX_TIME,
            percentiles=PERCENTILES,
            transport_modes=transport_modes,
            snap_to_network=True
        )
        
        # Convert to standard pandas DataFrame
        df_result = pd.DataFrame(ttm)
        
        # Identify columns
        # r5py outputs 'from_id', 'to_id', 'travel_time_p50', 'travel_time_p90' (or 'travel_time' if only p50)
        p50_col = "travel_time_p50" if "travel_time_p50" in df_result.columns else "travel_time"
        p90_col = "travel_time_p90" if "travel_time_p90" in df_result.columns else p50_col
        
        if "from_id" not in df_result.columns or "to_id" not in df_result.columns:
            logger.error("Unexpected columns in r5py output: %s", df_result.columns.tolist())
            continue
        
        # Standardize columns
        df_clean = pd.DataFrame({
            "origin_h3": df_result["from_id"].astype(str),
            "destination_id": df_result["to_id"].astype(str),
            "travel_time_p50": df_result[p50_col].apply(to_minutes_float),
            "travel_time_p90": df_result[p90_col].apply(to_minutes_float)
        })
        
        # Filter out unreachable routes (NaN travel times or > 45 mins)
        df_valid = df_clean.dropna(subset=["travel_time_p50"]).copy()
        df_valid = df_valid[df_valid["travel_time_p50"] <= MAX_TIME_MINUTES]
        
        batch_valid_count = len(df_valid)
        total_valid_records += batch_valid_count
        batch_elapsed = time.time() - batch_start_time
        
        if batch_valid_count > 0:
            con.register("df_batch_valid", df_valid)
            con.execute("""
                INSERT OR REPLACE INTO melb_travel_matrix (origin_h3, destination_id, travel_time_p50, travel_time_p90)
                SELECT origin_h3, destination_id, travel_time_p50, travel_time_p90
                FROM df_batch_valid;
            """)
            con.unregister("df_batch_valid")
        
        logger.info(
            "    Completed Batch %d/%d in %.1fs | Stored %d valid reachable routes (Cumulative: %d)",
            chunk_idx + 1, num_chunks, batch_elapsed, batch_valid_count, total_valid_records
        )
        
        # Clean up batch memory and trigger GC
        del chunk_origins
        del ttm
        del df_result
        del df_clean
        del df_valid
        gc.collect()
    
    # 6. Verify and audit database results
    logger.info("=" * 70)
    logger.info("VERIFYING DATABASE PERSISTENCE & MATRIX COVERAGE")
    logger.info("=" * 70)
    
    total_stored = con.execute("SELECT COUNT(*) FROM melb_travel_matrix;").fetchone()[0]
    logger.info("Total reachable origin-destination pairs stored in `melb_travel_matrix`: %d", total_stored)
    
    summary = con.execute("""
        SELECT 
            destination_id,
            COUNT(*) AS reachable_origins,
            ROUND(MIN(travel_time_p50), 1) AS min_p50_mins,
            ROUND(AVG(travel_time_p50), 1) AS avg_p50_mins,
            ROUND(MAX(travel_time_p50), 1) AS max_p50_mins,
            ROUND(AVG(travel_time_p90), 1) AS avg_p90_mins
        FROM melb_travel_matrix
        GROUP BY destination_id
        ORDER BY destination_id;
    """).fetchdf()
    
    logger.info("\nPOIs Accessibility Summary (within 45-min transit cutoff):\n%s", summary.to_string(index=False))
    
    sample_records = con.execute("SELECT * FROM melb_travel_matrix LIMIT 5;").fetchdf()
    logger.info("\nSample Stored Matrix Records:\n%s", sample_records.to_string(index=False))
    
    con.close()
    
    total_elapsed = time.time() - start_total_time
    logger.info("=" * 70)
    logger.info("PHASE 2 ROUTING MATRIX COMPUTATION COMPLETED IN %.1f MINUTES!", total_elapsed / 60.0)
    logger.info("=" * 70)


if __name__ == "__main__":
    compute_and_store_matrix()
