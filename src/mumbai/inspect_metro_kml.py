import os
import json
import re
import xml.etree.ElementTree as ET

KML_PATH = "data/mumbai/raw/metro_network/Mumbai Metro v2.kml"
RAW_STATIONS_JSON = "data/mumbai/raw/metro_network/kml_raw_stations.json"
RAW_LINES_JSON = "data/mumbai/raw/metro_network/kml_raw_lines.json"

def clean_station_name(raw_name: str) -> str:
    if not raw_name:
        return ""
    # Remove non-ascii characters (Hindi/Marathi script)
    ascii_only = re.sub(r'[^\x00-\x7F]+', '', raw_name)
    # Strip leading/trailing commas and whitespace
    cleaned = ascii_only.strip(" ,.-")
    return cleaned

def parse_raw_kml():
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    try:
        tree = ET.parse(KML_PATH)
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f"Failed to parse KML: {e}")
        
    # Check if we need empty namespace
    if root.find('.//kml:Placemark', ns) is None:
        if root.find('.//Placemark') is not None:
            ns = {'kml': ''}
            
    raw_points = []
    raw_lines = []
    
    placemarks = root.findall('.//kml:Placemark', ns) if ns['kml'] else root.findall('.//Placemark')
    
    for placemark in placemarks:
        pm_name_tag = placemark.find('kml:name', ns) if ns['kml'] else placemark.find('name')
        pm_name = pm_name_tag.text if pm_name_tag is not None else "Unnamed"
        
        # Check for LineString
        ls = placemark.find('.//kml:LineString', ns) if ns['kml'] else placemark.find('.//LineString')
        if ls is not None:
            raw_lines.append(pm_name)
            
        # Check for Point
        pt = placemark.find('.//kml:Point', ns) if ns['kml'] else placemark.find('.//Point')
        if pt is not None:
            cleaned_name = clean_station_name(pm_name)
            raw_points.append(cleaned_name)
            
    return raw_lines, raw_points

def main():
    print(f"Parsing entire KML: {KML_PATH}")
    raw_lines, raw_points = parse_raw_kml()
    
    # Save to JSON
    with open(RAW_STATIONS_JSON, 'w', encoding='utf-8') as f:
        json.dump(raw_points, f, indent=2, ensure_ascii=False)
        
    with open(RAW_LINES_JSON, 'w', encoding='utf-8') as f:
        json.dump(raw_lines, f, indent=2, ensure_ascii=False)
        
    print("\n=== RAW KML Extraction Summary ===")
    print(f"Total LineStrings extracted: {len(raw_lines)}")
    print(f"Total Points extracted: {len(raw_points)}")
    
    print("\nSample of 15 Extracted Station Names:")
    for name in raw_points[:15]:
        print(f"  - {name}")
        
    print(f"\nExports:")
    print(f"  Stations -> {RAW_STATIONS_JSON}")
    print(f"  Lines -> {RAW_LINES_JSON}")

if __name__ == "__main__":
    main()
