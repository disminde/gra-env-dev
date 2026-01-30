import os
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
import logging
from dotenv import load_dotenv
import pandas as pd
import time
import openmeteo_requests
import requests_cache
from retry_requests import retry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("batch_fetch.log"),
        logging.StreamHandler()
    ]
)

# Load environment variables
load_dotenv()

# Database configuration
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "gra_env_db")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password_dev")

def get_db_connection():
    """Establish a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        return conn
    except Exception as e:
        logging.error(f"Error connecting to database: {e}")
        raise

def create_grid_table(conn):
    """Create the grid_weather_data table if it doesn't exist."""
    create_table_query = """
    CREATE TABLE IF NOT EXISTS grid_weather_data (
        id SERIAL PRIMARY KEY,
        latitude FLOAT NOT NULL,
        longitude FLOAT NOT NULL,
        timestamp TIMESTAMP NOT NULL,
        temperature FLOAT,
        precipitation FLOAT,
        et0_fao_evapotranspiration FLOAT,
        soil_moisture_0_to_7cm FLOAT,
        relative_humidity_2m FLOAT,
        wind_speed_10m FLOAT,
        shortwave_radiation FLOAT,
        UNIQUE (latitude, longitude, timestamp)
    );
    """
    try:
        cur = conn.cursor()
        cur.execute(create_table_query)
        # 检查是否需要添加新列（如果表已存在但缺少新变量）
        new_columns = [
            ("relative_humidity_2m", "FLOAT"),
            ("wind_speed_10m", "FLOAT"),
            ("shortwave_radiation", "FLOAT")
        ]
        for col_name, col_type in new_columns:
            cur.execute(f"""
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                   WHERE table_name='grid_weather_data' AND column_name='{col_name}') THEN
                        ALTER TABLE grid_weather_data ADD COLUMN {col_name} {col_type};
                    END IF;
                END $$;
            """)
        conn.commit()
        logging.info("Table 'grid_weather_data' checked/updated successfully.")
        cur.close()
    except Exception as e:
        logging.error(f"Error creating/updating table: {e}")
        conn.rollback()
        raise

