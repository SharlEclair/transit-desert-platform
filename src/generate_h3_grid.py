"""
H3 Resolution 9 Grid Generator for Greater Melbourne.
Strict adherence to geospatial-audit rules:
- Bounding Box: lng_min=144.40, lat_min=-38.50, lng_max=145.80, lat_max=-37.40
- Resolution 9 hexagons generated across bounding geometry.
- Centroids extracted explicitly via h3.cell_to_latlng() (H3 polyfill join is strictly prohibited).
- Stored in DuckDB 'melb_h3_grid' with ST_Point geometries.
"""

import duckdb
import h3
import logging
from shapely.geometry import Polygon

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s - %(message)s')
logger = logging.getLogger("H3GridGenerator")

DB_PATH = "data/processed/transit_equity.db"
H3_RESOLUTION = 9

# Bounding box for Greater Melbourne (inclusive of Frankston & Mornington Peninsula)
BBOX = {
    'lng_min': 144.40,
    'lat_min': -38.50,
    'lng_max': 145.80,
    'lat_max': -37.40
}

def generate_h3_grid(bbox=BBOX, resolution=H3_RESOLUTION, db_path=DB_PATH):
    logger.info("Generating H3 grid at Resolution %d for bounding box: %s", resolution, bbox)
    
    # Define polygon vertices (GeoJSON coordinates: [lng, lat])
    # h3-py expects polygon as LatLng coordinates or GeoJSON [lng, lat] depending on function
    # Using Polygon representation:
    poly_coords = [
        (bbox['lat_min'], bbox['lng_min']),
        (bbox['lat_min'], bbox['lng_max']),
        (bbox['lat_max'], bbox['lng_max']),
        (bbox['lat_max'], bbox['lng_min']),
        (bbox['lat_min'], bbox['lng_min'])
    ]
    
    # In h3-py v4+: polygon_to_cells takes a LatLngPoly
    # Alternatively, geo_to_cells with LatLngPoly
    lat_lng_poly = h3.LatLngPoly(poly_coords)
    cells = h3.polygon_to_cells(lat_lng_poly, resolution)
    
    logger.info("Generated %d H3 hexagons at Resolution %d", len(cells), resolution)
    
    records = []
    for cell in cells:
        # Centroid extraction via cell_to_latlng (MANDATORY RULE)
        lat, lng = h3.cell_to_latlng(cell)
        records.append({
            'h3_index': str(cell),
            'centroid_lat': float(lat),
            'centroid_lng': float(lng)
        })
    
    import pandas as pd
    df_grid = pd.DataFrame(records)
    
    logger.info("Inserting %d H3 grid cells into DuckDB 'melb_h3_grid'...", len(df_grid))
    con = duckdb.connect(db_path)
    con.execute("LOAD spatial;")
    con.register("df_grid_temp", df_grid)
    con.execute("DELETE FROM melb_h3_grid;")
    con.execute("""
        INSERT INTO melb_h3_grid
        SELECT 
            h3_index,
            centroid_lat,
            centroid_lng,
            ST_Point(centroid_lng, centroid_lat) AS centroid_geom
        FROM df_grid_temp;
    """)
    con.unregister("df_grid_temp")
    
    count = con.execute("SELECT COUNT(*) FROM melb_h3_grid;").fetchone()[0]
    sample = con.execute("SELECT h3_index, centroid_lat, centroid_lng, ST_AsText(centroid_geom) FROM melb_h3_grid LIMIT 1;").fetchone()
    logger.info("[AUDIT SUCCESS] Saved %d H3 cells in DuckDB. Sample: %s", count, sample)
    con.close()

if __name__ == "__main__":
    generate_h3_grid()
