# -*- coding: utf-8 -*-
"""
核心任务 2：干旱预测时间序列特征工程 (Machine Learning Feature Engineering)

目标：基于技术路线图 v2 (3.2.2节)，将基础气象数据和月度 SPEI 数据转化为
      LSTM/XGBoost 模型所需的“有监督学习格式 (Supervised Learning Format)”。
      核心操作包括构建滞后特征 (Lagged)、滑动窗口统计量 (Rolling) 和周期性时间编码。
执行策略：本文件采用“逐步测试”模式开发，每个 TODO 块独立编写并验证。
"""

import os
import time
import psycopg2
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine
import pyarrow as pa
import pyarrow.parquet as pq

# ==============================================================================
# 全局控制开关
# ==============================================================================
# 测试开关：如果为 True，则只抽取极少量网格点进行极速逻辑验证。
# 正式运行时，请将其改为 False。
IS_TEST_MODE = False

# 分块配置：每次处理的网格点数量
# 建议：10~20 个网格点（约 4~8 万行），能在极低内存下保证最快的 Pandas 计算速度
CHUNK_SIZE_GRIDS = 15

# 数据库连接配置
load_dotenv()
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'dbname': os.getenv('POSTGRES_DB', 'gra_env_db'),
    'user': os.getenv('POSTGRES_USER', 'admin'),
    'password': os.getenv('POSTGRES_PASSWORD', 'secure_password_dev')
}

def get_db_connection():
    """获取 PostgreSQL 数据库连接"""
    return psycopg2.connect(**DB_CONFIG)

# ==============================================================================
# TODO 1: 月度基准数据加载与辅助物理量聚合 (Data Loading & Monthly Aggregation)
# ==============================================================================
# [理论解释]: 
# 我们的主要数据源是任务 1 生成的 `monthly_spei_features` (包含 D值, P_sum, T_mean 和各尺度 SPEI)。
# 同时，根据路线图，我们还需要从 1 亿条日级表 `high_res_daily_weather_et0` 中提取辅助变量
# （如：月均相对湿度、月均风速、月总辐射）。由于数据量大，这部分辅助变量的聚合也必须使用 SQL 下推。
#
# [测试目标]: 
# 1. 成功执行 SQL 联合查询或分别查询后 Merge。
# 2. 返回包含完整基准字段的 DataFrame (例如: year, month, spei_3, humidity_mean 等)。

def get_all_grid_points(engine):
    """从数据库中获取所有不重复的网格点坐标"""
    print("\n>>> [初始化] 正在扫描华北平原全域网格点...")
    sql = """
        SELECT DISTINCT latitude, longitude 
        FROM monthly_spei_features 
        ORDER BY latitude, longitude
    """
    if IS_TEST_MODE:
        sql += " LIMIT 2  -- 测试模式仅取 2 个网格点"
        
    grids_df = pd.read_sql_query(sql, engine)
    grids = list(zip(grids_df['latitude'], grids_df['longitude']))
    print(f"    [成功] 共发现 {len(grids)} 个目标网格点。")
    return grids

def build_where_clause_for_chunk(grids_chunk):
    """为当前批次的网格点构建精确的 SQL WHERE 子句"""
    conditions = []
    for lat, lon in grids_chunk:
        # 使用 BETWEEN 触发索引，这是防全表扫描的关键
        lat_min, lat_max = float(lat) - 0.01, float(lat) + 0.01
        lon_min, lon_max = float(lon) - 0.01, float(lon) + 0.01
        
        # 构建当前点在两张表中的联合过滤条件
        cond = f"((latitude BETWEEN {lat_min} AND {lat_max}) AND (longitude BETWEEN {lon_min} AND {lon_max}))"
        conditions.append(cond)
        
    combined_cond = " OR ".join(conditions)
    
    # 因为 CTE 中别名不同，我们需要生成两套
    where_injection = f"WHERE {combined_cond}"
    
    s_conditions = [c.replace("latitude", "s.latitude").replace("longitude", "s.longitude") for c in conditions]
    s_where_injection = f"WHERE {' OR '.join(s_conditions)}"
    
    return where_injection, s_where_injection

