"""
Multimodal Travel Time Matrix Computation for Mumbai Transit Desert Platform (2024 Baseline & 2030 Future State).
Utilizes r5py.TransportNetwork and TravelTimeMatrixComputer (R5 FastRaptor engine)
to compute multimodal transit + walking travel times from Mumbai H3 Resolution-9 grid
centroids to key Strategic Mega-Hubs (POIs).

Features:
- Multi-scenario support: 2024 Baseline (Suburban + BEST) vs 2030 Future State (Suburban + BEST + Metro)
- 18GB JVM Memory allocation (OpenJDK 21) with ForkJoinPool single-thread safety
- WGS84 (EPSG:4326) CRS spatial standard
- Tuesday morning peak departure: 2026-09-08 08:45 AM
- 90-minute max travel time cutoff
- Multimodal routing: Transit (Suburban Local Trains + BEST Buses + Metro Network) + Walk
- Percentiles: p50 (median) and p90 (worst-case)
- Memory-safe origin chunking (5,000 cells/batch) with garbage collection
- Persists to DuckDB `mumbai_travel_matrix` (2024) and `mumbai_travel_matrix_2030` (2030)
"""

import os
import sys
import gc
import glob
import time
import argparse
import logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import duckdb

# Configure Java 21 environment
DEFAULT_JDK_PATH = r"C:\Users\91704\.jdk\jdk-21.0.6+7"
if os.path.exists(DEFAULT_JDK_PATH) and "JAVA_HOME" not in os.environ:
    os.environ["JAVA_HOME"] = DEFAULT_JDK_PATH

# Thread safety & JVM options (14GB heap allocation for r5py)
os.environ["_JAVA_OPTIONS"] = "-Djava.util.concurrent.ForkJoinPool.common.parallelism=1 -Xmx14G"

import r5py
from r5py import TransportMode, TransportNetwork, TravelTimeMatrix

# Alias TravelTimeMatrixComputer for API consistency
TravelTimeMatrixComputer = getattr(r5py, "TravelTimeMatrixComputer", TravelTimeMatrix)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("MumbaiMatrixComputation")

# Paths
DB_PATH = "data/mumbai/processed/mumbai_equity.db"
OSM_PBF_PATH = "data/mumbai/processed/mumbai_roads.osm.pbf"

# Feeds
FEED_BUS = "data/mumbai/raw/gtfs.zip"
FEED_TRAIN = "data/mumbai/processed/train_gtfs.zip"
FEED_METRO_OPERATIONAL = "data/mumbai/processed/mumbai_operational_metro_gtfs.zip"
FEED_METRO_2030 = "data/mumbai/processed/mumbai_2030_metro_gtfs.zip"

FEEDS_2024 = [FEED_BUS, FEED_TRAIN]
FEEDS_CURRENT_METRO = [FEED_BUS, FEED_TRAIN, FEED_METRO_OPERATIONAL]
FEEDS_2030 = [FEED_BUS, FEED_TRAIN, FEED_METRO_2030]

# Strategic Mega-Hubs (POIs) in EPSG:4326
POIS = [
    {
        "id": "BKC",
        "name": "Bandra Kurla Complex (BKC)",
        "lat": 19.0657,
        "lon": 72.8682,
        "category": "Employment"
    },
    {
        "id": "KEM_HOSPITAL",
        "name": "KEM Hospital Parel",
        "lat": 19.0028,
        "lon": 72.8415,
        "category": "Healthcare"
    },
    {
        "id": "IIT_BOMBAY",
        "name": "IIT Bombay Powai",
        "lat": 19.1334,
        "lon": 72.9133,
        "category": "Education"
    },
    {
        "id": "PALLADIUM",
        "name": "Palladium / High Street Phoenix Lower Parel",
        "lat": 18.9940,
        "lon": 72.8248,
        "category": "Commercial"
    }
]

# Routing Parameters
DEPARTURE_DATETIME = datetime(2026, 9, 8, 8, 45, 0)  # Tuesday 08:45 AM peak
MAX_TIME_MINUTES = 90
MAX_TIME = timedelta(minutes=MAX_TIME_MINUTES)
MAX_TIME_WALKING = timedelta(minutes=25)  # 25-min walking radius to reach mega-hub centroids / transfers
MAX_PUBLIC_TRANSPORT_TRANSFERS = 2
PERCENTILES = [50, 90]
CHUNK_SIZE = 5000


