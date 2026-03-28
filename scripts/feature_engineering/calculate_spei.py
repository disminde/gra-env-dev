# -*- coding: utf-8 -*-
"""
核心任务 1：标准化降水蒸散指数 (SPEI) 计算框架

目标：基于高分辨率日级气象数据，计算各个网格点多时间尺度（1个月、3个月、12个月）的 SPEI 干旱指数。
执行策略：本文件采用“逐步测试”模式开发，每个 TODO 块独立编写并验证。
"""

import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv

# ==============================================================================
# 全局控制开关
# ==============================================================================
# 测试开关：如果为 True，则只抽取 1 个网格点进行极速计算和测试。
# 正式运行时，请将其改为 False。
IS_TEST_MODE = False

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
# TODO 1: 数据库连接与 SQL 下推聚合 (Database Connection & SQL Pushdown)
# ==============================================================================
# [理论解释]: 
# 将 1 亿条日级数据直接全部拉到 Python 内存中会导致严重的 OOM (内存溢出)。
# 因此，我们需要利用 PostgreSQL 强大的聚合能力，在数据库端执行 SQL。
# 按 (latitude, longitude, year, month) 进行分组 (GROUP BY)，计算出每月的总降水(P)和总蒸散发(ET0)，
# 并在 SQL 中直接求出月度水分盈亏量 D = P - ET0。
#
# [测试目标]: 
# 1. 确保能成功连接数据库。
# 2. 打印出前几行聚合数据，验证网格点和年月日的聚合是否正确，且数据量是否如预期缩减至约 338 万条。
def fetch_and_aggregate_monthly_data():
    print(">>> [TODO 1] 正在连接数据库并执行 SQL 下推聚合...")
    
    # 推荐使用 SQLAlchemy 引擎来配合 Pandas
    from sqlalchemy import create_engine
    engine_url = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
    engine = create_engine(engine_url)
    
    # 构建基础 SQL 查询
    # EXTRACT 提取年月，SUM 聚合降水和蒸散发，直接在数据库层计算差值 D
    base_sql = """
        SELECT 
            latitude,
            longitude,
            EXTRACT(YEAR FROM date) AS year,
            EXTRACT(MONTH FROM date) AS month,
            SUM(precipitation) AS p_sum,
            SUM(et0) AS et0_sum,
            SUM(precipitation) - SUM(et0) AS d_value
        FROM high_res_daily_weather_et0
    """
    
    # 如果是测试模式，只取 1 个网格点以保证 1 秒内完成查询
    if IS_TEST_MODE:
        print("    [提示] 当前为测试模式 (IS_TEST_MODE=True)，仅抽取 1 个网格点数据。")
        # 利用子查询动态获取一个网格点的经纬度
        sql_query = f"""
            WITH SampleGrid AS (
                SELECT latitude, longitude 
                FROM high_res_daily_weather_et0 
                LIMIT 1
            )
            {base_sql}
            WHERE latitude = (SELECT latitude FROM SampleGrid)
              AND longitude = (SELECT longitude FROM SampleGrid)
            GROUP BY latitude, longitude, year, month
            ORDER BY year, month
        """
    else:
        print("    [警告] 当前为正式模式 (IS_TEST_MODE=False)，将处理全量 8050 个网格点 (1亿条数据)！这可能需要几分钟。")
        sql_query = f"""
            {base_sql}
            GROUP BY latitude, longitude, year, month
            ORDER BY latitude, longitude, year, month
        """
        
    try:
        # 使用 pandas 直接读取 SQL 结果为 DataFrame
        df_monthly = pd.read_sql_query(sql_query, engine)
        
        # 数据类型转换，确保 year 和 month 是整数
        df_monthly['year'] = df_monthly['year'].astype(int)
        df_monthly['month'] = df_monthly['month'].astype(int)
        
        print(f"    [成功] 数据拉取完成！共获取 {len(df_monthly)} 条月度聚合记录。")
        print("-" * 50)
        print(df_monthly.head())
        print("-" * 50)
        
        return df_monthly
    except Exception as e:
        print(f"    [错误] 数据库查询失败: {e}")
        raise


