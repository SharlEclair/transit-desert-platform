import os
import zipfile
import pandas as pd
import geopandas as gpd
from pathlib import Path
import warnings
import pyogrio

# Suppress warnings
warnings.filterwarnings('ignore', category=UserWarning)

# Define paths
DATA_DIR = Path('data/mumbai/raw')
GTFS_FILE = DATA_DIR / 'gtfs.zip'
KML_FILE = DATA_DIR / '5d6f72ed-a290-4931-821f-5476c148407b.kml'
CENSUS_FILE = DATA_DIR / '95e22d97-7f59-4214-b244-2abbf52e6027.csv'
TRAIN_DIR = DATA_DIR / 'Mumbai Local Train Time'

def inspect_gtfs():
    print("=== Profiling GTFS (gtfs.zip) ===")
    if not GTFS_FILE.exists():
        print(f"File not found: {GTFS_FILE}")
        return
    with zipfile.ZipFile(GTFS_FILE, 'r') as z:
        files = z.namelist()
        print(f"Contents of {GTFS_FILE.name}:")
        for f in files:
            print(f"  - {f}")
        
        # Profile a couple of key files
        for f in ['stops.txt', 'routes.txt', 'agency.txt']:
            if f in files:
                with z.open(f) as file:
                    df = pd.read_csv(file)
                    print(f"  > {f} Shape: {df.shape}")
                    print(f"  > {f} Columns: {list(df.columns)}")
    print()

def inspect_kml():
    print(f"=== Profiling Slum KML ({KML_FILE.name}) ===")
    if not KML_FILE.exists():
        print(f"File not found: {KML_FILE}")
        return
    
    
    try:
        gdf = gpd.read_file(KML_FILE, engine='pyogrio')
        print(f"Shape: {gdf.shape}")
        print(f"Columns: {list(gdf.columns)}")
        print(gdf.head(3))
    except Exception as e:
        print(f"Failed to read KML: {e}")
    print()

def inspect_census():
    print(f"=== Profiling Census CSV ({CENSUS_FILE.name}) ===")
    if not CENSUS_FILE.exists():
        print(f"File not found: {CENSUS_FILE}")
        return
    try:
        df = pd.read_csv(CENSUS_FILE)
        print(f"Shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print(df.head(3))
    except Exception as e:
        print(f"Failed to read CSV: {e}")
    print()

def inspect_train_csvs():
    print("=== Profiling Local Train CSVs ===")
    if not TRAIN_DIR.exists():
        print(f"Directory not found: {TRAIN_DIR}")
        return
    
    csv_files = list(TRAIN_DIR.glob('*.csv'))
    print(f"Found {len(csv_files)} CSV files in {TRAIN_DIR.name}/")
    
    if len(csv_files) > 0:
        sample_file = csv_files[0]
        print(f"Inspecting sample file: {sample_file.name}")
        try:
            df = pd.read_csv(sample_file)
            print(f"Shape: {df.shape}")
            print(f"Columns: {list(df.columns)}")
            print(df.head(3))
        except Exception as e:
            print(f"Failed to read CSV: {e}")
    print()

if __name__ == '__main__':
    inspect_gtfs()
    inspect_kml()
    inspect_census()
    inspect_train_csvs()
