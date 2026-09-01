"""
Spatial Joins, Accessibility, Vulnerability, and Transit Desert Equity Scoring.
Executes high-performance spatial joins in DuckDB between:
1. melb_h3_grid (121,802 H3 Resolution-9 hexagons)
2. melb_demographics (11,487 ABS SA1 Census & SEIFA polygons, EPSG:4326)
3. melb_travel_matrix (Multimodal transit travel times to strategic POIs)

Persists:
- Materialized Table: `melb_equity_scores`
- Analytical SQL View: `v_transit_deserts` (Top 20% Transit Deserts)
"""

import time
import logging
import duckdb
import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("EquityScoringPipeline")

DB_PATH = "data/processed/transit_equity.db"
MAX_TRAVEL_TIME_MINUTES = 45.0


def compute_equity_scores(db_path=DB_PATH):
    start_time = time.time()
    logger.info("=" * 75)
    logger.info("STARTING PHASE 3: SPATIAL JOINS & TRANSIT EQUITY SCORING PIPELINE")
    logger.info("=" * 75)
    logger.info("Connecting to DuckDB database: %s", db_path)
    
    con = duckdb.connect(db_path)
    con.execute("LOAD spatial;")
    
    # 1. Inspect existing table counts
    h3_count = con.execute("SELECT COUNT(*) FROM melb_h3_grid;").fetchone()[0]
    demo_count = con.execute("SELECT COUNT(*) FROM melb_demographics;").fetchone()[0]
    matrix_count = con.execute("SELECT COUNT(*) FROM melb_travel_matrix;").fetchone()[0]
    
    logger.info("Input Database Inventory:")
    logger.info("  - melb_h3_grid:        %d cells", h3_count)
    logger.info("  - melb_demographics:   %d SA1 polygons", demo_count)
    logger.info("  - melb_travel_matrix:  %d reachable O-D pairs", matrix_count)
    
    # 2. Materialize melb_equity_scores Table
    logger.info("-" * 75)
    logger.info("MATERIALIZING `melb_equity_scores` TABLE VIA SPATIAL & MATRIX JOINS...")
    
    con.execute("DROP TABLE IF EXISTS melb_equity_scores;")
    
    materialize_sql = f"""
    CREATE TABLE melb_equity_scores AS
    WITH 
    -- Step A: Pivot travel matrix per H3 cell to individual POI travel times
    pivoted_travel_times AS (
        SELECT 
            h.h3_index,
            h.centroid_lat,
            h.centroid_lng,
            h.centroid_geom,
            -- Royal Melbourne Hospital (Healthcare)
            MAX(CASE WHEN tm.destination_id = 'RMH' THEN tm.travel_time_p50 END) AS raw_tt_rmh_p50,
            MAX(CASE WHEN tm.destination_id = 'RMH' THEN tm.travel_time_p90 END) AS raw_tt_rmh_p90,
            -- Monash University Clayton (Education / Innovation)
            MAX(CASE WHEN tm.destination_id = 'MONASH_CLAYTON' THEN tm.travel_time_p50 END) AS raw_tt_monash_p50,
            MAX(CASE WHEN tm.destination_id = 'MONASH_CLAYTON' THEN tm.travel_time_p90 END) AS raw_tt_monash_p90,
            -- Chadstone Shopping Centre (Commercial / Retail)
            MAX(CASE WHEN tm.destination_id = 'CHADSTONE' THEN tm.travel_time_p50 END) AS raw_tt_chadstone_p50,
            MAX(CASE WHEN tm.destination_id = 'CHADSTONE' THEN tm.travel_time_p90 END) AS raw_tt_chadstone_p90
        FROM melb_h3_grid h
        LEFT JOIN melb_travel_matrix tm ON h.h3_index = tm.origin_h3
        GROUP BY h.h3_index, h.centroid_lat, h.centroid_lng, h.centroid_geom
    ),
    
    -- Step B: Spatial join H3 centroids against ABS SA1 polygons (WGS84 EPSG:4326)
    joined_demographics AS (
        SELECT 
            pt.h3_index,
            pt.centroid_lat,
            pt.centroid_lng,
            pt.centroid_geom,
            -- Effective travel times: default to cutoff (45.0m) if unreachable
            COALESCE(pt.raw_tt_rmh_p50, {MAX_TRAVEL_TIME_MINUTES}) AS travel_time_rmh_p50,
            COALESCE(pt.raw_tt_rmh_p90, pt.raw_tt_rmh_p50, {MAX_TRAVEL_TIME_MINUTES}) AS travel_time_rmh_p90,
            COALESCE(pt.raw_tt_monash_p50, {MAX_TRAVEL_TIME_MINUTES}) AS travel_time_monash_p50,
            COALESCE(pt.raw_tt_monash_p90, pt.raw_tt_monash_p50, {MAX_TRAVEL_TIME_MINUTES}) AS travel_time_monash_p90,
            COALESCE(pt.raw_tt_chadstone_p50, {MAX_TRAVEL_TIME_MINUTES}) AS travel_time_chadstone_p50,
            COALESCE(pt.raw_tt_chadstone_p90, pt.raw_tt_chadstone_p50, {MAX_TRAVEL_TIME_MINUTES}) AS travel_time_chadstone_p90,
            -- SA1 demographic attributes
            d.sa1_code,
            d.sa2_code,
            d.sa2_name,
            d.gccsa_code,
            d.gccsa_name,
            COALESCE(d.population, 0) AS population,
            COALESCE(d.pop_density, 0.0) AS pop_density,
            d.seifa_irsd_score,
            d.seifa_irsd_decile,
            d.seifa_irsad_score,
            d.seifa_irsad_decile
        FROM pivoted_travel_times pt
        LEFT JOIN melb_demographics d 
            ON ST_Intersects(ST_Point(pt.centroid_lng, pt.centroid_lat), d.geom)
    ),
    
    -- Step C: Compute Accessibility and Vulnerability Scores
    scored_indicators AS (
        SELECT 
            h3_index,
            centroid_lat,
            centroid_lng,
            centroid_geom,
            sa1_code,
            sa2_code,
            sa2_name,
            gccsa_code,
            gccsa_name,
            population,
            pop_density,
            seifa_irsd_score,
            seifa_irsd_decile,
            seifa_irsad_score,
            seifa_irsad_decile,
            travel_time_rmh_p50,
            travel_time_rmh_p90,
            travel_time_monash_p50,
            travel_time_monash_p90,
            travel_time_chadstone_p50,
            travel_time_chadstone_p90,
            
            -- Individual POI accessibility scores (1.0 = instant access, 0.0 = >= 45 mins)
            ROUND(GREATEST(0.0, 1.0 - (travel_time_rmh_p50 / {MAX_TRAVEL_TIME_MINUTES})), 4) AS score_rmh,
            ROUND(GREATEST(0.0, 1.0 - (travel_time_monash_p50 / {MAX_TRAVEL_TIME_MINUTES})), 4) AS score_monash,
            ROUND(GREATEST(0.0, 1.0 - (travel_time_chadstone_p50 / {MAX_TRAVEL_TIME_MINUTES})), 4) AS score_chadstone,
            
            -- Composite Multimodal Accessibility Score (Mean across 3 POIs, scaled 0.0 - 1.0)
            ROUND(
                (
                    GREATEST(0.0, 1.0 - (travel_time_rmh_p50 / {MAX_TRAVEL_TIME_MINUTES})) +
                    GREATEST(0.0, 1.0 - (travel_time_monash_p50 / {MAX_TRAVEL_TIME_MINUTES})) +
                    GREATEST(0.0, 1.0 - (travel_time_chadstone_p50 / {MAX_TRAVEL_TIME_MINUTES}))
                ) / 3.0, 
                4
            ) AS accessibility_score,
            
            -- Demographic Need / Vulnerability Score (0.0 - 1.0)
            -- 60% Inverted SEIFA IRSD Disadvantage + 40% Log-Normalized Population Density
            ROUND(
                CASE 
                    WHEN population = 0 OR seifa_irsd_score IS NULL THEN 0.0
                    ELSE (
                        0.60 * ((1192.0 - LEAST(GREATEST(seifa_irsd_score, 266.0), 1192.0)) / (1192.0 - 266.0)) +
                        0.40 * LEAST(1.0, LN(1.0 + pop_density) / LN(1.0 + 35000.0))
                    )
                END,
                4
            ) AS vulnerability_score
        FROM joined_demographics
    )
    
    -- Step D: Final composite Transit Desert Index
    SELECT 
        *,
        ROUND(vulnerability_score * (1.0 - accessibility_score), 4) AS transit_desert_index
    FROM scored_indicators;
    """
    
    con.execute(materialize_sql)
    mat_elapsed = time.time() - start_time
    total_materialized = con.execute("SELECT COUNT(*) FROM melb_equity_scores;").fetchone()[0]
    logger.info("Materialized %d rows in `melb_equity_scores` in %.2f seconds", total_materialized, mat_elapsed)
    
    # 3. Create Analytical View `v_transit_deserts`
    logger.info("-" * 75)
    logger.info("CREATING ANALYTICAL VIEW `v_transit_deserts`...")
    
    # Compute P80 cutoff for populated transit deserts
    p80_cutoff = con.execute("""
        SELECT ROUND(PERCENTILE_CONT(0.80) WITHIN GROUP (ORDER BY transit_desert_index), 4)
        FROM melb_equity_scores
        WHERE population > 0 AND sa2_name IS NOT NULL;
    """).fetchone()[0]
    
    logger.info("Top 20th percentile (P80) Transit Desert Index cutoff: %.4f", p80_cutoff)
    
    con.execute("DROP VIEW IF EXISTS v_transit_deserts;")
    con.execute(f"""
        CREATE VIEW v_transit_deserts AS
        SELECT 
            h3_index,
            centroid_lat,
            centroid_lng,
            sa1_code,
            sa2_code,
            sa2_name,
            gccsa_name,
            population,
            pop_density,
            seifa_irsd_score,
            seifa_irsd_decile,
            travel_time_rmh_p50,
            travel_time_monash_p50,
            travel_time_chadstone_p50,
            score_rmh,
            score_monash,
            score_chadstone,
            accessibility_score,
            vulnerability_score,
            transit_desert_index,
            PERCENT_RANK() OVER (ORDER BY transit_desert_index) AS desert_percentile_rank,
            NTILE(5) OVER (ORDER BY transit_desert_index) AS desert_quintile
        FROM melb_equity_scores
        WHERE population > 0 
          AND sa2_name IS NOT NULL
          AND transit_desert_index >= {p80_cutoff};
    """)
    
    desert_count = con.execute("SELECT COUNT(*) FROM v_transit_deserts;").fetchone()[0]
    logger.info("View `v_transit_deserts` created successfully with %d high-priority desert cells", desert_count)
    
    # 4. Pipeline Validation & Quality Audit
    logger.info("=" * 75)
    logger.info("PIPELINE AUDIT & STATISTICAL VALIDATION REPORT")
    logger.info("=" * 75)
    
    # Audit 1: Spatial join match rate
    join_stats = con.execute("""
        SELECT 
            COUNT(*) AS total_grid_cells,
            COUNT(sa1_code) AS matched_to_sa1,
            ROUND(COUNT(sa1_code) * 100.0 / COUNT(*), 1) AS match_rate_pct,
            COUNT(CASE WHEN population > 0 THEN 1 END) AS populated_cells,
            ROUND(COUNT(CASE WHEN population > 0 THEN 1 END) * 100.0 / COUNT(*), 1) AS populated_pct
        FROM melb_equity_scores;
    """).fetchdf()
    logger.info("Audit 1 — Spatial Join Match Rate:\n%s\n", join_stats.to_string(index=False))
    
    # Audit 2: Index Distributions across Populated Greater Melbourne
    dist_stats = con.execute("""
        SELECT 
            'accessibility_score' AS metric,
            MIN(accessibility_score) AS min_val,
            ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY accessibility_score), 4) AS p25,
            ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY accessibility_score), 4) AS median,
            ROUND(AVG(accessibility_score), 4) AS mean,
            ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY accessibility_score), 4) AS p75,
            ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY accessibility_score), 4) AS p90,
            MAX(accessibility_score) AS max_val
        FROM melb_equity_scores WHERE population > 0
        UNION ALL
        SELECT 
            'vulnerability_score' AS metric,
            MIN(vulnerability_score) AS min_val,
            ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY vulnerability_score), 4) AS p25,
            ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY vulnerability_score), 4) AS median,
            ROUND(AVG(vulnerability_score), 4) AS mean,
            ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY vulnerability_score), 4) AS p75,
            ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY vulnerability_score), 4) AS p90,
            MAX(vulnerability_score) AS max_val
        FROM melb_equity_scores WHERE population > 0
        UNION ALL
        SELECT 
            'transit_desert_index' AS metric,
            MIN(transit_desert_index) AS min_val,
            ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY transit_desert_index), 4) AS p25,
            ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY transit_desert_index), 4) AS median,
            ROUND(AVG(transit_desert_index), 4) AS mean,
            ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY transit_desert_index), 4) AS p75,
            ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY transit_desert_index), 4) AS p90,
            MAX(transit_desert_index) AS max_val
        FROM melb_equity_scores WHERE population > 0;
    """).fetchdf()
    logger.info("Audit 2 — Populated Metric Distributions:\n%s\n", dist_stats.to_string(index=False))
    
    # Audit 3: Top 10 Worst Transit Desert Suburbs (Aggregated by SA2)
    top_deserts = con.execute("""
        SELECT 
            sa2_name AS suburb_precinct,
            COUNT(*) AS desert_hex_count,
            SUM(population) AS estimated_resident_pop,
            ROUND(AVG(pop_density), 0) AS avg_density_sqkm,
            ROUND(AVG(seifa_irsd_decile), 1) AS avg_seifa_decile,
            ROUND(AVG(accessibility_score), 3) AS avg_access_score,
            ROUND(AVG(vulnerability_score), 3) AS avg_vuln_score,
            ROUND(AVG(transit_desert_index), 3) AS avg_desert_index
        FROM v_transit_deserts
        GROUP BY sa2_name
        ORDER BY avg_desert_index DESC, desert_hex_count DESC
        LIMIT 10;
    """).fetchdf()
    logger.info("Audit 3 — Top 10 Priority Transit Desert Suburbs:\n%s\n", top_deserts.to_string(index=False))
    
    # Audit 4: Sample Data from `melb_equity_scores`
    sample_records = con.execute("""
        SELECT 
            h3_index,
            sa2_name,
            population,
            ROUND(pop_density, 0) AS density,
            seifa_irsd_decile AS seifa_dec,
            travel_time_rmh_p50 AS rmh_m,
            travel_time_monash_p50 AS mon_m,
            travel_time_chadstone_p50 AS chad_m,
            accessibility_score AS access,
            vulnerability_score AS vuln,
            transit_desert_index AS desert_idx
        FROM melb_equity_scores
        WHERE population > 0
        ORDER BY transit_desert_index DESC
        LIMIT 5;
    """).fetchdf()
    logger.info("Audit 4 — Sample Materialized Desert Records:\n%s\n", sample_records.to_string(index=False))
    
    con.close()
    total_elapsed = time.time() - start_time
    logger.info("=" * 75)
    logger.info("PHASE 3 PIPELINE COMPLETED IN %.2f SECONDS", total_elapsed)
    logger.info("=" * 75)


if __name__ == "__main__":
    compute_equity_scores()
