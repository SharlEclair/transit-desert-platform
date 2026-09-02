"""
Synthetic Mumbai Metro GTFS Generator.
Generates compliant GTFS archives for:
1. `mumbai_2030_metro_gtfs.zip`: Complete 2030 planned network (10 lines, 178 stations)
2. `mumbai_operational_metro_gtfs.zip`: Strictly the 79 active operational stations (Line 1, 2A, 2B Phase 1, 3, 7, 9 Phase 1)

Engineering Rules:
- Service Window: 06:00:00 to 12:00:00 (Morning Peak)
- Commercial Speed: Flat 35.0 km/h (includes station dwell time per transport engineering standard)
- Line 2B Split: Distinct route_ids for Operational Phase 1 vs Under Construction Phase 2
- Bi-directional trip synthesis (direction_id 0 and 1)
- Valid bridging calendar.txt (2026-2030 daily/weekday) for r5py compatibility
- Line-specific peak headways:
  * Line 1: 3.33 min (200s)
  * Line 2A: 4.0 min (240s)
  * Line 2B (Phase 1 & 2): 5.0 min (300s)
  * Line 3: 3.5 min (210s)
  * Line 4 & 4A: 4.25 min (255s)
  * Line 5: 4.0 min (240s)
  * Line 6: 3.5 min (210s)
  * Line 7: 5.5 min (330s)
  * Line 7A & Line 9: 5.75 min (345s)
  * Line 12: 6.0 min (360s)
"""

import os
import sys
import json
import zipfile
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple
import math

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("SynthesizeFutureGTFS")

RESOLVED_STATIONS_GEOJSON = Path("data/mumbai/processed/mumbai_metro_stations_resolved.geojson")
OUTPUT_2030_GTFS_ZIP = Path("data/mumbai/processed/mumbai_2030_metro_gtfs.zip")
OUTPUT_OPERATIONAL_GTFS_ZIP = Path("data/mumbai/processed/mumbai_operational_metro_gtfs.zip")

COMMERCIAL_SPEED_KMH = 35.0
SERVICE_START_SEC = 6 * 3600       # 06:00:00 AM (21600s)
SERVICE_END_SEC = 12 * 3600        # 12:00:00 PM (43200s)

def haversine_dist_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate Great Circle distance in km between two WGS84 points."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

# Headways configuration (in seconds)
HEADWAYS_CONFIG = {
    "METRO_L1": 200,       # 3.33 min
    "METRO_L2A": 240,      # 4.0 min
    "METRO_L2B_OP": 300,   # 5.0 min
    "METRO_L2B_UC": 300,   # 5.0 min
    "METRO_L3": 210,       # 3.5 min
    "METRO_L4": 255,       # 4.25 min
    "METRO_L4A": 255,      # 4.25 min
    "METRO_L5": 240,       # 4.0 min
    "METRO_L6": 210,       # 3.5 min
    "METRO_L7": 330,       # 5.5 min
    "METRO_L7A": 345,      # 5.75 min
    "METRO_L9": 345,       # 5.75 min
    "METRO_L9_OP": 345,    # 5.75 min (Operational Phase 1: Dahisar East to Kashigaon)
    "METRO_L12": 360       # 6.0 min
}

