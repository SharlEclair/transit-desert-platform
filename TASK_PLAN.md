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

---

## Phase 5: The Mumbai Adaptation (IN PROGRESS)

### 5.1 Data Setup and Profiling (COMPLETED)
- [x] **5.1.1** Initialize isolated Mumbai directory structure (`data/mumbai/`, `src/mumbai/`).
- [x] **5.1.2** Create `MUMBAI_PLAN.md` outlining the architecture and data inventory.
- [x] **5.1.3** Write and execute `src/mumbai/inspect_data.py` to profile `gtfs.zip`, Census CSV, Slum KML, and Local Train CSVs.

### 5.2 Local Train Schedule Harmonization to GTFS (COMPLETED)
- [x] **5.2.1** Implement `src/mumbai/harmonize_trains.py`:
  - Un-pivot all 54 timetable CSV files using block detection and monotonic time validation
  - Map station names/acronyms to high-precision WGS84 coordinates across 119 suburban stations
  - Handle midnight rollover and deduplicate consecutive identical stations
  - Generate full GTFS tables: `agency.txt`, `calendar.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`, `stops.txt`
  - Package clean feed into `data/mumbai/processed/train_gtfs.zip` (4,957 trips, 79,343 stop times)

### 5.3 Spatial Demographics & Vulnerability Proxy (COMPLETED)
- [x] **5.3.1** Implement `src/mumbai/build_demographics.py`:
  - Initialize DuckDB database `data/mumbai/processed/mumbai_equity.db` with spatial extension
  - Generate H3 Resolution 9 grid (10,891 cells) with exact `cell_to_latlng()` centroids
  - Flatten 3D slum KML (`POLYGON Z`) to 2D `POLYGON` (EPSG:4326) and ingest 2,542 polygons to `mumbai_slums`
  - Compute spatial `ST_Intersects` join to assign baseline vulnerability proxy (`1.0` for 360 slum cells, `0.2` baseline)
  - Ingest 2011 Census (`mumbai_ward_census`) and BMC Ward boundaries (`mumbai_bmc_wards`)

### 5.4 Network Graph & Routing Engine (COMPLETED)
- [x] **5.4.1** Implement `src/mumbai/extract_mumbai_osm.py`:
  - 2-pass reference-complete extraction clipping regional OSM PBF to Greater Mumbai bbox (`data/mumbai/processed/mumbai_roads.osm.pbf`, 11.58 MB, 1.33M nodes, 176K ways) to adhere to R5's geographic extent limit (< 975,000 km²)
- [x] **5.4.2** Implement and execute `src/mumbai/compute_travel_matrix.py`:
  - Configured OpenJDK 21 with 10GB JVM heap allocation and single-thread safety
  - Compiled `r5py.TransportNetwork` from `mumbai_roads.osm.pbf`, BEST bus `gtfs.zip`, and suburban train `train_gtfs.zip` in 64.2s
  - Defined 4 Destination Mega-Hubs: `BKC`, `KEM_HOSPITAL`, `IIT_BOMBAY`, `PALLADIUM`
  - Computed travel time matrix across 10,891 H3 origins (Tuesday 08:45 AM peak, 90-min cutoff, Transit + Walk)
  - Persisted 24,299 reachable origin-destination pairs in DuckDB `mumbai_travel_matrix`

### 5.5 Spatial Equity Scoring & Informal Settlement Desert Analysis (COMPLETED)
- [x] **5.5.1** Implement and execute `src/mumbai/calculate_equity.py`:
  - Joined `mumbai_demographics` (10,891 cells) with `mumbai_travel_matrix`
  - Imputed 90.0-minute penalty for unreachable origin-destination pairs
  - Computed 4 individual mega-hub accessibility scores ($A_{i, \text{BKC}}$, $A_{i, \text{KEM}}$, $A_{i, \text{IIT}}$, $A_{i, \text{PAL}}$) and composite $A_i$
  - Calculated composite Transit Desert Index ($TDI_i = V_i \times (1.0 - A_i)$)
  - Materialized table `mumbai_equity_scores` in `mumbai_equity.db` (10,891 rows)
  - Constructed view `v_mumbai_transit_deserts` filtering for 194 high-severity transit desert cells ($TDI_i \ge 0.5$)

---

## Phase 6: Multi-City Interactive Geospatial Dashboard (COMPLETED)

