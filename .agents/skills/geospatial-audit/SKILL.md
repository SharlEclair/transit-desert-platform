---
name: geospatial-audit
description: Audits the codebase for spatial coordinate system (CRS) mismatches, routing memory leaks, and database integrity. 
---

# Skill: Geospatial & Architecture Auditor

**Instructions for Agent:**
When invoked, you act as a Senior Spatial Data Engineer conducting a rigorous QA review of the codebase. You are looking specifically for domain-specific spatial and memory errors that generic linters miss.
1. **Coordinate Reference Systems (CRS):** Verify that all demographic geometries (e.g., ABS SEIFA) are explicitly transformed to WGS84 (EPSG:4326) before performing spatial joins with H3 centroids or GTFS data. Flag any missing `ST_Transform()` calls.
2. **DuckDB Spatial Integrity:** Ensure that H3 to demographic joins NEVER use H3 Polyfill due to border distortion. Confirm the code uses `h3_cell_to_latlng()` and DuckDB's `ST_Intersects` (R-Tree).
3. **r5py Memory Management:** Scan the Python environment or configuration files to confirm that the JVM memory limit is explicitly increased (e.g., `max-memory: 12G`). Flag default instantiations of `r5py` as fatal errors.