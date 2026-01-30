import pandas as pd
import numpy as np

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
    为每个 NOAA 站点寻找最近的 Open-Meteo 网格点。
    """
    print("生成华北平原网格点...")
    # 模拟 batch_fetch_weather.py 中的网格生成逻辑
    lat_min, lat_max = 32.0, 42.0
    lon_min, lon_max = 110.0, 123.0
    res = 0.25
    
    lats = np.arange(lat_min, lat_max + res, res)
    lons = np.arange(lon_min, lon_max + res, res)
    
    grid_points = []
    for lat in lats:
        for lon in lons:
            grid_points.append({'latitude': lat, 'longitude': lon})
    
    grid_df = pd.DataFrame(grid_points)
    
    mapping = []
    
    for _, station in stations_df.iterrows():
        s_lat = station['LAT']
        s_lon = station['LON']
        
        # 计算欧氏距离 (近似)
        dist = np.sqrt((grid_df['latitude'] - s_lat)**2 + (grid_df['longitude'] - s_lon)**2)
        nearest_idx = dist.idxmin()
        nearest_grid = grid_df.iloc[nearest_idx]
        
        mapping.append({
            'station_id': f"{station['USAF']}-{station['WBAN']}",
            'station_name': station['STATION NAME'],
            'station_lat': s_lat,
            'station_lon': s_lon,
            'grid_lat': nearest_grid['latitude'],
            'grid_lon': nearest_grid['longitude'],
            'distance_deg': dist.min()
        })
    
    mapping_df = pd.DataFrame(mapping)
    output_path = "station_grid_mapping.csv"
    mapping_df.to_csv(output_path, index=False)
    print(f"网格映射关系已保存至: {output_path}")

if __name__ == "__main__":
    stations = filter_ncp_noaa_stations("isd-history.csv")
    if not stations.empty:
        map_stations_to_grid(stations)
