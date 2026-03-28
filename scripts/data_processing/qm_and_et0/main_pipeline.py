import os
import pandas as pd
import numpy as np
import psycopg2
import psycopg2.extras
import math
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
import geopandas as gpd
from shapely.geometry import Point
from scipy.spatial import cKDTree
from scipy import stats

# ==========================================
# 1. 基础配置与日志设置
# ==========================================

# 配置日志，方便我们跟踪进度
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"qm_et0_process_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 全局配置变量
CONFIG = {
    'start_year': 1990,
    'end_year': 2023,
    'noaa_raw_dir': 'data/raw/noaa/noaa_raw',  # NOAA 原始 ISD-Lite 压缩包存放目录
    'mapping_file': 'station_grid_mapping.csv', # 我们刚刚生成的映射文件
    'target_resolution': 0.1,  # 最终高清网格的分辨率（度）
    'lat_range': (32.0, 42.0), # 华北平原纬度范围
    'lon_range': (110.0, 123.0) # 华北平原经度范围
}

# ==========================================
# 1.5 NOAA ISD-Lite 格式解析配置
# ==========================================
ISD_LITE_COLUMNS = [
    'Year', 'Month', 'Day', 'Hour', 'AirTemp', 'DewPoint', 
    'Pressure', 'WindDir', 'WindSpeed', 'SkyCover', 
    'Precip1h', 'Precip6h'
]
# 缺失值标记
MISSING_VALUE = -9999

# ==========================================
# 2. 数据库连接模块
# ==========================================

def get_db_connection():
    """获取 PostgreSQL 数据库连接"""
    load_dotenv()
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', '5432'),
            dbname=os.getenv('POSTGRES_DB', 'gra_env_db'),
            user=os.getenv('POSTGRES_USER', 'admin'),
            password=os.getenv('POSTGRES_PASSWORD', 'secure_password_dev')
        )
        return conn
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        raise

# ==========================================
# 3. NOAA 数据处理模块 (步骤 1)
# ==========================================

def calculate_rh_from_dewpoint(temp_c, dewpoint_c):
    """
    根据气温和露点温度计算相对湿度 (RH)
    公式: RH = 100 * (exp((17.625 * Td) / (243.04 + Td)) / exp((17.625 * T) / (243.04 + T)))
    """
    if pd.isna(temp_c) or pd.isna(dewpoint_c):
        return np.nan
    
    # 避免除以零或极小值导致溢出
    if temp_c < -50 or dewpoint_c < -50:
        return np.nan
        
    try:
        e_td = math.exp((17.625 * dewpoint_c) / (243.04 + dewpoint_c))
        e_t = math.exp((17.625 * temp_c) / (243.04 + temp_c))
        rh = 100 * (e_td / e_t)
        return min(max(rh, 0), 100)  # 限制在 0-100 之间
    except:
        return np.nan

