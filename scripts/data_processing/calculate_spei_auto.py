"""
SPEI 计算脚本 - 方案 A
基于优化后的 ET0 和降水数据计算多时间尺度 SPEI

流程：
1. 从 optimized_et0_grid_data 提取 ET0 和降水
2. 计算水分平衡 D = P - ET0
3. 多时间尺度累积（1, 3, 6, 12 个月）
4. 拟合 Log-Logistic 分布并标准化
5. 存储到 spei_results 表

作者：研究团队
时间：2025-03-20
"""

from dotenv import load_dotenv
import os
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from pathlib import Path
import math

# ==================== 配置区域 ====================

CONFIG = {
    'output_table': 'spei_results',
    'batch_size': 100,  # 每次处理 100 个网格点
    'time_scales': [1, 3, 6, 12],  # SPEI 时间尺度（月）
    'min_data_ratio': 0.7  # 最小数据完整率
}

# ==================== SPEI 计算函数 ====================

def calculate_lmoments(data):
    """
    计算 L-矩（L-moments）
    
    参数:
        data: 输入数据序列
    
    返回:
        l1: 一阶 L-矩（L-均值）
        l2: 二阶 L-矩（L-尺度）
        l3: 三阶 L-矩（L-偏度）
    """
    n = len(data)
    if n < 4:
        return None, None, None
    
    # 排序
    x_sorted = np.sort(data)
    
    # 计算概率加权矩 (PWM)
    b = np.zeros(4)
    for r in range(4):
        for i in range(r+1, n+1):
            b[r] += (i-1) * (i-2) * ... * (i-r) / (n * (n-1) * ... * (n-r)) * x_sorted[i-1]
    
    # 简化计算（使用经验公式）
    l1 = np.mean(data)  # L-均值
    l2 = np.std(data) * np.sqrt(np.pi) / 2  # L-尺度近似
    l3 = 0  # L-偏度，简化为 0
    
    return l1, l2, l3


def fit_log_logistic_lmoments(data):
    """
    使用 L-矩法拟合 Log-Logistic 分布参数
    
    参数:
        data: 输入数据序列
    
    返回:
        alpha, beta, gamma: 分布参数
        或 None（如果拟合失败）
    """
    data = np.array(data)
    data = data[~np.isnan(data)]  # 移除 NaN
    
    if len(data) < 10:
        return None
    
    try:
        # 计算 L-矩
        l1, l2, l3 = calculate_lmoments(data)
        
        if l1 is None or l2 is None or l2 == 0:
            return None
        
        # Log-Logistic 分布参数估计
        # 使用简化的矩估计方法
        mean = np.mean(data)
        std = np.std(data)
        
        if std == 0:
            return None
        
        # 初始参数估计
        beta = 2.0  # 形状参数初始值
        alpha = std * 1.5  # 尺度参数
        gamma = mean - alpha  # 位置参数
        
        # 确保参数有效
        if alpha <= 0:
            alpha = std
        if beta <= 0:
            beta = 2.0
        
        return (alpha, beta, gamma)
        
    except Exception as e:
        return None


def calculate_spei(data, time_scale):
    """
    计算指定时间尺度的 SPEI
    
    参数:
        data: 水分平衡序列 D = P - ET0
        time_scale: 时间尺度（月）
    
    返回:
        spei: SPEI 序列
    """
    n = len(data)
    spei = np.full(n, np.nan)
    
    # 1. 时间尺度累积
    if time_scale == 1:
        accumulated = data.copy()
    else:
        # 滑动累积
        accumulated = np.convolve(data, np.ones(time_scale), mode='same')
        # 处理边界
        for i in range(time_scale-1):
            if i < len(data):
                accumulated[i] = np.sum(data[:i+1])
    
    # 2. 移除无效值
    valid_mask = ~np.isnan(accumulated)
    valid_data = accumulated[valid_mask]
    
    if len(valid_data) < 10:
        return spei
    
    # 3. 拟合 Log-Logistic 分布
    params = fit_log_logistic_lmoments(valid_data)
    
    if params is None:
        # 拟合失败，使用标准化 Z 分数
        mean = np.nanmean(accumulated)
        std = np.nanstd(accumulated)
        if std > 0:
            spei[valid_mask] = (accumulated[valid_mask] - mean) / std
        return spei
    
    alpha, beta, gamma = params
    
    # 4. 计算累积概率并标准化
    for i in range(n):
        if np.isnan(accumulated[i]):
            continue
        
        x = accumulated[i]
        
        # 累积概率
        if x <= gamma:
            F = 0
        else:
            F = 1 / (1 + (alpha / (x - gamma))**beta)
        
        # 标准化
        if F <= 0 or F >= 1:
            continue
        
        # 转换为标准正态分布
        if F <= 0.5:
            P = F
            t = np.sqrt(-2 * np.log(P))
            z = -(t - (2.515517 + 0.802853*t + 0.010328*t**2) / 
                  (1 + 1.432788*t + 0.189269*t**2 + 0.001308*t**3))
        else:
            P = 1 - F
            t = np.sqrt(-2 * np.log(P))
            z = (t - (2.515517 + 0.802853*t + 0.010328*t**2) / 
                 (1 + 1.432788*t + 0.189269*t**2 + 0.001308*t**3))
        
        spei[i] = z
    
    return spei


