import os
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
import logging
from dotenv import load_dotenv

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("weather_fetch.log"),
        logging.StreamHandler()
    ]
)

# 加载环境变量
load_dotenv()

# 数据库配置
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "gra_env_db")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password_dev")

def get_db_connection():
    """建立与 PostgreSQL 数据库的连接。"""
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

def create_table(conn):
    """如果 weather_samples 表不存在，则创建该表。"""
    create_table_query = """
    CREATE TABLE IF NOT EXISTS weather_samples (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMP NOT NULL UNIQUE,
        temperature FLOAT,
        humidity FLOAT,
        wind_speed FLOAT
    );
    """
    try:
        cur = conn.cursor()
        cur.execute(create_table_query)
        conn.commit()
        logging.info("Table 'weather_samples' checked/created successfully.")
        cur.close()
    except Exception as e:
        logging.error(f"Error creating table: {e}")
        conn.rollback()
        raise

def fetch_weather_data():
    """Fetch recent 3 days weather data from Open-Meteo API."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": 39.90,
        "longitude": 116.40,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "past_days": 3,
        "forecast_days": 1 # Include today to get full recent context
    }
    
    try:
        logging.info(f"Fetching data from {url}...")
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        logging.info("Data fetched successfully.")
        return data
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error fetching data: {e}")
        raise
    except ValueError as e:
        logging.error(f"Error parsing JSON response: {e}")
        raise

def process_and_store_data(conn, data):
    """Process API data and store it in the database."""
    try:
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        hums = hourly.get("relative_humidity_2m", [])
        winds = hourly.get("wind_speed_10m", [])
        
        if not times:
            logging.warning("No data found in response.")
            return

        records = []
        for i, t_str in enumerate(times):
            # Open-Meteo 返回 ISO8601 格式的字符串
            t = datetime.fromisoformat(t_str)
            temp = temps[i]
            hum = hums[i]
            wind = winds[i]
            records.append((t, temp, hum, wind))
        
        # 使用 execute_values 进行批量插入
        insert_query = """
        INSERT INTO weather_samples (timestamp, temperature, humidity, wind_speed)
        VALUES %s
        ON CONFLICT (timestamp) DO UPDATE SET
            temperature = EXCLUDED.temperature,
            humidity = EXCLUDED.humidity,
            wind_speed = EXCLUDED.wind_speed;
        """
        
        cur = conn.cursor()
        execute_values(cur, insert_query, records)
        conn.commit()
        logging.info(f"Successfully inserted/updated {len(records)} records.")
        cur.close()
        
    except Exception as e:
        logging.error(f"Error processing/storing data: {e}")
        conn.rollback()
        raise

def main():
    try:
        conn = get_db_connection()
        create_table(conn)
        data = fetch_weather_data()
        process_and_store_data(conn, data)
        conn.close()
        logging.info("Process completed successfully.")
    except Exception as e:
        logging.error(f"Process failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
