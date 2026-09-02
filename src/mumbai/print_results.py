import duckdb
import json
import h3
import pandas as pd

con = duckdb.connect("data/mumbai/processed/mumbai_equity.db", read_only=True)
with open("data/mumbai/processed/mumbai_metro_stations_resolved.json", "r", encoding="utf-8") as f:
    stations = json.load(f)["stations"]

print("=" * 85)
print("REVISED LINE 6 (PINK LINE) STATIONS -> IIT BOMBAY COMMUTE TIMES")
print("=" * 85)
l6_rows = []
for s in [st for st in stations if st["line_id"] == "6"]:
    h = h3.latlng_to_cell(s["lat"], s["lon"], 9)
    res = con.execute("""
        SELECT 
            c.travel_time_p50 AS t24, 
            f.travel_time_p50 AS t30, 
            ROUND(c.travel_time_p50 - f.travel_time_p50, 1) AS saved
        FROM mumbai_travel_matrix c
        JOIN mumbai_travel_matrix_2030 f 
          ON c.origin_h3 = f.origin_h3 AND c.destination_id = f.destination_id
        WHERE c.origin_h3 = ? AND c.destination_id = 'IIT_BOMBAY';
    """, [h]).fetchone()
    if res:
        l6_rows.append({
            "Seq": s["sequence"],
            "Station": s["station_name"],
            "Latitude": f"{s['lat']:.4f}",
            "Longitude": f"{s['lon']:.4f}",
            "2024 Commute (min)": f"{res[0]:.1f}",
            "2030 Commute (min)": f"{res[1]:.1f}",
            "Time Saved (min)": f"{res[2]:.1f}"
        })
print(pd.DataFrame(l6_rows).to_string(index=False))

print("\n" + "=" * 85)
print("REVISED LINE 3 (AQUA LINE) STATIONS -> BKC COMMUTE TIMES")
print("=" * 85)
l3_rows = []
for s in [st for st in stations if st["line_id"] == "3"]:
    h = h3.latlng_to_cell(s["lat"], s["lon"], 9)
    res = con.execute("""
        SELECT 
            c.travel_time_p50 AS t24, 
            f.travel_time_p50 AS t30, 
            ROUND(c.travel_time_p50 - f.travel_time_p50, 1) AS saved
        FROM mumbai_travel_matrix c
        JOIN mumbai_travel_matrix_2030 f 
          ON c.origin_h3 = f.origin_h3 AND c.destination_id = f.destination_id
        WHERE c.origin_h3 = ? AND c.destination_id = 'BKC';
    """, [h]).fetchone()
    if res:
        l3_rows.append({
            "Seq": s["sequence"],
            "Station": s["station_name"],
            "Latitude": f"{s['lat']:.4f}",
            "Longitude": f"{s['lon']:.4f}",
            "2024 Commute (min)": f"{res[0]:.1f}",
            "2030 Commute (min)": f"{res[1]:.1f}",
            "Time Saved (min)": f"{res[2]:.1f}"
        })
print(pd.DataFrame(l3_rows).to_string(index=False))

print("\n" + "=" * 85)
print("NEWLY CALCULATED CITYWIDE EQUITY GAIN & DELTA SUMMARY")
print("=" * 85)
comp = con.execute("""
    SELECT 
        ROUND(AVG(current_tdi), 4) AS baseline_tdi,
        ROUND(AVG(future_tdi), 4) AS future_tdi,
        ROUND(AVG(delta_tdi), 4) AS avg_delta_tdi,
        ROUND(MAX(delta_tdi), 4) AS max_delta_tdi,
        ROUND(AVG(current_accessibility), 4) AS baseline_acc,
        ROUND(AVG(future_accessibility), 4) AS future_acc,
        ROUND(AVG(delta_accessibility), 4) AS avg_delta_acc,
        ROUND(MAX(delta_accessibility), 4) AS max_delta_acc,
        ROUND(SUM(CASE WHEN delta_tdi > 0.0001 THEN 1.0 ELSE 0.0 END) / COUNT(*) * 100.0, 1) AS pct_cells_improved
    FROM v_mumbai_equity_comparison;
""").fetchdf()
print(comp.to_string(index=False))

slum_comp = con.execute("""
    SELECT 
        ROUND(AVG(current_tdi), 4) AS slum_baseline_tdi,
        ROUND(AVG(future_tdi), 4) AS slum_future_tdi,
        ROUND(AVG(delta_tdi), 4) AS slum_delta_tdi_reduction,
        ROUND(AVG(delta_accessibility), 4) AS slum_accessibility_gain
    FROM v_mumbai_equity_comparison
    WHERE is_slum_cluster = 1;
""").fetchdf()
print("\nInformal Slum Clusters (N=360):")
print(slum_comp.to_string(index=False))
