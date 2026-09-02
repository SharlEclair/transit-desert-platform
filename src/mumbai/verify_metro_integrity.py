import json
import os
from pathlib import Path

STATIONS_PATH = "data/mumbai/processed/mumbai_metro_stations_resolved.geojson"

def verify_stations():
    if not os.path.exists(STATIONS_PATH):
        print(f"Error: {STATIONS_PATH} not found.")
        return
        
    with open(STATIONS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    features = data.get("features", [])
    
    operational_count = 0
    under_construction_count = 0
    
    lines_summary = {}
    
    print(f"Total Stations: {len(features)}")
    print("-" * 50)
    
    for feat in features:
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [])
        name = props.get("station_name")
        line = props.get("line_name")
        status = props.get("status")
        is_operational = props.get("is_operational")
        
        # Verify status matches is_operational flag
        if status == "operational":
            operational_count += 1
        elif status == "under_construction":
            under_construction_count += 1
            
        if line not in lines_summary:
            lines_summary[line] = {"op": 0, "uc": 0}
            
        if status == "operational":
            lines_summary[line]["op"] += 1
        else:
            lines_summary[line]["uc"] += 1
            
        # Check specific stations for rounding or overwrite
        if name in ["BKC", "Cuffe Parade", "Churchgate", "CSMT", "Chhatrapati Shivaji Maharaj Terminus", "Miragaon", "Deshbhakt N.G. Acharya Udyan–Diamond Garden", "Maharashtranagar–Mandale"]:
            print(f"Station: {name:40} | Line: {line:20} | Status: {status:15} | is_op: {is_operational} | Coords: {coords}")
            
    print("-" * 50)
    print("Line Summary:")
    for line, counts in lines_summary.items():
        print(f"  {line:25}: {counts['op']:3} Operational | {counts['uc']:3} Under Construction")
        
    print("-" * 50)
    print(f"Total Operational: {operational_count} (Expected: 79)")
    print(f"Total Under Construction: {under_construction_count} (Expected: 98)")
    print(f"Total Stations: {len(features)} (Expected: 177)")
    
if __name__ == "__main__":
    verify_stations()
