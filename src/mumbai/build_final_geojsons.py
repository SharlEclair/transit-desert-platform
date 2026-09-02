"""
Build Final Standardized Mumbai GeoJSON Datasets from Verified KML v3.

Generates:
1. `data/mumbai/processed/mumbai_metro_stations_resolved.geojson`:
   All 177 resolved 2030 Mumbai Metro station points (79 operational, 98 under-construction).
2. `data/mumbai/processed/mumbai_metro_stations_resolved.json`:
   JSON structured dataset of the 177 stations.
3. `data/mumbai/processed/mumbai_metro_tracks_styled.geojson`:
   Physical track LineString alignments for each metro corridor with MMRDA colors and status.
4. `data/mumbai/processed/mumbai_suburban_rail_styled.geojson`:
   Suburban Rail tracks styled in #546E7A Dark Slate.
5. `data/mumbai/processed/mumbai_transit_lines.geojson`:
   Combined transit network (Metro + Suburban Rail).
"""

import os
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("BuildFinalGeoJSONs")

KML_V3_PATH = Path("data/mumbai/raw/metro_network/Mumbai Metro v3.kml")
FINAL_MAPPING_PATH = Path("data/mumbai/raw/metro_network/final_station_mapping.json")
OFFICIAL_STATIONS_JSON = Path("data/mumbai/raw/metro_network/mumbai_metro_stations.json")

STATIONS_GEOJSON_OUT = Path("data/mumbai/processed/mumbai_metro_stations_resolved.geojson")
STATIONS_JSON_OUT = Path("data/mumbai/processed/mumbai_metro_stations_resolved.json")
METRO_TRACKS_OUT = Path("data/mumbai/processed/mumbai_metro_tracks_styled.geojson")
SUBURBAN_RAIL_OUT = Path("data/mumbai/processed/mumbai_suburban_rail_styled.geojson")
TRANSIT_LINES_OUT = Path("data/mumbai/processed/mumbai_transit_lines.geojson")

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


def build_stations_geojson():
    logger.info("Building Mumbai Metro Stations GeoJSON & JSON...")
    with open(FINAL_MAPPING_PATH, "r", encoding="utf-8") as f:
        map_data = json.load(f)

    with open(OFFICIAL_STATIONS_JSON, "r", encoding="utf-8") as f:
        official_data = json.load(f)

    # Index official stations by station_name and line_id
    raw_stations = [s for s in official_data.get("stations", []) if s.get("station_name") != "National College"]

    # Match detailed entries
    detailed_map = {
        (s["official_name"], s["line_id"]): s
        for s in map_data.get("detailed_stations", [])
    }
    
    # Fallback map by name only
    detailed_by_name = {
        s["official_name"]: s
        for s in map_data.get("detailed_stations", [])
    }

    station_features = []
    station_json_list = []

    seq_counters: Dict[str, int] = {}

    for s in raw_stations:
        st_name = s["station_name"]
        lid = str(s.get("line_id", ""))
        status = str(s.get("status", "under_construction"))
        
        # Determine sequence
        seq_counters[lid] = seq_counters.get(lid, 0) + 1
        seq = seq_counters[lid]

        # Retrieve coordinates
        coords = None
        key = (st_name, lid)
        if key in detailed_map and detailed_map[key].get("coordinates"):
            coords = detailed_map[key]["coordinates"]
        elif st_name in detailed_by_name and detailed_by_name[st_name].get("coordinates"):
            coords = detailed_by_name[st_name]["coordinates"]
        elif s.get("lon") is not None and s.get("lat") is not None:
            coords = [float(s["lon"]), float(s["lat"])]

        if not coords:
            logger.error(f"Missing coordinates for station: {st_name} (Line {lid})")
            continue

        lon, lat = float(coords[0]), float(coords[1])
        color = MMRDA_COLORS.get(lid, "#00AEEF")
        lname = LINE_NAMES.get(lid, f"Line {lid}")
        is_op = (status == "operational")

        station_record = {
            "station_name": st_name,
            "line_id": lid,
            "line_name": lname,
            "status": status,
            "is_operational": is_op,
            "sequence": seq,
            "stop_sequence": seq,
            "lon": lon,
            "lat": lat,
            "color": color,
            "interchange": s.get("interchange", "—")
        }
        station_json_list.append(station_record)

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "station_name": st_name,
                "line_id": lid,
                "line_name": lname,
                "status": status,
                "is_operational": is_op,
                "sequence": seq,
                "stop_sequence": seq,
                "color": color,
                "interchange": str(s.get("interchange", "—"))
            }
        }
        station_features.append(feature)

    # Save Stations GeoJSON
    fc = {
        "type": "FeatureCollection",
        "metadata": {
            "title": "Mumbai Metro Stations (2030 Network)",
            "count": len(station_features),
            "operational_count": sum(1 for f in station_features if f["properties"]["is_operational"]),
            "under_construction_count": sum(1 for f in station_features if not f["properties"]["is_operational"])
        },
        "features": station_features
    }

    STATIONS_GEOJSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(STATIONS_GEOJSON_OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2, ensure_ascii=False)

    # Save Stations JSON
    with open(STATIONS_JSON_OUT, "w", encoding="utf-8") as f:
        json.dump({
            "metadata": fc["metadata"],
            "stations": station_json_list
        }, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(station_features)} station features to {STATIONS_GEOJSON_OUT} ({fc['metadata']['operational_count']} Operational, {fc['metadata']['under_construction_count']} Under Construction)")
    return station_json_list


