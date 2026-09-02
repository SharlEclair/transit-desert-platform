# PROGRESS.md — Multimodal Transit Desert Platform

---

## Session Log

### Session 1 — 2026-09-01T21:58:00+10:00

**Status:** Phase 1 (Workspace Setup & Data Ingestion) COMPLETED SUCCESSFULLY.

**Actions Taken This Session:**
- Configured JVM heap limit to **12GB** in `~/.config/r5py.yml` (max-memory: 12G).
- Initialized Python 3.11 virtual environment (`.venv`) and installed core dependencies (`duckdb`, `r5py`, `geopandas`, `h3`, `osmnx`, `fastapi`, `uvicorn`, `pandas`, `shapely`, `pyogrio`, `openpyxl`).
- Implemented and executed `src/preprocess_gtfs.py` (utilizing the `gtfs-osm-preprocessor` skill):
  - Extracted 8 nested feeds from `data/raw/gtfs.zip`.
  - Validated calendar schedules and repackaged into flat root-level archives in `data/processed/gtfs_feeds/` (Train, Tram, Bus, Regional, etc.).
- Implemented and executed `src/init_db.py`:
  - Initialized `data/processed/transit_equity.db`.
  - Loaded DuckDB `spatial` extension.
  - Created schemas for `melb_demographics`, `melb_h3_grid`, and `melb_travel_matrix`.
- Implemented and executed `src/ingest_demographics.py` (incorporating `geospatial-audit` rules):
  - Ingested 11,487 SA1 polygons for Greater Melbourne from `data/raw/ASGS_2021_Main_Structure_GDA2020.gpkg`.
  - Transformed CRS from EPSG:7844 to EPSG:4326.
  - Enforced Python assertion `assert gdf.crs.to_epsg() == 4326` prior to DB insertion.
  - Merged SEIFA IRSD/IRSAD scores and computed population densities.
- Implemented and executed `src/generate_h3_grid.py` (incorporating `geospatial-audit` rules):
  - Generated 121,802 H3 Resolution-9 hexagons across the expanded bounding box (144.40 to 145.80, -38.50 to -37.40).
  - Extracted centroids strictly using `h3.cell_to_latlng()` without polyfill.
  - Saved as `ST_Point` geometries in DuckDB `melb_h3_grid`.
- Verified spatial join integrity: Executed DuckDB `ST_Intersects` join matching 73,951 H3 centroids against SA1 polygons in 2.03 seconds.

