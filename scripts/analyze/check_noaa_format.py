#!/usr/bin/env python3
"""
检查NOAA数据文件格式
"""

import gzip
import os

# 测试文件路径
test_file = "data/raw/noaa/noaa_raw/533520-99999/533520-99999-2023.gz"

print(f"检查文件: {test_file}")
print("=" * 60)

try:
    with gzip.open(test_file, 'rt', encoding='utf-8') as f:
        # 读取前10行
        for i, line in enumerate(f):
            if i >= 10:
                break
            line = line.strip()
            print(f"第{i+1}行: {line}")
            print(f"长度: {len(line)}")
            print(f"分割后: {line.split()}")
            print("-" * 40)
            
except Exception as e:
    print(f"错误: {e}")
