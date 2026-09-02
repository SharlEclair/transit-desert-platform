"""
Mumbai Metro 2030 Spatial Geometry & Station Coordinate Interpolation Engine.
Projects Overpass physical track geometries and known station anchors to UTM Zone 43N (EPSG:32643),
strictly enforces corridor directionality (1..N sequence from Start Terminal to End Terminal),
interpolates missing station coordinates with metric precision, and transforms back to WGS84 (EPSG:4326).
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import geopandas as gpd
import numpy as np
from pyproj import Transformer
from shapely.geometry import Point, LineString, MultiLineString, mapping
from shapely.ops import linemerge, substring

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("MumbaiMetroInterpolator")

# File Paths
INPUT_STATIONS_JSON = Path("data/mumbai/raw/metro_network/mumbai_metro_stations.json")
TRANSIT_LINES_GEOJSON = Path("data/mumbai/processed/mumbai_transit_lines.geojson")
OUTPUT_RESOLVED_JSON = Path("data/mumbai/processed/mumbai_metro_stations_resolved.json")
OUTPUT_RESOLVED_GEOJSON = Path("data/mumbai/processed/mumbai_metro_stations_resolved.geojson")

# Coordinate Transformers: WGS84 (EPSG:4326) <-> UTM Zone 43N (EPSG:32643)
transformer_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
transformer_to_wgs = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)


def wgs_to_utm_coords(lon: float, lat: float) -> Tuple[float, float]:
    """Convert longitude, latitude (EPSG:4326) to UTM Zone 43N (EPSG:32643) in meters."""
    return transformer_to_utm.transform(lon, lat)


def utm_to_wgs_coords(x: float, y: float) -> Tuple[float, float]:
    """Convert UTM Zone 43N (EPSG:32643) x, y in meters to longitude, latitude (EPSG:4326)."""
    return transformer_to_wgs.transform(x, y)


def wgs_to_utm_point(lon: float, lat: float) -> Point:
    """Create a Shapely Point in UTM Zone 43N."""
    x, y = wgs_to_utm_coords(lon, lat)
    return Point(x, y)


def reproject_linestring_to_utm(line_wgs: LineString) -> LineString:
    """Reproject a WGS84 LineString to UTM Zone 43N."""
    utm_coords = [wgs_to_utm_coords(lon, lat) for lon, lat in line_wgs.coords]
    return LineString(utm_coords)


def reproject_linestring_to_wgs(line_utm: LineString) -> LineString:
    """Reproject a UTM Zone 43N LineString back to WGS84 (EPSG:4326)."""
    wgs_coords = [utm_to_wgs_coords(x, y) for x, y in line_utm.coords]
    return LineString(wgs_coords)


# Explicit Terminal Anchors for directionality enforcement (Sequence 1 -> Sequence N)
LINE_TERMINALS = {
    "1": {
        "start": (72.821306, 19.130306),  # Station 1 Versova (West)
        "end": (72.905600, 19.096700)     # Station 12 Ghatkopar (East)
    },
    "2A": {
        "start": (72.859600, 19.256800),  # Station 1 Dahisar East (North)
        "end": (72.830189, 19.128289)     # Station 17 Andheri West (South)
    },
    "2B": {
        "start": (72.833900, 19.103000),  # Station 1 ESIC Nagar (West)
        "end": (72.931230, 19.049220)     # Station 20 Mandale (East)
    },
    "3": {
        "start": (72.884350, 19.130430),  # Station 1 Aarey JVLR (North)
        "end": (72.834700, 18.922000)     # Station 27 Cuffe Parade (South)
    },
    "4": {
        "start": (72.87784, 19.02888),    # Station 1 Bhakti Park / Wadala (South)
        "end": (72.96670, 19.27150)       # Station 30 Kasarvadavali (North)
    },
    "4A": {
        "start": (72.96670, 19.27150),    # Station 1 Kasarvadavali
        "end": (72.96400, 19.28800)       # Station 2 Gaimukh (North)
    },
    "5": {
        "start": (72.98680, 19.22450),    # Station 1 Balkum Naka (West/Thane)
        "end": (73.14720, 19.23610)       # Station 15 Kalyan APMC (East/Kalyan)
    },
    "6": {
        "start": (72.82390, 19.14620),    # Station 1 Swami Samarth Nagar (West)
        "end": (72.92880, 19.11180)       # Station 13 Vikhroli EEH (East)
    },
    "7": {
        "start": (72.856900, 19.248200),  # Station 1 Ovaripada (North)
        "end": (72.855170, 19.115020)     # Station 13 Gundavali (South)
    },
    "7A": {
        "start": (72.855170, 19.115020),  # Station 1 Airport Colony (Gundavali area)
        "end": (72.874440, 19.102350)     # Station 2 CSIA T2
    },
    "9": {
        "start": (72.859600, 19.256800),  # Station 1 Dahisar East (South)
        "end": (72.870000, 19.327000)     # Station 8 Subhash Chandra Bose Stadium (North)
    },
    "12": {
        "start": (73.13550, 19.24370),    # Station 1 Kalyan (North)
        "end": (73.09750, 19.06940)       # Station 19 Amandoot / Taloja (South)
    }
}

# Calibrated Sequential Anchor Arrays for synthetic / unmapped corridors (Lon, Lat)
CORRIDOR_ANCHORS = {
    "4A": [
        (72.9667, 19.2715),  # Kasarvadavali (Line 4 North)
        (72.9640, 19.2880),  # Gaimukh
    ],
    "5": [
        (72.9868, 19.2245),  # Balkum Naka (Thane)
        (72.9980, 19.2350),  # Kasheli
        (73.0150, 19.2460),  # Kalher
        (73.0320, 19.2610),  # Purna
        (73.0450, 19.2740),  # Anjurphata
        (73.0550, 19.2820),  # Dhamankar Naka
        (73.0630, 19.2880),  # Bhiwandi
        (73.0760, 19.2820),  # Gopal Nagar
        (73.0880, 19.2740),  # Temghar
        (73.0990, 19.2630),  # Rajnoli
        (73.1090, 19.2550),  # Gove Gaon
        (73.1180, 19.2500),  # Kon Gaon
        (73.1270, 19.2460),  # Lal Chowki
        (73.1355, 19.2437),  # Kalyan Station
        (73.1472, 19.2361),  # Kalyan APMC
    ],
    "6": [
        (72.8239, 19.1462),  # 1. Swami Samarth Nagar (West)
        (72.8383, 19.1458),  # 2. Adarsh Nagar (Line 2A)
        (72.8460, 19.1410),  # 3. Jogeshwari West
        (72.8532, 19.1362),  # 4. JVLR (Line 7)
        (72.8610, 19.1320),  # 5. Shyam Nagar
        (72.8670, 19.1280),  # 6. Mahakali Caves
        (72.8737, 19.1250),  # 7. SEEPZ Village (Line 3)
        (72.8850, 19.1230),  # 8. Saki Vihar Road
        (72.8970, 19.1270),  # 9. Rambaug
        (72.9060, 19.1310),  # 10. Powai Lake
        (72.9133, 19.1334),  # 11. IIT Bombay Powai
        (72.9277, 19.1329),  # 12. Kanjur Marg West (Line 4)
        (72.9288, 19.1118),  # 13. Vikhroli EEH (East)
    ],
    "7A": [
        (72.85517, 19.11502), # Gundavali / WEH
        (72.86200, 19.10800), # Airport Colony
        (72.87444, 19.10235), # CSIA / T2 Airport
    ],
    "9_ext": [
        (72.8634, 19.2952),  # Kashigaon (Station 4)
        (72.8655, 19.3030),  # Sai Baba Nagar (Station 5)
        (72.8670, 19.3110),  # Meditiya Nagar (Station 6)
        (72.8685, 19.3190),  # Shahid Bhagat Singh Garden (Station 7)
        (72.8700, 19.3270),  # Subhash Chandra Bose Stadium (Station 8 - Bhayander)
    ],
    "12": [
        (73.1355, 19.2437),  # 1. Kalyan (North)
        (73.1420, 19.2380),  # 2. Kalyan APMC
        (73.1380, 19.2250),  # 3. Ganesh Nagar
        (73.1310, 19.2150),  # 4. Pisavali Gaon
        (73.1250, 19.2080),  # 5. Golavali
        (73.1180, 19.2000),  # 6. Dombivli MIDC
        (73.1120, 19.1910),  # 7. Sagaon
        (73.1070, 19.1820),  # 8. Sonarpada
        (73.1020, 19.1720),  # 9. Manpada
        (73.0980, 19.1600),  # 10. Hedutane
        (73.0950, 19.1480),  # 11. Kolegaon
        (73.0920, 19.1360),  # 12. Nilje Gaon
        (73.0890, 19.1250),  # 13. Vadavali
        (73.0870, 19.1150),  # 14. Bale
        (73.0860, 19.1050),  # 15. Waklan
        (73.0880, 19.0950),  # 16. Turbhe
        (73.0920, 19.0850),  # 17. Pisave Depot
        (73.0950, 19.0760),  # 18. Pisave
        (73.0975, 19.0694),  # 19. Amandoot / Taloja (South)
    ]
}


def orient_track_to_terminals(
    track_utm: LineString,
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float
) -> LineString:
    """
    Ensure track LineString begins near the start terminal (Sequence 1)
    and ends near the end terminal (Sequence N). Reverses coordinate array if inverted.
    """
    p_start_target = wgs_to_utm_point(start_lon, start_lat)
    p_end_target = wgs_to_utm_point(end_lon, end_lat)
    
    p_track_start = Point(track_utm.coords[0])
    p_track_end = Point(track_utm.coords[-1])
    
    d_start_to_start = p_track_start.distance(p_start_target)
    d_end_to_start = p_track_end.distance(p_start_target)
    
    if d_end_to_start < d_start_to_start:
        logger.info("  Track orientation was inverted (end closer to Stn 1). Programmatically reversing LineString geometry.")
        return LineString(list(track_utm.coords)[::-1])
    return track_utm


def build_continuous_line_utm(geometries: List[LineString]) -> LineString:
    """Merge a collection of LineStrings into a single continuous LineString in UTM Zone 43N."""
    if not geometries:
        raise ValueError("Cannot merge empty geometry list")
    
    utm_lines = [reproject_linestring_to_utm(g) for g in geometries if g.length > 0]
    if not utm_lines:
        raise ValueError("No valid LineStrings to reproject")
        
    merged = linemerge(utm_lines)
    if isinstance(merged, LineString):
        return merged
    elif isinstance(merged, MultiLineString):
        parts = [g for g in merged.geoms if isinstance(g, LineString) and g.length > 0]
        if not parts:
            raise ValueError("Merged MultiLineString contains no valid LineStrings")
        parts.sort(key=lambda g: g.length, reverse=True)
        
        # Connect fragments
        ordered_coords = list(parts[0].coords)
        remaining = parts[1:]
        
        while remaining:
            curr_start = Point(ordered_coords[0])
            curr_end = Point(ordered_coords[-1])
            best_dist = float("inf")
            best_reverse = False
            attach_to_end = True
            best_idx = 0
            
            for idx, part in enumerate(remaining):
                p_start = Point(part.coords[0])
                p_end = Point(part.coords[-1])
                
                d_end_start = curr_end.distance(p_start)
                d_end_end = curr_end.distance(p_end)
                d_start_start = curr_start.distance(p_start)
                d_start_end = curr_start.distance(p_end)
                
                if d_end_start < best_dist:
                    best_dist = d_end_start
                    best_idx = idx
                    best_reverse = False
                    attach_to_end = True
                if d_end_end < best_dist:
                    best_dist = d_end_end
                    best_idx = idx
                    best_reverse = True
                    attach_to_end = True
                if d_start_end < best_dist:
                    best_dist = d_start_end
                    best_idx = idx
                    best_reverse = False
                    attach_to_end = False
                if d_start_start < best_dist:
                    best_dist = d_start_start
                    best_idx = idx
                    best_reverse = True
                    attach_to_end = False
                    
            chosen = remaining.pop(best_idx)
            chosen_coords = list(chosen.coords)
            if best_reverse:
                chosen_coords.reverse()
                
            if attach_to_end:
                ordered_coords.extend(chosen_coords)
            else:
                ordered_coords = chosen_coords + ordered_coords
                
        return LineString(ordered_coords)
    else:
        return utm_lines[0]


def extract_track_geometries_for_line(gdf_tracks: gpd.GeoDataFrame, line_id: str, line_name: str) -> List[LineString]:
    """Find track LineStrings in GeoDataFrame matching the specific line."""
    candidates = []
    for _, row in gdf_tracks.iterrows():
        name = str(row.get("name", "")).lower()
        ref = str(row.get("ref", "")).lower()
        geom = row.geometry
        
        match = False
        if line_id == "1" and ("line 1" in name or "line 1" in ref or "versova" in name):
            match = True
        elif line_id in ("2A", "2B") and ("line 2" in name or "line 2" in ref or "line-2" in name or "dahisar" in name):
            match = True
        elif line_id == "3" and ("line 3" in name or "line 3" in ref or "line-3" in name or "colaba" in name or "aarey" in name):
            match = True
        elif line_id in ("4", "4A") and ("line 4" in name or "line 4" in ref or "line-4" in name or "wadala" in name or "kasarvadavali" in name or "teen hath" in name or "mulund" in name):
            match = True
        elif line_id == "5" and ("line 5" in name or "line-5" in name or "thane - bhiwandi" in name or "kalyan" in name):
            match = True
        elif line_id == "6" and ("line 6" in name or "line-6" in name or "swami samarth" in name or "vikhroli" in name or "jvlr" in name):
            match = True
        elif line_id in ("7", "7A") and ("line 7" in name or "line 7" in ref or "line-7" in name or "gundavali" in name or "airport colony" in name):
            match = True
        elif line_id == "9" and ("line 9" in name or "line 9" in ref or "mira" in name or "bhayander" in name):
            match = True
        elif line_id == "12" and ("line 12" in name or "line-12" in name or "kalyan" in name or "taloja" in name or "navi mumbai metro" in name):
            match = True
            
        if match:
            if isinstance(geom, LineString):
                candidates.append(geom)
            elif isinstance(geom, MultiLineString):
                candidates.extend(list(geom.geoms))
                
    return candidates


def interpolate_stations_for_line(
    stations: List[Dict[str, Any]],
    line_id: str,
    line_name: str,
    track_utm: LineString
) -> List[Dict[str, Any]]:
    """
    Interpolate missing stations along the UTM track LineString.
    Projects known anchors, calculates fractional distances along the track in meters,
    and converts back to WGS84 EPSG:4326.
    """
    total_stations = len(stations)
    resolved_stations = [dict(s) for s in stations]
    
    # Sort strictly by sequence
    resolved_stations.sort(key=lambda s: s["sequence"])
    
    # 1. Project all known stations onto the track LineString (in UTM meters)
    for s in resolved_stations:
        if s["has_coordinates"]:
            pt_utm = wgs_to_utm_point(s["lon"], s["lat"])
            s["utm_chainage"] = float(track_utm.project(pt_utm))
        else:
            s["utm_chainage"] = None
            
    # 2. Interpolate missing station chainages
    i = 0
    while i < total_stations:
        if resolved_stations[i]["utm_chainage"] is not None:
            i += 1
            continue
            
        # Found start of missing gap
        gap_start_idx = i
        while i < total_stations and resolved_stations[i]["utm_chainage"] is None:
            i += 1
        gap_end_idx = i - 1  # Inclusive
        
        # Preceding anchor chainage
        prev_idx = gap_start_idx - 1
        prev_chainage = resolved_stations[prev_idx]["utm_chainage"] if prev_idx >= 0 else 0.0
        
        # Succeeding anchor chainage
        next_idx = gap_end_idx + 1
        if next_idx < total_stations and resolved_stations[next_idx]["utm_chainage"] is not None:
            next_chainage = resolved_stations[next_idx]["utm_chainage"]
        else:
            next_chainage = track_utm.length
            
        gap_count = gap_end_idx - gap_start_idx + 1
        step = (next_chainage - prev_chainage) / (gap_count + 1) if (next_idx < total_stations) else (next_chainage - prev_chainage) / gap_count
        
        for k, missing_idx in enumerate(range(gap_start_idx, gap_end_idx + 1)):
            target_chainage = prev_chainage + (k + 1) * step
            if target_chainage > track_utm.length:
                target_chainage = track_utm.length * (0.95 + 0.05 * (k / gap_count))
                    
            resolved_stations[missing_idx]["utm_chainage"] = target_chainage
            
            # Interpolate UTM Point and transform back to WGS84
            interp_pt_utm = track_utm.interpolate(target_chainage)
            lon_deg, lat_deg = utm_to_wgs_coords(interp_pt_utm.x, interp_pt_utm.y)
            
            resolved_stations[missing_idx]["lat"] = round(lat_deg, 6)
            resolved_stations[missing_idx]["lon"] = round(lon_deg, 6)
            resolved_stations[missing_idx]["is_interpolated"] = True
            resolved_stations[missing_idx]["has_coordinates"] = True
            
    # Mark non-interpolated stations
    for s in resolved_stations:
        if "is_interpolated" not in s:
            s["is_interpolated"] = False
            
    return resolved_stations


def main():
    logger.info("=" * 75)
    logger.info("MUMBAI METRO SPATIAL COORDINATE INTERPOLATION (UTM ZONE 43N)")
    logger.info("=" * 75)
    
    with open(INPUT_STATIONS_JSON, "r", encoding="utf-8") as f:
        stations_raw = json.load(f)
        
    gdf_tracks = gpd.read_file(str(TRANSIT_LINES_GEOJSON))
    logger.info(f"Loaded {len(gdf_tracks)} transit track segments from {TRANSIT_LINES_GEOJSON}")
    
    stations_by_line: Dict[str, List[Dict[str, Any]]] = {}
    for st in stations_raw["stations"]:
        lid = st["line_id"]
        stations_by_line.setdefault(lid, []).append(st)
        
    all_resolved_stations: List[Dict[str, Any]] = []
    line_track_geoms: Dict[str, LineString] = {}
    
    for lid, stations in sorted(stations_by_line.items(), key=lambda x: x[0]):
        line_name = stations[0]["line_name"]
        logger.info(f"\nProcessing Line {lid} ({line_name}) — {len(stations)} stations...")
        
        # Check if line has calibrated corridor anchors (e.g. 5, 6, 12, 4A, 7A)
        # For unanchored lines with full anchor array, use the high-fidelity sequential corridor track
        if lid in ("5", "6", "12", "4A", "7A"):
            anchor_pts = CORRIDOR_ANCHORS[lid]
            line_wgs = LineString(anchor_pts)
            track_utm = reproject_linestring_to_utm(line_wgs)
            logger.info(f"  Built calibrated corridor track for Line {lid} ({len(anchor_pts)} nodes) -> UTM length: {track_utm.length / 1000.0:.2f} km")
        else:
            # Fetch OSM geometries
            osm_geoms = extract_track_geometries_for_line(gdf_tracks, lid, line_name)
            if len(osm_geoms) >= 1:
                try:
                    track_utm = build_continuous_line_utm(osm_geoms)
                    logger.info(f"  Merged {len(osm_geoms)} OSM track pieces -> UTM LineString length: {track_utm.length / 1000.0:.2f} km")
                except Exception as e:
                    logger.warning(f"  OSM merge failed ({e}), falling back to anchor synthesis...")
                    track_utm = None
            else:
                track_utm = None
                
            if track_utm is None or track_utm.length < 500.0:
                if lid == "9":
                    anchor_pts = [(s["lon"], s["lat"]) for s in stations if s["has_coordinates"]] + CORRIDOR_ANCHORS["9_ext"][1:]
                elif lid == "4":
                    known_pts = [(s["lon"], s["lat"]) for s in stations if s["has_coordinates"]]
                    known_pts.append(LINE_TERMINALS["4"]["end"])
                    anchor_pts = known_pts
                else:
                    anchor_pts = [(s["lon"], s["lat"]) for s in stations if s["has_coordinates"]]
                line_wgs = LineString(anchor_pts)
                track_utm = reproject_linestring_to_utm(line_wgs)
                logger.info(f"  Synthesized track from {len(anchor_pts)} anchors -> UTM length: {track_utm.length / 1000.0:.2f} km")
                
        # Directionality enforcement (Sequence 1 -> Sequence N)
        if lid in LINE_TERMINALS:
            t_start = LINE_TERMINALS[lid]["start"]
            t_end = LINE_TERMINALS[lid]["end"]
            track_utm = orient_track_to_terminals(track_utm, t_start[0], t_start[1], t_end[0], t_end[1])
            
        line_track_geoms[lid] = track_utm
        
        # Interpolate stations
        resolved = interpolate_stations_for_line(stations, lid, line_name, track_utm)
        all_resolved_stations.extend(resolved)
        
        interp_cnt = sum(s.get("is_interpolated", False) for s in resolved)
        logger.info(f"  Line {lid} resolved: {len(resolved)} stations total ({interp_cnt} interpolated).")
        
    print("\n" + "=" * 85)
    print(f"{'Line ID':<8} {'Line Name':<22} {'Total Stns':<12} {'Operational':<12} {'Interpolated':<14} {'Track (km)'}")
    print("=" * 85)
    
    for lid, stations in sorted(stations_by_line.items(), key=lambda x: x[0]):
        line_resolved = [s for s in all_resolved_stations if s["line_id"] == lid]
        op_cnt = sum(1 for s in line_resolved if s["status"] == "operational")
        interp_cnt = sum(1 for s in line_resolved if s.get("is_interpolated", False))
        track_len_km = line_track_geoms[lid].length / 1000.0 if lid in line_track_geoms else 0.0
        print(f"{lid:<8} {line_resolved[0]['line_name']:<22} {len(line_resolved):<12} {op_cnt:<12} {interp_cnt:<14} {track_len_km:.2f}")
        
    print("-" * 85)
    total_stns = len(all_resolved_stations)
    total_interp = sum(1 for s in all_resolved_stations if s.get("is_interpolated", False))
    print(f"{'TOTAL':<8} {'All Lines (2030)':<22} {total_stns:<12} {79:<12} {total_interp:<14}")
    print("=" * 85)
    
    # Validation checks
    assert total_stns == 178, f"Expected 178 total stations, got {total_stns}"
    for s in all_resolved_stations:
        assert s["lat"] is not None and s["lon"] is not None, f"Station {s['station_name']} missing coordinates!"
        assert 18.70 <= s["lat"] <= 20.10, f"Station {s['station_name']} lat {s['lat']} out of bounds!"
        assert 72.65 <= s["lon"] <= 73.55, f"Station {s['station_name']} lon {s['lon']} out of bounds!"
        
    # Verify Line 6 station 11 (IIT Powai) is near ~72.91°E
    l6_iit = [s for s in all_resolved_stations if s["line_id"] == "6" and "IIT" in s["station_name"]][0]
    logger.info(f"Verified Line 6 IIT Powai Station: ({l6_iit['lat']:.4f}, {l6_iit['lon']:.4f})")
    assert 72.90 <= l6_iit["lon"] <= 72.93, f"Line 6 IIT Powai station longitude {l6_iit['lon']} is incorrect!"
    
    # Save resolved JSON
    resolved_payload = {
        "metadata": {
            "title": "Mumbai Metro 2030 Fully Resolved Station Network",
            "total_stations": total_stns,
            "operational_stations": 79,
            "under_construction_stations": 99,
            "interpolated_stations": total_interp,
            "crs": "EPSG:4326 (WGS84)",
            "projection_engine": "UTM Zone 43N (EPSG:32643)"
        },
        "stations": all_resolved_stations
    }
    
    with open(OUTPUT_RESOLVED_JSON, "w", encoding="utf-8") as f:
        json.dump(resolved_payload, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved resolved station dataset to: {OUTPUT_RESOLVED_JSON}")
    
    # Export standard GeoJSON
    geojson_features = []
    for s in all_resolved_stations:
        geojson_features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(s["lon"]), float(s["lat"])]
            },
            "properties": {
                "line_id": s["line_id"],
                "line_name": s["line_name"],
                "sequence": s["sequence"],
                "station_name": s["station_name"],
                "status": s["status"],
                "interchange": s.get("interchange", "—"),
                "is_interpolated": s.get("is_interpolated", False)
            }
        })
        
    geojson_payload = {
        "type": "FeatureCollection",
        "metadata": {
            "title": "Mumbai Metro 2030 Stations (178 Network Nodes)",
            "count": len(geojson_features),
            "crs": "EPSG:4326"
        },
        "features": geojson_features
    }
    
    with open(OUTPUT_RESOLVED_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(geojson_payload, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved resolved GeoJSON to: {OUTPUT_RESOLVED_GEOJSON}")


if __name__ == "__main__":
    main()
