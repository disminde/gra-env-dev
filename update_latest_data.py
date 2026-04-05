import os
import pandas as pd
import numpy as np
import openmeteo_requests
import requests_cache
from retry_requests import retry
from datetime import datetime
from tqdm import tqdm
from scipy import stats

HISTORICAL_FEATURES_PATH = "data/processed/ml_feature_table.parquet"
OUTPUT_PATH = "latest_inference_features.parquet"
START_YEAR = 2024

def get_grid_points_and_buffer():
    """
    1. 从历史宽表中读取 2023 年的数据作为缓冲池（用于计算 Lag 和 Rolling）
    2. 提取需要抓取的唯一网格点 (latitude, longitude)
    """
    print(f"Loading historical data from {HISTORICAL_FEATURES_PATH}...")
    df_hist = pd.read_parquet(HISTORICAL_FEATURES_PATH)
    
    # 仅保留 2023 年的数据作为特征工程缓冲池
    df_buffer = df_hist[df_hist['year'] == 2023].copy()
    
    # 提取所有唯一的网格点
    grid_points = df_hist[['latitude', 'longitude']].drop_duplicates().reset_index(drop=True)
    print(f"Extracted {len(grid_points)} unique grid points. Buffer size: {len(df_buffer)} rows.")
    
    return grid_points, df_buffer

def fetch_daily_data(grid_points):
    """
    2. 从 Open-Meteo 拉取 2024 年至今的日级数据，并在线聚合为月级
    """
    
    def create_client():
        cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        return openmeteo_requests.Client(session=retry_session)

    openmeteo = create_client()
    url = "https://archive-api.open-meteo.com/v1/archive"
    
    start_date = f"{START_YEAR}-01-01"
    end_date = datetime.now().strftime("%Y-%m-%d")
    
    # 策略 A：化整为零，极度缩小单次请求的数据量
    # 从 50 降至 10，避免触发 Open-Meteo 隐藏的“数据量(Data Volume)乘数惩罚”
    chunk_size = 10
    monthly_records = []
    
    print(f"Fetching daily data from {start_date} to {end_date}...")
    
    for i in tqdm(range(0, len(grid_points), chunk_size), desc="Fetching Open-Meteo"):
        chunk = grid_points.iloc[i:i+chunk_size]
        lats = chunk['latitude'].tolist()
        lons = chunk['longitude'].tolist()
        
        params = {
            "latitude": lats,
            "longitude": lons,
            "start_date": start_date,
            "end_date": end_date,
            "daily": [
                "temperature_2m_mean", 
                "precipitation_sum", 
                "et0_fao_evapotranspiration",
                "wind_speed_10m_max", 
                "shortwave_radiation_sum",
                "relative_humidity_2m_mean"
            ],
            "timezone": "auto"
        }
        
        # 无限重试机制：只要没抓到，就一直换节点一直试，绝对不跳过任何数据
        success = False
        retry_count = 0
        
        while not success:
            try:
                responses = openmeteo.weather_api(url, params=params)
                
                for j, response in enumerate(responses):
                    lat = response.Latitude()
                    lon = response.Longitude()
                    daily = response.Daily()
                    
                    # 构造 Daily DataFrame
                    df_daily = pd.DataFrame({
                        "date": pd.date_range(
                            start=pd.to_datetime(daily.Time(), unit="s", utc=True),
                            end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
                            freq=pd.Timedelta(seconds=daily.Interval()),
                            inclusive="left"
                        ),
                        "temp": daily.Variables(0).ValuesAsNumpy(),
                        "precip": daily.Variables(1).ValuesAsNumpy(),
                        "et0": daily.Variables(2).ValuesAsNumpy(),
                        "wind": daily.Variables(3).ValuesAsNumpy(),
                        "rad": daily.Variables(4).ValuesAsNumpy(),
                        "rh": daily.Variables(5).ValuesAsNumpy()
                    })
                    
                    # 添加年月列
                    df_daily['year'] = df_daily['date'].dt.year
                    df_daily['month'] = df_daily['date'].dt.month
                    
                    # 日级到月级聚合 (Daily to Monthly Aggregation)
                    df_monthly = df_daily.groupby(['year', 'month']).agg({
                        'temp': 'mean',
                        'precip': 'sum',
                        'et0': 'sum',
                        'wind': 'mean',
                        'rad': 'sum',
                        'rh': 'mean'
                    }).reset_index()
                    
                    df_monthly['latitude'] = round(lat, 2)
                    df_monthly['longitude'] = round(lon, 2)
                    monthly_records.append(df_monthly)
                
                # 🚨 策略 A 配套休眠：我们每个 chunk 有 10 个点。
                # 按照每分钟 600 个点的配额，我们理论上每分钟可以请求 60 次。
                # 但为了安全，我们每次请求后休眠 1.5 秒（即每分钟 40 次，远低于安全线）
                import time
                time.sleep(1.5) 
                success = True # 标记为成功，跳出 while 循环
                    
            except Exception as e:
                error_msg = str(e)
                import time
                
                if "Minutely" in error_msg:
                    retry_count += 1
                    print(f"\n⏳ 触发每分钟限流 (Minutely limit)！系统休眠 65 秒后重试 (第 {retry_count} 次)...")
                    time.sleep(65)
                elif "Hourly" in error_msg:
                    retry_count += 1
                    print(f"\n⏳ 触发每小时限流 (Hourly limit)！Open-Meteo 免费版每小时最多 5000 个点。")
                    print(f"   系统将进行深度休眠 1 小时 (3600秒) 以恢复额度，请勿关闭程序...")
                    # 分段打印倒计时，让用户知道没有死机
                    for remaining in range(3600, 0, -600):
                        print(f"   ... 距离继续抓取还剩 {remaining//60} 分钟")
                        time.sleep(min(600, remaining))
                elif "Daily" in error_msg:
                    retry_count += 1
                    print(f"\n⏳ 触发每日限流 (Daily limit)！系统将休眠 24 小时...")
                    time.sleep(86400)
                else:
                    retry_count += 1
                    print(f"\n⚠️ 发生未知网络错误 ({e})。休眠 30 秒后重试 (第 {retry_count} 次)...")
                    time.sleep(30)
             
    if not monthly_records:
        raise ValueError("No data fetched from API.")
        
    df_new = pd.concat(monthly_records, ignore_index=True)
    
    # 字段重命名对齐历史表
    df_new = df_new.rename(columns={
        'temp': 'temp_mean',
        'precip': 'p_sum',
        'et0': 'et0_sum',
        'wind': 'wind_speed_mean',
        'rad': 'radiation_sum',
        'rh': 'humidity_mean'
    })
    
    # 计算 D 值
    df_new['d_value'] = df_new['p_sum'] - df_new['et0_sum']
    return df_new

