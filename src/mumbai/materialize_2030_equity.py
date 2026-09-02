"""
Materialize 3-Stage Mumbai Transit Equity Scores & Master Comparison View.
Stages:
1. Legacy Network (Without Metro): `mumbai_equity_legacy` (from `mumbai_travel_matrix`)
2. Current Network (Active Metro - 79 Stns): `mumbai_equity_current` (from `mumbai_travel_matrix_current_metro`)
3. 2030 Network (Full Expansion - 178 Stns): `mumbai_equity_2030` (from `mumbai_travel_matrix_2030`)

Master Unified View:
- `v_mumbai_equity_master`:
  * `delta_active_metro` = TDI_legacy - TDI_current
  * `delta_future_expansion` = TDI_current - TDI_2030
  * `delta_total_metro` = TDI_legacy - TDI_2030
"""

import os
import sys
import logging
from pathlib import Path
import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("Materialize3StageEquity")

DB_PATH = Path("data/mumbai/processed/mumbai_equity.db")
MAX_TIME_CUTOFF = 90.0


def materialize_stage_table(con: duckdb.DuckDBPyConnection, matrix_table: str, target_equity_table: str):
    """Helper to compute accessibility and TDI scores from a travel matrix into a target equity table."""
    logger.info("Computing equity scores from `%s` into `%s`...", matrix_table, target_equity_table)
    con.execute(f"""
        CREATE OR REPLACE TABLE {target_equity_table} AS
        WITH matrix_pivoted AS (
            SELECT 
                origin_h3,
                MAX(CASE WHEN destination_id = 'BKC' THEN travel_time_p50 ELSE NULL END) AS raw_time_bkc,
                MAX(CASE WHEN destination_id = 'KEM_HOSPITAL' THEN travel_time_p50 ELSE NULL END) AS raw_time_kem,
                MAX(CASE WHEN destination_id = 'IIT_BOMBAY' THEN travel_time_p50 ELSE NULL END) AS raw_time_iit,
                MAX(CASE WHEN destination_id = 'PALLADIUM' THEN travel_time_p50 ELSE NULL END) AS raw_time_pal
            FROM {matrix_table}
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
                
                -- Linear decay accessibility scores [0.0, 1.0]
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
            
            -- Composite Accessibility Score
            ROUND((access_bkc + access_kem + access_iit + access_pal) / 4.0, 4) AS accessibility_score,
            
            -- Transit Desert Index (TDI = Vulnerability * (1 - Accessibility))
            ROUND(vulnerability_score * (1.0 - ((access_bkc + access_kem + access_iit + access_pal) / 4.0)), 4) AS tdi_score
        FROM joined_scores;
    """)
    cnt = con.execute(f"SELECT COUNT(*) FROM {target_equity_table};").fetchone()[0]
    logger.info("  -> Materialized `%s` (%d records).", target_equity_table, cnt)


