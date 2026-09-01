# TASK_PLAN.md — Multimodal Transit Desert Platform (Melbourne MVP)

> **Last Updated:** 2026-09-02T00:10:00+10:00
> **Current Phase:** Phase 4 — COMPLETED | Full Melbourne MVP Operational

---

## Phase 1: Workspace Setup & Data Ingestion (COMPLETED)

### 1.0 Environment
- [x] **1.0.1** Configure `~/.config/r5py.yml` with `max-memory: 12G` (GEMINI.md rule 1) and JDK 21 runtime
- [x] **1.0.2** Setup Python 3.11 virtual environment (`.venv`) and install `duckdb`, `r5py`, `geopandas`, `h3`, `osmnx`, `fastapi`, `uvicorn`, `pandas`, `shapely`, `pyogrio`, `openpyxl`
- [x] **1.0.3** Ensure directory structure exists: `data/raw/`, `data/processed/gtfs_feeds/`, `src/`

### 1.1 GTFS Preprocessing (gtfs-osm-preprocessor skill)
- [x] **1.1.1** Write `src/preprocess_gtfs.py` using `zipfile` + `pandas`
  - Unpacks nested Victoria GTFS subdirectories
  - Validates and handles schedule integrity (all 8 feeds validated with active schedules)
  - Repackages clean flat root-level feeds to `data/processed/gtfs_feeds/`
- [x] **1.1.2** Run `src/preprocess_gtfs.py`: Produced 8 clean feeds (`metro_train.zip`, `metro_tram.zip`, `metro_bus.zip`, `vline_regional_train.zip`, `regional_coach.zip`, `regional_bus.zip`, `telebus.zip`, `night_bus.zip`)

### 1.2 DuckDB Initialization
- [x] **1.2.1** Write `src/init_db.py`
  - Creates `data/processed/transit_equity.db`
  - Installs & loads `spatial` extension
  - Creates schemas: `melb_demographics`, `melb_h3_grid`, `melb_travel_matrix`
- [x] **1.2.2** Run `src/init_db.py`: Database and spatial extension verified

### 1.3 Spatial Demographics Ingestion (geospatial-audit rules)
- [x] **1.3.1** Write `src/ingest_demographics.py`
  - Ingests ABS SA1 polygons from `data/raw/ASGS_2021_Main_Structure_GDA2020.gpkg`
  - Transforms CRS from EPSG:7844 to EPSG:4326 via GeoPandas
  - Enforces strict Python assertion `assert gdf.crs.to_epsg() == 4326`
  - Merges SEIFA IRSD/IRSAD and population metrics from Excel
  - Ingests 11,487 SA1 polygons into DuckDB `melb_demographics`
- [x] **1.3.2** Run `src/ingest_demographics.py`: Verified 11,487 records with density and SEIFA deciles

### 1.4 H3 Grid Generation
- [x] **1.4.1** Write `src/generate_h3_grid.py`
  - Bounding box: `lng_min=144.40, lat_min=-38.50, lng_max=145.80, lat_max=-37.40`
  - Resolution 9 H3 hexagons
  - MANDATORY: Centroids extracted via `h3.cell_to_latlng()` (H3 polyfill join strictly banned)
  - Stores `(h3_index, centroid_lat, centroid_lng, centroid_geom)` in DuckDB `melb_h3_grid`
- [x] **1.4.2** Run `src/generate_h3_grid.py`: 121,802 cells created; verified spatial join via `ST_Intersects` (73,951 hex centroids intersecting Greater Melbourne SA1 boundaries in 2.0s)

---

## Phase 2: Network Graph & Routing Engine (COMPLETED)

- [x] **2.1** Set up Java 21 environment and configure `r5py` with 18.8GB JVM allocation & ForkJoin single-thread safety
- [x] **2.2** Define Target Destinations GeoDataFrame (EPSG:4326):
  - Royal Melbourne Hospital (`id: RMH`, Lat: -37.7990, Lon: 144.9560)
  - Monash University Clayton (`id: MONASH_CLAYTON`, Lat: -37.9150, Lon: 145.1300)
  - Chadstone Shopping Centre (`id: CHADSTONE`, Lat: -37.8860, Lon: 145.0830)