# ==============================================================================
# TODO 2: 时间尺度滑动窗口计算 (Rolling Window Calculation)
# ==============================================================================
# [理论解释]: 
# 农业干旱具有累积效应。SPEI 具有多时间尺度特性，例如 SPEI-3 反映过去 3 个月的干旱累积。
# 在 Python 端接收到月度 D 值后，我们需要按 grid_id 分组，
# 利用 Pandas 或 Polars 的 rolling(window=n).sum() 函数，计算 D_1, D_3, D_12 序列。
#
# [测试目标]: 
# 1. 抽取单个网格点，检查时间序列是否连续（无断层）。
# 2. 验证滑动窗口的累加值是否正确（例如，某年 3 月的 D_3 是否等于 1月+2月+3月的 D 值之和）。
def calculate_rolling_water_deficit(df_monthly, scales=[1, 3, 12]):
    print(f"\n>>> [TODO 2] 正在进行多时间尺度 {scales} 的滑动窗口计算...")
    
    # 1. 确保数据按空间（网格）和时间（年月）严格排序
    # 这是滑动窗口计算准确性的绝对前提
    df = df_monthly.sort_values(by=['latitude', 'longitude', 'year', 'month']).copy()
    
    # 2. 按网格点进行分组，计算不同尺度的滑动和
    # 由于我们的 df 已经排序好了，所以可以直接在每个 group 内使用 rolling
    for scale in scales:
        col_name = f'd_{scale}'
        
        if scale == 1:
            # SPEI-1 尺度就是当月的 D 值本身
            df[col_name] = df['d_value']
        else:
            # SPEI-n 尺度是过去 n 个月 D 值的累加 (包含当月)
            # min_periods=scale 保证只有积累满 n 个月才会有有效值，否则为 NaN (例如第1年的前几个月)
            df[col_name] = df.groupby(['latitude', 'longitude'])['d_value'] \
                             .rolling(window=scale, min_periods=scale) \
                             .sum() \
                             .reset_index(level=[0, 1], drop=True)
                             
    print(f"    [成功] 滑动窗口计算完成！新增了列: {[f'd_{s}' for s in scales]}")
    
    # 测试模式下：验证逻辑是否正确
    if IS_TEST_MODE:
        print("    [验证] 随机抽取前 5 个月的数据，检查 D_3 (3个月滑动和) 是否正确:")
        test_view = df[['year', 'month', 'd_value', 'd_1', 'd_3', 'd_12']].head(5)
        print("-" * 50)
        print(test_view)
        print("-" * 50)
        
        # 简单做个断言测试 (取出第3个月的数据，它的 d_3 应该等于前三个月的 d_value 之和)
        # 注意 index 2 是第 3 个月（因为索引从 0 开始）
        if len(df) >= 3:
            expected_d3 = df['d_value'].iloc[0:3].sum()
            actual_d3 = df['d_3'].iloc[2]
            # 浮点数比较可能存在极小误差，用 round 保留两位小数比较
            if round(expected_d3, 2) == round(actual_d3, 2):
                print("    [测试通过] 第3个月的 D_3 累加值与预期完全一致！")
            else:
                print(f"    [测试失败] 预期 D_3={expected_d3}, 实际为 {actual_d3}")
                
    return df


# ==============================================================================
# TODO 3: Log-Logistic 分布拟合 (Log-Logistic Distribution Fitting)
# ==============================================================================
# [理论解释]: 
# 核心难点！水分盈亏量 D 序列并不服从正态分布，气象学上通常采用 Log-Logistic 分布（或 Pearson III）拟合。
# 我们需要对每个网格点（8050个）的每个特定月份（如历年的 1 月），独立拟合三个参数：
# 尺度参数 (scale)、形状参数 (shape) 和位置参数 (location)。
# 考虑到计算量极其庞大（8050 * 12 = 96600 次拟合），此处必须设计多进程并行框架。
#
# [测试目标]: 
# 1. 先用单个网格点单个月份的数据跑通 scipy.stats.fisk 的拟合。
# 2. 启动多进程框架，验证并行计算的加速比及内存占用情况。

