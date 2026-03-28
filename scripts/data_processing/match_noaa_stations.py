import pandas as pd
import numpy as np
import psycopg2
import os
import warnings
from dotenv import load_dotenv

# 忽略 pandas 关于 sqlalchemy 的警告，因为我们只是简单的读操作
warnings.filterwarnings('ignore', category=UserWarning)

def get_db_connection():
    load_dotenv()
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        dbname=os.getenv('POSTGRES_DB', 'gra_env_db'),
        user=os.getenv('POSTGRES_USER', 'admin'),
        password=os.getenv('POSTGRES_PASSWORD', 'secure_password_dev')
    )

def filter_ncp_noaa_stations(csv_path):
    """
    从 NOAA 历史站点列表中筛选出华北平原 (NCP) 范围内的站点。
    NCP 范围定义: 32°N-42°N, 110°E-123°E
    """
    print(f"读取站点列表: {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # 清洗列名 (去掉引号)
    df.columns = [c.replace('"', '') for c in df.columns]
    
    # 筛选 NCP 范围
    ncp_mask = (
        (df['LAT'] >= 32.0) & (df['LAT'] <= 42.0) &
        (df['LON'] >= 110.0) & (df['LON'] <= 123.0)
    )
    ncp_stations = df[ncp_mask].copy()
    
    # 进一步筛选: 必须有 1990-2023 期间的数据 (BEGIN < 1991, END > 2022)
    # 注意: CSV 中的 BEGIN/END 通常是 YYYYMMDD
    ncp_stations['BEGIN'] = ncp_stations['BEGIN'].astype(str)
    ncp_stations['END'] = ncp_stations['END'].astype(str)
    
    time_mask = (
        (ncp_stations['BEGIN'].str[:4].astype(int) <= 1991) &
        (ncp_stations['END'].str[:4].astype(int) >= 2022)
    )
    final_stations = ncp_stations[time_mask].copy()
    
    # 格式化输出
    output_cols = ['USAF', 'WBAN', 'STATION NAME', 'CTRY', 'LAT', 'LON', 'ELEV(M)', 'BEGIN', 'END']
    final_stations = final_stations[output_cols]
    
    print(f"筛选完成! 在华北平原范围内找到 {len(final_stations)} 个符合时间要求的 NOAA 站点。")
    
    output_path = "ncp_noaa_stations.csv"
    final_stations.to_csv(output_path, index=False)
    print(f"站点列表已保存至: {output_path}")
    
    return final_stations

def map_stations_to_grid(stations_df):
    """
    为每个 NOAA 站点寻找最近的真实 Open-Meteo 网格点。
    网格点从 PostgreSQL 数据库中真实提取。
    """
    print("从数据库中提取真实的华北平原网格点...")
    
    try:
        conn = get_db_connection()
        # 从数据库中提取唯一存在的网格点
        query = "SELECT DISTINCT latitude, longitude FROM grid_weather_data"
        grid_df = pd.read_sql(query, conn)
        conn.close()
        
        if grid_df.empty:
            print("错误: 从数据库中未能读取到任何网格点，请确保 grid_weather_data 表中有数据。")
            return
            
        print(f"成功从数据库提取了 {len(grid_df)} 个真实网格点。")
    except Exception as e:
        print(f"数据库连接或查询失败: {e}")
        return

    mapping = []
    
    # 将网格点的经纬度转换为 numpy 数组，加速距离计算
    grid_lats = grid_df['latitude'].values
    grid_lons = grid_df['longitude'].values
    
    for _, station in stations_df.iterrows():
        s_lat = station['LAT']
        s_lon = station['LON']
        
        # 计算欧氏距离 (近似)
        dist = np.sqrt((grid_lats - s_lat)**2 + (grid_lons - s_lon)**2)
        nearest_idx = np.argmin(dist)
        
        mapping.append({
            'station_id': f"{station['USAF']}-{station['WBAN']}",
            'station_name': station['STATION NAME'],
            'station_lat': s_lat,
            'station_lon': s_lon,
            'grid_lat': grid_lats[nearest_idx],
            'grid_lon': grid_lons[nearest_idx],
            'distance_deg': dist[nearest_idx]
        })
    
    mapping_df = pd.DataFrame(mapping)
    output_path = "station_grid_mapping.csv"
    mapping_df.to_csv(output_path, index=False)
    print(f"网格映射关系已保存至: {output_path}")

if __name__ == "__main__":
    stations = filter_ncp_noaa_stations("isd-history.csv")
    if not stations.empty:
        map_stations_to_grid(stations)