def materialize_3stage_equity(db_path: Path = DB_PATH):
    logger.info("=" * 80)
    logger.info("MATERIALIZING 3-STAGE MUMBAI TRANSIT EQUITY & MASTER VIEW")
    logger.info("=" * 80)
    
    con = duckdb.connect(str(db_path))
    con.execute("LOAD spatial;")
    
    tables = [t[0] for t in con.execute("SHOW TABLES;").fetchall()]
    logger.info("Existing database tables: %s", tables)
    
    if "mumbai_demographics" not in tables:
        raise RuntimeError(f"Missing required table `mumbai_demographics` in {db_path}")
        
    # 1. Stage 1: Legacy (Without Metro)
    if "mumbai_travel_matrix" in tables:
        materialize_stage_table(con, "mumbai_travel_matrix", "mumbai_equity_legacy")
        # Ensure mumbai_equity_scores points to legacy for backward compatibility
        con.execute("CREATE OR REPLACE TABLE mumbai_equity_scores AS SELECT * FROM mumbai_equity_legacy;")
    else:
        logger.warning("Table `mumbai_travel_matrix` not found, skipping legacy materialization.")
        
    # 2. Stage 2: Current Active Metro (79 Stations)
    if "mumbai_travel_matrix_current_metro" in tables:
        materialize_stage_table(con, "mumbai_travel_matrix_current_metro", "mumbai_equity_current")
    else:
        logger.warning("Table `mumbai_travel_matrix_current_metro` not found, skipping current metro materialization.")
        
    # 3. Stage 3: Future 2030 Metro (178 Stations)
    if "mumbai_travel_matrix_2030" in tables:
        materialize_stage_table(con, "mumbai_travel_matrix_2030", "mumbai_equity_2030")
    else:
        logger.warning("Table `mumbai_travel_matrix_2030` not found, skipping 2030 metro materialization.")
        
    # 4. Master Unified View: v_mumbai_equity_master
    logger.info("\nCreating Unified Master View `v_mumbai_equity_master`...")
    con.execute("""
        CREATE OR REPLACE VIEW v_mumbai_equity_master AS
        SELECT 
            l.h3_index,
            l.centroid_lat,
            l.centroid_lng,
            l.centroid_geom,
            l.is_slum_cluster,
            l.vulnerability_score,
            
            -- Stage 1: Legacy Network (Without Metro)
            l.accessibility_score AS legacy_accessibility,
            l.tdi_score AS legacy_tdi,
            l.time_bkc AS legacy_time_bkc,
            l.time_kem AS legacy_time_kem,
            l.time_iit AS legacy_time_iit,
            l.time_pal AS legacy_time_pal,
            
            -- Stage 2: Current Network (Active Metro)
            c.accessibility_score AS current_accessibility,
            c.tdi_score AS current_tdi,
            c.time_bkc AS current_time_bkc,
            c.time_kem AS current_time_kem,
            c.time_iit AS current_time_iit,
            c.time_pal AS current_time_pal,
            
            -- Stage 3: 2030 Network (Full Expansion)
            f.accessibility_score AS future_accessibility,
            f.tdi_score AS future_tdi,
            f.time_bkc AS future_time_bkc,
            f.time_kem AS future_time_kem,
            f.time_iit AS future_time_iit,
            f.time_pal AS future_time_pal,
            
            -- 2-Stage Specific Deltas (TDI Reductions / Equity Gains)
            ROUND(l.tdi_score - c.tdi_score, 4) AS delta_active_metro,
            ROUND(c.tdi_score - f.tdi_score, 4) AS delta_future_expansion,
            ROUND(l.tdi_score - f.tdi_score, 4) AS delta_total_metro,
            
            -- Accessibility Gains
            ROUND(c.accessibility_score - l.accessibility_score, 4) AS delta_accessibility_active,
            ROUND(f.accessibility_score - c.accessibility_score, 4) AS delta_accessibility_future,
            ROUND(f.accessibility_score - l.accessibility_score, 4) AS delta_accessibility_total,
            
            -- Time Saved (Active Metro vs Legacy)
            ROUND(l.time_bkc - c.time_bkc, 1) AS time_saved_active_bkc,
            ROUND(l.time_kem - c.time_kem, 1) AS time_saved_active_kem,
            ROUND(l.time_iit - c.time_iit, 1) AS time_saved_active_iit,
            ROUND(l.time_pal - c.time_pal, 1) AS time_saved_active_pal,
            
            -- Time Saved (Future Expansion vs Active Metro)
            ROUND(c.time_bkc - f.time_bkc, 1) AS time_saved_future_bkc,
            ROUND(c.time_kem - f.time_kem, 1) AS time_saved_future_kem,
            ROUND(c.time_iit - f.time_iit, 1) AS time_saved_future_iit,
            ROUND(c.time_pal - f.time_pal, 1) AS time_saved_future_pal,
            
            -- Total Time Saved (2030 vs Legacy)
            ROUND(l.time_bkc - f.time_bkc, 1) AS time_saved_total_bkc,
            ROUND(l.time_kem - f.time_kem, 1) AS time_saved_total_kem,
            ROUND(l.time_iit - f.time_iit, 1) AS time_saved_total_iit,
            ROUND(l.time_pal - f.time_pal, 1) AS time_saved_total_pal
        FROM mumbai_equity_legacy l
        JOIN mumbai_equity_current c ON l.h3_index = c.h3_index
        JOIN mumbai_equity_2030 f ON l.h3_index = f.h3_index;
    """)
    logger.info("Created view `v_mumbai_equity_master`.")
    
    # 5. Backward-compatibility view: v_mumbai_equity_comparison
    con.execute("""
        CREATE OR REPLACE VIEW v_mumbai_equity_comparison AS
        SELECT 
            h3_index, centroid_lat, centroid_lng, centroid_geom, is_slum_cluster, vulnerability_score,
            legacy_tdi AS current_tdi,
            future_tdi AS future_tdi,
            delta_total_metro AS delta_tdi,
            legacy_accessibility AS current_accessibility,
            future_accessibility AS future_accessibility,
            delta_accessibility_total AS delta_accessibility,
            legacy_time_bkc AS current_time_bkc,
            future_time_bkc AS future_time_bkc,
            time_saved_total_bkc AS time_saved_bkc,
            legacy_time_kem AS current_time_kem,
            future_time_kem AS future_time_kem,
            time_saved_total_kem AS time_saved_kem,
            legacy_time_iit AS current_time_iit,
            future_time_iit AS future_time_iit,
            time_saved_total_iit AS time_saved_iit,
            legacy_time_pal AS current_time_pal,
            future_time_pal AS future_time_pal,
            time_saved_total_pal AS time_saved_pal
        FROM v_mumbai_equity_master;
    """)
    logger.info("Created view `v_mumbai_equity_comparison`.")
    
    # 6. Print 3-Stage Statistical Report
    df_report = con.execute("""
        SELECT 
            'Stage 1: Legacy (No Metro)' AS stage,
            ROUND(AVG(legacy_accessibility), 4) AS avg_accessibility,
            ROUND(AVG(legacy_tdi), 4) AS avg_tdi,
            0.0 AS avg_delta_tdi_reduction,
            0.0 AS max_delta_tdi_reduction
        FROM v_mumbai_equity_master
        UNION ALL
        SELECT 
            'Stage 2: Current (Active Metro)' AS stage,
            ROUND(AVG(current_accessibility), 4) AS avg_accessibility,
            ROUND(AVG(current_tdi), 4) AS avg_tdi,
            ROUND(AVG(delta_active_metro), 4) AS avg_delta_tdi_reduction,
            ROUND(MAX(delta_active_metro), 4) AS max_delta_tdi_reduction
        FROM v_mumbai_equity_master
        UNION ALL
        SELECT 
            'Stage 3: 2030 (Full Expansion)' AS stage,
            ROUND(AVG(future_accessibility), 4) AS avg_accessibility,
            ROUND(AVG(future_tdi), 4) AS avg_tdi,
            ROUND(AVG(delta_future_expansion), 4) AS avg_delta_tdi_reduction,
            ROUND(MAX(delta_future_expansion), 4) AS max_delta_tdi_reduction
        FROM v_mumbai_equity_master;
    """).fetchdf()
    
    print("\n" + "=" * 95)
    print("MUMBAI 3-STAGE CHRONOLOGICAL EVALUATION SUMMARY")
    print("=" * 95)
    print(df_report.to_string(index=False))
    print("=" * 95)
    
    con.close()


if __name__ == "__main__":
    materialize_3stage_equity()
