# Phase 5: The Mumbai Adaptation

## Architecture Overview
The goal of Phase 5 is to adapt our pristine Melbourne MVP pipeline to handle the complexities of Mumbai's multimodal transit network, which includes standard GTFS feeds, informal settlement data, and unstructured local train schedules.

To ensure we do not corrupt or overwrite the Melbourne MVP, all Mumbai pipeline logic will be strictly isolated under `src/mumbai/` and `data/mumbai/`.

## Data Inventory
The raw data is stored in `data/mumbai/raw/`:
- **`gtfs.zip`**: Standard BEST Bus GTFS feed.
- **`5d6f72ed-a290-4931-821f-5476c148407b.kml`**: Mumbai Slum Cluster Map.
- **`95e22d97-7f59-4214-b244-2abbf52e6027.csv`**: Ward-wise Census Data 2011.
- **`western-zone-260831.osm.pbf`**: Maharashtra/Mumbai OSM topological road graph.
- **`Mumbai Local Train Time/`**: Directory containing 54 CSV files (`Table - 1.csv` through `Table - 54.csv`), representing wide-format timetables scraped from the web.

## Handling Fragmented Data
1. **Unstructured Train Schedules**: We will need to write custom parsers for the 54 "wide-format" CSV files in `Mumbai Local Train Time/` to harmonize them into standard GTFS files (`stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`) so they can be merged into a cohesive GTFS package.
2. **Informal Settlements**: The KML file containing the Mumbai Slum Cluster Map must be parsed, converted to standard GeoJSON or loaded into DuckDB, and joined against the Ward-wise Census CSV to create an accurate demographic spatial layer.
3. **OSM Integration**: The `western-zone-260831.osm.pbf` will provide the walking paths and road networks, similar to the Melbourne implementation.

## Next Steps
1. Profile the raw data schemas and shapes.
2. Develop harmonization scripts to convert local train CSVs to GTFS.
3. Clean and merge the slum KML and census CSV into a unified demographic layer.
4. Generate the H3 grid for Mumbai.
5. Compute the travel time matrix using `r5py`.
6. Calculate equity scores and visualize.