def extract_kml_tracks():
    """Extract LineString physical track geometries from Mumbai Metro v3.kml."""
    logger.info(f"Extracting track geometries from {KML_V3_PATH}...")
    tree = ET.parse(KML_V3_PATH)
    root = tree.getroot()
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    if root.find('.//kml:Placemark', ns) is None:
        ns = {'kml': ''}

    kml_lines: Dict[str, List[List[float]]] = {}
    placemarks = root.findall('.//kml:Placemark', ns) if ns['kml'] else root.findall('.//Placemark')

    for pm in placemarks:
        ls = pm.find('.//kml:LineString', ns) if ns['kml'] else pm.find('.//LineString')
        if ls is not None:
            name_tag = pm.find('kml:name', ns) if ns['kml'] else pm.find('name')
            name = name_tag.text.strip() if name_tag is not None and name_tag.text else "Unnamed"
            coords_tag = ls.find('kml:coordinates', ns) if ns['kml'] else ls.find('coordinates')
            coords_str = coords_tag.text.strip() if coords_tag is not None and coords_tag.text else ""
            
            coord_pairs = []
            for c in coords_str.split():
                parts = c.strip().split(",")
                if len(parts) >= 2:
                    try:
                        coord_pairs.append([float(parts[0]), float(parts[1])])
                    except ValueError:
                        pass
            if coord_pairs:
                kml_lines[name] = coord_pairs

    return kml_lines