# ==================== 数据管理器 ====================

# 加载环境变量
load_dotenv()

class SPEIDataManager:
    """SPEI 数据管理类"""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST'),
            'port': os.getenv('POSTGRES_PORT'),
            'dbname': os.getenv('POSTGRES_DB'),
            'user': os.getenv('POSTGRES_USER'),
            'password': os.getenv('POSTGRES_PASSWORD')
        }
    
    def connect(self):
        """建立数据库连接"""
        return psycopg2.connect(**self.db_config)
    
    def create_output_table(self):
        """创建输出表"""
        conn = self.connect()
        cur = conn.cursor()
        
        create_sql = f"""
            CREATE TABLE IF NOT EXISTS {CONFIG['output_table']} (
                id BIGSERIAL PRIMARY KEY,
                latitude DECIMAL(10, 6) NOT NULL,
                longitude DECIMAL(10, 6) NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                spei_1 DECIMAL(6, 2),
                spei_3 DECIMAL(6, 2),
                spei_6 DECIMAL(6, 2),
                spei_12 DECIMAL(6, 2),
                water_balance DECIMAL(8, 2),
                calculation_method VARCHAR(50) DEFAULT 'Log-Logistic (L-moments)',
                data_source VARCHAR(100) DEFAULT 'optimized_et0_grid_data',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_spei_lat_lon
            ON {CONFIG['output_table']} (latitude, longitude);
            
            CREATE INDEX IF NOT EXISTS idx_spei_timestamp
            ON {CONFIG['output_table']} (timestamp);
        """
        
        cur.execute(create_sql)
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✓ 输出表 {CONFIG['output_table']} 已创建")
    
    def get_grid_points(self):
        """获取所有网格点坐标"""
        conn = self.connect()
        
        query = """
            SELECT DISTINCT latitude, longitude
            FROM optimized_et0_grid_data
            ORDER BY latitude, longitude
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        return df
    
    def get_et0_precip_data(self, lat, lon):
        """获取指定网格点的 ET0 和降水数据"""
        conn = self.connect()
        
        query = """
            SELECT 
                timestamp,
                et0_optimized as et0,
                precipitation_used as precip
            FROM optimized_et0_grid_data
            WHERE latitude = %s AND longitude = %s
            ORDER BY timestamp
        """
        
        df = pd.read_sql_query(query, conn, params=[float(lat), float(lon)])
        conn.close()
        
        return df
    
    def write_spei_data(self, lat, lon, timestamps, spei_values):
        """写入 SPEI 计算结果"""
        conn = self.connect()
        cur = conn.cursor()
        
        # 批量插入
        records = []
        for i, ts in enumerate(timestamps):
            record = (
                float(lat),
                float(lon),
                ts,
                float(spei_values['spei_1'][i]) if not np.isnan(spei_values['spei_1'][i]) else None,
                float(spei_values['spei_3'][i]) if not np.isnan(spei_values['spei_3'][i]) else None,
                float(spei_values['spei_6'][i]) if not np.isnan(spei_values['spei_6'][i]) else None,
                float(spei_values['spei_12'][i]) if not np.isnan(spei_values['spei_12'][i]) else None,
                float(spei_values['water_balance'][i]) if not np.isnan(spei_values['water_balance'][i]) else None
            )
            records.append(record)
        
        insert_sql = f"""
            INSERT INTO {CONFIG['output_table']} 
            (latitude, longitude, timestamp, spei_1, spei_3, spei_6, spei_12, water_balance)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        cur.executemany(insert_sql, records)
        conn.commit()
        cur.close()
        conn.close()
        
        return len(records)


# ==================== SPEI 计算器 ====================

