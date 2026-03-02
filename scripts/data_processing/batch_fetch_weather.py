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
from tqdm import tqdm

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
# 配置更新时间: 2026-02-19 (根据用户本地 config.yaml 自动校准)
# 优先从环境变量读取（用于隔离模式），否则使用默认值
CLASH_API_URL = os.getenv("CLASH_API_URL", "http://127.0.0.1:10380")
CLASH_SECRET = os.getenv("CLASH_SECRET", "44976f0a-414c-48b1-bda7-5759fef634d3")
PROXY_GROUP_NAME = "猫猫云" 
HTTP_PROXY_URL = os.getenv("HTTP_PROXY", "http://127.0.0.1:7890") 

class ClashController:
    def __init__(self):
        # 自动从配置文件读取配置
        self.api_url = CLASH_API_URL
        self.secret = CLASH_SECRET
        self._try_load_from_config()
        
        self.headers = {"Authorization": f"Bearer {self.secret}"} if self.secret else {}
        self.available_nodes = []
        self.current_node_idx = 0
        
        # 优先使用配置的端口，如果连不上再探测
        if not self._check_current_port():
             self._auto_detect_port()
        self._init_nodes()

    def _try_load_from_config(self):
        """尝试从 Clash 配置文件自动读取端口和密钥"""
        # 如果环境变量已指定，则优先使用环境变量，不再读取文件
        if os.environ.get("CLASH_API_URL"):
            logging.info(f"使用环境变量指定的 Clash API: {self.api_url}")
            return

        try:
            user_home = os.path.expanduser("~")
            config_path = os.path.join(user_home, ".config", "clash", "config.yaml")
            
            if os.path.exists(config_path):
                logging.info(f"发现 Clash 配置文件: {config_path}")
                with open(config_path, 'r', encoding='utf-8') as f:
                    import yaml
                    config = yaml.safe_load(f)
                    
                    # 读取 external-controller
                    if 'external-controller' in config:
                        controller = config['external-controller']
                        # 处理可能是 0.0.0.0 的情况，替换为 127.0.0.1
                        if controller.startswith(':'):
                            controller = f"127.0.0.1{controller}"
                        elif controller.startswith('0.0.0.0:'):
                            controller = controller.replace('0.0.0.0:', '127.0.0.1:')
                        
                        # 确保有 http 前缀
                        if not controller.startswith('http'):
                            self.api_url = f"http://{controller}"
                        else:
                            self.api_url = controller
                        logging.info(f"  -> 自动读取到 API 地址: {self.api_url}")
                        
                    # 读取 secret
                    if 'secret' in config:
                        self.secret = config['secret']
                        logging.info(f"  -> 自动读取到 API 密钥: {self.secret[:3]}***{self.secret[-3:]}")
        except Exception as e:
            logging.warning(f"尝试读取 Clash 配置文件失败: {e} (将使用默认配置)")

    def _check_current_port(self):
        """检查当前配置的端口是否可用"""
        try:
            resp = requests.get(f"{self.api_url}/version", headers=self.headers, timeout=1)
            if resp.status_code == 200:
                logging.info(f"Clash API 连接成功: {self.api_url}")
                return True
        except:
            pass
        return False

    def _auto_detect_port(self):
        """自动探测 Clash API 端口"""
        common_ports = [3936, 9090, 7342, 5492, 10380, 9097, 7890, 6821, 12531, 12280] # 优先尝试已知端口
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

STATE_FILE = "fetch_progress.json"

