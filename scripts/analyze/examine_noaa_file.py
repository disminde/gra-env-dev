#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查 NOAA 原始数据文件格式，查看包含哪些变量
"""

import gzip
import os
from pathlib import Path

# 查看一个 NOAA 原始文件
def examine_noaa_file(file_path):
    """
    检查 NOAA 原始文件的内容格式
    """
    print(f"\n检查文件: {file_path}")
    
    try:
        with gzip.open(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
            lines = []
            for i, line in enumerate(f):
                if i < 100:  # 只读取前 100 行
                    lines.append(line.strip())
                else:
                    break
            
        print(f"文件有 {len(lines)} 行")
        print("\n前 20 行内容:")
        for i, line in enumerate(lines[:20]):
            print(f"{i+1:3d}: {line}")
        
        # 分析每一行的格式
        if lines:
            print("\n行格式分析:")
            first_line = lines[0]
            print(f"第一行长度: {len(first_line)}")
            print(f"前 100 个字符: {first_line[:100]}")
            
            # 尝试分割字段
            parts = first_line.split()
            print(f"\n分割后字段数: {len(parts)}")
            print(f"前 10 个字段: {parts[:10]}")
            
    except Exception as e:
        print(f"读取文件失败: {e}")

# 主函数
def main():
    # 找到一个 NOAA 原始文件
    noaa_dir = Path('data/raw/noaa/noaa_raw')
    
    # 找到第一个站点目录
    station_dirs = list(noaa_dir.iterdir())
    if not station_dirs:
        print("未找到站点目录")
        return
    
    station_dir = station_dirs[0]
    print(f"使用站点: {station_dir.name}")
    
    # 找到一个 .gz 文件
    gz_files = list(station_dir.glob('*.gz'))
    if not gz_files:
        print("未找到 .gz 文件")
        return
    
    gz_file = gz_files[0]
    examine_noaa_file(gz_file)

if __name__ == '__main__':
    main()