def compute_features(df_buffer, df_new):
    """
    3. 拼接历史缓冲池，计算滞后特征、滚动统计量和 SPEI
    """
    print("Computing features and SPEI...")
    # 拼接数据，确保时间连续性
    df_combined = pd.concat([df_buffer, df_new], ignore_index=True)
    df_combined = df_combined.sort_values(by=['latitude', 'longitude', 'year', 'month']).reset_index(drop=True)
    
    # 1. 计算不同时间尺度的 D 值累加 (d_1, d_3, d_12)
    scales = [1, 3, 12]
    for scale in scales:
        col_name = f'd_{scale}'
        if scale == 1:
            df_combined[col_name] = df_combined['d_value']
        else:
            df_combined[col_name] = df_combined.groupby(['latitude', 'longitude'])['d_value'] \
                                               .rolling(window=scale, min_periods=1) \
                                               .sum().reset_index(level=[0, 1], drop=True)
                                               
    # 2. 计算 SPEI (此处为了解耦和轻量化，采用简化版 Z-Score)
    # 真实业务中，应读取基于 1980-2023 拟合的 Log-Logistic 参数进行映射
    for scale in scales:
        d_col = f'd_{scale}'
        spei_col = f'spei_{scale}'
        
        # 提取缓冲池中的历史均值和标准差作为基准
        hist_mean = df_buffer[d_col].mean()
        hist_std = df_buffer[d_col].std()
        
        # 仅对新数据计算近似 SPEI
        df_combined[spei_col] = df_combined[spei_col].fillna(
            (df_combined[d_col] - hist_mean) / (hist_std + 1e-6)
        )
        # 截断处理防异常
        df_combined[spei_col] = df_combined[spei_col].clip(-3.0, 3.0)

    # 3. 滞后特征 (Lagged Features)
    lag_cols = ['p_sum', 'temp_mean', 'spei_1', 'spei_3', 'spei_12']
    for col in lag_cols:
        for lag in range(1, 13):
            df_combined[f'{col}_lag{lag}'] = df_combined.groupby(['latitude', 'longitude'])[col].shift(lag)

    # 4. 滚动统计量 (Rolling Statistics)
    roll_configs = {
        3: [('p_sum', 'mean'), ('p_sum', 'var'), ('temp_mean', 'max'), ('temp_mean', 'min')],
        6: [('p_sum', 'mean'), ('p_sum', 'var'), ('temp_mean', 'max'), ('temp_mean', 'min')]
    }
    for window, stats_list in roll_configs.items():
        for col, stat in stats_list:
            feat_name = f"{col}_rolling{window}_{stat}"
            if stat == 'mean':
                df_combined[feat_name] = df_combined.groupby(['latitude', 'longitude'])[col].rolling(window).mean().reset_index(level=[0,1], drop=True)
            elif stat == 'var':
                df_combined[feat_name] = df_combined.groupby(['latitude', 'longitude'])[col].rolling(window).var().reset_index(level=[0,1], drop=True)
            elif stat == 'max':
                df_combined[feat_name] = df_combined.groupby(['latitude', 'longitude'])[col].rolling(window).max().reset_index(level=[0,1], drop=True)
            elif stat == 'min':
                df_combined[feat_name] = df_combined.groupby(['latitude', 'longitude'])[col].rolling(window).min().reset_index(level=[0,1], drop=True)

    # 5. 时间周期编码
    df_combined['month_sin'] = np.sin(2 * np.pi * df_combined['month'] / 12)
    df_combined['month_cos'] = np.cos(2 * np.pi * df_combined['month'] / 12)
    
    # 填充缺失值（针对方差等）
    df_combined = df_combined.fillna(0)
    
    return df_combined

def main():
    # 1. 加载历史网格和缓冲数据
    grid_points, df_buffer = get_grid_points_and_buffer()
    
    # 为了测试速度，可以只取前 50 个网格点，正式运行去掉这行
    # grid_points = grid_points.head(50)
    
    # 2. 拉取日级数据并聚合
    df_new = fetch_daily_data(grid_points)
    
    # 3. 拼接计算特征
    df_final = compute_features(df_buffer, df_new)
    
    # 4. 剔除缓冲池数据，仅保留 2024 年以后的最新推理数据
    df_inference = df_final[df_final['year'] >= START_YEAR].copy()
    
    # 5. 保存为 Parquet
    print(f"Saving {len(df_inference)} rows to {OUTPUT_PATH}...")
    df_inference.to_parquet(OUTPUT_PATH, index=False)
    print("Done! 🎉")

if __name__ == "__main__":
    main()