def load_and_aggregate_noaa_station(station_id, start_year, end_year):
    """
    读取单个 NOAA 站点的多年 ISD-Lite 压缩数据，清洗并聚合为日数据
    """
    station_dir = os.path.join(CONFIG['noaa_raw_dir'], station_id)
    if not os.path.exists(station_dir):
        logger.warning(f"站点目录不存在: {station_dir}")
        return None
        
    all_years_data = []
    
    for year in range(start_year, end_year + 1):
        file_path = os.path.join(station_dir, f"{station_id}-{year}.gz")
        if not os.path.exists(file_path):
            continue
            
        try:
            # ISD-Lite 是固定宽度格式，或者用空格分隔
            # 新版 pandas 用 sep=r'\s+' 代替 delim_whitespace=True
            df = pd.read_csv(
                file_path, 
                sep=r'\s+', 
                names=ISD_LITE_COLUMNS,
                na_values=[MISSING_VALUE]
            )
            all_years_data.append(df)
        except Exception as e:
            logger.error(f"读取文件 {file_path} 失败: {e}")
            
    if not all_years_data:
        return None
        
    # 合并所有年份数据
    full_df = pd.concat(all_years_data, ignore_index=True)
    
    # 构造日期时间列
    full_df['date'] = pd.to_datetime(
        full_df['Year'].astype(str) + '-' + 
        full_df['Month'].astype(str).str.zfill(2) + '-' + 
        full_df['Day'].astype(str).str.zfill(2)
    )
    
    # 按照 ISD-Lite 缩放因子还原真实物理值
    full_df['AirTemp'] = full_df['AirTemp'] / 10.0      # 摄氏度
    full_df['DewPoint'] = full_df['DewPoint'] / 10.0    # 摄氏度
    full_df['WindSpeed'] = full_df['WindSpeed'] / 10.0  # m/s
    full_df['Precip1h'] = full_df['Precip1h'] / 10.0    # mm
    full_df['Precip6h'] = full_df['Precip6h'] / 10.0    # mm
    
    # 计算相对湿度
    full_df['RelativeHumidity'] = full_df.apply(
        lambda row: calculate_rh_from_dewpoint(row['AirTemp'], row['DewPoint']), 
        axis=1
    )
    
    # ---------------------------------------------------------
    # 核心：按天聚合 (降维)
    # ---------------------------------------------------------
    daily_agg = full_df.groupby('date').agg({
        'AirTemp': 'mean',           # 日均温
        'WindSpeed': 'mean',         # 日均风速
        'RelativeHumidity': 'mean',  # 日均相对湿度
        'Precip1h': 'sum',           # 假设如果有 1h 降水，就累加
        'Precip6h': 'sum'            # 如果有 6h 降水，也累加 (注意排重逻辑，这里简化为如果有就加)
    }).reset_index()
    
    # 整合降水：ISD-Lite 中 Precip1h 和 Precip6h 可能同时存在，取最大或合理合并
    # 为了简化且确保不漏雨，我们以两者的最大和作为保守的日降水估计 (可根据实际需求调整)
    daily_agg['precipitation'] = daily_agg[['Precip1h', 'Precip6h']].max(axis=1)
    
    # 重命名列以匹配我们后续的标准变量名
    daily_agg = daily_agg.rename(columns={
        'AirTemp': 'temperature',
        'WindSpeed': 'wind_speed',
        'RelativeHumidity': 'relative_humidity'
    })
    
    # 只保留我们 QM 需要的四个变量
    final_daily = daily_agg[['date', 'temperature', 'precipitation', 'wind_speed', 'relative_humidity']]
    
    return final_daily

def process_all_noaa_stations():
    """读取 mapping 文件，处理所有映射站点的 NOAA 数据"""
    mapping_df = pd.read_csv(CONFIG['mapping_file'])
    station_ids = mapping_df['station_id'].unique()
    
    logger.info(f"计划处理 {len(station_ids)} 个 NOAA 站点数据...")
    
    all_stations_daily_data = {}
    
    for st_id in station_ids:  # 恢复全部站点的处理
        logger.info(f"正在处理站点 {st_id} (聚合小时 -> 日)...")
        daily_df = load_and_aggregate_noaa_station(st_id, CONFIG['start_year'], CONFIG['end_year'])
        if daily_df is not None and not daily_df.empty:
            all_stations_daily_data[st_id] = daily_df
        else:
            logger.warning(f"站点 {st_id} 未能提取到有效数据。")
            
    logger.info(f"成功提取并聚合了 {len(all_stations_daily_data)} 个站点的日数据。")
    return all_stations_daily_data

# ==========================================
# 4. Open-Meteo 网格数据处理模块 (步骤 2)
# ==========================================

