"""
内存消耗监控脚本
用于实时监控迁移过程的内存使用情况
"""

import psutil
import time
from datetime import datetime
import sys

def get_process_memory(process_name):
    """获取指定进程的内存使用"""
    total_mem = 0
    for proc in psutil.process_iter(['name', 'memory_info']):
        try:
            if process_name.lower() in proc.info['name'].lower():
                total_mem += proc.info['memory_info'].rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total_mem

def monitor():
    """主监控循环"""
    print("=" * 80)
    print("📊 数据迁移内存监控")
    print("=" * 80)
    print(f"开始时间：{datetime.now().strftime('%H:%M:%S')}")
    print("按 Ctrl+C 停止监控\n")
    
    print(f"{'时间':<10} | {'Python':<10} | {'PostgreSQL':<12} | {'系统总内存':<12} | {'使用率':<8}")
    print("-" * 80)
    
    start_time = time.time()
    
    try:
        while True:
            current_time = datetime.now().strftime('%H:%M:%S')
            
            # 获取 Python 进程内存（迁移脚本）
            python_mem = get_process_memory('python') / 1024 / 1024  # MB
            
            # 获取 PostgreSQL 进程内存（Docker 容器内）
            postgres_mem = get_process_memory('postgres') / 1024 / 1024  # MB
            
            # 系统总内存
            system_mem = psutil.virtual_memory()
            system_used_gb = system_mem.used / 1024 / 1024 / 1024
            system_percent = system_mem.percent
            
            # 显示
            print(f"{current_time:<10} | {python_mem:>8.1f} MB  | {postgres_mem:>10.1f} MB   | "
                  f"{system_used_gb:>10.2f} GB  | {system_percent:>6.1f}%")
            
            # 警告
            if system_percent > 85:
                print(f"  ⚠️  警告：系统内存使用率过高！({system_percent}%)")
            elif postgres_mem > 600:
                print(f"  ⚠️  警告：PostgreSQL 内存使用异常！({postgres_mem:.1f} MB)")
            
            time.sleep(5)  # 每 5 秒更新一次
            
    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n监控停止，运行时间：{elapsed/60:.1f} 分钟")

if __name__ == "__main__":
    monitor()