def load_and_prepare_monthly_base_data(engine, grids_chunk, chunk_id):
    print(f"\n    -> [Chunk {chunk_id}] 执行 SQL 下推聚合...")
    
    # 【核心逻辑】：构建绝对健壮的 JOIN SQL
    # 为了解决浮点数 JOIN 匹配失败的问题，我们在聚合日级数据时，
    # 强制将 FLOAT 类型的 latitude/longitude 转换为 NUMERIC(5,2)。
    # 这样在与 monthly_spei_features (本身就是 NUMERIC(5,2)) JOIN 时，就能做到 100% 精准咬合！
    core_join_sql = """
        WITH monthly_aux AS (
            SELECT 
                CAST(latitude AS NUMERIC(5,2)) AS latitude_num,
                CAST(longitude AS NUMERIC(5,2)) AS longitude_num,
                EXTRACT(YEAR FROM date) AS year,
                EXTRACT(MONTH FROM date) AS month,
                AVG(temperature) AS temp_mean,
                AVG(relative_humidity) AS humidity_mean,
                AVG(wind_speed) AS wind_speed_mean,
                SUM(shortwave_radiation) AS radiation_sum
            FROM high_res_daily_weather_et0
            -- 测试模式下的动态注入点 (WHERE 子句将插入在这里)
            {where_clause}
            GROUP BY CAST(latitude AS NUMERIC(5,2)), CAST(longitude AS NUMERIC(5,2)), EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date)
        )
        SELECT 
            s.*,
            a.temp_mean,
            a.humidity_mean,
            a.wind_speed_mean,
            a.radiation_sum
        FROM monthly_spei_features s
        JOIN monthly_aux a 
          -- 使用强转后的定点数进行绝对精准匹配
          ON s.latitude = a.latitude_num 
         AND s.longitude = a.longitude_num 
         AND s.year = a.year 
         AND s.month = a.month
        {s_where_clause}
    """
    
    where_injection, s_where_injection = build_where_clause_for_chunk(grids_chunk)
    sql_query = core_join_sql.format(where_clause=where_injection, s_where_clause=s_where_injection)
    sql_query += "\nORDER BY s.latitude, s.longitude, s.year, s.month"
    
    try:
        # 统一使用同一个 read_sql_query 路线，杜绝 Pandas Merge
        df_base = pd.read_sql_query(sql_query, engine)
        
        # 数据类型清洗：确保年份和月份是标准的整数格式
        df_base['year'] = df_base['year'].astype(int)
        df_base['month'] = df_base['month'].astype(int)
        
        print(f"       [成功] 获取本批次 {len(grids_chunk)} 个网格点，共 {len(df_base)} 条基础记录。")
        return df_base
        
    except Exception as e:
        print(f"       [错误] 数据库查询或拼接失败: {e}")
        raise


# ==============================================================================
# TODO 2: 构建滞后特征 (Lagged Features)
# ==============================================================================
# [理论解释]: 
# 这是时间序列预测的灵魂。模型需要“看到”过去发生的事情才能预测未来。
# 我们需要对 SPEI_3、降水(P)、气温(T)等关键变量，构建过去 1 到 12 个月的历史值。
# 例如：如果当前行是 2000年5月，那么 spei_3_lag1 就是 2000年4月的 SPEI_3 值。
#
# [测试目标]: 
# 使用 Pandas 的 shift() 函数按 (latitude, longitude) 分组操作，验证某行的 lag1 数据是否确实等于上一行。

def create_lagged_features(df_base, lag_steps=12):
    print(f"\n>>> [TODO 2] 正在构建过去 1 到 {lag_steps} 个月的历史滞后特征 (Lagged Features)...")
    
    # 1. 强制排序：时间序列操作的生命线！必须按空间和时间严格正序排列
    df = df_base.sort_values(by=['latitude', 'longitude', 'year', 'month']).copy()
    
    # 2. 定义需要进行滞后操作的核心变量列表
    # 我们选择最具代表性的：水分收入(p_sum)、热量支出(temp_mean)、综合干旱状态(spei_1, spei_3, spei_12)
    target_cols = ['p_sum', 'temp_mean', 'spei_1', 'spei_3', 'spei_12']
    
    # 3. 按网格点分组，生成滞后特征
    # 使用 groupby 确保在网格边界处（比如北京的1月不会拉取到天津的12月）发生隔离
    grouped = df.groupby(['latitude', 'longitude'])
    
    for col in target_cols:
        for lag in range(1, lag_steps + 1):
            new_col_name = f'{col}_lag{lag}'
            # shift(lag) 会将整列数据向下移动 lag 行
            df[new_col_name] = grouped[col].shift(lag)
            
    print(f"    [成功] 滞后特征构建完成！每个网格点新增了 {len(target_cols) * lag_steps} 个特征列。")
    
    if IS_TEST_MODE:
        print("    [验证] 检查滞后对齐逻辑 (观察 1991年1月 的 lag1 是否等于 1990年12月 的本期值):")
        # 提取相关列，并截取 1990年12月 到 1991年2月 的数据
        test_view = df[['year', 'month', 'spei_3', 'spei_3_lag1', 'spei_3_lag2']].iloc[11:14]
        print("-" * 50)
        print(test_view)
        print("-" * 50)
        
        # 自动化断言：第 13 行(1991-02) 的 lag1 必须完全等于 第 12 行(1991-01) 的本期值
        if len(df) > 13:
            val_current = df['spei_3'].iloc[12]
            val_lag1 = df['spei_3_lag1'].iloc[13]
            # 如果存在 NaN（比如前几个月算不出 SPEI_3），则跳过断言；如果有值，必须相等
            if pd.notna(val_current) and pd.notna(val_lag1):
                if val_current == val_lag1:
                    print("    [测试通过] shift(1) 时序平移完全正确！")
                else:
                    print(f"    [测试失败] 数据错位！当前值={val_current}, 但下一行的lag1={val_lag1}")
            else:
                print("    [提示] 遇到 NaN 值，跳过严格相等断言。")
                
    return df


