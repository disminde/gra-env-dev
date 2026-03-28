import os
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
import logging
import time
from dotenv import load_dotenv
from scripts.clash_manager import ClashManager

class TimezoneFormatter(logging.Formatter):
    def converter(self, timestamp):
        # Always return time in local system time (which should be correct on Windows)
        # or convert UTC to Shanghai time explicitly if needed
        dt = datetime.fromtimestamp(timestamp)
        return dt

# Configure logging
formatter = TimezoneFormatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler("weather_fetch.log", encoding='utf-8')
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler]
)

load_dotenv()

# Proxy Configuration
PROXY_URL = os.getenv("HTTP_PROXY", None)
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

# Initialize Clash Manager
clash_manager = None
if PROXY_URL:
    try:
        clash_manager = ClashManager()
        logging.info("ClashManager initialized.")
    except Exception as e:
        logging.warning(f"Failed to initialize ClashManager: {e}")

# DB Configuration
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "gra_env_db")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password_dev")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )

def get_grid_points(conn):
    """
    Get all unique grid points from the database to process.
    """
    logging.info("Fetching grid points from database...")
    try:
        cur = conn.cursor()
        # Use a recursive CTE to efficiently get distinct lat/lon pairs from large table
        query = """
        WITH RECURSIVE t AS (
           (SELECT latitude, longitude FROM grid_weather_data ORDER BY latitude, longitude LIMIT 1)
           UNION ALL
           SELECT (SELECT latitude, longitude FROM grid_weather_data WHERE (latitude, longitude) > (t.latitude, t.longitude) ORDER BY latitude, longitude LIMIT 1)
           FROM t
           WHERE t.latitude IS NOT NULL
        )
        SELECT latitude, longitude FROM t WHERE latitude IS NOT NULL;
        """
        cur.execute(query)
        points = cur.fetchall()
        cur.close()
        logging.info(f"Found {len(points)} grid points in database.")
        return points
    except Exception as e:
        logging.error(f"Error fetching grid points (CTE method failed, trying simple DISTINCT): {e}")
        conn.rollback()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT latitude, longitude FROM grid_weather_data")
        points = cur.fetchall()
        cur.close()
        logging.info(f"Found {len(points)} grid points in database.")
        return points

def get_last_timestamp(conn, lat, lon):
    """Get the last timestamp for a given grid point."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT MAX(timestamp) FROM grid_weather_data WHERE latitude = %s AND longitude = %s",
            (lat, lon)
        )
        result = cur.fetchone()[0]
        cur.close()
        return result
    except Exception as e:
        logging.error(f"Error getting last timestamp: {e}")
        return None

def fetch_archive_data(lat, lon, start_date, end_date):
    """Fetch historical data from Open-Meteo Archive API."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": "temperature_2m,precipitation,et0_fao_evapotranspiration,soil_moisture_0_to_7cm,relative_humidity_2m,wind_speed_10m,shortwave_radiation",
        "timezone": "UTC"
    }
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            if PROXIES:
                logging.debug(f"Using proxy: {PROXY_URL}")
            
            # Use session with retries for connection stability
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(max_retries=3)
            session.mount('https://', adapter)
            session.mount('http://', adapter)
            
            response = session.get(url, params=params, timeout=45, proxies=PROXIES)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logging.warning(f"Request failed (attempt {attempt+1}/{max_retries}): {e}")
            
            # Handle rate limits or forbidden access by switching IP
            if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code in [403, 429]:
                 logging.warning(f"Access denied ({e.response.status_code}). Switching proxy...")
                 if clash_manager and clash_manager.switch_proxy():
                     logging.info("Switched proxy successfully. Waiting 3s before retry...")
                     time.sleep(3)
                     continue
            
            # Exponential backoff for other errors
            sleep_time = 5 * (attempt + 1)
            logging.info(f"Waiting {sleep_time}s before retry...")
            time.sleep(sleep_time)
    
    raise Exception(f"Failed to fetch data for ({lat}, {lon}) after {max_retries} retries")