def load_progress():
    """Load the last processed index from the state file."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                return data.get('next_start_index', 0)
        except Exception as e:
            logging.warning(f"Failed to load progress file: {e}")
            return 0
    return 0

def save_progress(index):
    """Save the current progress index to the state file."""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({'next_start_index': index}, f)
    except Exception as e:
        logging.warning(f"Failed to save progress: {e}")

# Load environment variables
load_dotenv()

# Database configuration
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "gra_env_db")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password_dev")

def check_if_data_exists(conn, lat, lon, year):
    """
    Check if data for a specific year and location already exists in the database.
    Optimized to use index on latitude, longitude and timestamp.
    Now checks for COMPLETENESS (>8000 records) instead of just existence to fix partial data issues.
    """
    try:
        cur = conn.cursor()
        query = """
        SELECT count(*)
        FROM grid_weather_data 
        WHERE latitude BETWEEN %s - 0.1 AND %s + 0.1
          AND longitude BETWEEN %s - 0.1 AND %s + 0.1
          AND timestamp >= %s AND timestamp <= %s;
        """
        # Create datetime objects for range query to utilize index
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
        
        cur.execute(query, (lat, lat, lon, lon, start_date, end_date))
        count = cur.fetchone()[0]
        cur.close()
        
        # Consider complete if we have more than 8000 records (leap year is 8784, normal 8760)
        # This handles the case where we have partial data (e.g. only 8 records)
        if count > 0 and count <= 8000:
             logging.info(f"  [PARTIAL DATA DETECTED] Year {year} has only {count} records. Will re-fetch.")
             return False
             
        return count > 8000
    except Exception as e:
        # Don't fail the whole process, just assume not exists to be safe
        logging.warning(f"Error checking existing data: {e}")
        return False

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
    # Increased chunk size to 10 for better efficiency
    chunk_size = 10

    total_points = len(grid_points)
    print(f"DEBUG: Optimized Chunk size is {chunk_size}, Total points: {total_points}")
    
    start_index = load_progress()
    logging.info(f"Loaded progress: resuming from index {start_index}")
    
    conn = get_db_connection()
    create_grid_table(conn)
    
    # Use tqdm for progress tracking
    with tqdm(total=total_points, initial=start_index, desc="Processing Grid Points", unit="point") as pbar:
        for i in range(start_index, total_points, chunk_size):
            chunk = grid_points.iloc[i:i+chunk_size]
            lats = chunk['latitude'].tolist()
            lons = chunk['longitude'].tolist()
            
            chunk_idx = i//chunk_size + 1
            total_chunks = (total_points-1)//chunk_size + 1
            logging.info(f"Processing chunk {chunk_idx}/{total_chunks} ({len(chunk)} points)...")
            
            # Iterate by year to keep memory usage low and provide frequent feedback
            start_year = 1990
            end_year = 2023
            
            # 为了减轻单次请求负载，严格限制每次只请求 1 年的数据
            for year in range(start_year, end_year + 1):
                
                # Skip future dates if we are in the current year (adjust logic if needed)
                if year > datetime.now().year:
                    break

                # --- INTELLIGENT SKIP CHECK ---
                # Check if we already have data for this chunk (checking the first point is sufficient as a proxy)
                if check_if_data_exists(conn, lats[0], lons[0], year):
                    logging.info(f"  [SKIP] Data for year {year} already exists in DB. Skipping...")
                    continue
                    
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
                                # 如果自动切换失败，改为等待较长时间重试，而不是阻塞
                                logging.error("自动切换节点失败！可能是没有可用节点或 Clash API 异常。")
                                logging.info("将等待 300 秒 (5分钟) 后重试...")
                                time.sleep(300)
                                
                                # 尝试重新初始化节点列表
                                clash._init_nodes()
                                
                                retry_count += 1
                                continue
                        else:
                            logging.error(f"Error processing chunk {i} for year {year}: {e}")
                            break
            
                if not success:
                     logging.error(f"Failed to fetch data for year {year} after {max_retries} retries.")
            
            # Update progress bar
            pbar.update(len(chunk))

            # Brief pause between chunks
            time.sleep(1)
            
            # Save progress to checkpoint file
            save_progress(i + len(chunk))

    conn.close()
    logging.info("Batch processing completed.")

if __name__ == "__main__":
    from generate_grid import generate_ncp_grid
    
    # Generate grid points
    grid = generate_ncp_grid()
    
    # Start fetching
    fetch_grid_data(grid)