def fetch_grid_data(grid_points):
    """
    Fetch historical weather data for multiple grid points using Open-Meteo API.
    
    Args:
        grid_points (pd.DataFrame): DataFrame containing 'latitude' and 'longitude'.
    """
    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    url = "https://archive-api.open-meteo.com/v1/archive"
    
    # Process in chunks to avoid API limits (Open-Meteo accepts multiple points but keep it reasonable)
    # Reduced chunk size to avoid memory issues (was 50)
    chunk_size = 5 

    total_points = len(grid_points)
    print(f"DEBUG: Chunk size is {chunk_size}, Total points: {total_points}")
    
    conn = get_db_connection()
    create_grid_table(conn)
    
    for i in range(0, total_points, chunk_size):
        chunk = grid_points.iloc[i:i+chunk_size]
        lats = chunk['latitude'].tolist()
        lons = chunk['longitude'].tolist()
        
        logging.info(f"Processing grid points chunk {i//chunk_size + 1}/{(total_points-1)//chunk_size + 1} ({len(chunk)} points)...")
        
        # Iterate by year to keep memory usage low and provide frequent feedback
        start_year = 1990
        end_year = 2023
        
        for year in range(start_year, end_year + 1):
            year_start = f"{year}-01-01"
            year_end = f"{year}-12-31"
            
            # Skip future dates if we are in the current year (adjust logic if needed)
            if year > datetime.now().year:
                break
                
            logging.info(f"  Fetching data for year {year}...")

            params = {
                "latitude": lats,
                "longitude": lons,
                "start_date": year_start,
                "end_date": year_end,
                "hourly": [
                    "temperature_2m", 
                    "precipitation", 
                    "et0_fao_evapotranspiration", 
                    "soil_moisture_0_to_7cm",
                    "relative_humidity_2m",
                    "wind_speed_10m",
                    "shortwave_radiation"
                ]
            }
            
            # Retry loop for API rate limits
            max_retries = 5
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    responses = openmeteo_requests.Client(session = retry_session).weather_api(url, params=params)
                    success = True # Mark as success if no exception
                    
                    all_records = []
                    
                    for j, response in enumerate(responses):
                        lat = response.Latitude()
                        lon = response.Longitude()
                        
                        # Process hourly data
                        hourly = response.Hourly()
                        hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()
                        hourly_precipitation = hourly.Variables(1).ValuesAsNumpy()
                        hourly_et0 = hourly.Variables(2).ValuesAsNumpy()
                        hourly_soil_moisture = hourly.Variables(3).ValuesAsNumpy()
                        hourly_humidity = hourly.Variables(4).ValuesAsNumpy()
                        hourly_wind_speed = hourly.Variables(5).ValuesAsNumpy()
                        hourly_radiation = hourly.Variables(6).ValuesAsNumpy()
                        
                        hourly_data = {"date": pd.date_range(
                            start = pd.to_datetime(hourly.Time(), unit = "s", utc = True),
                            end = pd.to_datetime(hourly.TimeEnd(), unit = "s", utc = True),
                            freq = pd.Timedelta(seconds = hourly.Interval()),
                            inclusive = "left"
                        )}
                        
                        # Create DataFrame for easier handling
                        df = pd.DataFrame(data = hourly_data)
                        df["temperature"] = hourly_temperature_2m
                        df["precipitation"] = hourly_precipitation
                        df["et0"] = hourly_et0
                        df["soil_moisture"] = hourly_soil_moisture
                        df["humidity"] = hourly_humidity
                        df["wind_speed"] = hourly_wind_speed
                        df["radiation"] = hourly_radiation
                        
                        # Convert to list of tuples for DB insertion
                        # Use a generator or direct iteration to save memory
                        for _, row in df.iterrows():
                            all_records.append((
                                lat, 
                                lon, 
                                row['date'], 
                                float(row['temperature']), 
                                float(row['precipitation']), 
                                float(row['et0']), 
                                float(row['soil_moisture']),
                                float(row['humidity']),
                                float(row['wind_speed']),
                                float(row['radiation'])
                            ))
                    
                    # Batch insert for this year
                    if all_records:
                        insert_query = """
                        INSERT INTO grid_weather_data (
                            latitude, longitude, timestamp, temperature, precipitation, 
                            et0_fao_evapotranspiration, soil_moisture_0_to_7cm,
                            relative_humidity_2m, wind_speed_10m, shortwave_radiation
                        )
                        VALUES %s
                        ON CONFLICT (latitude, longitude, timestamp) DO NOTHING;
                        """
                        
                        cur = conn.cursor()
                        execute_values(cur, insert_query, all_records)
                        conn.commit()
                        cur.close()
                        logging.info(f"  Inserted {len(all_records)} records for year {year}.")
                    
                    # Small pause between years
                    time.sleep(1)

                except Exception as e:
                    error_msg = str(e)
                    if "Hourly API request limit exceeded" in error_msg or "429" in error_msg:
                        wait_time = 60 * (retry_count + 1) # Linear backoff: 60s, 120s, ...
                        logging.warning(f"Rate limit hit for year {year}. Waiting {wait_time}s before retry {retry_count + 1}/{max_retries}...")
                        time.sleep(wait_time)
                        retry_count += 1
                    else:
                        logging.error(f"Error processing chunk {i} for year {year}: {e}")
                        # Non-retryable error (or unknown), break inner loop to skip this year
                        break
            
            if not success:
                 logging.error(f"Failed to fetch data for year {year} after {max_retries} retries.")

        # Be nice to the API between chunks
        time.sleep(2)

    conn.close()
    logging.info("Batch processing completed.")

if __name__ == "__main__":
    from generate_grid import generate_ncp_grid
    
    # Generate grid points
    grid = generate_ncp_grid()
    
    # Start fetching
    fetch_grid_data(grid)