# ==============================================================================
# TODO 3: 计算滑动窗口统计量 (Rolling Statistics)
# ==============================================================================
# [理论解释]: 
# 捕捉短中期的气候波动特征。我们将计算过去 3 个月和 6 个月内，
# 降水的方差 (Variance) 和气温的极值 (Max/Min)。这比单纯的滞后值更能反映环境的剧烈变化。
#
# [测试目标]: 
# 验证 rolling(window=n) 计算的方差和极值逻辑正确，且没有发生跨网格点的“数据泄漏”。
def create_rolling_statistics(df):
    print("\n>>> [TODO 3] 正在计算滑动窗口统计量 (Rolling Statistics)...")
    
    # 按网格点分组，避免跨网格计算滑动窗口
    grouped = df.groupby(['latitude', 'longitude'])
    
    # 过去3个月和6个月的降水均值和方差
    for window in [3, 6]:
        # 注意：rolling 操作在 groupby 之后可能会带上多重索引，使用 reset_index(level=[0,1], drop=True) 重新对齐
        df[f'p_sum_rolling{window}_mean'] = grouped['p_sum'].rolling(window=window, min_periods=1).mean().reset_index(level=[0,1], drop=True)
        df[f'p_sum_rolling{window}_var'] = grouped['p_sum'].rolling(window=window, min_periods=1).var().reset_index(level=[0,1], drop=True)
        
        # 过去3个月和6个月的气温极值
        df[f'temp_mean_rolling{window}_max'] = grouped['temp_mean'].rolling(window=window, min_periods=1).max().reset_index(level=[0,1], drop=True)
        df[f'temp_mean_rolling{window}_min'] = grouped['temp_mean'].rolling(window=window, min_periods=1).min().reset_index(level=[0,1], drop=True)

    print(f"    [成功] 滑动窗口统计量计算完成！每个网格点新增了 8 个特征列。")
    
    if IS_TEST_MODE:
        print("    [验证] 查看前 6 行的降水 3 个月均值 (p_sum_rolling3_mean):")
        print("-" * 50)
        print(df[['year', 'month', 'p_sum', 'p_sum_rolling3_mean']].head(6))
        print("-" * 50)
        
    return df


# ==============================================================================
# TODO 4: 周期性时间编码与目标列构建 (Time Encoding & Target Shift)
# ==============================================================================
# [理论解释]: 
# 1. 时间编码：将 month(1-12) 转化为 month_sin 和 month_cos，让模型理解 12 月和 1 月是相连的。
# 2. 目标列 (Target)：我们要预测的是未来的 SPEI。因此需要将 SPEI_3 的序列“向上平移 (shift(-n))”，
#    生成 target_spei_1m_ahead 和 target_spei_3m_ahead，作为监督学习的 Y 值。
#
# [测试目标]: 
# 确保正弦/余弦变换范围在 [-1, 1] 内；验证 target_spei_1m_ahead 正确指向了未来的真实值。
def create_time_encoding_and_targets(df):
    print("\n>>> [TODO 4] 正在进行周期性时间编码与目标列构建...")
    
    # 1. 周期性时间编码
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
    
    # 2. 构建目标列 (Target) - 注意我们要预测的是未来，所以是负数 shift(-n) 向前拉取
    grouped = df.groupby(['latitude', 'longitude'])
    df['target_spei_1m_ahead'] = grouped['spei_3'].shift(-1)
    df['target_spei_3m_ahead'] = grouped['spei_3'].shift(-3)
    df['target_spei_6m_ahead'] = grouped['spei_3'].shift(-6)

    print(f"    [成功] 时间编码与目标列构建完成！")
    
    if IS_TEST_MODE:
        print("    [验证] 检查时间编码极值，范围必须在 [-1, 1] 内:")
        print(f"           sin_max: {df['month_sin'].max():.2f}, sin_min: {df['month_sin'].min():.2f}")
        print("    [验证] 查看最后 3 行，验证目标列是否被平移产生了 NaN (因为未来没有数据了):")
        print("-" * 50)
        print(df[['year', 'month', 'spei_3', 'target_spei_1m_ahead']].tail(3))
        print("-" * 50)
        
    return df