def fetch_and_aggregate_grid_data():
    """
    从 PostgreSQL 数据库中提取 Open-Meteo 网格数据，
    并直接利用 SQL 的 GROUP BY DATE() 在数据库层面完成日数据聚合。
    这样可以极大减少数据传输量和内存消耗。
    
    返回: Dict[Tuple[float, float], pd.DataFrame]
          键是 (latitude, longitude) 元组，值是聚合后的日数据 DataFrame
    """
    logger.info("正在连接数据库执行网格数据日聚合查询 (这可能需要几分钟)...")
    
    # 构建聚合 SQL 查询
    # 注意：我们这里直接聚合我们需要的 5 个变量：温、降水、风速、相对湿度、短波辐射
    query = """
        SELECT 
            latitude,
            longitude,
            DATE(timestamp) as date,
            AVG(temperature) as temperature,
            SUM(precipitation) as precipitation,
            AVG(wind_speed_10m) as wind_speed,
            AVG(relative_humidity_2m) as relative_humidity,
            SUM(shortwave_radiation) as shortwave_radiation
        FROM grid_weather_data
        GROUP BY latitude, longitude, DATE(timestamp)
        ORDER BY latitude, longitude, date;
    """
    
    try:
        conn = get_db_connection()
        # 使用 pandas 直接执行 SQL 并读取结果
        # 因为聚合后数据量会从 1.7 亿条缩减到 611 * 12410 ≈ 750 万条，pandas 完全可以装下
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        logger.info(f"成功从数据库读取并聚合了 {len(df)} 条网格日数据。")
        
        # 将日期列转换为 datetime 类型
        df['date'] = pd.to_datetime(df['date'])
        
        # 将大 DataFrame 拆分成以 (lat, lon) 为键的字典，方便后续按点查询
        grid_daily_dict = {}
        grouped = df.groupby(['latitude', 'longitude'])
        
        for name, group in grouped:
            # name 是 (latitude, longitude) 元组
            # 存入字典，并去掉经纬度列以节省内存
            grid_daily_dict[name] = group.drop(columns=['latitude', 'longitude']).reset_index(drop=True)
            
        logger.info(f"成功将网格数据拆分为 {len(grid_daily_dict)} 个网格点的字典。")
        return grid_daily_dict
        
    except Exception as e:
        logger.error(f"提取网格数据失败: {e}")
        return None

# ==========================================
# 5. 分位数映射 (QM) 模型模块 (步骤 3)
# ==========================================

class QuantileMappingModel:
    """
    单个气象变量的经验分位数映射 (Empirical Quantile Mapping) 模型。
    通过构建观测值(obs)和模拟值(sim)的经验累积分布函数(eCDF)来进行偏差校正。
    """
    def __init__(self, quantiles=100):
        self.quantiles = quantiles
        self.sim_q = None
        self.obs_q = None
        self.is_fitted = False

    def fit(self, sim_data, obs_data):
        """训练模型：计算并保存模拟数据和观测数据的分位数"""
        # 清理 NaN 值 (传入的可能是 numpy array)
        sim_clean = sim_data[~np.isnan(sim_data)]
        obs_clean = obs_data[~np.isnan(obs_data)]
        
        if len(sim_clean) < 10 or len(obs_clean) < 10:
            return False # 数据太少，无法拟合
            
        # 生成分位数概率点 (例如 0.01, 0.02 ... 0.99, 1.0)
        q_probs = np.linspace(0, 1, self.quantiles)
        
        # 计算这些概率点对应的数据值
        self.sim_q = np.quantile(sim_clean, q_probs)
        self.obs_q = np.quantile(obs_clean, q_probs)
        
        self.is_fitted = True
        return True

    def transform(self, sim_data_new):
        """应用模型：将新的模拟数据校正到观测数据的分布上"""
        if not self.is_fitted:
            raise ValueError("模型尚未拟合，请先调用 fit()")
            
        # 使用线性插值，将新的模拟数据映射到观测分布上
        # np.interp(要校正的值, 模拟数据的分位数值, 观测数据的分位数值)
        corrected_data = np.interp(sim_data_new, self.sim_q, self.obs_q)
        return corrected_data

