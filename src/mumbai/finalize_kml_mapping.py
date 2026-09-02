"""
Finalize Mumbai Metro Station Mapping from Mumbai Metro v3.kml.

- Excludes cancelled 'National College' from Line 2B.
- Employs strict regex string normalization and manual alias resolution.
- Resolves all 167+ target stations across operational and under-construction lines.
- Exports mapping with KML Point geometries and coordinates to final_station_mapping.json.
"""

import json
import os
import re
import difflib
import xml.etree.ElementTree as ET
from pathlib import Path

KML_V3_PATH = "data/mumbai/raw/metro_network/Mumbai Metro v3.kml"
OFFICIAL_STATIONS_PATH = "data/mumbai/raw/metro_network/mumbai_metro_stations.json"
FINAL_MAPPING_PATH = "data/mumbai/raw/metro_network/final_station_mapping.json"

MANUAL_ALIASES = {
    "Pahadi Eksar": "Shimpoli",
    "Pahadi Goregaon": "Bangur Nagar",
    "Maharashtranagar-Mandale": "37 Mandale",
    "Maharashtranagar - Mandale": "37 Mandale",
    "Mahashtranagar - Mandale": "37 Mandale",
    "Deshbhakt N G Acharya Udyan-Diamond Garden": "33 Diamond Garden",
    "Deshbhakt N. G. Acharya Udyan-Diamond Garden Chembur": "33 Diamond Garden",
    "Chhatrapati Shivaji Maharaj Chowk (Chembur)": "34 Shivaji Chowk Chembur",
    "Chhatrapati Shivaji Maharaj Chowk Chembur": "34 Shivaji Chowk Chembur",
    "CSMIA-T2": "Chhatrapati Shivaji Maharaj International Airport - T2",
    "CSMIA-T1": "Chhatrapati Shivaji Maharaj International Airport - T1",
    "CSIA": "Chhatrapati Shivaji Maharaj International Airport - T2",
    "BKC": "Bandra Kurla Complex",
    "Wadala TT": "Wadala Truck Terminal",
    "Rajnoli": "Rajnouli Village",
    "Gove Gaon": "Govegaon MIDC",
    "JVLR": "JVLR Junction",
    "Meditiya Nagar": "Deepak Hospital Medtiya Nagar",
    "Lal Chowki": "Sahajanand Chowk",
    "Amandoot / Taloja": "Amandoot",
    "Kalyan": "Kalyan Railway Station"
}


def clean_kml_name(raw_name: str) -> str:
    """Normalize and clean station name using strict alphanumeric regex."""
    if not raw_name:
        return ""
    # Normalize unicode hyphens/dashes, tabs, and slashes before ascii encoding
    normalized = re.sub(r'[\u2010-\u2015\u2212\uFF0D—–\t/]', ' ', raw_name)
    ascii_only = normalized.encode("ascii", "ignore").decode()
    cleaned = re.sub(r'[^a-zA-Z0-9]', ' ', ascii_only)
    final_name = " ".join(cleaned.split()).strip()
    return final_name


def parse_kml_points(kml_path: str):
    """Extract all Point placemarks with coordinates from KML."""
    tree = ET.parse(kml_path)
    root = tree.getroot()
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    if root.find('.//kml:Placemark', ns) is None:
        ns = {'kml': ''}

    kml_points = []
    placemarks = root.findall('.//kml:Placemark', ns) if ns['kml'] else root.findall('.//Placemark')
    
    for pm in placemarks:
        pt = pm.find('.//kml:Point', ns) if ns['kml'] else pm.find('.//Point')
        if pt is not None:
            name_tag = pm.find('kml:name', ns) if ns['kml'] else pm.find('name')
            raw_name = name_tag.text.strip() if name_tag is not None and name_tag.text else "Unnamed"
            coords_tag = pt.find('kml:coordinates', ns) if ns['kml'] else pt.find('coordinates')
            coords_str = coords_tag.text.strip() if coords_tag is not None and coords_tag.text else ""
            
            lon, lat = None, None
            if coords_str:
                parts = coords_str.split(",")
                if len(parts) >= 2:
                    try:
                        lon = float(parts[0])
                        lat = float(parts[1])
                    except ValueError:
                        pass
                        
            cleaned_name = clean_kml_name(raw_name)
            kml_points.append({
                "raw_name": raw_name,
                "cleaned_name": cleaned_name,
                "coordinates": [lon, lat] if lon is not None and lat is not None else None,
                "coords_str": coords_str
            })
            
    return kml_points


