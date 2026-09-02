"""
Spatial Transit Equity Scoring & Informal Settlement Desert Analysis for Mumbai.
Computes multimodal accessibility metrics across 4 strategic Mega-Hubs (BKC, KEM Hospital,
IIT Bombay, Palladium) and synthesizes the Transit Desert Index (TDI) weighted by
slum cluster vulnerability proxies.
"""

import os
import logging
import duckdb
import pandas as pd
import numpy as np
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s - %(message)s')
logger = logging.getLogger("MumbaiEquityCalculator")

DB_PATH = Path("data/mumbai/processed/mumbai_equity.db")
MAX_TIME_CUTOFF = 90.0

def calculate_mumbai_equity(db_path=DB_PATH):
    logger.info("=" * 75)
    logger.info("COMPUTING MUMBAI MULTIMODAL TRANSIT EQUITY SCORES & TDI")
    logger.info("=" * 75)
    
    con = duckdb.connect(str(db_path))
    con.execute("LOAD spatial;")
    
    # 1. Check prerequisite tables
    tables = [t[0] for t in con.execute("SHOW TABLES;").fetchall()]
    for req in ["mumbai_demographics", "mumbai_travel_matrix"]:
        if req not in tables:
            raise RuntimeError(f"Missing required table '{req}' in {db_path}")
            
    # 2. Materialize mumbai_equity_scores with pivoted travel times & accessibility calculations
    logger.info("Materializing table `mumbai_equity_scores`...")
    con.execute(f"""
        CREATE OR REPLACE TABLE mumbai_equity_scores AS
        WITH matrix_pivoted AS (
            SELECT 
                origin_h3,
                MAX(CASE WHEN destination_id = 'BKC' THEN travel_time_p50 ELSE NULL END) AS raw_time_bkc,
                MAX(CASE WHEN destination_id = 'KEM_HOSPITAL' THEN travel_time_p50 ELSE NULL END) AS raw_time_kem,
                MAX(CASE WHEN destination_id = 'IIT_BOMBAY' THEN travel_time_p50 ELSE NULL END) AS raw_time_iit,
                MAX(CASE WHEN destination_id = 'PALLADIUM' THEN travel_time_p50 ELSE NULL END) AS raw_time_pal
            FROM mumbai_travel_matrix
            GROUP BY origin_h3
        ),
        joined_scores AS (
            SELECT 
                d.h3_index,
                d.centroid_lat,
                d.centroid_lng,
                d.centroid_geom,
                d.is_slum_cluster,
                CAST(d.vulnerability_score AS DOUBLE) AS vulnerability_score,
                
                -- Effective Travel Times (Impute 90.0-min penalty for unreachable pairs)
                COALESCE(m.raw_time_bkc, {MAX_TIME_CUTOFF}) AS time_bkc,
                COALESCE(m.raw_time_kem, {MAX_TIME_CUTOFF}) AS time_kem,
                COALESCE(m.raw_time_iit, {MAX_TIME_CUTOFF}) AS time_iit,
                COALESCE(m.raw_time_pal, {MAX_TIME_CUTOFF}) AS time_pal,
                
                -- Destination-specific linear decay accessibility scores [0.0, 1.0]
                GREATEST(0.0, 1.0 - (COALESCE(m.raw_time_bkc, {MAX_TIME_CUTOFF}) / {MAX_TIME_CUTOFF})) AS access_bkc,
                GREATEST(0.0, 1.0 - (COALESCE(m.raw_time_kem, {MAX_TIME_CUTOFF}) / {MAX_TIME_CUTOFF})) AS access_kem,
                GREATEST(0.0, 1.0 - (COALESCE(m.raw_time_iit, {MAX_TIME_CUTOFF}) / {MAX_TIME_CUTOFF})) AS access_iit,
                GREATEST(0.0, 1.0 - (COALESCE(m.raw_time_pal, {MAX_TIME_CUTOFF}) / {MAX_TIME_CUTOFF})) AS access_pal
            FROM mumbai_demographics d
            LEFT JOIN matrix_pivoted m ON d.h3_index = m.origin_h3
        )
        SELECT 
            h3_index,
            centroid_lat,
            centroid_lng,
            centroid_geom,
            is_slum_cluster,
            vulnerability_score,
            ROUND(time_bkc, 1) AS time_bkc,
            ROUND(time_kem, 1) AS time_kem,
            ROUND(time_iit, 1) AS time_iit,
            ROUND(time_pal, 1) AS time_pal,
            ROUND(access_bkc, 4) AS access_bkc,
            ROUND(access_kem, 4) AS access_kem,
            ROUND(access_iit, 4) AS access_iit,
            ROUND(access_pal, 4) AS access_pal,
            
            -- Composite Accessibility Score (Unweighted mean across 4 Mega-Hubs)
            ROUND((access_bkc + access_kem + access_iit + access_pal) / 4.0, 4) AS accessibility_score,
            
            -- Transit Desert Index (TDI = Vulnerability * (1 - Accessibility))
            ROUND(vulnerability_score * (1.0 - ((access_bkc + access_kem + access_iit + access_pal) / 4.0)), 4) AS tdi_score
        FROM joined_scores;
    """)
    
    total_records = con.execute("SELECT COUNT(*) FROM mumbai_equity_scores;").fetchone()[0]
    logger.info("Successfully populated `mumbai_equity_scores` with %d records.", total_records)
    
    # 3. Create analytical view for high-severity transit deserts (e.g. TDI >= 0.5 or Top 20th percentile)
    con.execute("""
        CREATE OR REPLACE VIEW v_mumbai_transit_deserts AS
        SELECT *
        FROM mumbai_equity_scores
        WHERE tdi_score >= 0.5
        ORDER BY tdi_score DESC;
    """)
    
    desert_count = con.execute("SELECT COUNT(*) FROM v_mumbai_transit_deserts;").fetchone()[0]
    logger.info("Created view `v_mumbai_transit_deserts` with %d severe transit desert cells (TDI >= 0.5).", desert_count)
    
    # 4. Statistical Distributions Summary
    print("\n" + "=" * 75)
    print("MUMBAI TRANSIT EQUITY STATISTICAL SUMMARY")
    print("=" * 75)
    
    stats_df = con.execute("""
        SELECT 
            'Accessibility (A_i)' AS metric,
            ROUND(MIN(accessibility_score), 4) AS min_val,
            ROUND(MAX(accessibility_score), 4) AS max_val,
            ROUND(AVG(accessibility_score), 4) AS mean_val,
            ROUND(MEDIAN(accessibility_score), 4) AS median_val,
            ROUND(STDDEV(accessibility_score), 4) AS std_val
        FROM mumbai_equity_scores
        UNION ALL
        SELECT 
            'Transit Desert Index (TDI)' AS metric,
            ROUND(MIN(tdi_score), 4) AS min_val,
            ROUND(MAX(tdi_score), 4) AS max_val,
            ROUND(AVG(tdi_score), 4) AS mean_val,
            ROUND(MEDIAN(tdi_score), 4) AS median_val,
            ROUND(STDDEV(tdi_score), 4) AS std_val
        FROM mumbai_equity_scores
        UNION ALL
        SELECT 
            'Vulnerability Score (V_i)' AS metric,
            ROUND(MIN(vulnerability_score), 4) AS min_val,
            ROUND(MAX(vulnerability_score), 4) AS max_val,
            ROUND(AVG(vulnerability_score), 4) AS mean_val,
            ROUND(MEDIAN(vulnerability_score), 4) AS median_val,
            ROUND(STDDEV(vulnerability_score), 4) AS std_val
        FROM mumbai_equity_scores;
    """).fetchdf()
    print(stats_df.to_string(index=False))
    
    # Slum vs Non-Slum comparison
    print("\n" + "-" * 75)
    print("INFORMAL SETTLEMENTS (SLUMS) VS. BASELINE URBAN FABRIC:")
    print("-" * 75)
    slum_comparison = con.execute("""
        SELECT 
            CASE WHEN is_slum_cluster = 1 THEN 'Slum Clusters (Informal)' ELSE 'Baseline Urban Fabric' END AS category,
            COUNT(*) AS total_cells,
            ROUND(AVG(accessibility_score), 4) AS avg_accessibility,
            ROUND(AVG(tdi_score), 4) AS avg_tdi,
            ROUND(MIN(tdi_score), 4) AS min_tdi,
            ROUND(MAX(tdi_score), 4) AS max_tdi
        FROM mumbai_equity_scores
        GROUP BY is_slum_cluster
        ORDER BY is_slum_cluster DESC;
    """).fetchdf()
    print(slum_comparison.to_string(index=False))
    
    # 5. Top 10 Most Severe Transit Deserts
    print("\n" + "=" * 75)
    print("TOP 10 MOST SEVERE MUMBAI TRANSIT DESERTS (HIGHEST TDI):")
    print("=" * 75)
    top10_df = con.execute("""
        SELECT 
            h3_index,
            centroid_lat AS lat,
            centroid_lng AS lon,
            is_slum_cluster AS is_slum,
            vulnerability_score AS vuln,
            accessibility_score AS access,
            tdi_score AS tdi,
            time_bkc,
            time_kem,
            time_iit,
            time_pal
        FROM mumbai_equity_scores
        ORDER BY tdi_score DESC, accessibility_score ASC
        LIMIT 10;
    """).fetchdf()
    print(top10_df.to_string(index=False))
    
    con.close()
    print("\n" + "=" * 75)
    print("EQUITY CALCULATION COMPLETE & MATERIALIZED IN DATABASE!")
    print("=" * 75)

if __name__ == "__main__":
    calculate_mumbai_equity()
