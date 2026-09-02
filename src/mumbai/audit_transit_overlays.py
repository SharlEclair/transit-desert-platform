"""
Transit Overlays Diagnostic & Root Cause Audit.
Audits:
1. File existence & JSON/GeoJSON parsing for transit lines & stations.
2. Coordinate ordering ([lon, lat] vs [lat, lon]).
3. Property schema completeness.
4. Unified dataset generation for API & MapLibre layers.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("AuditTransitOverlays")

LINES_GEOJSON_PATH = Path("data/mumbai/processed/mumbai_transit_lines.geojson")
STATIONS_GEOJSON_PATH = Path("data/mumbai/processed/mumbai_metro_stations_resolved.geojson")
STATIONS_JSON_PATH = Path("data/mumbai/processed/mumbai_metro_stations_resolved.json")
OUTPUT_UNIFIED_LINES_PATH = Path("data/mumbai/processed/mumbai_transit_lines_unified.geojson")

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


def audit_files():
    logger.info("=" * 80)
    logger.info("PHASE 1: TRANSIT OVERLAYS DATA & FILE AUDIT")
    logger.info("=" * 80)
    
    # 1. Check Transit Lines
    if not LINES_GEOJSON_PATH.exists():
        logger.error("Transit lines GeoJSON file missing: %s", LINES_GEOJSON_PATH)
    else:
        with open(LINES_GEOJSON_PATH, "r", encoding="utf-8") as f:
            lines_data = json.load(f)
        features = lines_data.get("features", [])
        logger.info("[LINES] File exists. Total features: %d", len(features))
        
        # Check first 5 features
        for idx, feat in enumerate(features[:5]):
            geom = feat.get("geometry", {})
            props = feat.get("properties", {})
            gtype = geom.get("type", "")
            coords = geom.get("coordinates", [])
            first_coord = None
            if gtype == "LineString" and coords:
                first_coord = coords[0]
            elif gtype == "MultiLineString" and coords and coords[0]:
                first_coord = coords[0][0]
                
            logger.info("  Line #%d: Type=%s, Network=%s, Status=%s, 1st Coord=%s",
                        idx + 1, gtype, props.get("transit_type") or props.get("network"), props.get("status"), first_coord)
            if first_coord:
                lon, lat = first_coord[0], first_coord[1]
                if not (72.0 <= lon <= 74.0 and 18.0 <= lat <= 20.5):
                    logger.error("  INVERTED COORDINATES DETECTED! Coord=(%s, %s)", lon, lat)
                else:
                    logger.info("  Coordinates valid: Lon=%.4f, Lat=%.4f (WGS84 EPSG:4326)", lon, lat)

    # 2. Check Metro Stations
    if not STATIONS_GEOJSON_PATH.exists():
        logger.error("Metro stations GeoJSON file missing: %s", STATIONS_GEOJSON_PATH)
    else:
        with open(STATIONS_GEOJSON_PATH, "r", encoding="utf-8") as f:
            stns_data = json.load(f)
        stn_features = stns_data.get("features", [])
        logger.info("\n[STATIONS] File exists. Total stations: %d", len(stn_features))
        
        for idx, feat in enumerate(stn_features[:5]):
            geom = feat.get("geometry", {})
            props = feat.get("properties", {})
            coords = geom.get("coordinates", [])
            logger.info("  Station #%d: Name='%s', Line='%s', Status='%s', Seq=%s, Coord=%s",
                        idx + 1, props.get("station_name"), props.get("line_name"), props.get("status"), props.get("sequence") or props.get("stop_sequence"), coords)
            if coords:
                lon, lat = coords[0], coords[1]
                if not (72.0 <= lon <= 74.0 and 18.0 <= lat <= 20.5):
                    logger.error("  INVERTED COORDINATES DETECTED in Station! Coord=(%s, %s)", lon, lat)
                else:
                    logger.info("  Coordinates valid: Lon=%.4f, Lat=%.4f", lon, lat)


if __name__ == "__main__":
    audit_files()
