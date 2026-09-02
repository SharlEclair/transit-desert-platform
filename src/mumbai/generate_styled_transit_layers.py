"""
Generate Styled Multi-Modal Transit Vector Layers for MapLibre GL JS.
Builds:
1. `data/mumbai/processed/mumbai_metro_tracks_styled.geojson`: Continuous Metro corridor track lines
   with MMRDA official hex colors and operational/under-construction statuses.
2. `data/mumbai/processed/mumbai_suburban_rail_styled.geojson`: Suburban Rail lines styled with Dark Slate (#546E7A).
3. `data/mumbai/processed/mumbai_transit_network_complete.geojson`: Unified vector network.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any
from shapely.geometry import LineString, MultiLineString, mapping

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("GenerateStyledTransitLayers")

RESOLVED_STATIONS_PATH = Path("data/mumbai/processed/mumbai_metro_stations_resolved.json")
TRANSIT_LINES_PATH = Path("data/mumbai/processed/mumbai_transit_lines.geojson")
OUTPUT_METRO_TRACKS_PATH = Path("data/mumbai/processed/mumbai_metro_tracks_styled.geojson")
OUTPUT_RAIL_PATH = Path("data/mumbai/processed/mumbai_suburban_rail_styled.geojson")

# Official MMRDA Hex Colors
MMRDA_COLORS = {
    "1": "#00AEEF",    # Cyan / Blue
    "2A": "#FFC600",   # Yellow
    "2B": "#FFC600",   # Yellow
    "3": "#059DB2",    # Aqua / Teal
    "4": "#00AE5A",    # Green
    "4A": "#00AE5A",   # Green Extension
    "5": "#FF8200",    # Orange
    "6": "#F99FC9",    # Pink
    "7": "#D83431",    # Red
    "7A": "#D83431",   # Red Extension
    "9": "#D83431",    # Red Extension
    "12": "#FF8200"    # Orange / Amber
}

LINE_NAMES = {
    "1": "Line 1 (Blue Line)",
    "2A": "Line 2A (Yellow Line)",
    "2B": "Line 2B (Yellow Line)",
    "3": "Line 3 (Aqua Line)",
    "4": "Line 4 (Green Line)",
    "4A": "Line 4A (Green Line Ext)",
    "5": "Line 5 (Orange Line)",
    "6": "Line 6 (Pink Line)",
    "7": "Line 7 (Red Line)",
    "7A": "Line 7A (Red Line Ext)",
    "9": "Line 9 (Red Line Ext)",
    "12": "Line 12 (Orange Line Ext)"
}


def build_styled_metro_tracks():
    """Construct continuous track LineString features for all 10 Metro lines split by operational status."""
    with open(RESOLVED_STATIONS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    stations = data["stations"]
    features = []
    
    # Group stations by line
    line_ids = ["1", "2A", "2B", "3", "4", "4A", "5", "6", "7", "7A", "9", "12"]
    
    for lid in line_ids:
        stns = [s for s in stations if s["line_id"] == lid]
        stns.sort(key=lambda s: s["sequence"])
        if len(stns) < 2:
            continue
            
        color = MMRDA_COLORS.get(lid, "#FFFFFF")
        lname = LINE_NAMES.get(lid, f"Line {lid}")
        
        # Check if line has mixed status (e.g. Line 2B or Line 9)
        statuses = [s["status"] for s in stns]
        unique_statuses = set(statuses)
        
        if len(unique_statuses) == 1:
            # Single uniform status
            coords = [[s["lon"], s["lat"]] for s in stns]
            geom = LineString(coords)
            status_str = list(unique_statuses)[0]
            is_op = (status_str == "operational")
            
            features.append({
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {
                    "line_id": lid,
                    "line_name": lname,
                    "status": status_str,
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
            # Split into operational and under-construction segments
            # E.g. Line 2B (stns 1-6 op, stns 7-20 uc) or Line 9 (stns 1-4 op, stns 5-8 uc)
            op_stns = [s for s in stns if s["status"] == "operational"]
            uc_stns = [s for s in stns if s["status"] == "under_construction"]
            
            if len(op_stns) >= 2:
                coords = [[s["lon"], s["lat"]] for s in op_stns]
                features.append({
                    "type": "Feature",
                    "geometry": mapping(LineString(coords)),
                    "properties": {
                        "line_id": lid,
                        "line_name": f"{lname} (Phase 1)",
                        "status": "operational",
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
                # Include last operational station as connection bridge if adjacent
                bridge_coords = []
                if op_stns and op_stns[-1]["sequence"] + 1 == uc_stns[0]["sequence"]:
                    bridge_coords.append([op_stns[-1]["lon"], op_stns[-1]["lat"]])
                bridge_coords.extend([[s["lon"], s["lat"]] for s in uc_stns])
                
                features.append({
                    "type": "Feature",
                    "geometry": mapping(LineString(bridge_coords)),
                    "properties": {
                        "line_id": lid,
                        "line_name": f"{lname} (Phase 2)",
                        "status": "under_construction",
                        "is_operational": False,
                        "color": color,
                        "stroke_width": 3.5,
                        "dasharray": [2, 2],
                        "station_count": len(uc_stns),
                        "start_station": uc_stns[0]["station_name"],
                        "end_station": uc_stns[-1]["station_name"]
                    }
                })
                
    metro_fc = {
        "type": "FeatureCollection",
        "metadata": {
            "title": "Mumbai Metro Track Network",
            "count": len(features)
        },
        "features": features
    }
    
    with open(OUTPUT_METRO_TRACKS_PATH, "w", encoding="utf-8") as f:
        json.dump(metro_fc, f, indent=2)
    logger.info(f"Saved {len(features)} styled Metro corridor features to: {OUTPUT_METRO_TRACKS_PATH}")
    return metro_fc


def build_styled_suburban_rail():
    """Extract and style Suburban Rail tracks (#546E7A)."""
    with open(TRANSIT_LINES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    rail_features = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        if props.get("transit_type") == "suburban_rail" or props.get("railway") == "rail":
            feat["properties"]["color"] = "#546E7A"
            feat["properties"]["stroke_width"] = 1.8
            feat["properties"]["is_operational"] = True
            feat["properties"]["transit_type"] = "suburban_rail"
            rail_features.append(feat)
            
    rail_fc = {
        "type": "FeatureCollection",
        "metadata": {
            "title": "Mumbai Suburban Rail Network",
            "count": len(rail_features)
        },
        "features": rail_features
    }
    
    with open(OUTPUT_RAIL_PATH, "w", encoding="utf-8") as f:
        json.dump(rail_fc, f, indent=2)
    logger.info(f"Saved {len(rail_features)} styled Suburban Rail features to: {OUTPUT_RAIL_PATH}")
    return rail_fc


def main():
    logger.info("=" * 80)
    logger.info("GENERATING STYLED VECTOR TRANSIT LAYERS FOR MAPLIBRE GL JS")
    logger.info("=" * 80)
    build_styled_metro_tracks()
    build_styled_suburban_rail()


if __name__ == "__main__":
    main()