from scipy import stats
import numpy as np
from joblib import Parallel, delayed
import multiprocessing

def fit_single_group(group_data, col_name):
    """
    对单个网格点、单个月份、单一时间尺度（如 d_3）的序列进行 Log-Logistic 拟合
    返回: (c, loc, scale) 三个参数，如果失败则返回 (np.nan, np.nan, np.nan)
    """
    # 提取有效数据（剔除前几个月因为滑动窗口产生的 NaN）
    data = group_data[col_name].dropna().values
    
    # 如果有效数据太少（比如不足 10 年），拟合没有统计学意义
    if len(data) < 10:
        return (np.nan, np.nan, np.nan)
        
    try:
        # 使用 scipy 的 fisk 分布 (即 Log-Logistic 分布) 进行拟合
        # fisk.fit 返回三个参数: shape(c), location, scale
        params = stats.fisk.fit(data)
        return params
    except Exception:
        # 容错处理：如果数据全为0或极度异常导致不收敛，直接返回 NaN
        return (np.nan, np.nan, np.nan)

def process_group(lat, lon, month, group_data, scales):
    """
    多进程 Worker 函数：处理单个 (lat, lon, month) 组合的拟合任务
    """
    row_result = {
        'latitude': lat,
        'longitude': lon,
        'month': month
    }
    
    for scale in scales:
        col_name = f'd_{scale}'
        params = fit_single_group(group_data, col_name)
        row_result[f'params_{scale}_c'] = params[0]
        row_result[f'params_{scale}_loc'] = params[1]
        row_result[f'params_{scale}_scale'] = params[2]
        
    return row_result

def fit_log_logistic_parallel(df_rolling, scales=[1, 3, 12]):
    print("\n>>> [TODO 3] 正在进行 Log-Logistic 分布拟合...")
    
    grouped = df_rolling.groupby(['latitude', 'longitude', 'month'])
    print(f"    [提示] 共有 {len(grouped)} 个独立的拟合任务 (网格点数 * 12个月)。")
    
    if IS_TEST_MODE:
        # 测试模式：数据量极小，直接使用单线程 for 循环，避免启动进程池的开销
        print("    [提示] 当前为测试模式，使用单线程快速拟合。")
        results = []
        for (lat, lon, month), group in grouped:
            results.append(process_group(lat, lon, month, group, scales))
    else:
        # 正式模式：启动多进程并行计算
        num_cores = multiprocessing.cpu_count()
        # 预留1个核心给系统，防止机器卡死
        n_jobs = max(1, num_cores - 1)
        print(f"    [警告] 当前为正式模式，启动 {n_jobs} 个进程进行并行加速计算！这可能需要几分钟...")
        
        # 使用 joblib 的 Parallel 框架并行执行 process_group
        results = Parallel(n_jobs=n_jobs, verbose=5)(
            delayed(process_group)(lat, lon, month, group, scales) 
            for (lat, lon, month), group in grouped
        )
        
    # 将拟合出的参数表转换为 DataFrame
    params_df = pd.DataFrame(results)
    
    print(f"    [成功] 参数拟合完成！共生成 {len(params_df)} 条参数记录。")
    
    if IS_TEST_MODE:
        print("    [验证] 查看 1 月份的拟合参数:")
        test_view = params_df[params_df['month'] == 1]
        print("-" * 50)
        print(test_view)
        print("-" * 50)
        
    return params_df


