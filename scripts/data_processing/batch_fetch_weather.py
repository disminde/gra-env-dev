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
import json
import sys

# --- 强制配置日志，确保在所有操作前生效 ---
log_path = os.path.join(os.getcwd(), "batch_fetch.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_path, mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.info(f"日志系统启动，路径: {log_path}")

# --- Clash API & Proxy 配置 ---
CLASH_API_URL = "http://127.0.0.1:12531" 
CLASH_SECRET = "44976f0a-414c-48b1-bda7-5759fef634d3" 
PROXY_GROUP_NAME = "猫猫云" 
HTTP_PROXY_URL = "http://127.0.0.1:7890" 

class ClashController:
    def __init__(self):
        self.headers = {"Authorization": f"Bearer {CLASH_SECRET}"} if CLASH_SECRET else {}
        self.available_nodes = []
        self.current_node_idx = 0
        self.api_url = CLASH_API_URL
        self._auto_detect_port()
        self._init_nodes()

    def _auto_detect_port(self):
        """自动探测 Clash API 端口"""
        common_ports = [12531, 9090, 9097, 7890] # 优先尝试探测到的 12531
        current_port = int(self.api_url.split(':')[-1])
        if current_port not in common_ports:
            common_ports.insert(0, current_port)
            
        for port in common_ports:
            test_url = f"http://127.0.0.1:{port}"
            try:
                resp = requests.get(f"{test_url}/version", headers=self.headers, timeout=1)
                if resp.status_code == 200:
                    self.api_url = test_url
                    logging.info(f"成功探测到 Clash API 运行在端口: {port}")
                    return
                elif resp.status_code == 401:
                    self.api_url = test_url
                    logging.warning(f"🎯 找到 API 端口 {port}，但提示 'Unauthorized'。请在 CLASH_SECRET 中填入密钥。")
                    return
            except requests.exceptions.ConnectionError:
                continue
            except Exception as e:
                logging.debug(f"探测端口 {port} 时发生意外错误: {e}")
                continue
        
        logging.error("❌ 无法连接到 Clash API。请确保：\n"
                      "1. Clash for Windows 已启动\n"
                      "2. 在 [General] -> [External Control] 查看真实的端口并更新 CLASH_API_URL\n"
                      "3. 如果设置了 Secret，请确保 CLASH_SECRET 已正确填写")

    def _init_nodes(self):
        try:
            resp = requests.get(f"{self.api_url}/proxies", headers=self.headers, timeout=5)
            if resp.status_code == 200:
                proxies = resp.json()["proxies"]
                if PROXY_GROUP_NAME in proxies:
                    self.available_nodes = proxies[PROXY_GROUP_NAME]["all"]
                    # 排除特殊节点和策略组名
                    exclude_names = ["DIRECT", "REJECT", "GLOBAL", "故障转移", "负载均衡", "自动选择", "猫猫云"]
                    self.available_nodes = [n for n in self.available_nodes if n not in exclude_names]
                    logging.info(f"成功加载 {len(self.available_nodes)} 个可切换节点。")
                else:
                    logging.error(f"未找到代理组 '{PROXY_GROUP_NAME}'，请检查 Clash 配置中的组名是否为 '{PROXY_GROUP_NAME}'。")
            elif resp.status_code == 401:
                logging.error("❌ Clash API 认证失败 (401)。请务必在脚本顶部的 CLASH_SECRET 中填写正确的密钥。")
            else:
                logging.error(f"获取 Clash 代理列表失败，状态码: {resp.status_code}, 响应: {resp.text}")
        except Exception as e:
            logging.error(f"初始化 Clash 节点失败: {e}")

    def switch_to_next(self):
        if not self.available_nodes:
            return False
        
        # 随机选择一个节点，避免按顺序遇到连片失效的节点
        import random
        node_name = random.choice(self.available_nodes)
        
        try:
            url = f"{self.api_url}/proxies/{PROXY_GROUP_NAME}"
            payload = {"name": node_name}
            resp = requests.put(url, headers=self.headers, data=json.dumps(payload), timeout=5)
            if resp.status_code == 204:
                logging.info(f">>> 随机切换节点成功: {node_name}")
                return True
        except Exception as e:
            logging.error(f"切换节点出错: {e}")
        return False

clash = ClashController()

# ----------------------------

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
    
    # 强制让 requests 走 Clash 代理端口，不依赖系统全局代理设置
    cache_session.proxies = {
        "http": HTTP_PROXY_URL,
        "https": HTTP_PROXY_URL
    }
    
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    url = "https://archive-api.open-meteo.com/v1/archive"
    
    # Process in chunks to avoid API limits (Open-Meteo accepts multiple points but keep it reasonable)
    # Reducing chunk size to 5 points to minimize load per request.
    chunk_size = 5 

    total_points = len(grid_points)
    print(f"DEBUG: Optimized Chunk size is {chunk_size}, Total points: {total_points}")
    
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
        
        # 为了减轻单次请求负载，严格限制每次只请求 1 年的数据
        for year in range(start_year, end_year + 1):
            
            # Skip future dates if we are in the current year (adjust logic if needed)
            if year > datetime.now().year:
                break
                
            logging.info(f"  Fetching data for year {year}...")

            params = {
                "latitude": lats,
                "longitude": lons,
                "start_date": f"{year}-01-01",
                "end_date": f"{year}-12-31",
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
                        # Direct iteration to save memory
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
                        logging.info(f"  Inserted {len(all_records)} records for year {year} ({len(chunk)} points).")
                    
                    # Pause between years to stay under minutely rate limit (600/min)
                    # 1 request per 1.2s = 50 requests per minute
                    time.sleep(1.2)

                except Exception as e:
                    error_msg = str(e)
                    if "request limit exceeded" in error_msg or "429" in error_msg:
                        logging.warning(f"Quota limit reached (API Error: {error_msg}). Automatically switching Clash node...")
                        
                        # 如果是 Minutely 限制，额外等待一段时间，给 API 喘息的机会
                        if "Minutely" in error_msg:
                            logging.info("检测到每分钟频率限制，额外冷却 15 秒...")
                            time.sleep(15)

                        # 自动尝试切换到下一个节点
                        if clash.switch_to_next():
                            # 延长等待时间，让新节点链路完全打通
                            wait_time = 15
                            logging.info(f"等待 {wait_time} 秒让新节点链路稳定...")
                            time.sleep(wait_time)
                            
                            # 验证新 IP
                            try:
                                # 增加验证时的重试
                                for _ in range(3):
                                    try:
                                        new_ip = requests.get('https://api.ipify.org', proxies=cache_session.proxies, timeout=10).text
                                        logging.info(f"新节点 IP 验证成功: {new_ip}")
                                        break
                                    except:
                                        time.sleep(2)
                            except:
                                logging.warning("无法验证新 IP，但将尝试继续。")
                            
                            # 重置重试计数并立即继续循环
                            retry_count = 0
                            continue
                        else:
                            # 如果自动切换失败（可能 API 配置有误），回退到手动模式
                            print("\n" + "!"*50)
                            print("自动切换节点失败！请检查 Clash API 配置。")
                            print("手动切换后按下 [Enter] 键继续...")
                            print("!"*50 + "\n")
                            input(">>> 按下 Enter 键以继续...")
                            retry_count = 0
                            continue
                    else:
                        logging.error(f"Error processing chunk {i} for year {year}: {e}")
                        break
            
            if not success:
                 logging.error(f"Failed to fetch data for year {year} after {max_retries} retries.")
            
            # 即使成功了，也在年份之间加个小停顿，避免触发 Burst Limit
            time.sleep(2)

        # Brief pause between chunks
        time.sleep(2)

    conn.close()
    logging.info("Batch processing completed.")

if __name__ == "__main__":
    from generate_grid import generate_ncp_grid
    
    # Generate grid points
    grid = generate_ncp_grid()
    
    # Start fetching
    fetch_grid_data(grid)
