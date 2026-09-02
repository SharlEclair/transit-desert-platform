"""
Standardize and Enrich All Mumbai Transit GeoJSON Overlays.
Ensures strictly compliant schemas:
- Lines: `line_name`, `color` (hex), `status` ('operational' vs 'under_construction'), `network` ('metro' vs 'rail')
- Stations: `station_name`, `line_name`, `status`, `stop_sequence`, `line_id`, `color`
- All Coordinates formatted as [longitude, latitude] in WGS84 EPSG:4326
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any
from shapely.geometry import LineString, MultiLineString, Point, mapping

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("StandardizeTransitGeoJSON")

STATIONS_JSON_PATH = Path("data/mumbai/processed/mumbai_metro_stations_resolved.json")
STATIONS_GEOJSON_PATH = Path("data/mumbai/processed/mumbai_metro_stations_resolved.geojson")
RAW_TRANSIT_LINES_PATH = Path("data/mumbai/processed/mumbai_transit_lines.geojson")
METRO_TRACKS_PATH = Path("data/mumbai/processed/mumbai_metro_tracks_styled.geojson")
SUBURBAN_RAIL_PATH = Path("data/mumbai/processed/mumbai_suburban_rail_styled.geojson")

MMRDA_COLORS = {
    "1": "#00AEEF",
    "2A": "#FFC600",
    "2B": "#FFC600",
    "3": "#059DB2",
    "4": "#00AE5A",
    "4A": "#00AE5A",
    "5": "#FF8200",
    "6": "#F99FC9",
    "7": "#D83431",
    "7A": "#D83431",
    "9": "#D83431",
    "12": "#FF8200"
}

LINE_NAMES = {
    "1": "Line 1 (Blue Line)",
    "2A": "Line 2A (Yellow Line)",
    "2B": "Line 2B (Yellow Line)",
    "3": "Line 3 (Aqua Line)",
    "4": "Line 4 (Green Line)",
    "4A": "Line 4A (Green Line Extension)",
    "5": "Line 5 (Orange Line)",
    "6": "Line 6 (Pink Line)",
    "7": "Line 7 (Red Line)",
    "7A": "Line 7A (Red Line Extension)",
    "9": "Line 9 (Red Line Extension)",
    "12": "Line 12 (Orange Line Extension)"
}


def process_stations():
    logger.info("Processing Mumbai Metro Stations GeoJSON...")
    with open(STATIONS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    stations = data["stations"]
    features = []
    
    for s in stations:
        lid = str(s.get("line_id", ""))
        color = MMRDA_COLORS.get(lid, "#00AEEF")
        seq = int(s.get("sequence", 1))
        
        feat = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(s["lon"]), float(s["lat"])]
            },
            "properties": {
                "station_name": str(s["station_name"]),
                "line_id": lid,
                "line_name": LINE_NAMES.get(lid, s.get("line_name", f"Line {lid}")),
                "status": str(s["status"]),
                "stop_sequence": seq,
                "sequence": seq,
                "color": color,
                "is_operational": (s["status"] == "operational"),
                "is_interpolated": bool(s.get("is_interpolated", False)),
                "interchange": str(s.get("interchange", "-"))
            }
        }
        features.append(feat)
        
    fc = {
        "type": "FeatureCollection",
        "metadata": {
            "title": "Mumbai Metro Stations (2030 Network)",
            "count": len(features)
        },
        "features": features
    }
    
    with open(STATIONS_GEOJSON_PATH, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    logger.info("Saved %d standard stations to: %s", len(features), STATIONS_GEOJSON_PATH)
    return stations


def process_metro_tracks(stations: List[Dict[str, Any]]):
    logger.info("Processing Metro Tracks GeoJSON...")
    features = []
    line_ids = ["1", "2A", "2B", "3", "4", "4A", "5", "6", "7", "7A", "9", "12"]
    
    for lid in line_ids:
        stns = [s for s in stations if s["line_id"] == lid]
        stns.sort(key=lambda s: s["sequence"])
        if len(stns) < 2:
            continue
            
        color = MMRDA_COLORS.get(lid, "#FFFFFF")
        lname = LINE_NAMES.get(lid, f"Line {lid}")
        statuses = [s["status"] for s in stns]
        unique_statuses = set(statuses)
        
        if len(unique_statuses) == 1:
            coords = [[float(s["lon"]), float(s["lat"])] for s in stns]
            status_str = list(unique_statuses)[0]
            is_op = (status_str == "operational")
            
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords
                },
                "properties": {
                    "line_id": lid,
                    "line_name": lname,
                    "status": status_str,
                    "network": "metro",
                    "transit_type": "metro",
                    "is_operational": is_op,
                    "color": color,
                    "stroke_width": 4.5 if is_op else 3.5,
                    "dasharray": [] if is_op else [2, 2],
                    "station_count": len(stns),
                    "start_station": stns[0]["station_name"],
                    "end_station": stns[-1]["station_name"]
                }
            })
        else:
            op_stns = [s for s in stns if s["status"] == "operational"]
            uc_stns = [s for s in stns if s["status"] == "under_construction"]
            
            if len(op_stns) >= 2:
                coords = [[float(s["lon"]), float(s["lat"])] for s in op_stns]
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords
                    },
                    "properties": {
                        "line_id": lid,
                        "line_name": f"{lname} (Phase 1 Operational)",
                        "status": "operational",
                        "network": "metro",
                        "transit_type": "metro",
                        "is_operational": True,
                        "color": color,
                        "stroke_width": 4.5,
                        "dasharray": [],
                        "station_count": len(op_stns),
                        "start_station": op_stns[0]["station_name"],
                        "end_station": op_stns[-1]["station_name"]
                    }
                })
                
            if len(uc_stns) >= 2:
                bridge_coords = []
                if op_stns and op_stns[-1]["sequence"] + 1 == uc_stns[0]["sequence"]:
                    bridge_coords.append([float(op_stns[-1]["lon"]), float(op_stns[-1]["lat"])])
                bridge_coords.extend([[float(s["lon"]), float(s["lat"])] for s in uc_stns])
                
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": bridge_coords
                    },
                    "properties": {
                        "line_id": lid,
                        "line_name": f"{lname} (Phase 2 Under Construction)",
                        "status": "under_construction",
                        "network": "metro",
                        "transit_type": "metro",
                        "is_operational": False,
                        "color": color,
                        "stroke_width": 3.5,
                        "dasharray": [2, 2],
                        "station_count": len(uc_stns),
                        "start_station": uc_stns[0]["station_name"],
                        "end_station": uc_stns[-1]["station_name"]
                    }
                })
                
    fc = {
        "type": "FeatureCollection",
        "metadata": {"title": "Mumbai Metro Tracks", "count": len(features)},
        "features": features
    }
    with open(METRO_TRACKS_PATH, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    logger.info("Saved %d styled Metro track features to: %s", len(features), METRO_TRACKS_PATH)
    return features


def process_suburban_rail():
    logger.info("Processing Suburban Rail GeoJSON...")
    with open(RAW_TRANSIT_LINES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    rail_features = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        if props.get("transit_type") == "suburban_rail" or props.get("railway") == "rail":
            name = props.get("name") or "Suburban Rail Corridor"
            feat["properties"]["line_name"] = name
            feat["properties"]["network"] = "rail"
            feat["properties"]["transit_type"] = "suburban_rail"
            feat["properties"]["status"] = "operational"
            feat["properties"]["color"] = "#546E7A"
            feat["properties"]["stroke_width"] = 1.8
            feat["properties"]["is_operational"] = True
            rail_features.append(feat)
            
    fc = {
        "type": "FeatureCollection",
        "metadata": {"title": "Mumbai Suburban Rail", "count": len(rail_features)},
        "features": rail_features
    }
    with open(SUBURBAN_RAIL_PATH, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    logger.info("Saved %d Suburban Rail features to: %s", len(rail_features), SUBURBAN_RAIL_PATH)
    return rail_features


def main():
    logger.info("=" * 80)
    logger.info("STANDARDIZING MUMBAI TRANSIT GEOJSON DATASETS")
    logger.info("=" * 80)
    stns = process_stations()
    metro_feats = process_metro_tracks(stns)
    rail_feats = process_suburban_rail()
    
    # Save combined master transit lines GeoJSON as well
    combined_fc = {
        "type": "FeatureCollection",
        "metadata": {
            "title": "Mumbai Combined Transit Network",
            "count": len(metro_feats) + len(rail_feats)
        },
        "features": metro_feats + rail_feats
    }
    with open(RAW_TRANSIT_LINES_PATH, "w", encoding="utf-8") as f:
        json.dump(combined_fc, f, indent=2)
    logger.info("Saved %d combined transit features to: %s", len(combined_fc["features"]), RAW_TRANSIT_LINES_PATH)


if __name__ == "__main__":
    main()