# ==============================================================================
# TODO 5: 清洗与持久化机器学习宽表 (Clean & Export ML Feature Table)
# ==============================================================================
# [理论解释]: 
# 由于大量使用了 shift(lag) 操作，数据集的前 12 个月会产生大量的 NaN（因为没有更早的历史数据）。
# 我们需要清洗这些由于特征工程产生的天然缺失值，然后将这份完美的监督学习特征大宽表
# 导出为 Parquet 格式或写回 PostgreSQL，供后续 LSTM/XGBoost 训练直接读取。
#
# [测试目标]: 
# 验证缺失值剔除逻辑，测试数据导出性能。
def export_ml_feature_table_chunk(df, out_path, is_first_chunk):
    # 1. 清洗天然缺失值 (前 12 个月的 lag 产生的 NaN，以及最后几个月的 target 产生的 NaN)
    df_clean = df.dropna().copy()
    
    # 2. 追加导出
    if is_first_chunk:
        # 第一批：创建新文件
        df_clean.to_parquet(out_path, index=False)
    else:
        # 后续批次：采用 Fastparquet 引擎或者简单的 to_csv 模式？
        # 这里最安全的方案是不在循环里读写同一个巨大文件，而是把每个 chunk 保存为独立文件
        # 最后再把它们合起来，或者交给 Dask/PySpark 处理多文件。
        # 考虑到只有 ~536 个分块文件，存成单独的 parquet 是最佳实践！
        chunk_file = out_path.replace('.parquet', f'_chunk_{time.time_ns()}.parquet')
        df_clean.to_parquet(chunk_file, index=False)
        
    return len(df_clean)


if __name__ == "__main__":
    # 主流程运行框架
    print(">>> 启动机器学习时间序列特征工程聚合框架 (Chunking 模式) <<<")
    
    start_time_total = time.time()
    
    from sqlalchemy import create_engine
    engine_url = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
    engine = create_engine(engine_url)
    
    # 获取所有网格点
    all_grids = get_all_grid_points(engine)
    total_grids = len(all_grids)
    
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'processed', 'ml_features_chunks')
    os.makedirs(out_dir, exist_ok=True)
    
    # 分块处理循环
    total_processed_rows = 0
    chunk_id = 1
    
    for i in range(0, total_grids, CHUNK_SIZE_GRIDS):
        grids_chunk = all_grids[i : i + CHUNK_SIZE_GRIDS]
        print(f"\n========================================================")
        print(f"开始处理第 {chunk_id} 批次 (进度: {i}/{total_grids} 个网格点)")
        print(f"========================================================")
        
        chunk_start_time = time.time()
        
        # 1. 基础数据加载
        df_base = load_and_prepare_monthly_base_data(engine, grids_chunk, chunk_id)
        
        # 2. 特征工程流水线
        df_lagged = create_lagged_features(df_base)
        df_rolling = create_rolling_statistics(df_lagged)
        df_final = create_time_encoding_and_targets(df_rolling)
        
        # 3. 清洗并追加写入 (每个 chunk 写一个独立文件)
        df_clean = df_final.dropna().copy()
        chunk_file = os.path.join(out_dir, f'chunk_{chunk_id:04d}.parquet')
        df_clean.to_parquet(chunk_file, index=False)
        
        valid_rows = len(df_clean)
        total_processed_rows += valid_rows
        
        print(f"    [Chunk {chunk_id} 完成] 耗时: {time.time() - chunk_start_time:.2f} 秒。累计写入有效特征行数: {total_processed_rows}")
        chunk_id += 1
        
    print("\n" + "="*50)
    print(f">>> 框架运行完毕！ <<<")
    print(f"总耗时: {time.time() - start_time_total:.2f} 秒")
    print(f"总计写入 {total_processed_rows} 条机器学习特征数据。")
    print(f"分块文件已保存至: {out_dir}")
    print("="*50)
    
    # 最终合并步骤
    print("\n>>> 正在将所有分块文件合并为单一的最终宽表...")
    merge_start = time.time()
    all_chunk_files = [os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.endswith('.parquet')]
    
    # 读入所有 chunk (此时特征工程已完成，纯读取并 concat 占用内存小且安全)
    dfs = [pd.read_parquet(f) for f in all_chunk_files]
    final_df = pd.concat(dfs, ignore_index=True)
    
    final_out_path = os.path.join(os.path.dirname(out_dir), 'ml_feature_table.parquet')
    final_df.to_parquet(final_out_path, index=False)
    
    print(f"合并完成！最终宽表已保存至: {final_out_path}")
    print(f"最终合并耗时: {time.time() - merge_start:.2f} 秒。最终行数: {len(final_df)}")