def build_metro_tracks(station_json_list: List[Dict[str, Any]], kml_lines: Dict[str, List[List[float]]]):
    logger.info("Synthesizing Styled Metro Track alignments...")
    features = []

    # Map KML track names to line_id
    kml_name_mapping = {
        "Metro Line 1 (Blue)": "1",
        "Yellow Line (Line 2A)": "2A",
        "Line 2B": "2B",
        "Metro Line 3 (Aqua)": "3",
        "Line 4": "4",
        "Line 4A": "4A",
        "Metro Line 5 (Orange) ong.": "5",
        "Metro Line 6 (Pink)": "6",
        "Metro Line 7 (Red)": "7",
        "Metro Line 9 (Red)": "9",
        "Metro Line 12 (Orange)": "12"
    }

    line_ids = ["1", "2A", "2B", "3", "4", "4A", "5", "6", "7", "7A", "9", "12"]

    for lid in line_ids:
        stns = [s for s in station_json_list if s["line_id"] == lid]
        stns.sort(key=lambda s: s["sequence"])
        if len(stns) < 2:
            continue

        color = MMRDA_COLORS.get(lid, "#FFFFFF")
        lname = LINE_NAMES.get(lid, f"Line {lid}")

        # Find raw KML track if available
        matched_kml_track = None
        for k_name, l_id in kml_name_mapping.items():
            if l_id == lid and k_name in kml_lines:
                matched_kml_track = kml_lines[k_name]
                break

        # Fallback to station sequence line if KML LineString not present
        if not matched_kml_track:
            matched_kml_track = [[s["lon"], s["lat"]] for s in stns]

        # Check operational split (Line 2B and Line 9)
        op_stns = [s for s in stns if s["status"] == "operational"]
        uc_stns = [s for s in stns if s["status"] == "under_construction"]

        if lid == "2B":
            # Phase 1 Operational: Mandale to Chembur (6 stations)
            if len(op_stns) >= 2:
                op_coords = [[s["lon"], s["lat"]] for s in op_stns]
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": op_coords},
                    "properties": {
                        "line_id": "2B",
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

            # Phase 2 Under Construction: ESIC Nagar to EEH (13 stations)
            if len(uc_stns) >= 2:
                uc_coords = [[s["lon"], s["lat"]] for s in uc_stns]
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": uc_coords},
                    "properties": {
                        "line_id": "2B",
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

        elif lid == "9":
            # Phase 1 Operational: Dahisar East to Kashigaon (4 stations)
            if len(op_stns) >= 2:
                op_coords = [[s["lon"], s["lat"]] for s in op_stns]
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": op_coords},
                    "properties": {
                        "line_id": "9",
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

            # Phase 2 Under Construction (4 stations)
            if len(uc_stns) >= 2:
                uc_coords = [[op_stns[-1]["lon"], op_stns[-1]["lat"]]] + [[s["lon"], s["lat"]] for s in uc_stns]
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": uc_coords},
                    "properties": {
                        "line_id": "9",
                        "line_name": f"{lname} (Phase 2 Extension)",
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

        elif lid == "7A":
            # 2 stations: Andheri East -> CSIA
            coords = [[s["lon"], s["lat"]] for s in stns]
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "line_id": "7A",
                    "line_name": lname,
                    "status": "under_construction",
                    "network": "metro",
                    "transit_type": "metro",
                    "is_operational": False,
                    "color": color,
                    "stroke_width": 3.5,
                    "dasharray": [2, 2],
                    "station_count": len(stns),
                    "start_station": stns[0]["station_name"],
                    "end_station": stns[-1]["station_name"]
                }
            })

        else:
            # Single status line (Line 1, 2A, 3, 7 are operational; 4, 4A, 5, 6, 12 are under_construction)
            is_op = (stns[0]["status"] == "operational")
            status_str = "operational" if is_op else "under_construction"
            
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": matched_kml_track},
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

    fc = {
        "type": "FeatureCollection",
        "metadata": {
            "title": "Mumbai Metro Track Alignments (2030 Network)",
            "count": len(features)
        },
        "features": features
    }

    with open(METRO_TRACKS_OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(features)} Metro track features to {METRO_TRACKS_OUT}")
    return features


def build_suburban_rail():
    logger.info("Standardizing Suburban Rail GeoJSON...")
    rail_features = []

    if SUBURBAN_RAIL_OUT.exists():
        with open(SUBURBAN_RAIL_OUT, "r", encoding="utf-8") as f:
            data = json.load(f)
            rail_features = data.get("features", [])
    elif TRANSIT_LINES_OUT.exists():
        with open(TRANSIT_LINES_OUT, "r", encoding="utf-8") as f:
            data = json.load(f)
            for feat in data.get("features", []):
                p = feat.get("properties", {})
                if p.get("network") == "rail" or p.get("transit_type") == "suburban_rail" or p.get("railway") == "rail":
                    feat["properties"]["network"] = "rail"
                    feat["properties"]["transit_type"] = "suburban_rail"
                    feat["properties"]["status"] = "operational"
                    feat["properties"]["is_operational"] = True
                    feat["properties"]["color"] = "#546E7A"
                    feat["properties"]["stroke_width"] = 1.8
                    rail_features.append(feat)

    # Standardize properties
    for feat in rail_features:
        feat["properties"]["network"] = "rail"
        feat["properties"]["transit_type"] = "suburban_rail"
        feat["properties"]["status"] = "operational"
        feat["properties"]["is_operational"] = True
        feat["properties"]["color"] = "#546E7A"
        feat["properties"]["stroke_width"] = 1.8

    fc = {
        "type": "FeatureCollection",
        "metadata": {"title": "Mumbai Suburban Rail", "count": len(rail_features)},
        "features": rail_features
    }

    with open(SUBURBAN_RAIL_OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(rail_features)} Suburban Rail features to {SUBURBAN_RAIL_OUT}")
    return rail_features


def main():
    logger.info("=" * 80)
    logger.info("GENERATING FINAL MUMBAI TRANSIT GEOJSON DATASETS")
    logger.info("=" * 80)

    stations = build_stations_geojson()
    kml_lines = extract_kml_tracks()
    metro_tracks = build_metro_tracks(stations, kml_lines)
    suburban_rail = build_suburban_rail()

    # Save Combined Master Transit Network
    combined_fc = {
        "type": "FeatureCollection",
        "metadata": {
            "title": "Mumbai Multimodal Transit Network (Metro + Suburban Rail)",
            "metro_track_count": len(metro_tracks),
            "suburban_rail_count": len(suburban_rail),
            "total_count": len(metro_tracks) + len(suburban_rail)
        },
        "features": metro_tracks + suburban_rail
    }

    with open(TRANSIT_LINES_OUT, "w", encoding="utf-8") as f:
        json.dump(combined_fc, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(combined_fc['features'])} combined transit features to {TRANSIT_LINES_OUT}")
    logger.info("GeoJSON generation completed successfully.")


if __name__ == "__main__":
    main()