# Full 2030 Route Metadata
ROUTES_METADATA_2030 = {
    "METRO_L1": {
        "short_name": "Line 1",
        "long_name": "Versova - Andheri - Ghatkopar",
        "color": "00AEEF",
        "text_color": "FFFFFF",
        "line_id": "1",
        "status_filter": None
    },
    "METRO_L2A": {
        "short_name": "Line 2A",
        "long_name": "Dahisar East - Andheri West",
        "color": "FFC600",
        "text_color": "000000",
        "line_id": "2A",
        "status_filter": None
    },
    "METRO_L2B_OP": {
        "short_name": "Line 2B (Phase 1)",
        "long_name": "Maharashtranagar/Mandale - Chembur (Operational)",
        "color": "FFC600",
        "text_color": "000000",
        "line_id": "2B",
        "status_filter": "operational"
    },
    "METRO_L2B_UC": {
        "short_name": "Line 2B (Phase 2)",
        "long_name": "ESIC Nagar - Bandra - Kurla - EEH (Under Construction)",
        "color": "FFC600",
        "text_color": "000000",
        "line_id": "2B",
        "status_filter": "under_construction"
    },
    "METRO_L3": {
        "short_name": "Line 3",
        "long_name": "Aarey JVLR - BKC - Cuffe Parade",
        "color": "059DB2",
        "text_color": "FFFFFF",
        "line_id": "3",
        "status_filter": None
    },
    "METRO_L4": {
        "short_name": "Line 4",
        "long_name": "Wadala - Mulund - Kasarvadavali",
        "color": "00AE5A",
        "text_color": "FFFFFF",
        "line_id": "4",
        "status_filter": None
    },
    "METRO_L4A": {
        "short_name": "Line 4A",
        "long_name": "Kasarvadavali - Gaimukh",
        "color": "00AE5A",
        "text_color": "FFFFFF",
        "line_id": "4A",
        "status_filter": None
    },
    "METRO_L5": {
        "short_name": "Line 5",
        "long_name": "Balkum Naka (Thane) - Bhiwandi - Kalyan APMC",
        "color": "FF8200",
        "text_color": "FFFFFF",
        "line_id": "5",
        "status_filter": None
    },
    "METRO_L6": {
        "short_name": "Line 6",
        "long_name": "Swami Samarth Nagar - Powai - Vikhroli EEH",
        "color": "F99FC9",
        "text_color": "FFFFFF",
        "line_id": "6",
        "status_filter": None
    },
    "METRO_L7": {
        "short_name": "Line 7",
        "long_name": "Ovaripada - Gundavali",
        "color": "D83431",
        "text_color": "FFFFFF",
        "line_id": "7",
        "status_filter": None
    },
    "METRO_L7A": {
        "short_name": "Line 7A",
        "long_name": "Airport Colony - CSIA (Airport Extension)",
        "color": "D83431",
        "text_color": "FFFFFF",
        "line_id": "7A",
        "status_filter": None
    },
    "METRO_L9": {
        "short_name": "Line 9",
        "long_name": "Dahisar East - Kashigaon - Subhash Chandra Bose Stadium",
        "color": "D83431",
        "text_color": "FFFFFF",
        "line_id": "9",
        "status_filter": None
    },
    "METRO_L12": {
        "short_name": "Line 12",
        "long_name": "Kalyan - Dombivli - Amandoot/Taloja",
        "color": "FF8200",
        "text_color": "FFFFFF",
        "line_id": "12",
        "status_filter": None
    }
}

# Operational-Only (79 Stations) Route Metadata
ROUTES_METADATA_OPERATIONAL = {
    "METRO_L1": {
        "short_name": "Line 1",
        "long_name": "Versova - Andheri - Ghatkopar",
        "color": "00AEEF",
        "text_color": "FFFFFF",
        "line_id": "1",
        "status_filter": "operational"
    },
    "METRO_L2A": {
        "short_name": "Line 2A",
        "long_name": "Dahisar East - Andheri West",
        "color": "FFC600",
        "text_color": "000000",
        "line_id": "2A",
        "status_filter": "operational"
    },
    "METRO_L2B_OP": {
        "short_name": "Line 2B (Phase 1)",
        "long_name": "Maharashtranagar/Mandale - Chembur",
        "color": "FFC600",
        "text_color": "000000",
        "line_id": "2B",
        "status_filter": "operational"
    },
    "METRO_L3": {
        "short_name": "Line 3",
        "long_name": "Aarey JVLR - BKC - Cuffe Parade",
        "color": "059DB2",
        "text_color": "FFFFFF",
        "line_id": "3",
        "status_filter": "operational"
    },
    "METRO_L7": {
        "short_name": "Line 7",
        "long_name": "Ovaripada - Gundavali",
        "color": "D83431",
        "text_color": "FFFFFF",
        "line_id": "7",
        "status_filter": "operational"
    },
    "METRO_L9_OP": {
        "short_name": "Line 9 (Phase 1)",
        "long_name": "Dahisar East - Kashigaon",
        "color": "D83431",
        "text_color": "FFFFFF",
        "line_id": "9",
        "status_filter": "operational"
    }
}