- [x] **2.3** Extract Origin Centroids GeoDataFrame (EPSG:4326) from DuckDB `melb_h3_grid` (121,802 cells)
- [x] **2.4** Implement `src/compute_travel_matrix.py`:
  - Initialize `r5py.TransportNetwork` with OSM PBF and all 8 flat GTFS zip feeds
  - Configure `r5py.TravelTimeMatrixComputer` with departure `2026-09-08 08:00:00` and `max_time=45` minutes
  - Implement memory-safe batching/chunking for origins (7 batches of 20,000 cells) with garbage collection
  - Filter out unreachable routes (NaN travel times) prior to insertion
  - Persist computed travel times (`travel_time_p50`, `travel_time_p90`) into DuckDB `melb_travel_matrix`
- [x] **2.5** Execute `src/compute_travel_matrix.py`: 2,598 reachable origin-destination pairs populated across RMH (1,104), Monash Clayton (789), and Chadstone (705) in 40.4 minutes.

---

## Phase 3: Spatial Joins & Equity Scoring (COMPLETED)

- [x] **3.1** Implement `src/compute_equity_scores.py`:
  - Execute DuckDB `ST_Intersects` spatial join between H3 centroids (WGS84) and ABS SA1 demographic polygons
  - Left join with `melb_travel_matrix`, imputing 45.0-minute penalty for unreachable pairs
  - Compute linear decay accessibility scores (`score_rmh`, `score_monash`, `score_chadstone`, composite `accessibility_score`)
  - Compute normalized demographic vulnerability score (60% inverted SEIFA IRSD disadvantage + 40% log-normalized population density)
  - Compute composite `transit_desert_index = vulnerability_score * (1.0 - accessibility_score)`
- [x] **3.2** Materialize table `melb_equity_scores` in DuckDB (121,802 rows, 27 columns)
- [x] **3.3** Create analytical SQL view `v_transit_deserts` filtering for top 20th percentile transit deserts (12,959 cells with `transit_desert_index >= 0.3447`)
- [x] **3.4** Validate match rates (73,951 SA1-matched cells) and export priority suburban desert rankings

---

## Phase 4: API & Visualization (COMPLETED)

- [x] **4.1** Implement FastAPI backend ([`src/api/main.py`](file:///c:/Users/91704/Desktop/transit-desert/src/api/main.py)):
  - Health check endpoint `GET /api/v1/health` with table inventories
  - GeoJSON feature server `GET /api/v1/transit-deserts` streaming H3 hexagon 3D polygon geometries
  - Aggregated leaderboard endpoint `GET /api/v1/suburbs/top`
  - Statistical distributions and totals `GET /api/v1/stats`
  - Strategic POIs endpoint `GET /api/v1/pois`
  - Static frontend mount serving `/` and `/static`
- [x] **4.2** Build MapLibre GL JS 3D interactive frontend ([`frontend/`](file:///c:/Users/91704/Desktop/transit-desert/frontend/)):
  - Dark glassmorphism UI centered on Melbourne (`[144.9631, -37.8136]`, pitch 45°, bearing -15°)
  - Dynamic 3D `fill-extrusion` hexagonal layers colored with multi-stop color ramps
  - Real-time metric switcher (Transit Desert Index $TDI$, Vulnerability $V_i$, Accessibility $A_i$)
  - Dynamic 3D height scale slider (0.2x to 3.5x) and Min TDI cutoff filter
  - Interactive top 10 worst suburbs leaderboard with camera fly-to animation
  - Interactive Hexagon Inspector card showing exact SA1, SEIFA decile, density, population, and peak transit travel times (RMH, Monash Clayton, Chadstone)
  - 3D custom glowing POI markers
- [x] **4.3** End-to-end browser subagent verification and recording
