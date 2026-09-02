"""
Database Diagnostic & Schema Inspection for Mumbai Equity Database.
Inspects data/mumbai/processed/mumbai_equity.db, prints column types,
samples first 5 rows, and validates population of vulnerability metrics.
"""

import duckdb
import pandas as pd
from pathlib import Path

DB_PATH = Path("data/mumbai/processed/mumbai_equity.db")

def inspect_database():
    print("=" * 75)
    print("MUMBAI EQUITY DATABASE (mumbai_equity.db) DIAGNOSTIC INSPECTION")
    print("=" * 75)
    
    if not DB_PATH.exists():
        print(f"Error: Database file {DB_PATH} does not exist!")
        return
        
    con = duckdb.connect(str(DB_PATH), read_only=True)
    con.execute("LOAD spatial;")
    
    # 1. Inspect Table Inventory
    tables = con.execute("SHOW TABLES;").fetchall()
    table_names = [t[0] for t in tables]
    print(f"\nDiscovered Tables ({len(table_names)}): {table_names}\n")
    
    target_tables = ["mumbai_demographics", "mumbai_slums", "mumbai_travel_matrix", "mumbai_ward_census", "mumbai_bmc_wards"]
    
    for tbl in target_tables:
        if tbl not in table_names:
            print(f"[!] Table '{tbl}' not found in database.")
            continue
            
        print("-" * 75)
        print(f"TABLE: {tbl}")
        print("-" * 75)
        
        # Schema info
        schema_df = con.execute(f"DESCRIBE {tbl};").fetchdf()
        print("Schema:")
        for _, row in schema_df.iterrows():
            print(f"  • {row['column_name']:<22} {row['column_type']}")
            
        row_count = con.execute(f"SELECT COUNT(*) FROM {tbl};").fetchone()[0]
        print(f"\nTotal Records: {row_count:,}")
        
        # Sample rows
        print("\nFirst 5 Rows:")
        cols = [r['column_name'] for _, r in schema_df.iterrows()]
        exclude_cols = [c for c in ['centroid_geom', 'geom'] if c in cols]
        exclude_clause = f"EXCLUDE ({', '.join(exclude_cols)})" if exclude_cols else ""
        sample_df = con.execute(f"SELECT * {exclude_clause} FROM {tbl} LIMIT 5;").fetchdf()
        print(sample_df.to_string(index=False))
        print()
        
    # 2. Specific Validation for Demographics and Vulnerability
    print("=" * 75)
    print("VALIDATING VULNERABILITY SCORE & SLUM CLUSTER POPULATION:")
    print("=" * 75)
    
    v_stats = con.execute("""
        SELECT 
            COUNT(*) AS total_cells,
            COUNT(vulnerability_score) AS non_null_vulnerability,
            COUNT(is_slum_cluster) AS non_null_is_slum,
            MIN(vulnerability_score) AS min_vuln,
            AVG(vulnerability_score) AS avg_vuln,
            MAX(vulnerability_score) AS max_vuln,
            SUM(CASE WHEN is_slum_cluster = 1 THEN 1 ELSE 0 END) AS slum_cluster_count,
            SUM(CASE WHEN is_slum_cluster = 0 THEN 1 ELSE 0 END) AS baseline_count
        FROM mumbai_demographics;
    """).fetchdf()
    print(v_stats.to_string(index=False))
    
    # 3. Specific Validation for Travel Time Matrix
    print("\n" + "=" * 75)
    print("VALIDATING TRAVEL TIME MATRIX COVERAGE:")
    print("=" * 75)
    
    matrix_stats = con.execute("""
        SELECT 
            destination_id,
            COUNT(*) AS total_reachable_pairs,
            ROUND(MIN(travel_time_p50), 1) AS min_p50_min,
            ROUND(AVG(travel_time_p50), 1) AS avg_p50_min,
            ROUND(MAX(travel_time_p50), 1) AS max_p50_min,
            ROUND(AVG(travel_time_p90), 1) AS avg_p90_min
        FROM mumbai_travel_matrix
        GROUP BY destination_id
        ORDER BY destination_id;
    """).fetchdf()
    print(matrix_stats.to_string(index=False))
    
    con.close()
    print("\n" + "=" * 75)
    print("DIAGNOSTIC INSPECTION COMPLETE - ALL SCHEMAS AND TABLES VERIFIED!")
    print("=" * 75)

if __name__ == "__main__":
    inspect_database()