def create_destinations_gdf():
    """Create destinations GeoDataFrame in EPSG:4326."""
    gdf = gpd.GeoDataFrame(
        POIS,
        geometry=[Point(p["lon"], p["lat"]) for p in POIS],
        crs="EPSG:4326"
    )
    logger.info("Initialized %d Mumbai Destination Mega-Hubs (EPSG:4326):", len(gdf))
    for idx, row in gdf.iterrows():
        logger.info("  [%s] %s (%s) @ (%.4f, %.4f)", row["id"], row["name"], row["category"], row["lat"], row["lon"])
    return gdf


def load_origins_gdf(db_path=DB_PATH):
    """Load Mumbai H3 grid centroids from DuckDB into a GeoDataFrame (EPSG:4326)."""
    logger.info("Connecting to DuckDB at: %s", db_path)
    con = duckdb.connect(db_path, read_only=True)
    con.execute("LOAD spatial;")
    
    query = "SELECT h3_index AS id, centroid_lng, centroid_lat FROM mumbai_h3_grid ORDER BY h3_index;"
    df = con.execute(query).fetchdf()
    con.close()
    
    logger.info("Loaded %d H3 centroids from DuckDB `mumbai_h3_grid`", len(df))
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


def compute_mumbai_travel_matrix(scenario: str = "current_metro"):
    """
    Orchestrate multi-modal travel time matrix computation using r5py.
    Scenarios:
      - 'legacy' / '2024': BEST Bus + Suburban Rail -> `mumbai_travel_matrix`
      - 'current_metro': BEST Bus + Suburban Rail + Active Metro (79 stns) -> `mumbai_travel_matrix_current_metro`
      - '2030' / 'future_2030': BEST Bus + Suburban Rail + 2030 Metro (178 stns) -> `mumbai_travel_matrix_2030`
    """
    start_total_time = time.time()
    if scenario in ("current_metro", "current"):
        target_table = "mumbai_travel_matrix_current_metro"
        active_feeds = FEEDS_CURRENT_METRO
    elif scenario in ("2030", "future_2030"):
        target_table = "mumbai_travel_matrix_2030"
        active_feeds = FEEDS_2030
    else:
        target_table = "mumbai_travel_matrix"
        active_feeds = FEEDS_2024
    
    logger.info("=" * 70)
    logger.info("STARTING MUMBAI MULTIMODAL TRAVEL TIME MATRIX COMPUTATION")
    logger.info("Scenario: %s | Target Table: %s | Active Feeds: %d", scenario, target_table, len(active_feeds))
    logger.info("=" * 70)
    
    # 1. Check input files
    if not os.path.exists(OSM_PBF_PATH):
        raise FileNotFoundError(f"OSM PBF file not found: {OSM_PBF_PATH}")
    for feed in active_feeds:
        if not os.path.exists(feed):
            raise FileNotFoundError(f"GTFS feed not found: {feed}")
            
    logger.info("OSM PBF Extract: %s (%.1f MB)", OSM_PBF_PATH, os.path.getsize(OSM_PBF_PATH) / (1024 * 1024))
    for feed in active_feeds:
        logger.info("GTFS Feed:       %s (%.2f MB)", feed, os.path.getsize(feed) / (1024 * 1024))
        
    # 2. Build destinations and origins
    destinations_gdf = create_destinations_gdf()
    origins_gdf = load_origins_gdf(DB_PATH)
    total_origins = len(origins_gdf)
    
    # 3. Instantiate TransportNetwork
    logger.info("-" * 70)
    logger.info("INITIALIZING R5 TRANSPORT NETWORK GRAPH (MUMBAI)...")
    logger.info("Building network from %d GTFS feeds + OSM street network...", len(active_feeds))
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
        osm_pbf=OSM_PBF_PATH,
        gtfs=active_feeds
    )
    logger.info("Transport network compiled successfully in %.1f seconds!", time.time() - net_start_time)
    logger.info("-" * 70)
    
    # 4. Prepare DuckDB connection
    con = duckdb.connect(DB_PATH)
    con.execute("LOAD spatial;")
    
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {target_table} (
            origin_h3 VARCHAR,
            destination_id VARCHAR,
            travel_time_p50 DOUBLE,
            travel_time_p90 DOUBLE,
            PRIMARY KEY (origin_h3, destination_id)
        );
    """)
    con.execute(f"DELETE FROM {target_table};")
    logger.info(f"Initialized table `{target_table}` in DuckDB")
    
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
        
        ttm = TravelTimeMatrixComputer(
            transport_network=transport_network,
            origins=chunk_origins,
            destinations=destinations_gdf,
            departure=DEPARTURE_DATETIME,
            max_time=MAX_TIME,
            max_time_walking=MAX_TIME_WALKING,
            max_public_transport_rides=MAX_PUBLIC_TRANSPORT_TRANSFERS + 1,
            percentiles=PERCENTILES,
            transport_modes=transport_modes,
            snap_to_network=True
        )
        
        df_result = pd.DataFrame(ttm)
        p50_col = "travel_time_p50" if "travel_time_p50" in df_result.columns else "travel_time"
        p90_col = "travel_time_p90" if "travel_time_p90" in df_result.columns else p50_col
        
        if "from_id" not in df_result.columns or "to_id" not in df_result.columns:
            logger.error("Unexpected columns in r5py output: %s", df_result.columns.tolist())
            continue
            
        df_clean = pd.DataFrame({
            "origin_h3": df_result["from_id"].astype(str),
            "destination_id": df_result["to_id"].astype(str),
            "travel_time_p50": df_result[p50_col].apply(to_minutes_float),
            "travel_time_p90": df_result[p90_col].apply(to_minutes_float)
        })
        
        # Filter out unreachable routes (> 90 mins or NaN)
        df_valid = df_clean.dropna(subset=["travel_time_p50"]).copy()
        df_valid = df_valid[df_valid["travel_time_p50"] <= MAX_TIME_MINUTES]
        
        batch_valid_count = len(df_valid)
        total_valid_records += batch_valid_count
        batch_elapsed = time.time() - batch_start_time
        
        if batch_valid_count > 0:
            con.register("df_batch_valid", df_valid)
            con.execute(f"""
                INSERT OR REPLACE INTO {target_table} (origin_h3, destination_id, travel_time_p50, travel_time_p90)
                SELECT origin_h3, destination_id, travel_time_p50, travel_time_p90
                FROM df_batch_valid;
            """)
            con.unregister("df_batch_valid")
            
        logger.info(
            "    Completed Batch %d/%d in %.1fs | Stored %d valid reachable routes (Cumulative: %d)",
            chunk_idx + 1, num_chunks, batch_elapsed, batch_valid_count, total_valid_records
        )
        
        del chunk_origins
        del ttm
        del df_result
        del df_clean
        del df_valid
        gc.collect()
        
    # 6. Verify and audit database results
    logger.info("=" * 70)
    logger.info("VERIFYING MUMBAI DATABASE PERSISTENCE & MATRIX COVERAGE (%s)", scenario)
    logger.info("=" * 70)
    
    total_stored = con.execute(f"SELECT COUNT(*) FROM {target_table};").fetchone()[0]
    logger.info("Total reachable origin-destination pairs stored in `%s`: %d", target_table, total_stored)
    
    summary = con.execute(f"""
        SELECT 
            destination_id,
            COUNT(*) AS reachable_origins,
            ROUND(MIN(travel_time_p50), 1) AS min_p50_mins,
            ROUND(AVG(travel_time_p50), 1) AS avg_p50_mins,
            ROUND(MAX(travel_time_p50), 1) AS max_p50_mins,
            ROUND(AVG(travel_time_p90), 1) AS avg_p90_mins
        FROM {target_table}
        GROUP BY destination_id
        ORDER BY destination_id;
    """).fetchdf()
    
    logger.info("\nMumbai POIs Accessibility Summary (within 90-min transit cutoff):\n%s", summary.to_string(index=False))
    
    con.close()
    
    total_elapsed = time.time() - start_total_time
    logger.info("=" * 70)
    logger.info("MUMBAI TRAVEL TIME MATRIX COMPUTATION (%s) COMPLETED IN %.1f MINUTES!", scenario, total_elapsed / 60.0)
    logger.info("=" * 70)
    return total_stored


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute multimodal travel time matrix for Mumbai")
    parser.add_argument(
        "--scenario",
        choices=["legacy", "2024", "current_metro", "current", "2030", "future_2030"],
        default="current_metro",
        help="Simulation scenario: 'legacy' (no metro), 'current_metro' (79 stns), or '2030' (178 stns)"
    )
    args = parser.parse_args()
    
    compute_mumbai_travel_matrix(scenario=args.scenario)