# ==============================================================================
# TODO 4: 概率累积与标准化映射 (Standard Normal Distribution Mapping)
# ==============================================================================
# [理论解释]: 
# 根据 TODO 3 拟合出的分布参数，计算出特定 D 值在该分布下的累积概率 P (CDF)。
# 最后，将概率 P 映射到标准正态分布上（即求逆累积分布函数），得到最终的 Z-score，这就是 SPEI 值。
#
# [测试目标]: 
# 确保输出的 SPEI 值在合理范围内（通常在 -3.0 到 +3.0 之间，负数代表干旱，正数代表湿润），处理极值(如 P=0 或 P=1)导致的 Inf 问题。

def calculate_spei_from_cdf(fitted_params_df, df_rolling, scales=[1, 3, 12]):
    print("\n>>> [TODO 4] 正在进行概率累积 (CDF) 与标准正态分布映射...")
    
    # 1. 将包含参数的 DataFrame 与原始滚动数据按 (latitude, longitude, month) 进行合并(左连接)
    # 这样每一行 D 值旁边，就有了它对应的专属参数 (c, loc, scale)
    merged_df = pd.merge(
        df_rolling, 
        fitted_params_df, 
        on=['latitude', 'longitude', 'month'], 
        how='left'
    )
    
    # 2. 对每个时间尺度分别计算 SPEI
    for scale in scales:
        d_col = f'd_{scale}'
        spei_col = f'spei_{scale}'
        
        c_col = f'params_{scale}_c'
        loc_col = f'params_{scale}_loc'
        scale_col = f'params_{scale}_scale'
        
        # 提取数据向量
        d_values = merged_df[d_col].values
        c_values = merged_df[c_col].values
        loc_values = merged_df[loc_col].values
        scale_values = merged_df[scale_col].values
        
        # 使用 scipy.stats.fisk.cdf 计算累积概率 P
        # 如果参数中含有 NaN（即无法拟合的月份），cdf 函数会自动返回 NaN
        p_values = stats.fisk.cdf(d_values, c=c_values, loc=loc_values, scale=scale_values)
        
        # 极值保护：CDF 的结果可能极其接近 0 或 1，这会导致标准正态逆映射时产生无穷大 (Inf) 或无穷小 (-Inf)。
        # 将概率限制在 0.0001 到 0.9999 之间 (对应 SPEI 最大绝对值约为 3.7)
        p_values = np.clip(p_values, 0.0001, 0.9999)
        
        # 使用标准正态分布的逆累积分布函数 (PPF, Percent Point Function) 进行映射
        # ppf 就是将概率 P 转回 Z-score (均值为0，标准差为1的分布坐标)
        spei_values = stats.norm.ppf(p_values)
        
        # 将结果存回 DataFrame
        merged_df[spei_col] = spei_values
        
    print(f"    [成功] SPEI 计算完成！新增了列: {[f'spei_{s}' for s in scales]}")
    
    # 清理中间的参数列，保持数据清爽
    cols_to_keep = ['latitude', 'longitude', 'year', 'month', 'p_sum', 'et0_sum', 'd_value'] + \
                   [f'd_{s}' for s in scales] + \
                   [f'spei_{s}' for s in scales]
    final_df = merged_df[cols_to_keep].copy()
    
    if IS_TEST_MODE:
        print("    [验证] 查看计算出的 SPEI 值 (随机抽取中间的 5 个月):")
        # 抽取中间行（避开前面因为滚动窗口导致的 NaN）
        mid_idx = len(final_df) // 2
        test_view = final_df[['year', 'month', 'spei_1', 'spei_3', 'spei_12']].iloc[mid_idx:mid_idx+5]
        print("-" * 50)
        print(test_view)
        print("-" * 50)
        
    return final_df

