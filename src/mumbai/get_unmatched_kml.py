import json

KML_RAW_STATIONS = "data/mumbai/raw/metro_network/kml_raw_stations.json"
PROPOSED_MAPPING = "data/mumbai/raw/metro_network/proposed_station_mapping.json"

def main():
    with open(KML_RAW_STATIONS, "r", encoding="utf-8") as f:
        raw_kml_stations = json.load(f)

    with open(PROPOSED_MAPPING, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    # Extract all non-null matched KML names
    matched_kml_names = set(v for v in mapping.values() if v is not None)

    # Find unused KML station names (preserving order and deduplicating or showing unique)
    # Let's clean up/keep exact names from raw_kml_stations
    unused_kml = [name for name in raw_kml_stations if name not in matched_kml_names]
    
    # Unique unused while preserving order
    unique_unused = []
    seen = set()
    for name in unused_kml:
        if name not in seen:
            seen.add(name)
            unique_unused.append(name)

    print(f"Total raw KML stations: {len(raw_kml_stations)}")
    print(f"Total matched KML station values: {len(matched_kml_names)}")
    print(f"Total unused KML stations: {len(unused_kml)} ({len(unique_unused)} unique)\n")
    print("=== Unused / Unassigned KML Station Names ===")
    for i, name in enumerate(unique_unused, 1):
        print(f"{i:2d}. {name}")

if __name__ == "__main__":
    main()
