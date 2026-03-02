
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import psycopg2
from dotenv import load_dotenv
import gzip
import io

# 加载环境变量 (用于连接数据库)
load_dotenv()

# --- 配置部分 ---
# 选择一个测试站点：这里我们选 "百灵庙" (BAILING-MIAO)
TEST_STATION_ID = "533520-99999" 
TEST_STATION_NAME = "BAILING-MIAO"
# 百灵庙的经纬度 (从 find_available_match.py 查得的推荐值)
TEST_LAT = 41.7926
TEST_LON = 110.4782

# 测试时间段：不再硬编码 2020 年，而是自动寻找公共年份
TEST_YEAR = None

# 数据库连接配置
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "gra_env_db"),
    "user": os.getenv("POSTGRES_USER", "admin"),
    "password": os.getenv("POSTGRES_PASSWORD", "secure_password_dev")
}

def get_noaa_data(station_id, year=None):
    """
    读取本地下载的 NOAA ISD-Lite 原始数据
    如果不指定年份，则读取该站点目录下所有年份的数据并合并
    """
    station_dir = f"data/noaa_raw/{station_id}"
    if not os.path.exists(station_dir):
        raise FileNotFoundError(f"找不到站点目录: {station_dir}")
        
    all_dfs = []
    
    # 遍历该站点下的所有 .gz 文件
    files = sorted([f for f in os.listdir(station_dir) if f.endswith('.gz')])
    
    if not files:
        raise FileNotFoundError(f"目录 {station_dir} 下没有数据文件")
        
    print(f"[1/5] 读取 NOAA 本地文件 ({len(files)} 个年份)...")
    
    for filename in files:
        # 如果指定了年份，只读取该年份
        if year and str(year) not in filename:
            continue
            
        file_path = os.path.join(station_dir, filename)
        try:
            with gzip.open(file_path, 'rt') as f:
                df = pd.read_csv(f, delim_whitespace=True, header=None,
                                names=["Year", "Month", "Day", "Hour", "AirTemp", "DewPoint", "Pressure", "WindDir", "WindSpeed", "SkyCond", "Precip1h", "Precip6h"])
                all_dfs.append(df)
        except Exception as e:
            print(f"      [警告] 读取 {filename} 失败: {e}")
            
    if not all_dfs:
        return pd.DataFrame()
        
    df = pd.concat(all_dfs, ignore_index=True)

    # --- 数据清洗 ---
    # 1. 替换缺失值 -9999 为 NaN
    df = df.replace(-9999, np.nan)
    
    # 2. 转换单位 (ISD-Lite 的温度和风速都有 10 倍的缩放因子)
    df['AirTemp'] = df['AirTemp'] / 10.0
    
    # 3. 构建时间戳
    df['timestamp'] = pd.to_datetime(df[['Year', 'Month', 'Day', 'Hour']])
    
    # 4. 计算日平均气温 (Daily Mean)
    # 这一步是为了和 Open-Meteo 的日值数据对齐
    df_daily = df.groupby(df['timestamp'].dt.date)['AirTemp'].mean().reset_index()
    df_daily.columns = ['date', 'noaa_temp']
    df_daily['date'] = pd.to_datetime(df_daily['date'])
    
    print(f"      -> 成功加载 {len(df_daily)} 天的 NOAA 观测数据")
    return df_daily

def get_open_meteo_data(lat, lon, year=None):
    """
    从数据库中查询对应的 Open-Meteo 网格数据
    """
    print(f"[2/5] 从数据库查询 Open-Meteo 数据 (Lat: {lat}, Lon: {lon}, Year: {year})...")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        # 查询特定位置、特定年份的数据
        # 注意：我们需要按照经纬度范围模糊查询 (因为网格点可能有微小偏差)
        if year:
            query = """
            SELECT date(timestamp) as date, temperature as om_temp
            FROM grid_weather_data
            WHERE latitude BETWEEN %s - 0.1 AND %s + 0.1
              AND longitude BETWEEN %s - 0.1 AND %s + 0.1
              AND extract(year from timestamp) = %s
            ORDER BY timestamp;
            """
            params = (lat, lat, lon, lon, year)
        else:
            query = """
            SELECT date(timestamp) as date, temperature as om_temp
            FROM grid_weather_data
            WHERE latitude BETWEEN %s - 0.1 AND %s + 0.1
              AND longitude BETWEEN %s - 0.1 AND %s + 0.1
            ORDER BY timestamp;
            """
            params = (lat, lat, lon, lon)

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        # 重命名列以便后续合并
        # df.columns = ['date', 'om_temp']
        df['date'] = pd.to_datetime(df['date'])
        
        print(f"      -> 成功加载 {len(df)} 天的 Open-Meteo 模拟数据")
        return df
    except Exception as e:
        print(f"      [错误] 数据库查询失败: {e}")
        return pd.DataFrame()