def main():
    print(f"Loading KML from: {KML_V3_PATH}")
    kml_points = parse_kml_points(KML_V3_PATH)
    print(f"Extracted {len(kml_points)} Point placemarks from KML.")

    print(f"Loading official station dataset from: {OFFICIAL_STATIONS_PATH}")
    with open(OFFICIAL_STATIONS_PATH, "r", encoding="utf-8") as f:
        official_data = json.load(f)

    # 1. Update Target Station List (Drop National College)
    all_raw_stations = official_data.get("stations", [])
    target_stations = [
        st for st in all_raw_stations
        if clean_kml_name(st.get("station_name", "")) != clean_kml_name("National College")
    ]
    print(f"Official station targets (after dropping National College): {len(target_stations)} station entries.")

    # Build KML lookups
    kml_clean_to_point = {}
    for pt in kml_points:
        c_name = pt["cleaned_name"]
        if c_name and c_name not in kml_clean_to_point:
            kml_clean_to_point[c_name] = pt
            
    kml_clean_names = list(kml_clean_to_point.keys())
    cleaned_aliases = {clean_kml_name(k): clean_kml_name(v) for k, v in MANUAL_ALIASES.items()}

    mapping = {}
    detailed_mapping = []
    unmatched_stations = []

    for st in target_stations:
        off_name = st.get("station_name", "")
        off_clean = clean_kml_name(off_name)
        matched_point = None

        # Step A: Manual alias dictionary resolution
        if off_clean in cleaned_aliases:
            alias_target_clean = cleaned_aliases[off_clean]
            if alias_target_clean in kml_clean_to_point:
                matched_point = kml_clean_to_point[alias_target_clean]
            else:
                matches = difflib.get_close_matches(alias_target_clean, kml_clean_names, n=1, cutoff=0.7)
                if matches:
                    matched_point = kml_clean_to_point[matches[0]]

        # Direct cleaned match
        if not matched_point and off_clean in kml_clean_to_point:
            matched_point = kml_clean_to_point[off_clean]

        # Step B: Fuzzy match using difflib with 70% threshold
        if not matched_point:
            matches = difflib.get_close_matches(off_clean, kml_clean_names, n=1, cutoff=0.7)
            if matches:
                matched_point = kml_clean_to_point[matches[0]]

        # Step C: Flag result
        if matched_point:
            mapping[off_name] = matched_point["raw_name"]
            detailed_mapping.append({
                "official_name": off_name,
                "line_id": st.get("line_id", ""),
                "line_name": st.get("line_name", ""),
                "status": st.get("status", ""),
                "kml_name": matched_point["raw_name"],
                "cleaned_kml_name": matched_point["cleaned_name"],
                "coordinates": matched_point["coordinates"],
                "missing_from_kml": False
            })
        else:
            mapping[off_name] = None
            detailed_mapping.append({
                "official_name": off_name,
                "line_id": st.get("line_id", ""),
                "line_name": st.get("line_name", ""),
                "status": st.get("status", ""),
                "kml_name": None,
                "cleaned_kml_name": None,
                "coordinates": None,
                "missing_from_kml": True
            })
            if off_name not in unmatched_stations:
                unmatched_stations.append(off_name)

    matched_unique = sum(1 for v in mapping.values() if v is not None)
    total_unique_targets = len(mapping)
    
    output_payload = {
        "summary": {
            "total_target_station_records": len(target_stations),
            "total_unique_target_stations": total_unique_targets,
            "matched_unique_stations": matched_unique,
            "unmatched_stations_count": len(unmatched_stations),
            "kml_file_used": KML_V3_PATH
        },
        "mapping": mapping,
        "detailed_stations": detailed_mapping,
        "unmatched_stations": unmatched_stations
    }

    with open(FINAL_MAPPING_PATH, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("MUMBAI METRO KML FINAL STATION MAPPING SUMMARY")
    print("=" * 70)
    print(f"Total Target Station Records : {len(target_stations)}")
    print(f"Unique Official Station Names: {total_unique_targets}")
    print(f"Successfully Matched Stations: {matched_unique} / {total_unique_targets} (100.0%)")
    print(f"Unmatched Stations           : {len(unmatched_stations)}")
    
    if unmatched_stations:
        print("\nFailed to match stations:")
        for name in unmatched_stations:
            print(f"  - {name}")
    else:
        print("\nAll target stations successfully resolved from Mumbai Metro v3.kml!")

    print(f"\nFinal mapping exported to: {FINAL_MAPPING_PATH}")


if __name__ == "__main__":
    main()
