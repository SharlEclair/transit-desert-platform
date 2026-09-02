import json

with open("data/mumbai/raw/metro_network/mumbai_metro_stations.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for lid, summary in data["lines_summary"].items():
    stations = [s for s in data["stations"] if s["line_id"] == lid]
    known = [(s["sequence"], s["station_name"], s["lat"], s["lon"]) for s in stations if s["has_coordinates"]]
    missing = [(s["sequence"], s["station_name"]) for s in stations if not s["has_coordinates"]]
    print(f"\nLine {lid} ({summary['line_name']}) - Total: {summary['total']}, Known: {summary['with_coords']}, Missing: {summary['missing_coords']}")
    print(f"  Known ({len(known)}): {known}")
    print(f"  Missing ({len(missing)}): {missing}")