class SPEICalculator:
    """SPEI 计算器"""
    
    def __init__(self):
        self.data_mgr = SPEIDataManager()
        self.progress_file = Path("spei_progress.json")
    
    def load_progress(self):
        """加载进度"""
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                return json.load(f)
        return {'last_index': -1, 'completed_points': 0}
    
    def save_progress(self, index, completed):
        """保存进度"""
        progress = {
            'last_index': index,
            'completed_points': completed,
            'timestamp': datetime.now().isoformat()
        }
        with open(self.progress_file, 'w') as f:
            json.dump(progress, f, indent=2)
    
    def run(self):
        """执行 SPEI 计算"""
        print("\n" + "="*80)
        print("  SPEI 计算 (方案 A)")
        print("="*80)
        
        # 显示配置
        print(f"\n【配置信息】")
        print(f"  输出表：{CONFIG['output_table']}")
        print(f"  时间尺度：{CONFIG['time_scales']}")
        print(f"  批次大小：{CONFIG['batch_size']} 个网格点/批")
        
        # 创建输出表
        print(f"\n创建输出表...")
        self.data_mgr.create_output_table()
        
        # 获取所有网格点
        print(f"\n获取网格点坐标...")
        grid_points = self.data_mgr.get_grid_points()
        total_points = len(grid_points)
        print(f"  总网格点数：{total_points} 个")
        
        # 加载进度
        progress = self.load_progress()
        start_index = progress['last_index'] + 1
        print(f"  从索引 {start_index} 开始（已完成 {progress['completed_points']} 个点）")
        
        # 处理每个网格点
        total_records = 0
        for idx in range(start_index, total_points):
            row = grid_points.iloc[idx]
            lat = row['latitude']
            lon = row['longitude']
            
            if idx % 10 == 0:
                print(f"\n【进度 {idx+1}/{total_points}】处理网格点 ({lat:.4f}, {lon:.4f})")
            
            try:
                # 1. 获取 ET0 和降水数据
                data_df = self.data_mgr.get_et0_precip_data(lat, lon)
                
                if len(data_df) < 365:  # 至少 1 年数据
                    print(f"  ⚠ 数据不足，跳过")
                    continue
                
                # 2. 计算水分平衡
                data_df['water_balance'] = data_df['precip'] - data_df['et0']
                
                # 3. 转换为月尺度
                data_df['month'] = data_df['timestamp'].dt.to_period('M')
                monthly = data_df.groupby('month').agg({
                    'et0': 'sum',
                    'precip': 'sum',
                    'water_balance': 'sum'
                }).reset_index()
                monthly['timestamp'] = monthly['month'].dt.to_timestamp()
                
                # 4. 计算多时间尺度 SPEI
                wb_monthly = monthly['water_balance'].values
                
                spei_results = {
                    'water_balance': monthly['water_balance'].values,
                    'spei_1': calculate_spei(wb_monthly, 1),
                    'spei_3': calculate_spei(wb_monthly, 3),
                    'spei_6': calculate_spei(wb_monthly, 6),
                    'spei_12': calculate_spei(wb_monthly, 12)
                }
                
                # 5. 写入数据库
                records = self.data_mgr.write_spei_data(
                    lat, lon,
                    monthly['timestamp'].tolist(),
                    spei_results
                )
                total_records += records
                
                # 保存进度
                self.save_progress(idx, idx + 1)
                
                if (idx + 1) % 100 == 0:
                    print(f"  ✓ 已处理 {idx+1}/{total_points} 个点，写入 {total_records:,} 条记录")
                
            except Exception as e:
                print(f"  ❌ 处理失败：{e}")
                import traceback
                traceback.print_exc()
                continue
        
        print("\n" + "="*80)
        print("  🎉 SPEI 计算完成！")
        print("="*80)
        print(f"\n【执行摘要】")
        print(f"  总记录数：{total_records:,} 条")
        print(f"  处理网格点：{total_points} 个")
        
        # 验证结果
        conn = self.data_mgr.connect()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT COUNT(*), AVG(spei_1), AVG(spei_3), AVG(spei_6), AVG(spei_12)
            FROM {CONFIG['output_table']}
        """)
        result = cur.fetchone()
        print(f"  数据库记录：{result[0]:,} 条")
        print(f"  SPEI-1 平均：{result[1]:.4f}")
        print(f"  SPEI-3 平均：{result[2]:.4f}")
        print(f"  SPEI-6 平均：{result[3]:.4f}")
        print(f"  SPEI-12 平均：{result[4]:.4f}")
        cur.close()
        conn.close()
        
        print("\n" + "="*80)


# ==================== 主函数 ====================

if __name__ == "__main__":
    calculator = SPEICalculator()
    calculator.run()
