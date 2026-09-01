# Project Context: Multimodal Transit Desert & Dynamic Isochrone Platform

## Overview
This project transforms abstract transit maps into a rigorous, data-driven equity engine. It calculates actual commute times based on the exact minute a person leaves their door, accounting for walking, waiting, and transfer penalties, to identify "Transit Deserts" (areas with high population density but poor transit connectivity).

## Architecture & Tech Stack
- **Routing Engine:** `r5py` (Rapid Realistic Routing on Real-world Networks). This library strictly requires two inputs: a standard GTFS `.zip` file for transit, and an OpenStreetMap `.pbf` file for the pedestrian/street network.
- **Spatial Database:** `DuckDB` with the `spatial` extension. Used for high-speed spatial joins.
- **Spatial Indexing:** Uber `H3` (Resolution 9). We grid the city into hexagons and calculate travel times from the centroid of each hexagon.
- **Backend & Frontend:** FastAPI serving GeoJSON to MapLibre GL JS / Kepler.gl.

## Strict Data Requirements
To successfully build the `r5py` network and perform the DuckDB spatial joins, the following data types are required for any target city:

1. **Transit Schedules (GTFS):** Must be a standard `.zip` file containing at minimum `stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`, and `calendar.txt`. 
2. **Pedestrian/Street Network:** Must be an OpenStreetMap (OSM) extract in Protocolbuffer Binary Format (`.osm.pbf`). Standard shapefiles will not work for the `r5py` routing engine.
3. **Demographic/Census Data:** Must be spatial polygon data (Shapefiles, GeoJSON, or GeoPackage) representing localized census blocks or municipal wards. It must contain attributes for Population Density and ideally a Socio-Economic or vulnerability index.

## Objective of Research
To locate the exact URLs, developer portals, and repositories to download these three layers of data for Melbourne, Australia (first priority, high data quality) and Mumbai, India (second priority, highly fragmented data).