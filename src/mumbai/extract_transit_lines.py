"""
Extract Transit Lines for Mumbai Multimodal Network (Overpass API Ingestion).
Fetches physical track alignments for:
1. Operational Metro (railway=subway)
2. Under-Construction / Proposed Metro (railway=construction + construction=subway, route=subway relations)
3. Main Suburban Rail (railway=rail + usage=main)

Bounding box: [72.65, 18.70, 73.55, 20.10] (Greater Mumbai & MMR Region)
Output: data/mumbai/processed/mumbai_transit_lines.geojson
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import urllib.request
import urllib.parse
import urllib.error
import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, shape

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("ExtractTransitLines")

OUTPUT_PATH = Path("data/mumbai/processed/mumbai_transit_lines.geojson")
BBOX = (18.70, 72.65, 20.10, 73.55)  # (south, west, north, east)

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter"
]

OVERPASS_QUERY = f"""
[out:json][timeout:180];
(
  // 1. Operational Metro lines
  way["railway"="subway"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  
  // 2. Under-construction Metro lines
  way["railway"="construction"]["construction"="subway"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  way["construction"="subway"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  way["railway"="construction"]["subway"="yes"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  
  // 3. Metro Relations (Subway routes & proposed lines)
  relation["route"="subway"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  relation["route"="light_rail"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  relation["railway"="subway"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  relation["construction"="subway"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});

  // 4. Suburban Rail Main Lines
  way["railway"="rail"]["usage"="main"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
);
(._;>;);
out body geom;
"""


def fetch_overpass_data(query: str) -> Dict[str, Any]:
    """Execute Overpass QL query with fallback across multiple public mirrors."""
    post_data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    
    for endpoint in OVERPASS_ENDPOINTS:
        logger.info(f"Querying Overpass API endpoint: {endpoint}...")
        try:
            req = urllib.request.Request(
                endpoint,
                data=post_data,
                headers={
                    "User-Agent": "TransitDesertPlatform/2.0 (SpatialEquityEngine; Python3)",
                    "Accept": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=120) as response:
                if response.status == 200:
                    raw_data = response.read().decode("utf-8")
                    data = json.loads(raw_data)
                    element_count = len(data.get("elements", []))
                    logger.info(f"Successfully fetched {element_count} elements from {endpoint}")
                    return data
        except Exception as e:
            logger.warning(f"Endpoint {endpoint} failed: {e}. Trying fallback...")
            time.sleep(2)
            
    raise RuntimeError("All Overpass API endpoints failed. Please check network connectivity.")


def parse_osm_elements_to_geojson(osm_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse OSM elements (ways with geometry) into clean GeoJSON FeatureCollection.
    Distinguishes 'metro' (operational & construction) vs 'suburban_rail'.
    """
    elements = osm_data.get("elements", [])
    features = []
    
    metro_count = 0
    suburban_count = 0
    
    for el in elements:
        el_type = el.get("type")
        tags = el.get("tags", {})
        
        # We process ways that have coordinates in 'geometry'
        if el_type == "way" and "geometry" in el:
            geom_coords = el["geometry"]
            if len(geom_coords) < 2:
                continue
                
            coords = [[pt["lon"], pt["lat"]] for pt in geom_coords]
            
            railway = tags.get("railway", "")
            construction = tags.get("construction", "")
            name = tags.get("name", tags.get("name:en", ""))
            ref = tags.get("ref", "")
            
            # Determine transit classification
            is_metro = (
                railway in ("subway", "monorail", "light_rail") or
                construction in ("subway", "light_rail", "monorail") or
                tags.get("subway") == "yes" or
                "metro" in name.lower() or
                "line" in name.lower()
            )
            
            is_suburban = (railway == "rail" and tags.get("usage") == "main")
            
            if not is_metro and not is_suburban:
                continue
                
            transit_category = "metro" if is_metro else "suburban_rail"
            status = "operational"
            if railway == "construction" or construction:
                status = "under_construction"
            elif tags.get("proposed") or tags.get("state") == "proposed":
                status = "proposed"
                
            if transit_category == "metro":
                metro_count += 1
            else:
                suburban_count += 1
                
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords
                },
                "properties": {
                    "osm_id": el.get("id"),
                    "transit_type": transit_category,
                    "status": status,
                    "railway": railway,
                    "construction": construction,
                    "name": name,
                    "ref": ref,
                    "gauge": tags.get("gauge", ""),
                    "voltage": tags.get("voltage", ""),
                    "layer": tags.get("layer", "0")
                }
            }
            features.append(feature)
            
    logger.info(f"Processed {len(features)} total track segments: {metro_count} Metro segments, {suburban_count} Suburban Rail segments.")
    
    return {
        "type": "FeatureCollection",
        "metadata": {
            "bbox": list(BBOX),
            "total_features": len(features),
            "metro_segments": metro_count,
            "suburban_segments": suburban_count,
            "crs": "EPSG:4326"
        },
        "features": features
    }


def main():
    logger.info("=" * 70)
    logger.info("FETCHING MUMBAI TRANSIT TRACK ALIGNMENTS VIA OVERPASS API")
    logger.info("=" * 70)
    
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    osm_data = fetch_overpass_data(OVERPASS_QUERY)
    geojson_data = parse_osm_elements_to_geojson(osm_data)
    
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Saved {len(geojson_data['features'])} transit track features to: {OUTPUT_PATH}")
    
    # Load with GeoPandas and verify CRS & bounding box
    gdf = gpd.read_file(str(OUTPUT_PATH))
    logger.info(f"GeoDataFrame validation: {len(gdf)} rows, CRS: {gdf.crs}, Total bounds: {gdf.total_bounds}")
    
    assert len(gdf) > 0, "No transit lines extracted!"
    assert gdf.crs.to_epsg() == 4326, f"Expected EPSG:4326, got {gdf.crs}"
    
    metro_gdf = gdf[gdf["transit_type"] == "metro"]
    suburban_gdf = gdf[gdf["transit_type"] == "suburban_rail"]
    
    logger.info(f"Summary: {len(metro_gdf)} Metro features, {len(suburban_gdf)} Suburban Rail features.")
    print("\nExtraction Complete! File created at:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
