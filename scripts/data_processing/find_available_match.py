
import os
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "gra_env_db"),
    "user": os.getenv("POSTGRES_USER", "admin"),
    "password": os.getenv("POSTGRES_PASSWORD", "secure_password_dev")
}

def find_available_matches():
    print("--- 扫描数据库中的 Open-Meteo 数据范围 ---")
    conn = psycopg2.connect(**DB_CONFIG)
    
    # 1. 获取数据库中已有的所有不重复网格点 (Lat, Lon)
    # 只需要查询最近几年的数据即可判断覆盖范围
    query = """
    SELECT DISTINCT latitude, longitude 
    FROM grid_weather_data 
    WHERE timestamp >= '2020-01-01'
    """
    df_om = pd.read_sql_query(query, conn)
    conn.close()
    
    if df_om.empty:
        print("数据库中暂无 2020 年以后的数据。")
        return

    print(f"数据库中已覆盖 {len(df_om)} 个网格点。")
    # print(df_om.head())

    # 2. 读取所有 NOAA 站点列表
    df_noaa = pd.read_csv("ncp_noaa_stations.csv")
    print(f"NOAA 目标站点共 {len(df_noaa)} 个。")

    # 3. 寻找匹配
    # 简单的距离匹配：对于每个 NOAA 站点，看是否有距离 < 0.15 度的 Open-Meteo 网格点
    
    matches = []
    
    for _, station in df_noaa.iterrows():
        s_lat = station['LAT']
        s_lon = station['LON']
        s_name = station['STATION NAME']
        s_id = f"{station['USAF']}-{station['WBAN']}"
        
        # 计算距离 (欧氏距离近似)
        # 筛选 lat/lon 差异都小于 0.2 的点进行精细计算
        candidates = df_om[
            (df_om['latitude'].between(s_lat - 0.2, s_lat + 0.2)) & 
            (df_om['longitude'].between(s_lon - 0.2, s_lon + 0.2))
        ]
        
        if not candidates.empty:
            # 找到最近的一个
            candidates['dist'] = ((candidates['latitude'] - s_lat)**2 + (candidates['longitude'] - s_lon)**2)**0.5
            nearest = candidates.loc[candidates['dist'].idxmin()]
            
            if nearest['dist'] < 0.2: # 阈值：约 20km
                matches.append({
                    "station_name": s_name,
                    "station_id": s_id,
                    "station_pos": f"({s_lat}, {s_lon})",
                    "grid_pos": f"({nearest['latitude']}, {nearest['longitude']})",
                    "dist": f"{nearest['dist']:.4f}"
                })

    print(f"\n--- 匹配结果: 找到 {len(matches)} 个可用配对 ---")
    if matches:
        print(f"{'Station Name':<20} | {'Station ID':<15} | {'Grid Point':<20} | {'Dist':<8}")
        print("-" * 70)
        for m in matches:
            print(f"{m['station_name']:<20} | {m['station_id']:<15} | {m['grid_pos']:<20} | {m['dist']:<8}")
            
        # 推荐
        best = matches[0]
        print(f"\n[推荐] 可立即用于验证的站点: {best['station_name']} (ID: {best['station_id']})")
        print(f"对应网格点: {best['grid_pos']}")
    else:
        print("当前已爬取的 Open-Meteo 网格点尚未覆盖任何 NOAA 站点。")
        print("建议继续等待爬虫运行，或手动优先爬取某个站点附近的网格。")

if __name__ == "__main__":
    find_available_matches()