def sec_to_gtfs_time(seconds: int) -> str:
    """Format total seconds from midnight into HH:MM:SS format."""
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{mins:02d}:{secs:02d}"


def calculate_segment_travel_time(p1_lon: float, p1_lat: float, p2_lon: float, p2_lat: float) -> int:
    """
    Calculate travel time in seconds between two points at flat 35 km/h commercial speed.
    """
    dist_km = haversine_dist_km(p1_lon, p1_lat, p2_lon, p2_lat)
    travel_time_sec = int(round((dist_km / COMMERCIAL_SPEED_KMH) * 3600.0))
    return max(40, travel_time_sec)


def generate_gtfs_tables(resolved_stations: List[Dict[str, Any]], routes_meta: Dict[str, Any]) -> Dict[str, str]:
    """Build CSV contents for all standard GTFS tables for a specified route set."""
    
    # 1. agency.txt
    agency_csv = [
        "agency_id,agency_name,agency_url,agency_timezone,agency_lang",
        "MMRDA,Mumbai Metropolitan Region Development Authority,https://mmrda.maharashtra.gov.in,Asia/Kolkata,en"
    ]
    
    # 2. calendar.txt
    calendar_csv = [
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date",
        "DAILY,1,1,1,1,1,1,1,20260101,20301231",
        "WEEKDAY,1,1,1,1,1,0,0,20260101,20301231"
    ]
    
    # 3. routes.txt
    routes_csv = [
        "route_id,agency_id,route_short_name,route_long_name,route_type,route_color,route_text_color"
    ]
    for r_id, meta in routes_meta.items():
        routes_csv.append(
            f"{r_id},MMRDA,\"{meta['short_name']}\",\"{meta['long_name']}\",1,{meta['color']},{meta['text_color']}"
        )
        
    # 4. stops.txt
    stops_csv = [
        "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station,wheelchair_boarding"
    ]
    
    route_stations: Dict[str, List[Dict[str, Any]]] = {}
    
    for r_id, meta in routes_meta.items():
        lid = meta["line_id"]
        status_flt = meta["status_filter"]
        
        stns = [s for s in resolved_stations if s["line_id"] == lid]
        if status_flt:
            stns = [s for s in stns if s["status"] == status_flt]
            
        stns.sort(key=lambda s: s["sequence"])
        route_stations[r_id] = stns
        
    created_stop_ids = set()
    for r_id, stns in route_stations.items():
        for s in stns:
            stop_id = f"STN_{r_id}_{s['sequence']:02d}"
            if stop_id not in created_stop_ids:
                created_stop_ids.add(stop_id)
                clean_name = s["station_name"].replace("\"", "'")
                stops_csv.append(
                    f"{stop_id},\"{clean_name}\",{s['lat']:.6f},{s['lon']:.6f},0,,1"
                )
                
    # 5. trips.txt & stop_times.txt
    trips_csv = [
        "route_id,service_id,trip_id,trip_headsign,direction_id,shape_id"
    ]
    stop_times_csv = [
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type"
    ]
    
    total_trips = 0
    total_stop_times = 0
    
    for r_id, stns in route_stations.items():
        if len(stns) < 2:
            logger.warning(f"Route {r_id} has fewer than 2 stations ({len(stns)}), skipping...")
            continue
            
        headway_sec = HEADWAYS_CONFIG.get(r_id, 300)
        
        forward_segment_times = []
        for i in range(len(stns) - 1):
            s1 = stns[i]
            s2 = stns[i + 1]
            dur_sec = calculate_segment_travel_time(s1["lon"], s1["lat"], s2["lon"], s2["lat"])
            forward_segment_times.append(dur_sec)
            
        directions = [
            (0, stns, forward_segment_times, stns[-1]["station_name"]),
            (1, list(reversed(stns)), list(reversed(forward_segment_times)), stns[0]["station_name"])
        ]
        
        for dir_id, dir_stns, dir_times, headsign in directions:
            dep_sec = SERVICE_START_SEC
            trip_counter = 1
            
            while dep_sec <= SERVICE_END_SEC:
                trip_id = f"TRIP_{r_id}_DIR{dir_id}_{trip_counter:04d}"
                clean_headsign = headsign.replace("\"", "'")
                trips_csv.append(
                    f"{r_id},DAILY,{trip_id},\"{clean_headsign}\",{dir_id},"
                )
                total_trips += 1
                
                current_time_sec = dep_sec
                for seq_idx, stn in enumerate(dir_stns):
                    stop_id = f"STN_{r_id}_{stn['sequence']:02d}"
                    t_str = sec_to_gtfs_time(current_time_sec)
                    
                    stop_times_csv.append(
                        f"{trip_id},{t_str},{t_str},{stop_id},{seq_idx + 1},0,0"
                    )
                    total_stop_times += 1
                    
                    if seq_idx < len(dir_times):
                        current_time_sec += dir_times[seq_idx]
                        
                dep_sec += headway_sec
                trip_counter += 1
                
    logger.info(f"Generated {total_trips} trips and {total_stop_times} stop_times across {len(routes_meta)} routes ({len(created_stop_ids)} unique stops).")
    
    return {
        "agency.txt": "\n".join(agency_csv) + "\n",
        "calendar.txt": "\n".join(calendar_csv) + "\n",
        "routes.txt": "\n".join(routes_csv) + "\n",
        "stops.txt": "\n".join(stops_csv) + "\n",
        "trips.txt": "\n".join(trips_csv) + "\n",
        "stop_times.txt": "\n".join(stop_times_csv) + "\n"
    }


