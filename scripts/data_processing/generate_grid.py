import numpy as np
import pandas as pd
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def generate_ncp_grid(lat_min=32.0, lat_max=42.0, lon_min=110.0, lon_max=123.0, resolution=0.5):
    """
    生成华北平原网格，并优先包含 69 个核心站点。
    """
    # 1. 生成基础 0.5 度稀疏网格
    lats = np.arange(lat_min, lat_max + resolution, resolution)
    lons = np.arange(lon_min, lon_max + resolution, resolution)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    
    base_grid = pd.DataFrame({
        'latitude': lat_grid.flatten(),
        'longitude': lon_grid.flatten()
    })

    # 2. 读取并加入 69 个核心站点网格
    try:
        mapping_df = pd.read_csv("station_grid_mapping.csv")
        core_grids = mapping_df[['grid_lat', 'grid_lon']].rename(
            columns={'grid_lat': 'latitude', 'grid_lon': 'longitude'}
        )
        logging.info(f"成功读取 {len(core_grids)} 个核心校准点。")
    except Exception as e:
        logging.error(f"无法读取核心校准点文件: {e}")
        core_grids = pd.DataFrame(columns=['latitude', 'longitude'])

    # 3. 合并并去重
    # 我们把核心点排在最前面，确保它们先被抓取
    combined_grid = pd.concat([core_grids, base_grid], ignore_index=True)
    
    # 四舍五入避免浮点误差，然后去重
    combined_grid['latitude'] = combined_grid['latitude'].round(2)
    combined_grid['longitude'] = combined_grid['longitude'].round(2)
    
    # drop_duplicates 默认保留第一次出现的行，即保留了排在前面的核心点
    final_grid = combined_grid.drop_duplicates(subset=['latitude', 'longitude']).reset_index(drop=True)
    
    logging.info(f"生成网格完成：包含核心校准点后，总计 {len(final_grid)} 个有效网格点 (分辨率: {resolution}°)。")
    return final_grid

if __name__ == "__main__":
    grid = generate_ncp_grid()
    print(grid.head())
    print(f"Total points: {len(grid)}")
    # Optional: Save to CSV for inspection
    # grid.to_csv("ncp_grid_points.csv", index=False)