def save_data(conn, data, lat, lon):
    """Save fetched data to database."""
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    
    if not times:
        return 0
        
    records = []
    for i, t_str in enumerate(times):
        # API returns ISO format, e.g., "1990-01-01T00:00"
        timestamp = datetime.fromisoformat(t_str)
        records.append((
            lat, lon, timestamp,
            hourly.get("temperature_2m", [])[i],
            hourly.get("precipitation", [])[i],
            hourly.get("et0_fao_evapotranspiration", [])[i],
            hourly.get("soil_moisture_0_to_7cm", [])[i],
            hourly.get("relative_humidity_2m", [])[i],
            hourly.get("wind_speed_10m", [])[i],
            hourly.get("shortwave_radiation", [])[i]
        ))
        
    query = """
    INSERT INTO grid_weather_data (
        latitude, longitude, timestamp, 
        temperature, precipitation, et0_fao_evapotranspiration, 
        soil_moisture_0_to_7cm, relative_humidity_2m, 
        wind_speed_10m, shortwave_radiation
    ) VALUES %s
    ON CONFLICT (latitude, longitude, timestamp) DO UPDATE SET
        temperature = EXCLUDED.temperature,
        precipitation = EXCLUDED.precipitation,
        et0_fao_evapotranspiration = EXCLUDED.et0_fao_evapotranspiration,
        soil_moisture_0_to_7cm = EXCLUDED.soil_moisture_0_to_7cm,
        relative_humidity_2m = EXCLUDED.relative_humidity_2m,
        wind_speed_10m = EXCLUDED.wind_speed_10m,
        shortwave_radiation = EXCLUDED.shortwave_radiation;
    """
    
    try:
        cur = conn.cursor()
        execute_values(cur, query, records)
        conn.commit()
        cur.close()
        return len(records)
    except Exception as e:
        conn.rollback()
        logging.error(f"Error saving data: {e}")
        raise

def main():
    logging.info("Starting automated weather data fetcher...")
    
    # Define target range
    TARGET_START_DATE = datetime(1990, 1, 1)
    TARGET_END_DATE = datetime(2025, 1, 1)
    
    conn = None
    try:
        conn = get_db_connection()
        points = get_grid_points(conn)
        
        if not points:
            logging.error("No grid points found in database! Please import initial grid points first.")
            return

        total_points = len(points)
        for idx, (lat, lon) in enumerate(points):
            logging.info(f"Checking point {idx+1}/{total_points}: ({lat}, {lon})")
            
            # Check existing data range
            last_ts = get_last_timestamp(conn, lat, lon)
            
            if last_ts:
                # If data exists, start from the next day
                current_start = last_ts + timedelta(hours=1)
                # If last timestamp is already past target end date, skip
                if current_start >= TARGET_END_DATE:
                    logging.info(f"  Data already up to date ({last_ts}). Skipping.")
                    continue
                logging.info(f"  Resuming from {current_start}...")
            else:
                # No data, start from beginning
                current_start = TARGET_START_DATE
                logging.info(f"  No existing data. Starting from {current_start}...")
            
            # Fetch loop for this point (in chunks of 5 years)
            while current_start < TARGET_END_DATE:
                # Calculate chunk end (max 5 years or up to target end date)
                chunk_end = min(current_start + timedelta(days=365*5), TARGET_END_DATE)
                
                # Format dates for API (YYYY-MM-DD)
                s_str = current_start.strftime("%Y-%m-%d")
                # API end_date is inclusive, but we want up to TARGET_END_DATE (exclusive logic usually)
                # However, Open-Meteo handles inclusive dates. Let's use inclusive for chunk end.
                e_str = (chunk_end - timedelta(days=1)).strftime("%Y-%m-%d")
                
                if s_str > e_str:
                     break

                logging.info(f"  Fetching range: {s_str} to {e_str}")
                
                try:
                    data = fetch_archive_data(lat, lon, s_str, e_str)
                    count = save_data(conn, data, lat, lon)
                    logging.info(f"  Saved {count} records.")
                    
                    # Advance start date
                    current_start = chunk_end
                    
                    # Rate limiting wait
                    time.sleep(1)
                    
                except Exception as e:
                    logging.error(f"  Failed to fetch chunk {s_str}-{e_str}: {e}")
                    # On failure, maybe wait longer and retry or move to next point?
                    # Here we retry the chunk by not advancing current_start, but we need a break condition
                    # to avoid infinite loop. For now, let's skip to next point to keep overall progress.
                    logging.error("  Skipping to next point due to persistent error.")
                    break
            
    except Exception as e:
        logging.error(f"Critical process error: {e}")
    finally:
        if conn:
            conn.close()
            logging.info("Database connection closed.")

if __name__ == "__main__":
    main()
