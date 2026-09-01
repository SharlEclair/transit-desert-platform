# Implementation Plan: Multimodal Transit Desert Platform (Melbourne MVP)

## Phase 1: Workspace Setup & Data Ingestion
- [ ] **1.1 Environment:** Initialize Python virtual environment. Install `duckdb`, `h3`, `osmnx`, `r5py`, `fastapi`, and `geopandas`. Configure `r5py.yml` for JVM memory allocation (min 8GB+).
- [ ] **1.2 Database Initialization:** Create `transit_equity.db` using DuckDB. Load the `spatial` extension.
- [ ] **1.3 Spatial Demographics:** Ingest ABS SEIFA SA1 GeoPackage. Write a script to insert it into a DuckDB table `melb_demographics`.
- [ ] **1.4 H3 Grid Generation:** Generate an H3 Resolution 9 hex grid over the Melbourne bounding box. Extract centroids and save as `melb_h3_grid`.
- [ ] **1.5 GTFS Preprocessing:** Write a Python script to unzip the Victoria `gtfs.zip`, traverse the nested subdirectories, synthesize missing `calendar.txt` files if necessary, and repackage them into a standard flat `.zip` format acceptable by `r5py`.

## Phase 2: The Network Graph & Routing Engine
- [ ] **2.1 Network Compilation:** Instantiate `r5py.TransportNetwork` using the Geofabrik Victoria `.osm.pbf` and the cleaned Melbourne GTFS `.zip`. Save the compiled network to disk.
- [ ] **2.2 POI Definition:** Define target destinations (e.g., Melbourne CBD, major hospitals) as coordinate points.
- [ ] **2.3 Batch Isochrone Matrix:** Execute `r5py.TravelTimeMatrixComputer`. Set origins as the H3 centroids and destinations as POIs. Set max travel time to 45 minutes and departure to a Tuesday at 8:00 AM.
- [ ] **2.4 Matrix Storage:** Export the resulting origin-destination travel times into DuckDB as `melb_travel_matrix`.

## Phase 3: Spatial Joins & Equity Scoring (DuckDB)
- [ ] **3.1 Topological Join:** Execute an `ST_Intersects` join in DuckDB to precisely map H3 centroids to their underlying SA1 demographic polygons.
- [ ] **3.2 Score Calculation:** Calculate the `Accessibility Score` based on travel times and the number of reachable POIs.
- [ ] **3.3 Transit Desert Flagging:** Create a SQL view that filters for H3 hexes in the top 20th percentile of population density, but the bottom 20th percentile of accessibility. 

## Phase 4: API & Visualization
- [ ] **4.1 FastAPI Setup:** Create endpoints `/api/isochrones` and `/api/deserts` that execute DuckDB queries and return GeoJSON FeatureCollections.
- [ ] **4.2 Frontend Integration:** Set up a lightweight HTML/JS frontend utilizing MapLibre GL JS to render the GeoJSON layers in 3D.