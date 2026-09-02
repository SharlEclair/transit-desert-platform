---
name: gtfs-osm-preprocessor
description: Executes data validation and preprocessing for raw GTFS archives and OSM PBF files. Use this when the user asks to ingest or clean transit data.
---

# Skill: GTFS and OSM Preprocessor

**Instructions for Agent:**
When invoked, you are acting as an expert Data Engineer specializing in messy civic transit data. 
1. Your primary goal is to prepare raw GTFS and OSM data so that it will not crash the strict `r5py` routing engine.
2. You must write robust Python scripts utilizing the `zipfile` and `pandas` libraries to inspect GTFS archives. 
3. If a GTFS archive contains nested folders (like the Victoria dataset), your script must extract the relevant text files (`stops.txt`, `routes.txt`, `stop_times.txt`, etc.) and zip them back up at the root level of a new archive.
4. Validate the existence of `calendar.txt` in all GTFS feeds. If a feed relies solely on `calendar_dates.txt`, synthesize a valid bridging schedule to prevent routing failures.
5. Ensure you log all data transformations clearly in the terminal so the user knows exactly how the data was altered.