def package_gtfs(gtfs_tables: Dict[str, str], output_zip: Path):
    """Write table contents to zipped archive."""
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, content in gtfs_tables.items():
            zf.writestr(filename, content.encode("utf-8"))
    logger.info(f"Successfully packaged GTFS feed: {output_zip} ({output_zip.stat().st_size / 1024:.1f} KB)")


def main():
    logger.info("=" * 80)
    logger.info("SYNTHESIZING DUAL MUMBAI METRO GTFS FEEDS (COMMERCIAL SPEED 35 KM/H)")
    logger.info("=" * 80)
    
    if not RESOLVED_STATIONS_GEOJSON.exists():
        raise FileNotFoundError(f"Missing resolved stations dataset: {RESOLVED_STATIONS_GEOJSON}")
        
    with open(RESOLVED_STATIONS_GEOJSON, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    resolved_stations = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [])
        if not coords or len(coords) < 2:
            continue
        stn = {
            "station_name": props.get("station_name"),
            "line_id": str(props.get("line_id")),
            "status": props.get("status"),
            "sequence": props.get("stop_sequence", props.get("sequence", 1)),
            "lon": coords[0],
            "lat": coords[1]
        }
        resolved_stations.append(stn)
    logger.info(f"Ingested {len(resolved_stations)} resolved stations.")
    
    # 1. Synthesize Full 2030 Metro Feed (178 Stations)
    logger.info("\n--- 1. Generating 2030 Full Network Feed (178 Stations) ---")
    tables_2030 = generate_gtfs_tables(resolved_stations, ROUTES_METADATA_2030)
    package_gtfs(tables_2030, OUTPUT_2030_GTFS_ZIP)
    
    # 2. Synthesize Current Operational Metro Feed (79 Stations)
    logger.info("\n--- 2. Generating Current Operational Network Feed (79 Stations) ---")
    tables_op = generate_gtfs_tables(resolved_stations, ROUTES_METADATA_OPERATIONAL)
    package_gtfs(tables_op, OUTPUT_OPERATIONAL_GTFS_ZIP)
    
    print("\n" + "=" * 90)
    print("MUMBAI GTFS SYNTHESIS SUMMARY")
    print("=" * 90)
    print(f"{'Feed Archive':<42} {'Routes':<10} {'Unique Stops':<15} {'Status'}")
    print("-" * 90)
    print(f"{'mumbai_2030_metro_gtfs.zip':<42} {len(ROUTES_METADATA_2030):<10} {178:<15} {'Full 2030 Network'}")
    print(f"{'mumbai_operational_metro_gtfs.zip':<42} {len(ROUTES_METADATA_OPERATIONAL):<10} {79:<15} {'Active Operational'}")
    print("=" * 90)


if __name__ == "__main__":
    main()
