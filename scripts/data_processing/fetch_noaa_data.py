
import os
import requests
import pandas as pd
from datetime import datetime
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("noaa_fetch.log"),
        logging.StreamHandler()
    ]
)

# Base URL for NOAA NCEI Global Historical Climatology Network daily (GHCN-D)
# Note: GHCN-D is more reliable for daily data than ISD for long-term climate analysis
# However, your station list seems to come from ISD (based on USAF-WBAN columns)
# Let's try to fetch from NCEI's public API or simple file access
# Strategy: Use the NCEI CDO (Climate Data Online) API or direct CSV download if possible.
# Given the "USAF" and "WBAN" columns, this is ISD format.
# Let's use the ISD Lite format which is cleaner for daily averages.

BASE_URL = "https://www.ncei.noaa.gov/pub/data/noaa/isd-lite"
OUTPUT_DIR = "data/noaa_raw"
STATION_LIST_FILE = "ncp_noaa_stations.csv"

def setup_dir():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        logging.info(f"Created directory: {OUTPUT_DIR}")

def download_station_data(usaf, wban, start_year=1990, end_year=2023):
    """
    Download ISD-Lite data for a specific station year by year.
    URL Format: https://www.ncei.noaa.gov/pub/data/noaa/isd-lite/{year}/{usaf}-{wban}-{year}.gz
    """
    # Standardize IDs to string
    usaf = str(usaf).zfill(6)
    wban = str(wban).zfill(5)
    
    station_id = f"{usaf}-{wban}"
    station_dir = os.path.join(OUTPUT_DIR, station_id)
    
    if not os.path.exists(station_dir):
        os.makedirs(station_dir)

    success_count = 0
    
    for year in range(start_year, end_year + 1):
        filename = f"{usaf}-{wban}-{year}.gz"
        file_path = os.path.join(station_dir, filename)
        
        # Skip if already downloaded
        if os.path.exists(file_path):
            logging.info(f"  [SKIP] {filename} already exists.")
            success_count += 1
            continue
            
        url = f"{BASE_URL}/{year}/{filename}"
        
        try:
            logging.info(f"  Downloading {url}...")
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                success_count += 1
                time.sleep(0.5) # Be nice to NOAA servers
            elif response.status_code == 404:
                logging.warning(f"  [404] Data not available for {station_id} in {year}")
            else:
                logging.error(f"  [ERR] Failed to download {url}: Status {response.status_code}")
                
        except Exception as e:
            logging.error(f"  [EXC] Error downloading {url}: {e}")
            
    return success_count

def process_isd_lite(file_path):
    """
    Parse ISD-Lite fixed width format.
    Columns: Year, Month, Day, Hour, Air Temp, Dew Point, Sea Level Pressure, Wind Direction, Wind Speed, Sky Condition, Precip-1h, Precip-6h
    Missing values are -9999.
    Scale factors are usually 10 (e.g. 321 = 32.1 C)
    """
    # This function is for future use (processing step), not needed for raw download
    pass

def main():
    setup_dir()
    
    if not os.path.exists(STATION_LIST_FILE):
        logging.error(f"Station list file {STATION_LIST_FILE} not found!")
        return

    df = pd.read_csv(STATION_LIST_FILE)
    logging.info(f"Loaded {len(df)} stations from {STATION_LIST_FILE}")
    
    total_stations = len(df)
    
    for index, row in df.iterrows():
        usaf = row['USAF']
        wban = row['WBAN']
        station_name = row['STATION NAME']
        
        logging.info(f"[{index+1}/{total_stations}] Processing {station_name} ({usaf}-{wban})...")
        
        # Download data from 1990 to 2023
        count = download_station_data(usaf, wban, 1990, 2023)
        logging.info(f"  -> Downloaded {count} years of data for {station_name}")

if __name__ == "__main__":
    main()