def apply_qm_correction(merged_df):
    """
    核心步骤：执行 QM (分位数映射) 偏差校正
    这里使用 scikit-learn 的 QuantileTransformer 来模拟 QM 过程
    """
    print("[3/5] 执行 QM 偏差校正...")
    from sklearn.preprocessing import QuantileTransformer
    
    # 准备数据：删除任何包含 NaN 的行
    valid_data = merged_df.dropna()
    
    if len(valid_data) < 100:
        print("      [警告] 有效数据太少，无法进行可靠的 QM 校正！")
        return merged_df

    # X = 模拟数据 (Open-Meteo), Y = 观测真值 (NOAA)
    # 我们需要建立从 X 到 Y 的映射关系
    X = valid_data[['om_temp']]
    y = valid_data[['noaa_temp']]
    
    # 训练 QM 模型 (基于非参数的经验分布)
    # output_distribution='normal' 是将数据映射到正态分布，这里我们希望映射到观测值的分布
    # 所以我们使用两个转换器：
    # 1. 学习 NOAA 的分布 (Target Distribution)
    # 2. 将 Open-Meteo 数据转换到这个分布
    
    # 更简单的方法：直接计算分位数对应的差值
    # 这里我们演示一种简单的基于排序的 QM 实现 (Empirical Quantile Mapping)
    
    n_quantiles = 100
    quantiles = np.linspace(0, 1, n_quantiles)
    
    # 计算两个数据的分位数点
    om_quantiles = np.nanquantile(X, quantiles)
    noaa_quantiles = np.nanquantile(y, quantiles)
    
    # 建立插值函数：输入一个 Open-Meteo 温度，输出修正后的温度
    def qm_correct(val):
        return np.interp(val, om_quantiles, noaa_quantiles)
    
    # 应用校正
    merged_df['corrected_temp'] = merged_df['om_temp'].apply(qm_correct)
    
    # 计算偏差统计
    bias_before = (merged_df['om_temp'] - merged_df['noaa_temp']).mean()
    bias_after = (merged_df['corrected_temp'] - merged_df['noaa_temp']).mean()
    rmse_before = np.sqrt(((merged_df['om_temp'] - merged_df['noaa_temp'])**2).mean())
    rmse_after = np.sqrt(((merged_df['corrected_temp'] - merged_df['noaa_temp'])**2).mean())
    
    print(f"      -> 校正前偏差 (Bias): {bias_before:.2f}°C, RMSE: {rmse_before:.2f}°C")
    print(f"      -> 校正后偏差 (Bias): {bias_after:.2f}°C, RMSE: {rmse_after:.2f}°C")
    
    return merged_df

def visualize_results(df):
    """
    可视化：绘制 CDF (累积分布函数) 对比图
    这是验证 QM 效果最直观的方法
    """
    print("[4/5] 生成验证图表 (qm_validation_cdf.png)...")
    
    plt.figure(figsize=(12, 5))
    
    # 子图 1: 时间序列对比
    plt.subplot(1, 2, 1)
    plt.plot(df['date'], df['noaa_temp'], label='NOAA (Observed)', color='black', alpha=0.6, linewidth=1)
    plt.plot(df['date'], df['om_temp'], label='Open-Meteo (Raw)', color='red', alpha=0.6, linewidth=1)
    plt.plot(df['date'], df['corrected_temp'], label='Corrected (QM)', color='green', linestyle='--', linewidth=1)
    plt.title(f"Temperature Time Series ({TEST_YEAR})")
    plt.ylabel("Temperature (°C)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # 子图 2: CDF 累积分布对比
    plt.subplot(1, 2, 2)
    sns.ecdfplot(data=df, x='noaa_temp', label='NOAA (Target)', color='black', linewidth=2)
    sns.ecdfplot(data=df, x='om_temp', label='Open-Meteo (Raw)', color='red', linestyle=':')
    sns.ecdfplot(data=df, x='corrected_temp', label='Corrected (QM)', color='green', linestyle='--')
    plt.title("CDF (Cumulative Distribution Function)")
    plt.xlabel("Temperature (°C)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('qm_validation_result.png')
    print("      -> 图表已保存为 qm_validation_result.png")

def main():
    print(f"=== 开始 QM 可行性验证 ({TEST_STATION_NAME}) ===")
    
    # 1. 获取两套数据 (读取所有年份)
    df_noaa = get_noaa_data(TEST_STATION_ID)
    df_om = get_open_meteo_data(TEST_LAT, TEST_LON)
    
    if df_om.empty:
        print("[错误] 数据库中没有对应的 Open-Meteo 数据。请确认爬虫是否已抓取该年份和位置的数据。")
        return

    # 2. 合并数据 (按日期对齐)
    # inner join 确保只比较两天都有数据的日子
    merged_df = pd.merge(df_noaa, df_om, on='date', how='inner')
    print(f"      -> 合并后共有 {len(merged_df)} 个匹配样本对")
    
    if len(merged_df) == 0:
        print("[错误] 没有匹配的日期！")
        return

    # 3. 执行校正
    result_df = apply_qm_correction(merged_df)
    
    # 4. 可视化
    visualize_results(result_df)
    
    print("=== 验证完成 ===")

if __name__ == "__main__":
    main()
