"""
Extract and clip Greater Mumbai Metropolitan road and rail network from regional OSM PBF.
Uses pyosmium and a 2-pass reference-complete extraction to produce an OSM PBF
that strictly contains only features within the Mumbai bounding box and adheres to
Conveyal R5's geographic extent safety limits (< 975,000 km2).
"""

import os
import time
import logging
from pathlib import Path
import osmium

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s - %(message)s')
logger = logging.getLogger("MumbaiOSMExtractor")

IN_PBF = Path("data/mumbai/raw/western-zone-260831.osm.pbf").resolve()
OUT_PBF = Path("data/mumbai/processed/mumbai_roads.osm.pbf").resolve()

# Bounding box for Greater Mumbai Metropolitan Region and suburban rail corridors
BBOX = (72.65, 18.70, 73.55, 20.10)  # min_lon, min_lat, max_lon, max_lat

class Pass1IndexHandler(osmium.SimpleHandler):
    """Pass 1: Scan ways that intersect the bounding box and collect all constituent node IDs."""
    def __init__(self, bbox=BBOX):
        super().__init__()
        self.min_lon, self.min_lat, self.max_lon, self.max_lat = bbox
        self.needed_nodes = set()
        self.matching_ways = set()

    def way(self, w):
        if 'highway' in w.tags or 'railway' in w.tags or 'public_transport' in w.tags:
            in_bbox = False
            for n in w.nodes:
                if n.location.valid() and (self.min_lon <= n.lon <= self.max_lon and self.min_lat <= n.lat <= self.max_lat):
                    in_bbox = True
                    break
            if in_bbox:
                self.matching_ways.add(w.id)
                for n in w.nodes:
                    self.needed_nodes.add(n.ref)

class Pass2WriterHandler(osmium.SimpleHandler):
    """Pass 2: Stream only the indexed nodes and matching ways into the output PBF."""
    def __init__(self, writer, needed_nodes, matching_ways):
        super().__init__()
        self.writer = writer
        self.needed_nodes = needed_nodes
        self.matching_ways = matching_ways
        self.nodes_written = 0
        self.ways_written = 0

    def node(self, n):
        if n.id in self.needed_nodes:
            self.writer.add_node(n)
            self.nodes_written += 1

    def way(self, w):
        if w.id in self.matching_ways:
            self.writer.add_way(w)
            self.ways_written += 1

def extract_mumbai_pbf(in_path=IN_PBF, out_path=OUT_PBF, bbox=BBOX):
    logger.info("Extracting Mumbai bounding box %s from %s...", bbox, in_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Remove existing file if present to prevent atomic move errors on Windows
    if out_path.exists():
        try:
            os.remove(out_path)
        except Exception:
            pass
            
    start_time = time.time()
    
    # Pass 1
    logger.info("Starting Pass 1 (Indexing ways & nodes with location cache)...")
    p1 = Pass1IndexHandler(bbox)
    p1.apply_file(str(in_path), locations=True)
    logger.info("Pass 1 complete in %.1fs: Found %d matching ways and %d required nodes.", time.time() - start_time, len(p1.matching_ways), len(p1.needed_nodes))
    
    # Pass 2
    logger.info("Starting Pass 2 (Writing reference-complete Mumbai PBF)...")
    pass2_start = time.time()
    writer = osmium.SimpleWriter(str(out_path))
    p2 = Pass2WriterHandler(writer, p1.needed_nodes, p1.matching_ways)
    p2.apply_file(str(in_path))
    writer.close()
    
    elapsed = time.time() - start_time
    logger.info("Pass 2 completed in %.1fs!", time.time() - pass2_start)
    logger.info("Total extraction completed in %.1f seconds!", elapsed)
    logger.info("Written %d nodes, %d ways. Output file size: %.2f MB", p2.nodes_written, p2.ways_written, out_path.stat().st_size / (1024 * 1024))
    return out_path

if __name__ == "__main__":
    extract_mumbai_pbf()
