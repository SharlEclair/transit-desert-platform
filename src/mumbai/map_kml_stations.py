import json
import re
import difflib

KML_RAW_STATIONS = "data/mumbai/raw/metro_network/kml_raw_stations.json"
OFFICIAL_STATIONS = "data/mumbai/raw/metro_network/mumbai_metro_stations.json"
PROPOSED_MAPPING = "data/mumbai/raw/metro_network/proposed_station_mapping.json"

def clean_kml_name(raw_name):
    # Remove non-ascii characters (strips Marathi/Hindi)
    ascii_only = raw_name.encode("ascii", "ignore").decode()
    # Replace any character that is NOT a letter or number with a space
    cleaned = re.sub(r'[^a-zA-Z0-9]', ' ', ascii_only)
    # Collapse multiple spaces into a single space and trim edges
    final_name = " ".join(cleaned.split()).strip()
    return final_name

def main():
    # Load KML raw stations
    with open(KML_RAW_STATIONS, 'r', encoding='utf-8') as f:
        kml_raw = json.load(f)
        
    # Load official stations
    with open(OFFICIAL_STATIONS, 'r', encoding='utf-8') as f:
        official_data = json.load(f)
        
    official_names = []
    if "stations" in official_data:
        official_names = [st["station_name"] for st in official_data["stations"]]
    else:
        print("Error: Could not find 'stations' array in official JSON.")
        return
        
    print(f"Loaded {len(kml_raw)} KML stations and {len(official_names)} official stations.")
    
    # Clean KML names and map cleaned -> original
    kml_cleaned_map = {}
    for name in kml_raw:
        c_name = clean_kml_name(name)
        if c_name:
            kml_cleaned_map[c_name] = name
            
    kml_cleaned_names = list(kml_cleaned_map.keys())
    
    mapping = {}
    unmatched_official = []
    
    for off_name in official_names:
        off_cleaned = clean_kml_name(off_name)
        
        matches = difflib.get_close_matches(off_cleaned, kml_cleaned_names, n=1, cutoff=0.7)
        if matches:
            best_match = matches[0]
            # Mapping Official Name -> Original KML Name
            mapping[off_name] = kml_cleaned_map[best_match]
        else:
            mapping[off_name] = None
            unmatched_official.append(off_name)
            
    matched_count = sum(1 for v in mapping.values() if v is not None)
    
    with open(PROPOSED_MAPPING, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
        
    print(f"\nSuccessfully matched {matched_count} out of {len(official_names)} official stations.")
    print(f"Exported mapping to {PROPOSED_MAPPING}")
    
    print(f"\nStations mapped to null ({len(unmatched_official)}):")
    for ms in unmatched_official:
        print(f"  - {ms}")

if __name__ == "__main__":
    main()