# ==============================================================================
# TODO 5: SPEI 结果持久化落库 (Batch Insert to PostgreSQL)
# ==============================================================================
# [理论解释]: 
# 计算完成后，将最终结果（包含 grid_id, year, month, spei_1, spei_3, spei_12 等）
# 整理为 DataFrame，利用 psycopg2 的批量插入机制，写入到 PostgreSQL 新表 `monthly_spei_features` 中。
#
# [测试目标]: 
# 验证数据库表结构创建成功，测试批量插入性能。

import psycopg2.extras

def save_spei_to_database(spei_df):
    print("\n>>> [TODO 5] 正在将 SPEI 计算结果持久化到数据库...")
    
    table_name = "monthly_spei_features"
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # 1. 如果是测试模式，为了防止污染正式表，我们创建一个测试表
        if IS_TEST_MODE:
            table_name = "monthly_spei_features_test"
            print(f"    [提示] 当前为测试模式，数据将写入测试表: {table_name}")
            
        # 2. 创建表结构 (包含组合主键，防止重复插入)
        create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                latitude NUMERIC(5, 2),
                longitude NUMERIC(5, 2),
                year INTEGER,
                month INTEGER,
                p_sum NUMERIC(10, 4),
                et0_sum NUMERIC(10, 4),
                d_value NUMERIC(10, 4),
                d_1 NUMERIC(10, 4),
                d_3 NUMERIC(10, 4),
                d_12 NUMERIC(10, 4),
                spei_1 NUMERIC(8, 4),
                spei_3 NUMERIC(8, 4),
                spei_12 NUMERIC(8, 4),
                PRIMARY KEY (latitude, longitude, year, month)
            );
        """
        cur.execute(create_table_sql)
        conn.commit()
        print(f"    [成功] 表结构 '{table_name}' 已确认/创建。")
        
        # 3. 准备批量插入的数据元组
        # 处理 NaN 为 None (PostgreSQL 中的 NULL)
        insert_df = spei_df.replace({np.nan: None})
        
        # 将 DataFrame 转换为元组列表
        data_tuples = [tuple(x) for x in insert_df.to_numpy()]
        
        # 4. 使用 execute_values 进行高效批量插入 (带有 ON CONFLICT DO UPDATE 逻辑)
        insert_query = f"""
            INSERT INTO {table_name} (
                latitude, longitude, year, month, 
                p_sum, et0_sum, d_value, d_1, d_3, d_12, spei_1, spei_3, spei_12
            ) VALUES %s
            ON CONFLICT (latitude, longitude, year, month) 
            DO UPDATE SET 
                p_sum = EXCLUDED.p_sum,
                et0_sum = EXCLUDED.et0_sum,
                d_value = EXCLUDED.d_value,
                d_1 = EXCLUDED.d_1,
                d_3 = EXCLUDED.d_3,
                d_12 = EXCLUDED.d_12,
                spei_1 = EXCLUDED.spei_1,
                spei_3 = EXCLUDED.spei_3,
                spei_12 = EXCLUDED.spei_12;
        """
        
        psycopg2.extras.execute_values(
            cur, insert_query, data_tuples, template=None, page_size=10000
        )
        conn.commit()
        print(f"    [成功] 成功向 '{table_name}' 插入/更新了 {len(data_tuples)} 条 SPEI 记录！")
        
    except Exception as e:
        conn.rollback()
        print(f"    [错误] 数据落库失败: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    # 主流程运行框架 (按 TODO 进度逐步解开注释)
    print(">>> 启动 SPEI 计算框架 <<<")
    
    # --- 测试 TODO 1 ---
    df_monthly = fetch_and_aggregate_monthly_data()
    
    # --- 测试 TODO 2 ---
    df_rolling = calculate_rolling_water_deficit(df_monthly)
    
    # --- 测试 TODO 3 ---
    fitted_params = fit_log_logistic_parallel(df_rolling)
    
    # --- 测试 TODO 4 ---
    spei_result = calculate_spei_from_cdf(fitted_params, df_rolling)
    
    # --- 测试 TODO 5 ---
    save_spei_to_database(spei_result)
    
    print("框架已就绪")