### 6.1 Multi-City API Router & Geospatial Endpoints (COMPLETED)
- [x] **6.1.1** Implement `src/api/mumbai_router.py`:
  - `GET /api/v1/mumbai/health`: Database connection and table verification
  - `GET /api/v1/mumbai/transit-deserts`: Optimized GeoJSON FeatureCollection streaming 3D H3 hexagons with TDI, accessibility, vulnerability, travel times, and slum status
  - `GET /api/v1/mumbai/deserts/top`: Priority transit desert leaderboard with sorting by TDI
  - `GET /api/v1/mumbai/stats`: Statistical distributions for accessibility, vulnerability, and TDI
  - `GET /api/v1/mumbai/pois`: Mega-Hub reachability metadata (BKC, KEM Hospital, IIT Bombay, Palladium)
  - `GET /api/v1/mumbai/slums`: GeoJSON stream of 2,542 flattened 2D slum cluster polygons
  - `GET /api/v1/mumbai/wards`: GeoJSON stream of 24 BMC administrative ward boundaries
- [x] **6.1.2** Update `src/api/main.py`:
  - Mount `mumbai_router`
  - Implement `/api/v1/cities` discovery endpoint returning supported cities (Melbourne & Mumbai)
- [x] **6.1.3** Implement integration test suite `tests/test_mumbai_api.py` (9 passing tests)

### 6.2 Multi-City Switcher & Advanced Frontend Interactivity (COMPLETED)
- [x] **6.2.1** Update `frontend/index.html`, `frontend/style.css`, and `frontend/app.js`:
  - Modular city selector (Melbourne $\leftrightarrow$ Mumbai) with smooth fly-to animations
  - Dynamic 3D hexagon extrusion layer with metric switching (TDI, Accessibility, Vulnerability)
  - Custom thematic layer toggles (Slum Clusters overlay, BMC Ward boundaries, Mega-Hub POI glow markers)
  - Interactive Hexagon Inspector displaying commute times to BKC, KEM, IIT Bombay, and Palladium
  - Real-time controls: 3D Height Extrusion Slider (0.2x to 4.0x), Minimum TDI Cutoff, and Only Slums Filter
  - Priority Leaderboard with camera fly-to on item click

### 6.3 Verification & Visual Validation (COMPLETED)
- [x] **6.3.1** Browser subagent end-to-end testing of multi-city transitions, 3D rendering, and inspector interactions (zero console errors, session demo recorded).

---

## Phase 7: Mumbai 2030 Metro Simulation & Release Packaging (COMPLETED)

### 7.1 KML v3 Extraction & 100% Station Entity Resolution
- [x] **7.1.1** Ingested `Mumbai Metro v3.kml` and programmatically removed cancelled "National College" (Line 2B).
- [x] **7.1.2** Implemented `src/mumbai/finalize_kml_mapping.py` with alias dictionary and regex normalization; achieved 100% match rate across all 177 target station records (79 operational, 98 under-construction).
- [x] **7.1.3** Implemented `src/mumbai/build_final_geojsons.py` exporting `mumbai_metro_stations_resolved.geojson`, `mumbai_metro_tracks_styled.geojson`, and `mumbai_transit_lines.geojson`.

### 7.2 Dual GTFS Feeds & Multimodal Matrix Simulation
- [x] **7.2.1** Implemented `src/mumbai/synthesize_future_gtfs.py` generating `mumbai_operational_metro_gtfs.zip` (79 stops) and `mumbai_2030_metro_gtfs.zip` (177 stops) at 35 km/h commercial speed.
- [x] **7.2.2** Re-computed `mumbai_travel_matrix_current_metro` (22,068 reachable pairs) and `mumbai_travel_matrix_2030` (22,106 reachable pairs) via `src/mumbai/compute_travel_matrix.py`.
- [x] **7.2.3** Executed `src/mumbai/materialize_2030_equity.py` materializing DuckDB views `v_mumbai_equity_master` and `v_mumbai_equity_comparison`.

### 7.3 Security, Basemaps & Repository Finalization
- [x] **7.3.1** Configured `.env.example` and dynamic `/api/v1/config` API key retrieval.
- [x] **7.3.2** Upgraded `frontend/app.js` to high-performance CARTO Vector Basemaps (`dark-matter-gl-style/style.json`) with `transformRequest` API key authentication.
- [x] **7.3.3** Standardized `.gitignore`, added MIT `LICENSE`, and authored comprehensive portfolio `README.md`.



