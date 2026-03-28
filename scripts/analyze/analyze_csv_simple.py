import csv

print("=== CSV 文件分析 ===\n")

# 读取前 5 行
with open('migration_package/grid_weather_data.csv', 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    header = next(reader)
    print("1. 列名:")
    print(header)
    print("\n2. 前 5 行数据:")
    for i, row in enumerate(reader):
        if i < 5:
            print(row)
        else:
            break

# 统计行数
print("\n3. 计算总行数...")
with open('migration_package/grid_weather_data.csv', 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader)  # 跳过表头
    total_rows = sum(1 for _ in reader)
    print(f"   总行数：{total_rows:,} 条")

# 估算文件大小
import os
file_size = os.path.getsize('migration_package/grid_weather_data.csv')
print(f"\n4. 文件大小：{file_size / (1024*1024):.2f} MB")
