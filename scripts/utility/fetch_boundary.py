import os
import json
import requests
import geopandas as gpd
import pandas as pd
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

# API URLs provided by user
API_URLS = {
    "Hebei": "https://geo.datav.aliyun.com/areas_v3/bound/130000_full.json",
    "Shandong": "https://geo.datav.aliyun.com/areas_v3/bound/370000_full.json",
    "Henan": "https://geo.datav.aliyun.com/areas_v3/bound/410000_full.json",
    "Shanxi": "https://geo.datav.aliyun.com/areas_v3/bound/140000_full.json",
    "Jiangsu": "https://geo.datav.aliyun.com/areas_v3/bound/320000_full.json",
    "Anhui": "https://geo.datav.aliyun.com/areas_v3/bound/340000_full.json"
}

def fetch_and_merge_boundaries():
    print("开始从阿里云 DataV 下载省份边界数据...")
    
    geometries = []
    
    for province, url in API_URLS.items():
        print(f"正在下载 {province} 的边界数据...")
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # 提取特征中的几何对象
            for feature in data.get('features', []):
                geom = shape(feature['geometry'])
                geometries.append(geom)
        except Exception as e:
            print(f"下载 {province} 数据失败: {e}")
            
    if not geometries:
        print("未能下载到任何有效数据！")
        return
        
    print(f"共提取到 {len(geometries)} 个几何多边形，正在进行合并 (Union)...")
    
    # 合并所有省份的多边形，形成一个完整的大多边形
    merged_polygon = unary_union(geometries)
    
    # 转换为 GeoDataFrame
    gdf = gpd.GeoDataFrame(geometry=[merged_polygon], crs="EPSG:4326")
    
    # 保存目录
    save_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "external")
    os.makedirs(save_dir, exist_ok=True)
    
    save_path = os.path.join(save_dir, "ncp_boundary.geojson")
    
    # 保存为 GeoJSON
    gdf.to_file(save_path, driver="GeoJSON")
    print(f"合并成功！边界文件已保存至: {os.path.abspath(save_path)}")

if __name__ == "__main__":
    fetch_and_merge_boundaries()