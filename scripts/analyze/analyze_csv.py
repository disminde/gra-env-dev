import pandas as pd

# 读取 CSV 文件的元数据
print("=== CSV 文件分析 ===\n")

# 只读取前 5 行查看结构
df_sample = pd.read_csv('migration_package/grid_weather_data.csv', nrows=5)
print("1. 列名和数据类型:")
print(df_sample.dtypes)
print("\n2. 前 5 行数据:")
print(df_sample)

# 统计总行数 (使用 chunksize 避免内存溢出)
print("\n3. 计算总行数...")
total_rows = 0
for chunk in pd.read_csv('migration_package/grid_weather_data.csv', chunksize=10000):
    total_rows += len(chunk)

print(f"   总行数：{total_rows:,} 条")

# 统计基本信息
df_full = pd.read_csv('migration_package/grid_weather_data.csv', 
                      parse_dates=['timestamp'],
                      low_memory=False)

print("\n4. 数据时间范围:")
print(f"   最早时间：{df_full['timestamp'].min()}")
print(f"   最晚时间：{df_full['timestamp'].max()}")

print("\n5. 网格点数量:")
unique_points = df_full[['latitude', 'longitude']].drop_duplicates()
print(f"   唯一网格点数：{len(unique_points):,}")

print("\n6. 数据完整性:")
print(f"   缺失值统计:")
print(df_full.isnull().sum())