def train_qm_models_for_all_stations(noaa_daily_dict, grid_daily_dict):
    """
    基于 station_grid_mapping.csv 中的一一映射关系，
    为 69 个站点分别训练 4 个变量（温、降水、风、湿）的 QM 模型。
    
    返回: Dict[station_id, Dict[variable, QuantileMappingModel]]
    """
    logger.info("开始为 69 个站点训练 QM 模型...")
    mapping_df = pd.read_csv(CONFIG['mapping_file'])
    
    # 需要进行 QM 校正的变量列表
    variables_to_correct = ['temperature', 'precipitation', 'wind_speed', 'relative_humidity']
    
    qm_models = {}
    successful_stations = 0
    
    for _, row in mapping_df.iterrows():
        st_id = row['station_id']
        grid_lat = row['grid_lat']
        grid_lon = row['grid_lon']
        grid_key = (grid_lat, grid_lon)
        
        # 1. 检查该站点是否有 NOAA 观测数据
        if st_id not in noaa_daily_dict:
            logger.warning(f"站点 {st_id} 缺失 NOAA 日数据，跳过模型训练。")
            continue
            
        # 2. 检查该站点映射的网格点是否存在于提取的网格字典中
        # 由于浮点数精度问题，我们可能需要用一个很小的容差来匹配键
        # 这里为了稳妥，我们在 grid_daily_dict 中寻找最接近的键
        matched_grid_key = None
        for k in grid_daily_dict.keys():
            if abs(k[0] - grid_lat) < 1e-4 and abs(k[1] - grid_lon) < 1e-4:
                matched_grid_key = k
                break
                
        if matched_grid_key is None:
            logger.warning(f"站点 {st_id} 映射的网格点 {grid_key} 在网格数据中未找到，跳过。")
            continue
            
        # 获取两边的数据表
        obs_df = noaa_daily_dict[st_id]
        sim_df = grid_daily_dict[matched_grid_key]
        
        # 3. 对齐时间轴 (Inner Join)
        # QM 要求在同一段历史时期内计算分布，所以我们将它们按日期合并
        merged_df = pd.merge(
            obs_df, sim_df, 
            on='date', 
            how='inner', 
            suffixes=('_obs', '_sim')
        )
        
        if len(merged_df) < 365: # 如果重叠的有效天数少于一年，放弃拟合
            logger.warning(f"站点 {st_id} 的重叠有效数据太少 ({len(merged_df)} 天)，跳过。")
            continue
            
        # 4. 为这 4 个变量分别训练 QM 模型
        station_models = {}
        for var in variables_to_correct:
            model = QuantileMappingModel(quantiles=100)
            obs_col = f"{var}_obs"
            sim_col = f"{var}_sim"
            
            # 执行 Fit
            success = model.fit(merged_df[sim_col].values, merged_df[obs_col].values)
            if success:
                station_models[var] = model
                
        # 只有当 4 个变量都训练成功时，才保存这个站点的模型集合
        if len(station_models) == 4:
            qm_models[st_id] = station_models
            successful_stations += 1
            
    logger.info(f"QM 模型训练完成！成功训练了 {successful_stations} 个站点的校正模型。")
    return qm_models

# ==========================================
# 6. KDTree 空间插值模块 (步骤 4)
# ==========================================

def create_target_grid(grid_daily_dict):
    """
    根据配置的经纬度范围和 0.1 度分辨率，生成最终的高清网格坐标点。
    新增掩码逻辑：读取 data/external/ncp_boundary.geojson 进行严谨的空间过滤。
    """
    lats = np.arange(CONFIG['lat_range'][0], CONFIG['lat_range'][1] + 0.05, CONFIG['target_resolution'])
    lons = np.arange(CONFIG['lon_range'][0], CONFIG['lon_range'][1] + 0.05, CONFIG['target_resolution'])
    
    # 构造原始矩形网格点
    raw_points = [(lat, lon) for lat in lats for lon in lons]
    logger.info(f"生成了 {len(raw_points)} 个初始矩形高清网格点。")
    
    try:
        # 读取华北平原真实 GeoJSON 边界
        boundary_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "external", "ncp_boundary.geojson")
        ncp_boundary = gpd.read_file(boundary_path)
        
        # 将原始点转换为 GeoDataFrame
        geometry = [Point(lon, lat) for lat, lon in raw_points]
        points_gdf = gpd.GeoDataFrame(geometry=geometry, crs="EPSG:4326")
        
        # 执行空间连接 (只保留在边界内的点)
        # sjoin 的 inner 模式会自动过滤掉落在多边形外部的点
        filtered_points = gpd.sjoin(points_gdf, ncp_boundary, how="inner", predicate="intersects")
        
        target_points = [(row.geometry.y, row.geometry.x) for idx, row in filtered_points.iterrows()]
        
        logger.info(f"经过 GeoJSON 官方掩码裁剪，剩余 {len(target_points)} 个符合华北平原轮廓的高清点。")
        return target_points
        
    except Exception as e:
        logger.error(f"加载 GeoJSON 掩码失败 ({e})，回退到矩形网格。")
        return raw_points

# ==========================================
# 6. KDTree 空间插值与 ET0 计算 (向量化版)
# ==========================================