**Artifacts & Code Files Created:**
- [r5py config](file:///C:/Users/91704/.config/r5py.yml)
- [src/preprocess_gtfs.py](file:///c:/Users/91704/Desktop/transit-desert/src/preprocess_gtfs.py)
- [src/init_db.py](file:///c:/Users/91704/Desktop/transit-desert/src/init_db.py)
- [src/ingest_demographics.py](file:///c:/Users/91704/Desktop/transit-desert/src/ingest_demographics.py)
- [src/generate_h3_grid.py](file:///c:/Users/91704/Desktop/transit-desert/src/generate_h3_grid.py)
- [data/processed/transit_equity.db](file:///c:/Users/91704/Desktop/transit-desert/data/processed/transit_equity.db)
- [data/processed/gtfs_feeds/](file:///c:/Users/91704/Desktop/transit-desert/data/processed/gtfs_feeds/)

---

### Session 2 — 2026-09-01T23:18:00+10:00

**Status:** Phase 2 (The Network Graph & Routing Engine) COMPLETED SUCCESSFULLY.

**Actions Taken This Session:**
- Configured OpenJDK 21 runtime at `C:\Users\91704\.jdk\jdk-21.0.6+7` with 18.88 GB allocated JVM heap space.
- Identified and fixed R5 GTFS parsing constraint by pruning 0-data-row optional tables (`transfers.txt`, `pathways.txt`) in `src/preprocess_gtfs.py` across all 8 feeds to prevent `EmptyTableError`.
- Configured JVM `-Djava.util.concurrent.ForkJoinPool.common.parallelism=1` to guarantee thread-safe construction of stop-to-stop transfer distance tables in `r5py/util/jvm.py`.
- Implemented `src/compute_travel_matrix.py`:
  - Built `r5py.TransportNetwork` from OSM PBF (`data/raw/osm/victoria-latest.osm.pbf`) and 8 flat GTFS zip feeds (`data/processed/gtfs_feeds/`).
  - Created GeoDataFrame (EPSG:4326) for 3 strategic POIs: Royal Melbourne Hospital (`RMH`), Monash University Clayton (`MONASH_CLAYTON`), and Chadstone Shopping Centre (`CHADSTONE`).
  - Extracted 121,802 H3 Resolution-9 origins from DuckDB `melb_h3_grid`.
  - Executed matrix computation with departure Tuesday 2026-09-08 08:00 AM and 45-minute cutoff across 7 batches (20,000 origins/batch) with proactive memory cleanup and garbage collection.
  - Filtered out unreachable / `NaN` routes prior to streaming.
  - Populated DuckDB `melb_travel_matrix` with 2,598 reachable origin-destination pairs.
- Verified database persistence and matrix accessibility distributions:
  - **Royal Melbourne Hospital (`RMH`)**: 1,104 reachable origins | Mean p50: 35.0 mins | Min p50: 3.0 mins
  - **Monash University Clayton (`MONASH_CLAYTON`)**: 789 reachable origins | Mean p50: 35.1 mins | Min p50: 4.0 mins
  - **Chadstone Shopping Centre (`CHADSTONE`)**: 705 reachable origins | Mean p50: 36.2 mins | Min p50: 4.0 mins

**Artifacts & Code Files Created / Modified:**
- [src/compute_travel_matrix.py](file:///c:/Users/91704/Desktop/transit-desert/src/compute_travel_matrix.py)
- [src/preprocess_gtfs.py](file:///c:/Users/91704/Desktop/transit-desert/src/preprocess_gtfs.py)
- [r5py jvm config](file:///c:/Users/91704/Desktop/transit-desert/.venv/Lib/site-packages/r5py/util/jvm.py)
- [data/processed/transit_equity.db](file:///c:/Users/91704/Desktop/transit-desert/data/processed/transit_equity.db)

**Next Immediate Steps (Phase 3):**
1. Execute spatial join (`ST_Intersects`) in DuckDB linking `melb_h3_grid`, `melb_demographics` (SEIFA, population density), and `melb_travel_matrix`.
2. Formulate multimodal Transit Accessibility Score per H3 hexagon.
3. Construct SQL View `transit_deserts` capturing underserved high-density/low-SEIFA populations.

---

### Session 3 — 2026-09-01T23:48:00+10:00

**Status:** Phase 3 (Spatial Joins & Equity Scoring) COMPLETED SUCCESSFULLY.

**Actions Taken This Session:**
- Implemented and executed [`src/compute_equity_scores.py`](file:///c:/Users/91704/Desktop/transit-desert/src/compute_equity_scores.py):
  - Performed high-performance DuckDB spatial join using `ST_Intersects` between 121,802 H3 Resolution-9 centroids (`melb_h3_grid`) and 11,487 ABS SA1 demographic polygons (`melb_demographics`, EPSG:4326).
  - Left-joined the pivoted `melb_travel_matrix`, assigning effective travel times (45.0m penalty for unreachable destinations).
  - Computed individual linear decay accessibility scores (`score_rmh`, `score_monash`, `score_chadstone`) and composite `accessibility_score` (0.0 to 1.0).
  - Constructed normalized demographic `vulnerability_score` (0.0 to 1.0) weighting 60% inverted ABS SEIFA IRSD socio-economic disadvantage and 40% log-normalized population density.
  - Formulated composite `transit_desert_index = vulnerability_score * (1.0 - accessibility_score)`.
- Materialized `melb_equity_scores` table in DuckDB (121,802 rows, 27 fields).
- Created analytical view `v_transit_deserts` filtering for top 20th percentile transit deserts (`transit_desert_index >= 0.3447`, 12,959 high-priority cells).
- Verified statistical distributions and suburban rankings:
  - **Match Rate:** 73,951 H3 centroids intersect Greater Melbourne SA1 polygons (64,792 in populated SA1s).
  - **Identified Priority Desert Corridors:** Dandenong South, Meadow Heights, St Albans, Kings Park, Laverton, Doveton, Noble Park, Roxburgh Park, Broadmeadows.

**Artifacts & Code Files Created / Modified:**
- [src/compute_equity_scores.py](file:///c:/Users/91704/Desktop/transit-desert/src/compute_equity_scores.py)
- [data/processed/transit_equity.db](file:///c:/Users/91704/Desktop/transit-desert/data/processed/transit_equity.db)

**Next Immediate Steps (Phase 4):**
1. Implement FastAPI backend endpoints (`/api/health`, `/api/deserts`, `/api/isochrones`, `/api/equity-summary`).
2. Build responsive MapLibre GL JS 3D hexagonal visualization with dynamic parameter controls.

---

### Session 4 — 2026-09-02T00:10:00+10:00

**Status:** Phase 4 (API & Interactive 3D Visualization) COMPLETED SUCCESSFULLY.

**Actions Taken This Session:**
- Built and launched FastAPI backend ([`src/api/main.py`](file:///c:/Users/91704/Desktop/transit-desert/src/api/main.py)):
  - Read-only DuckDB spatial connection with query acceleration.
  - Endpoint `GET /api/v1/health`: Returns system inventory and DuckDB connection status.
  - Endpoint `GET /api/v1/transit-deserts`: Streams GeoJSON FeatureCollection with 3D H3 hexagon polygons and full demographic/travel time properties.
  - Endpoint `GET /api/v1/suburbs/top`: Serves aggregated suburb leaderboard ranking.
  - Endpoint `GET /api/v1/stats`: Serves metric distribution quantiles and population totals.
  - Endpoint `GET /api/v1/pois`: Serves POIs metadata and reachability metrics.
  - Static file server hosting `frontend/` at root URL.
- Developed modern MapLibre GL JS 3D web application ([`frontend/`](file:///c:/Users/91704/Desktop/transit-desert/frontend/)):
  - Dark glassmorphism theme (`frontend/style.css`, `frontend/index.html`, `frontend/app.js`).
  - Dynamic 3D `fill-extrusion` hexagonal columns with multi-stop color ramps.
  - Real-time metric toggle: Transit Desert Index ($TDI$), Vulnerability ($V_i$), Accessibility ($A_i$).
  - Dynamic 3D height scale slider (0.2x to 3.5x) and Min TDI cutoff filter.
  - Interactive top 10 worst suburbs leaderboard with camera fly-to animation.
  - Interactive Hexagon Inspector card showing SA1 code, SEIFA decile, density, and peak transit travel times to Royal Melbourne Hospital, Monash University Clayton, and Chadstone Shopping Centre.
  - Custom glowing 3D POI markers.
- Executed browser subagent testing:
  - Verified full UI interactivity, metric switching, leaderboard fly-to, height extrusion slider, and inspector population.
  - Recorded session demonstration video.

**Artifacts & Code Files Created / Modified:**
- [src/api/main.py](file:///c:/Users/91704/Desktop/transit-desert/src/api/main.py)
- [frontend/index.html](file:///c:/Users/91704/Desktop/transit-desert/frontend/index.html)
- [frontend/style.css](file:///c:/Users/91704/Desktop/transit-desert/frontend/style.css)
- [frontend/app.js](file:///c:/Users/91704/Desktop/transit-desert/frontend/app.js)
- [TASK_PLAN.md](file:///c:/Users/91704/Desktop/transit-desert/TASK_PLAN.md)
- [PROGRESS.md](file:///c:/Users/91704/Desktop/transit-desert/PROGRESS.md)

---

### Session 5 — 2026-09-02T03:15:00+10:00

**Status:** Phase 5 (The Mumbai Adaptation: Phases 5.1 to 5.4) COMPLETED SUCCESSFULLY.

**Actions Taken This Session:**
- Generated `MUMBAI_PLAN.md` and isolated Mumbai architecture under `src/mumbai/` and `data/mumbai/`.
- Implemented and executed [`src/mumbai/inspect_data.py`](file:///c:/Users/91704/Desktop/transit-desert/src/mumbai/inspect_data.py) to profile GTFS, Census CSV, Slum KML, and Local Train CSVs.
- Implemented and executed [`src/mumbai/harmonize_trains.py`](file:///c:/Users/91704/Desktop/transit-desert/src/mumbai/harmonize_trains.py):
  - Un-pivoted all 54 wide-format timetable CSVs.
  - Standardized station acronyms and geocoded 119 suburban rail stations to EPSG:4326.
  - Generated compliant GTFS feed [`data/mumbai/processed/train_gtfs.zip`](file:///c:/Users/91704/Desktop/transit-desert/data/mumbai/processed/train_gtfs.zip) (4,957 trips, 79,343 stop times).
- Implemented and executed [`src/mumbai/build_demographics.py`](file:///c:/Users/91704/Desktop/transit-desert/src/mumbai/build_demographics.py):
  - Initialized spatial DuckDB database [`data/mumbai/processed/mumbai_equity.db`](file:///c:/Users/91704/Desktop/transit-desert/data/mumbai/processed/mumbai_equity.db).
  - Generated 10,891 H3 Resolution-9 hexagons across Mumbai Metropolitan limits.
  - Flattened 2,542 3D KML slum polygons (`POLYGON Z` to 2D `EPSG:4326`).
  - Executed spatial `ST_Intersects` join: identified 360 informal settlement cells (`vulnerability = 1.0`) and 10,531 baseline cells (`0.2`).
  - Ingested 2011 Census (`mumbai_ward_census`) and BMC Ward boundaries (`mumbai_bmc_wards`).
- Implemented [`src/mumbai/extract_mumbai_osm.py`](file:///c:/Users/91704/Desktop/transit-desert/src/mumbai/extract_mumbai_osm.py):
  - Built a 2-pass reference-complete extraction clipping the Western Zone OSM PBF to Greater Mumbai (`data/mumbai/processed/mumbai_roads.osm.pbf`, 11.58 MB, 1.33M nodes, 176K ways) to adhere to Conveyal R5's geographic extent limit (< 975,000 km²).
- Implemented and executed [`src/mumbai/compute_travel_matrix.py`](file:///c:/Users/91704/Desktop/transit-desert/src/mumbai/compute_travel_matrix.py):
  - Initialized R5 multimodal transport network from `mumbai_roads.osm.pbf`, BEST bus `gtfs.zip`, and local train `train_gtfs.zip`.
  - Configured 4 Destination Mega-Hubs: `BKC`, `KEM_HOSPITAL`, `IIT_BOMBAY`, `PALLADIUM`.
  - Computed multimodal travel times for 10,891 H3 origins (Tuesday 08:45 AM peak, 90-min cutoff, Transit + Walk).
  - Populated DuckDB `mumbai_travel_matrix` with **24,299 reachable origin-destination pairs** in 7.3 minutes.

**Artifacts & Code Files Created / Modified:**
- [MUMBAI_PLAN.md](file:///c:/Users/91704/Desktop/transit-desert/MUMBAI_PLAN.md)
- [src/mumbai/inspect_data.py](file:///c:/Users/91704/Desktop/transit-desert/src/mumbai/inspect_data.py)
- [src/mumbai/harmonize_trains.py](file:///c:/Users/91704/Desktop/transit-desert/src/mumbai/harmonize_trains.py)
- [src/mumbai/build_demographics.py](file:///c:/Users/91704/Desktop/transit-desert/src/mumbai/build_demographics.py)
- [src/mumbai/extract_mumbai_osm.py](file:///c:/Users/91704/Desktop/transit-desert/src/mumbai/extract_mumbai_osm.py)
- [src/mumbai/compute_travel_matrix.py](file:///c:/Users/91704/Desktop/transit-desert/src/mumbai/compute_travel_matrix.py)
- [src/mumbai/calculate_equity.py](file:///c:/Users/91704/Desktop/transit-desert/src/mumbai/calculate_equity.py)
- [TASK_PLAN.md](file:///c:/Users/91704/Desktop/transit-desert/TASK_PLAN.md)
- [PROGRESS.md](file:///c:/Users/91704/Desktop/transit-desert/PROGRESS.md)

---

### Session 6 — 2026-09-02T03:50:00+10:00

**Status:** Phase 6 (Multi-City Interactive Geospatial Dashboard & Unified API) COMPLETED SUCCESSFULLY.

**Actions Taken This Session:**
- Implemented [`src/api/mumbai_router.py`](file:///c:/Users/91704/Desktop/transit-desert/src/api/mumbai_router.py):
  - GeoJSON 3D H3 hexagon streaming (`/api/v1/mumbai/transit-deserts`), Top Deserts leaderboard (`/api/v1/mumbai/deserts/top`), Statistical distributions (`/api/v1/mumbai/stats`), Strategic POIs (`/api/v1/mumbai/pois`), 2D Slum boundaries (`/api/v1/mumbai/slums`), and BMC Wards (`/api/v1/mumbai/wards`).
- Updated [`src/api/main.py`](file:///c:/Users/91704/Desktop/transit-desert/src/api/main.py):
  - Mounted Mumbai API router.
  - Implemented `/api/v1/cities` discovery endpoint.
- Implemented and executed integration test suite [`tests/test_mumbai_api.py`](file:///c:/Users/91704/Desktop/transit-desert/tests/test_mumbai_api.py) (all 9 tests passed in 4.85s).
- Implemented Frontend Multi-City 3D Geospatial Engine:
  - [`frontend/index.html`](file:///c:/Users/91704/Desktop/transit-desert/frontend/index.html): Responsive multi-city sidebar, City Switcher pills, thematic overlay toggles, and loading state.
  - [`frontend/style.css`](file:///c:/Users/91704/Desktop/transit-desert/frontend/style.css): Dark mode glassmorphism UI, glow effects, and responsive layout.
  - [`frontend/app.js`](file:///c:/Users/91704/Desktop/transit-desert/frontend/app.js): Multi-city state orchestrator, smooth MapLibre GL `flyTo` transitions, dynamic 3D `fill-extrusion` rendering, custom thematic layer controls (Informal Slums & BMC Wards), dynamic Hexagon Inspector, and Priority Leaderboard.
- Executed end-to-end Browser Subagent verification:
  - Verified default Melbourne load and 3D extrusion.
  - Verified seamless camera transition to Greater Mumbai.
  - Verified #1 severe transit desert camera fly-to and Inspector population (travel times to BKC, KEM, IIT Bombay, Palladium).
  - Verified metric switching (TDI, Accessibility, Vulnerability) and Slum layer toggling.
  - Verified zero browser console errors.
  - Captured session demonstration video.

**Artifacts & Code Files Created / Modified:**
- [src/api/mumbai_router.py](file:///c:/Users/91704/Desktop/transit-desert/src/api/mumbai_router.py)
- [src/api/main.py](file:///c:/Users/91704/Desktop/transit-desert/src/api/main.py)
- [tests/test_mumbai_api.py](file:///c:/Users/91704/Desktop/transit-desert/tests/test_mumbai_api.py)
- [frontend/index.html](file:///c:/Users/91704/Desktop/transit-desert/frontend/index.html)
- [frontend/style.css](file:///c:/Users/91704/Desktop/transit-desert/frontend/style.css)
- [frontend/app.js](file:///c:/Users/91704/Desktop/transit-desert/frontend/app.js)
- [TASK_PLAN.md](file:///c:/Users/91704/Desktop/transit-desert/TASK_PLAN.md)
- [PROGRESS.md](file:///c:/Users/91704/Desktop/transit-desert/PROGRESS.md)

---

### Session 6 — 2026-09-02T09:25:00+10:00

**Status:** Mumbai 2030 Multimodal What-If Transit Equity Simulation COMPLETED SUCCESSFULLY.

**Actions Taken This Session:**
- **Phase 1: Spatial Ingestion & 178-Station Coordinate Interpolation:**
  - Implemented `src/mumbai/parse_metro_markdown.py`: Unified 79 operational and 99 under-construction station records into `data/mumbai/raw/metro_network/mumbai_metro_stations.json` (178 records, preserving line sequences).
  - Implemented `src/mumbai/extract_transit_lines.py`: Fetched 2,020 physical track segments from Overpass API into `data/mumbai/processed/mumbai_transit_lines.geojson`.
  - Implemented `src/mumbai/interpolate_metro_stations.py`: Snapped anchors and interpolated missing coordinates along tracks in UTM Zone 43N (`EPSG:32643`), exporting `data/mumbai/processed/mumbai_metro_stations_resolved.geojson`.
  - Automated tests: `tests/test_phase1_spatial.py` (4/4 passed).
- **Phase 2: Synthetic 2030 GTFS Generator:**
  - Implemented `src/mumbai/synthesize_future_gtfs.py`: Generated `data/mumbai/processed/mumbai_2030_metro_gtfs.zip` (10 lines, 2,132 bidirectional trips, 30,334 stop times) using commercial speed $t = \frac{d_{\text{km}}}{35.0} \times 60.0$ and line headways (3.3m–6.0m).
  - Automated tests: `tests/test_phase2_gtfs.py` (5/5 passed).
- **Phase 3: R5 Multimodal Routing, DuckDB Materialization, Comparison API & Frontend:**
  - Updated `src/mumbai/compute_travel_matrix.py` to route across all 3 feeds (`train_gtfs.zip`, `gtfs.zip`, `mumbai_2030_metro_gtfs.zip`) and stored 24,390 reachable routes in `mumbai_travel_matrix_2030`.
  - Implemented `src/mumbai/materialize_2030_equity.py`: Materialized `mumbai_equity_2030` and DuckDB view `v_mumbai_equity_comparison` calculating `delta_tdi = current_tdi - future_tdi`.
  - Updated `src/api/mumbai_router.py`: Served 3 scenario modes (`current`, `future_2030`, `delta`), `/comparison-stats`, `/metro-lines`, and `/metro-stations`.
  - Updated `frontend/app.js` and `frontend/index.html`: Integrated 3-way Scenario Switcher, 2030 Metro vector tracks, delta diverging color ramp, and Before vs After transit commute inspector.
  - Verified 100% test pass rate across test suite (`24 passed`).
  ---

### Session 7 — 2026-09-02T21:50:00+10:00

**Status:** KML v3 Entity Resolution, Pristine Dual GTFS Feeds, R5 Matrix Re-Computation, CARTO Vector Integration & GitHub Release Preparation COMPLETED SUCCESSFULLY.

**Actions Taken This Session:**
- **Pristine Metro Network & Spatial Harmonization:**
  - Ingested updated `data/mumbai/raw/metro_network/Mumbai Metro v3.kml` (213 Point placemarks, 19 track LineStrings).
  - Implemented `src/mumbai/finalize_kml_mapping.py`: Programmatically removed cancelled "National College" (Line 2B) and resolved all 177 station records (79 operational, 98 under-construction across 172 unique official stations) at **100.0% match rate** using strict regex normalization and alias resolution.
  - Implemented `src/mumbai/build_final_geojsons.py`: Exported `mumbai_metro_stations_resolved.geojson` (177 Point features with official MMRDA hex colors), `mumbai_metro_tracks_styled.geojson` (14 corridor alignments), `mumbai_suburban_rail_styled.geojson` (1,569 features in `#546E7A`), and `mumbai_transit_lines.geojson`.
- **Dual GTFS Synthesis (Flat 35 km/h Commercial Speed):**
  - Updated `src/mumbai/synthesize_future_gtfs.py` with pure-math Great Circle distance calculation.
  - Synthesized `mumbai_operational_metro_gtfs.zip` (6 routes, 79 stops, 1,010 trips, 14,368 stop times).
  - Synthesized `mumbai_2030_metro_gtfs.zip` (13 routes, 177 stops, 2,132 trips, 30,188 stop times).
- **R5 FastRaptor Travel Time Matrix Computations & DuckDB Views:**
  - Re-computed `mumbai_travel_matrix_current_metro` (22,068 reachable pairs) and `mumbai_travel_matrix_2030` (22,106 reachable pairs) via `src/mumbai/compute_travel_matrix.py` under 14GB JVM heap allocation.
  - Executed `src/mumbai/materialize_2030_equity.py`: Materialized `mumbai_equity_legacy`, `mumbai_equity_current`, `mumbai_equity_2030`, and unified views `v_mumbai_equity_master` / `v_mumbai_equity_comparison`.
- **Security & Client Dynamic Configuration:**
  - Implemented `.env.example` and secured `.env` loading via `python-dotenv`.
  - Exposed `GET /api/v1/config` in FastAPI backend.
  - Upgraded `frontend/app.js` to CARTO Vector Basemap (`dark-matter-gl-style/style.json`) with automatic API key injection via MapLibre's `transformRequest` hook for crisp 3D rendering.
- **Repository Release Packaging:**
  - Standardized `.gitignore` protecting secrets and heavy spatial binaries.
  - Added MIT `LICENSE`.
  - Rewrote portfolio-grade `README.md` including complete data attribution for base KML geometry.

**Summary of Final Citywide Metrics (10,891 H3 Hexagons):**
- **Legacy Baseline Mean TDI:** `0.1745` (Accessibility: `0.2005`)
- **Current Active Metro Mean TDI:** `0.1743` (Accessibility: `0.2014`, 1,221 cells improved)
- **2030 Full Network Mean TDI:** `0.1741` (Accessibility: `0.2022`, 2,204 total cells improved / 20.2% of city)
- **Slum Cluster TDI Reduction:** `0.5522` $\rightarrow$ `0.5493`
- **Max Individual Cell Relief:** $+0.0389$ ($\Delta\text{TDI}$)






