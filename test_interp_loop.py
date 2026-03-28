"""测试插值循环是否真的在执行"""
from dotenv import load_dotenv
import os
load_dotenv()
import psycopg2
import numpy as np
from scipy.spatial import cKDTree
from datetime import datetime

conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST'),
    port=os.getenv('POSTGRES_PORT'),
    dbname=os.getenv('POSTGRES_DB'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD')
)

cur = conn.cursor()

print("开始测试插值循环...")
start_time = datetime.now()

# 获取第一个日期
cur.execute("""
    SELECT DISTINCT date FROM radiation_daily_temp ORDER BY date LIMIT 1
""")
first_date = cur.fetchone()[0]
print(f"测试日期：{first_date}")

# 获取源数据
cur.execute("""
    SELECT latitude, longitude, radiation_daily
    FROM radiation_daily_temp
    WHERE date = %s AND radiation_daily IS NOT NULL
""", (first_date,))

source_data = cur.fetchall()
print(f"获取到 {len(source_data)} 个源数据点")

if len(source_data) > 0:
    source_points = np.array([(float(row[0]), float(row[1])) for row in source_data])
    source_values = np.array([float(row[2]) for row in source_data])
    print(f"源数据范围：{source_values.min():.2f} - {source_values.max():.2f}")
    
    # 获取目标网格点 (前 10 个)
    cur.execute("""
        SELECT DISTINCT latitude, longitude
        FROM interpolated_grid_data
        ORDER BY latitude, longitude
        LIMIT 10
    """)
    target_points = np.array([(float(row[0]), float(row[1])) for row in cur.fetchall()])
    print(f"目标网格点数：{len(target_points)} 个")
    
    # IDW 插值
    tree = cKDTree(source_points)
    distances, indices = tree.query(target_points, k=10)
    distances = np.maximum(distances, 1e-10)
    weights = 1.0 / (distances ** 2)
    weights = weights / np.sum(weights, axis=1, keepdims=True)
    values = source_values[indices]
    interpolated = np.sum(values * weights, axis=1)
    
    print(f"插值结果范围：{interpolated.min():.2f} - {interpolated.max():.2f}")
    
    # 测试