def create_target_grid(grid_daily_dict):
    """
    根据配置的经纬度范围和 0.1 度分辨率，生成最终的高清网格坐标点。
    新增掩码逻辑：读取 data/external/ncp_boundary.geojson 进行严谨的空间过滤。
    """
    lats = np.arange(CONFIG['lat_range'][0], CONFIG['lat_range'][1] + 0.05, CONFIG['target_resolution'])
    lons = np.arange(CONFIG['lon_range'][0], CONFIG['lon_range'][1] + 0.05, CONFIG['target_resolution'])
    
    # 构造原始矩形网格点
    raw_points = [(lat, lon) for lat in lats for lon in lons]
    logger.info(f"生成了 {len(raw_points)} 个初始矩形高清网格点。")
    
    try:
        # 读取华北平原真实 GeoJSON 边界
        boundary_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "external", "ncp_boundary.geojson")
        ncp_boundary = gpd.read_file(boundary_path)
        
        # 将原始点转换为 GeoDataFrame
        geometry = [Point(lon, lat) for lat, lon in raw_points]
        points_gdf = gpd.GeoDataFrame(geometry=geometry, crs="EPSG:4326")
        
        # 执行空间连接 (只保留在边界内的点)
        # sjoin 的 inner 模式会自动过滤掉落在多边形外部的点
        filtered_points = gpd.sjoin(points_gdf, ncp_boundary, how="inner", predicate="intersects")
        
        target_points = [(row.geometry.y, row.geometry.x) for idx, row in filtered_points.iterrows()]
        
        logger.info(f"经过 GeoJSON 官方掩码裁剪，剩余 {len(target_points)} 个符合华北平原轮廓的高清点。")
        return target_points
        
    except Exception as e:
        logger.error(f"加载 GeoJSON 掩码失败 ({e})，回退到矩形网格。")
        return raw_points

def vectorized_calculate_et0_fao56(lat_array, temp, rh, wind, rad, elevation=50):
    """
    基于 FAO-56 PM 公式的全矩阵向量化计算版本，极大提升处理速度。
    接收的参数全是 1D Numpy Array，返回也是 1D Numpy Array。
    """
    # 1. 辐射转换 (处理异常极大值)
    Rs = np.where(rad > 1000, rad / 1000.0, rad * 0.0864)
    # 2. 风速高度校正 10m -> 2m
    u2 = wind * (4.87 / np.log(67.8 * 10 - 5.42))
    # 3. 大气压
    P = 101.3 * ((293 - 0.0065 * elevation) / 293) ** 5.26
    gamma = 0.000665 * P
    # 4. 水汽压
    es = 0.6108 * np.exp(17.27 * temp / (temp + 237.3))
    ea = es * (rh / 100.0)
    delta = 4098 * es / ((temp + 237.3) ** 2)
    # 5. 净辐射 (简化)
    Rn = 0.77 * Rs
    G = 0
    # 6. PM 核心公式
    num = 0.408 * delta * (Rn - G) + gamma * (900 / (temp + 273)) * u2 * (es - ea)
    den = delta + gamma * (1 + 0.34 * u2)
    et0 = num / den
    # 保证非负
    return np.maximum(0.0, et0)

def create_high_res_table():
    """初始化目标数据库表，加入 UNIQUE 约束以支持断点续传"""
    logger.info("检查并创建目标数据库表 high_res_daily_weather_et0 ...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 检查表是否存在，如果不存在则创建
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'high_res_daily_weather_et0'
        );
    """)
    exists = cur.fetchone()[0]
    
    if not exists:
        logger.info("表不存在，正在创建新表...")
        cur.execute("""
            CREATE TABLE high_res_daily_weather_et0 (
                id SERIAL PRIMARY KEY,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                date DATE NOT NULL,
                temperature DOUBLE PRECISION,
                precipitation DOUBLE PRECISION,
                wind_speed DOUBLE PRECISION,
                relative_humidity DOUBLE PRECISION,
                shortwave_radiation DOUBLE PRECISION,
                et0 DOUBLE PRECISION,
                CONSTRAINT unique_lat_lon_date UNIQUE (latitude, longitude, date)
            );
        """)
    else:
        # 尝试添加约束（如果约束已存在会报错，我们在外部捕获或忽略）
        logger.info("表已存在，检查并确保存在唯一约束...")
        try:
            cur.execute("""
                ALTER TABLE high_res_daily_weather_et0 
                ADD CONSTRAINT unique_lat_lon_date UNIQUE (latitude, longitude, date);
            """)
            logger.info("已成功添加 unique_lat_lon_date 约束。")
        except psycopg2.errors.DuplicateTable:
            # 约束已存在
            logger.info("唯一约束 unique_lat_lon_date 已存在。")
            conn.rollback() # 需要回滚以继续执行
        except Exception as e:
            logger.warning(f"添加约束时出现意外 (可能已存在): {e}")
            conn.rollback()
            
    conn.commit()
    cur.close()
    conn.close()

def get_last_processed_date():
    """查询数据库中已存在的最大日期，用于断点续传"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT MAX(date) FROM high_res_daily_weather_et0;")
    result = cur.fetchone()[0]
    cur.close()
    conn.close()
    return result

