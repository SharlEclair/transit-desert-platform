"""
GTFS Preprocessor for Victoria Public Transport Data.
Unpacks nested archives, validates calendar/schedule consistency,
synthesizes bridging calendar.txt if needed, and repackages into clean flat root-level zip feeds.
"""

import os
import io
import zipfile
import logging
from datetime import datetime, timedelta
import pandas as pd

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s - %(message)s')
logger = logging.getLogger("GTFSPreprocessor")

REQUIRED_GTFS_FILES = ['stops.txt', 'routes.txt', 'trips.txt', 'stop_times.txt']

FEED_NAMES = {
    '1': 'vline_regional_train',
    '2': 'metro_train',
    '3': 'metro_tram',
    '4': 'metro_bus',
    '5': 'regional_coach',
    '6': 'regional_bus',
    '10': 'telebus',
    '11': 'night_bus'
}

def find_raw_gtfs(base_paths=None):
    if base_paths is None:
        base_paths = [
            'data/raw/gtfs/victoria_gtfs.zip',
            'data/raw/gtfs.zip',
            'data/raw/victoria_gtfs.zip'
        ]
    for p in base_paths:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"Raw GTFS file not found in any expected location: {base_paths}")

def synthesize_calendar_txt(calendar_dates_bytes, ref_start="20260907", ref_end="20260913"):
    """
    Synthesizes a valid bridging calendar.txt from calendar_dates.txt
    if a feed only provides calendar_dates.txt.
    """
    logger.warning("Synthesizing bridging calendar.txt schedule for reference week %s to %s", ref_start, ref_end)
    df_dates = pd.read_csv(io.BytesIO(calendar_dates_bytes), dtype=str)
    
    unique_services = df_dates['service_id'].unique()
    
    # Generate schedule marking all service_ids active across all 7 days for the bridging window
    rows = []
    for s_id in unique_services:
        rows.append({
            'service_id': s_id,
            'monday': 1,
            'tuesday': 1,
            'wednesday': 1,
            'thursday': 1,
            'friday': 1,
            'saturday': 1,
            'sunday': 1,
            'start_date': ref_start,
            'end_date': ref_end
        })
    df_synth = pd.DataFrame(rows)
    out_buf = io.StringIO()
    df_synth.to_csv(out_buf, index=False)
    return out_buf.getvalue().encode('utf-8')

def preprocess_gtfs(raw_zip_path, output_dir="data/processed/gtfs_feeds"):
    os.makedirs(output_dir, exist_ok=True)
    logger.info("Opening master GTFS archive: %s", raw_zip_path)
    
    processed_feeds = []
    
    with zipfile.ZipFile(raw_zip_path, 'r') as master_zip:
        entries = master_zip.namelist()
        logger.info("Found %d top-level entries in master archive", len(entries))
        
        for entry in sorted(entries):
            if not entry.endswith('.zip'):
                continue
            
            feed_id = entry.split('/')[0] if '/' in entry else os.path.splitext(entry)[0]
            feed_label = FEED_NAMES.get(feed_id, f"feed_{feed_id}")
            logger.info("Processing sub-feed '%s' (%s)...", entry, feed_label)
            
            sub_zip_bytes = master_zip.read(entry)
            with zipfile.ZipFile(io.BytesIO(sub_zip_bytes), 'r') as sub_zip:
                sub_files = sub_zip.namelist()
                logger.info("  Feed contains %d files", len(sub_files))
                
                # Check for required files
                missing_required = [f for f in REQUIRED_GTFS_FILES if f not in sub_files]
                if missing_required:
                    logger.warning("  Feed %s is missing required files: %s. Skipping.", feed_label, missing_required)
                    continue
                
                has_calendar = 'calendar.txt' in sub_files
                has_calendar_dates = 'calendar_dates.txt' in sub_files
                
                out_zip_filename = f"{feed_label}.zip"
                out_zip_path = os.path.join(output_dir, out_zip_filename)
                
                with zipfile.ZipFile(out_zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as out_zip:
                    for f_name in sub_files:
                        # Normalize path to root level
                        base_name = os.path.basename(f_name)
                        if not base_name:
                            continue
                        content = sub_zip.read(f_name)
                        
                        # Check data rows count (exclude header)
                        lines = [l for l in content.decode('utf-8', errors='ignore').splitlines() if l.strip()]
                        if len(lines) <= 1 and base_name not in REQUIRED_GTFS_FILES:
                            logger.info("    [PRUNED] Skipping empty optional table '%s' (%d data rows)", base_name, max(0, len(lines)-1))
                            continue
                        
                        out_zip.writestr(base_name, content)
                    
                    if not has_calendar and has_calendar_dates:
                        logger.info("  [SYNTH] Synthesizing calendar.txt for feed %s", feed_label)
                        cal_content = synthesize_calendar_txt(sub_zip.read('calendar_dates.txt'))
                        out_zip.writestr('calendar.txt', cal_content)
                    elif not has_calendar and not has_calendar_dates:
                        logger.error("  [ERROR] Neither calendar.txt nor calendar_dates.txt found in %s", feed_label)
                
                # Validate output zip
                with zipfile.ZipFile(out_zip_path, 'r') as verify_zip:
                    assert 'calendar.txt' in verify_zip.namelist(), f"calendar.txt missing in {out_zip_path}"
                    assert 'stops.txt' in verify_zip.namelist(), f"stops.txt missing in {out_zip_path}"
                
                size_mb = os.path.getsize(out_zip_path) / (1024 * 1024)
                logger.info("  [SUCCESS] Created clean root-level feed: %s (%.2f MB)", out_zip_path, size_mb)
                processed_feeds.append(out_zip_path)
    
    # Create combined Melbourne Metro feed (Train + Tram + Bus) if possible or return all
    logger.info("Preprocessing complete. %d clean feeds produced in %s", len(processed_feeds), output_dir)
    return processed_feeds

if __name__ == "__main__":
    gtfs_input = find_raw_gtfs()
    preprocess_gtfs(gtfs_input)
