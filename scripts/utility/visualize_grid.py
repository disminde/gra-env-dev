import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import psycopg2
import os
from dotenv import load_dotenv
import geopandas as gpd
from shapely.geometry import Point

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号

def get_db_connection():
    load_dotenv()
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        dbname=os.getenv('POSTGRES_DB', 'gra_env_db'),
        user=os.getenv('POSTGRES_USER', 'admin'),
        password=os.getenv('POSTGRES_PASSWORD', 'secure_password_dev')
    )

def visualize_grids():
    print("正在从数据库提取原始 611 个网格点...")
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT DISTINCT latitude, longitude FROM grid_weather_data", conn)
    conn.close()
    
    # 原始 611 个点
    orig_lons = df['longitude'].values
    orig_lats = df['latitude'].values
    
    # 生成 0.1 度矩形网格
    lat_range = (32.0, 42.0)
    lon_range = (110.0, 123.0)
    res = 0.1
    lats = np.arange(lat_range[0], lat_range[1] + 0.05, res)
    lons = np.arange(lon_range[0], lon_range[1] + 0.05, res)
    
    raw_lons, raw_lats = np.meshgrid(lons, lats)
    raw_points_lons = raw_lons.flatten()
    raw_points_lats = raw_lats.flatten()
    print(f"生成的初始矩形高清点数量: {len(raw_points_lons)}")
    
    # 使用 GeoPandas 进行 GeoJSON 掩码过滤
    boundary_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "external", "ncp_boundary.geojson")
    ncp_boundary = gpd.read_file(boundary_path)
    
    geometry = [Point(lon, lat) for lon, lat in zip(raw_points_lons, raw_points_lats)]
    points_gdf = gpd.GeoDataFrame(geometry=geometry, crs="EPSG:4326")
    
    # 执行空间连接
    filtered_points = gpd.sjoin(points_gdf, ncp_boundary, how="inner", predicate="intersects")
    
    # 提取保留下来的点的坐标
    target_lons = [row.geometry.x for idx, row in filtered_points.iterrows()]
    target_lats = [row.geometry.y for idx, row in filtered_points.iterrows()]
    
    # 为了绘图，找出被剔除的点 (这里用简单的集合差集来找)
    target_set = set(zip(target_lons, target_lats))
    out_lons, out_lats = [], []
    for lon, lat in zip(raw_points_lons, raw_points_lats):
        if (lon, lat) not in target_set:
            out_lons.append(lon)
            out_lats.append(lat)
            
    print(f"经过 GeoJSON 官方掩码裁剪，保留点数量: {len(target_lons)}，剔除点数量: {len(out_lons)}")
    
    # 开始绘图
    fig, ax = plt.subplots(figsize=(14, 12))
    
    # 1. 绘制省份边界底图 (浅色背景)
    ncp_boundary.plot(ax=ax, facecolor='lightgreen', edgecolor='black', alpha=0.3, linewidth=1.5, label='华北平原 6 省边界')
    
    # 2. 绘制被剔除的矩形边缘点 (红色，半透明)
    ax.scatter(out_lons, out_lats, c='red', s=5, alpha=0.3, label='被 GeoJSON 剔除的无效网格点')
    
    # 3. 绘制保留下来的高清点 (浅蓝色，小点)
    ax.scatter(target_lons, target_lats, c='dodgerblue', s=3, alpha=0.7, label='GeoJSON 掩码后的高清点')
    
    # 4. 绘制原始的 611 个点 (黑色，大点)
    ax.scatter(orig_lons, orig_lats, c='black', s=15, marker='x', label='原始 Open-Meteo 网格点 (611)')
    
    ax.set_xlabel('经度 (Longitude)', fontsize=14)
    ax.set_ylabel('纬度 (Latitude)', fontsize=14)
    ax.grid(True, linestyle='--', alpha=0.7)
    
    # 设置显示范围稍微比矩形大一点
    ax.set_xlim(108, 125)
    ax.set_ylim(30, 44)
    
    plt.title('基于官方 GeoJSON 边界的华北平原高清网格裁剪', fontsize=16)
    plt.legend(loc='lower right', fontsize=12)
    
    save_path = "grid_mask_geojson_visualization.png"
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"\n基于 GeoJSON 的最新可视化图片已保存至: {os.path.abspath(save_path)}")

if __name__ == "__main__":
    visualize_grids()