def run_vectorized_pipeline(qm_models_dict, grid_daily_dict, mapping_df, test_mode=True):
    """
    全内存 NumPy 向量化的高清网格生成流水线 (带断点续传与按年分块防爆内存)：
    1. 检查断点续传日期。
    2. 构建 KDTree 空间索引。
    3. 外层循环：按年份分块 (Chunking) 处理。
    4. 内层循环：预先对当前年份所有站点的天数执行 QM 校正，然后按天极速插值与 ET0 计算。
    5. 批量入库，忽略重复数据 (ON CONFLICT DO NOTHING)。
    """
    logger.info("=== 启动向量化空间插值与 ET0 计算引擎 (支持断点续传与分块) ===")
    
    # 初始化表
    create_high_res_table()
    last_date = get_last_processed_date()
    
    if last_date:
        logger.info(f"检测到历史处理记录，将从 {last_date} 之后开始断点续传！")
    else:
        logger.info("未检测到历史记录，将从头开始全新处理。")
    
    available_stations = list(qm_models_dict.keys())
    
    # 1. 提取所有站点的经纬度和网格映射键
    station_coords = []
    matched_grid_keys = []
    
    for st_id in available_stations:
        row = mapping_df[mapping_df['station_id'] == st_id].iloc[0]
        station_coords.append([row['station_lat'], row['station_lon']])
        g_lat, g_lon = row['grid_lat'], row['grid_lon']
        
        # 寻找匹配的 grid key
        matched_key = None
        for k in grid_daily_dict.keys():
            if abs(k[0] - g_lat) < 1e-4 and abs(k[1] - g_lon) < 1e-4:
                matched_key = k
                break
        matched_grid_keys.append(matched_key)
        
    station_coords = np.array(station_coords)
    
    # 2. 统一时间轴并支持断点续传过滤
    sample_df = grid_daily_dict[matched_grid_keys[0]]
    all_dates = sample_df['date'].sort_values().values
    
    # 【断点续传逻辑】过滤掉已经处理过的日期
    if last_date:
        resume_mask = all_dates > np.datetime64(last_date)
        all_dates = all_dates[resume_mask]
        
    if test_mode:
        logger.info("【迷你测试模式】仅处理前 60 天的数据以验证分块逻辑。")
        all_dates = all_dates[:60]
        
    if len(all_dates) == 0:
        logger.info("所有数据均已处理完毕，无需再次运行！")
        return
        
    # 将日期按年份分组 (Chunking 核心逻辑)
    dates_series = pd.Series(all_dates)
    years = dates_series.dt.year.unique()
    num_stations = len(available_stations)
    
    # 3. 构建 KDTree 空间索引并预计算所有目标点的插值权重 (空间关系是不随时间改变的)
    logger.info("构建 KDTree 空间索引并预计算所有目标点的插值权重...")
    tree = cKDTree(station_coords)
    target_points = create_target_grid(grid_daily_dict)
    
    target_coords = np.array(target_points)
    target_lats = target_coords[:, 0]
    target_lons = target_coords[:, 1]
    
    distances, indices = tree.query(target_coords, k=4)
    # 计算 IDW 权重
    distances = np.maximum(distances, 1e-10)
    weights = 1.0 / (distances ** 2)
    weights_sum = np.sum(weights, axis=1, keepdims=True)
    normalized_weights = weights / weights_sum  # shape: (N, 4)
    # 扩展维度以支持 NumPy 广播乘法
    normalized_weights = normalized_weights[:, :, np.newaxis] # shape: (N, 4, 1)
    
    # 准备数据库连接
    conn = get_db_connection()
    cur = conn.cursor()
    # 使用 ON CONFLICT DO NOTHING 忽略重复主键
    insert_query = """
        INSERT INTO high_res_daily_weather_et0 
        (latitude, longitude, date, temperature, precipitation, wind_speed, relative_humidity, shortwave_radiation, et0)
        VALUES %s
        ON CONFLICT (latitude, longitude, date) DO NOTHING
    """
    
    total_inserted = 0
    start_time = time.time()
    
    # 4. 外层循环：按年份分块处理
    for year in years:
        year_dates = dates_series[dates_series.dt.year == year].values
        num_days_in_year = len(year_dates)
        logger.info(f"--- 开始处理 {year} 年数据 (共 {num_days_in_year} 天) ---")
        
        # 预先构建该年的数据矩阵 [num_days_in_year, num_stations, 5]
        station_data_matrix = np.zeros((num_days_in_year, num_stations, 5), dtype=np.float32)
        
        for s_idx, (st_id, g_key) in enumerate(zip(available_stations, matched_grid_keys)):
            if g_key is None:
                continue
                
            sim_df = grid_daily_dict[g_key]
            # 提取该年份的数据
            year_mask = (sim_df['date'] >= year_dates[0]) & (sim_df['date'] <= year_dates[-1])
            year_df = sim_df[year_mask].sort_values('date')
            
            raw_temp = year_df['temperature'].values
            raw_precip = year_df['precipitation'].values
            raw_wind = year_df['wind_speed'].values
            raw_rh = year_df['relative_humidity'].values
            raw_rad = year_df['shortwave_radiation'].values
            
            # QM 校正
            if len(raw_temp) > 0:
                station_data_matrix[:, s_idx, 0] = qm_models_dict[st_id]['temperature'].transform(raw_temp)
                station_data_matrix[:, s_idx, 1] = qm_models_dict[st_id]['precipitation'].transform(raw_precip)
                station_data_matrix[:, s_idx, 2] = qm_models_dict[st_id]['wind_speed'].transform(raw_wind)
                station_data_matrix[:, s_idx, 3] = qm_models_dict[st_id]['relative_humidity'].transform(raw_rh)
                station_data_matrix[:, s_idx, 4] = raw_rad
                
        # 5. 内层循环：按天执行极速插值与入库
        buffer = []
        batch_size = 50000 
        
        try:
            for d_idx, date_val in enumerate(year_dates):
                current_date = pd.Timestamp(date_val).date()
                
                day_station_data = station_data_matrix[d_idx]
                neighbors_vals = day_station_data[indices]
                
                interpolated = np.sum(neighbors_vals * normalized_weights, axis=1)
                
                temp = interpolated[:, 0]
                precip = np.maximum(0, interpolated[:, 1])
                wind = np.maximum(0, interpolated[:, 2])
                rh = np.clip(interpolated[:, 3], 0, 100)
                rad = np.maximum(0, interpolated[:, 4])
                
                et0 = vectorized_calculate_et0_fao56(target_lats, temp, rh, wind, rad)
                
                for i in range(len(target_points)):
                    buffer.append((
                        float(target_lats[i]), float(target_lons[i]), current_date,
                        float(temp[i]), float(precip[i]), float(wind[i]), float(rh[i]), float(rad[i]), float(et0[i])
                    ))
                    
                if len(buffer) >= batch_size:
                    psycopg2.extras.execute_values(cur, insert_query, buffer, page_size=10000)
                    conn.commit()
                    total_inserted += len(buffer)
                    buffer = []
                    logger.info(f"    - {year}年: 已处理并入库 {total_inserted} 条数据...")
                    
            # 年末清空尾部 buffer
            if buffer:
                psycopg2.extras.execute_values(cur, insert_query, buffer, page_size=10000)
                conn.commit()
                total_inserted += len(buffer)
                
            logger.info(f"{year} 年数据处理完成！累计已入库: {total_inserted} 条。")
            
        except Exception as e:
            logger.error(f"处理 {year} 年数据时发生崩溃错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            break
            
    cur.close()
    conn.close()
    
    total_time = time.time() - start_time
    logger.info(f"【全部跑批成功！】共插入/更新了 {total_inserted} 条记录，总耗时 {total_time:.2f} 秒。")

# ==========================================
# 主执行入口 (骨架)
# ==========================================

def main():
    logger.info("=== 开始执行 QM 校正与 ET0 空间插值全流程 ===")
    
    # 步骤 1: 读取并聚合 NOAA 站点数据 (小时 -> 日)
    logger.info("--- 步骤 1: 聚合 NOAA 站点日数据 ---")
    noaa_daily_dict = process_all_noaa_stations()
    if not noaa_daily_dict:
        logger.error("未成功提取到任何 NOAA 站点数据，流程终止。")
        return
        
    # [测试代码] 打印出字典的结构，验证是否正常运行
    first_station_id = list(noaa_daily_dict.keys())[0]
    sample_df = noaa_daily_dict[first_station_id]
    logger.info(f"\n【测试输出】字典的 Keys (前 5 个): {list(noaa_daily_dict.keys())[:5]}")
    logger.info(f"【测试输出】站点 {first_station_id} 的 DataFrame 形状: {sample_df.shape}")
    logger.info(f"【测试输出】站点 {first_station_id} 的前 3 行数据:\n{sample_df.head(3).to_string()}")
    
    # 步骤 2: 从数据库读取并聚合 Open-Meteo 网格数据 (小时 -> 日)
    logger.info("--- 步骤 2: 提取并聚合 Open-Meteo 网格日数据 ---")
    grid_daily_dict = fetch_and_aggregate_grid_data()
    if not grid_daily_dict:
        logger.error("未成功提取到网格数据，流程终止。")
        return
        
    # [测试代码] 打印网格数据字典结构
    first_grid_point = list(grid_daily_dict.keys())[0]
    sample_grid_df = grid_daily_dict[first_grid_point]
    logger.info(f"\n【测试输出】网格字典的 Keys (前 5 个坐标): {list(grid_daily_dict.keys())[:5]}")
    logger.info(f"【测试输出】网格点 {first_grid_point} 的 DataFrame 形状: {sample_grid_df.shape}")
    logger.info(f"【测试输出】网格点 {first_grid_point} 的前 3 行数据:\n{sample_grid_df.head(3).to_string()}")
    
    # 步骤 3: 基于 69 个站点的一一映射，训练 QM 模型
    logger.info("--- 步骤 3: 训练 69 个站点的 QM 模型 ---")
    qm_models_dict = train_qm_models_for_all_stations(noaa_daily_dict, grid_daily_dict)
    if not qm_models_dict:
        logger.error("未能训练出任何 QM 模型，流程终止。")
        return
        
    # [测试代码] 打印出模型的结构和测试转换效果
    first_model_st_id = list(qm_models_dict.keys())[0]
    temp_model = qm_models_dict[first_model_st_id]['temperature']
    logger.info(f"\n【测试输出】成功训练了 {len(qm_models_dict)} 个站点的模型集合。")
    logger.info(f"【测试输出】站点 {first_model_st_id} 的温度 QM 模型状态: is_fitted={temp_model.is_fitted}")
    
    # 模拟一个 20℃ 的网格温度，看看它会被校正成多少度
    test_sim_temp = np.array([20.0, -5.0, 35.0])
    corrected_temp = temp_model.transform(test_sim_temp)
    logger.info(f"【测试输出】温度校正测试 (网格原始值 -> 校正后观测值):")
    for orig, corr in zip(test_sim_temp, corrected_temp):
        logger.info(f"    {orig} ℃  ->  {corr:.2f} ℃")
        
    # 测试完毕后暂时退出，不往下执行
    # return
    
    # 步骤 4 & 5: 执行 NumPy 向量化插值、ET0 计算与数据库写入
    logger.info("--- 步骤 4 & 5: 向量化处理与批量入库 ---")
    mapping_df = pd.read_csv(CONFIG['mapping_file'])
    
    # 正式全量启动 (关闭 test_mode)
    run_vectorized_pipeline(qm_models_dict, grid_daily_dict, mapping_df, test_mode=False)
    
    logger.info("=== 全流程跑批圆满结束！ ===")

if __name__ == "__main__":
    main()
