#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
NOAA ISD API 数据获取脚本
========================
功能：通过 NOAA API 获取 69 个站点的多变量小时观测数据

可获取变量:
- 温度 (TEMPERATURE)
- 露点 (DEW_POINT) 
- 湿度 (RELATIVE_HUMIDITY)
- 风速 (WIND_SPEED)
- 风向 (WIND_DIRECTION)
- 降水 (PRECIPITATION)
- 海平面气压 (SEA_LEVEL_PRESSURE)

作者：GRA 团队
日期：2026-03-11
"""

import requests
import pandas as pd
from pathlib import Path
import time
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/noaa_api_fetch.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# NOAA ISD API 基础 URL
BASE_URL = "https://www.ncei.noaa.gov/access/services/data/v1"

# 可获取的数据类型（先测试基本变量）
DATA_TYPES = [
    "TEMPERATURE",
    "DEW_POINT",
    "WIND_SPEED",
    "PRECIPITATION"
]

# 69 个站点列表（从 station_grid_mapping.csv 读取）
def get_station_list():
    """获取站点列表"""
    mapping_file = Path('station_grid_mapping.csv')
    if not mapping_file.exists():
        logging.error("站点映射文件不存在")
        return []
    
    df = pd.read_csv(mapping_file)
    # 提取站点 ID 并转换为 NOAA 格式（去掉 -99999 后缀）
    # 533520-99999 → 53352099999
    stations = df['station_id'].str.replace('-', '').unique()
    logging.info(f"找到 {len(stations)} 个站点")
    return stations


def fetch_noaa_data(station_id, start_date, end_date):
    """
    从 NOAA API 获取单个站点数据
    """
    # 构建 URL（不使用 params，直接拼接）
    data_types_str = ','.join(DATA_TYPES)
    url = (f"{BASE_URL}?dataset=isd&stations={station_id}&startDate={start_date}"
           f"&endDate={end_date}&dataTypes={data_types_str}&format=json")
    
    logging.info(f"请求 URL: {url[:200]}...")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=120)  # 增加超时到 2 分钟
        
        # 打印响应信息
        logging.info(f"响应状态码：{response.status_code}")
        
        if response.status_code != 200:
            logging.error(f"API 返回错误：{response.status_code}")
            logging.error(f"响应内容：{response.text[:500]}")
            return None
        
        data = response.json()
        
        if not data or 'stations' not in data or len(data['stations']) == 0:
            logging.warning(f"站点 {station_id} 无数据返回")
            return None
        
        # 解析数据
        records = []
        for station in data['stations']:
            for obs in station.get('observations', []):
                record = {
                    'timestamp': obs.get('timestamp'),
                    'temperature': obs.get('temperature', {}).get('value') if obs.get('temperature') else None,
                    'dew_point': obs.get('dewPoint', {}).get('value') if obs.get('dewPoint') else None,
                    'relative_humidity': obs.get('relativeHumidity', {}).get('value') if obs.get('relativeHumidity') else None,
                    'wind_speed': obs.get('wind', {}).get('speed', {}).get('value') if obs.get('wind') and obs['wind'].get('speed') else None,
                    'wind_direction': obs.get('wind', {}).get('direction', {}).get('value') if obs.get('wind') and obs['wind'].get('direction') else None,
                    'precipitation': obs.get('precipitation', {}).get('value') if obs.get('precipitation') else None,
                    'sea_level_pressure': obs.get('seaLevelPressure', {}).get('value') if obs.get('seaLevelPressure') else None,
                }
                records.append(record)
        
        if not records:
            return None
        
        df = pd.DataFrame(records)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp')
        
        logging.info(f"站点 {station_id}: 获取到 {len(df)} 条记录")
        return df
        
    except requests.exceptions.RequestException as e:
        logging.error(f"站点 {station_id} 请求失败：{e}")
        return None
    except Exception as e:
        logging.error(f"站点 {station_id} 解析失败：{e}")
        import traceback
        logging.error(traceback.format_exc())
        return None


def aggregate_to_daily(df_hourly):
    """
    将小时数据聚合为日数据
    
    Parameters
    ----------
    df_hourly : DataFrame
        小时数据
    
    Returns
    -------
    df_daily : DataFrame
        日数据
    """
    daily = df_hourly.resample('D').agg({
        'temperature': 'mean',
        'dew_point': 'mean',
        'relative_humidity': 'mean',
        'wind_speed': 'mean',
        'precipitation': 'sum',
        'sea_level_pressure': 'mean'
    }).reset_index()
    
    # 添加日期列
    daily['date'] = daily['timestamp'].dt.date
    daily['year'] = daily['timestamp'].dt.year
    
    return daily


def main():
    """主函数"""
    logging.info("=" * 60)
    logging.info("NOAA ISD API 数据获取")
    logging.info("=" * 60)
    
    # 获取站点列表
    stations = get_station_list()
    if not stations:
        logging.error("未找到站点列表")
        return
    
    # 输出目录
    output_dir = Path('data/raw/noaa_api_data')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 测试：先获取 1 个站点 7 天的数据
    test_station = stations[0]
    logging.info(f"\n测试站点：{test_station}")
    
    df_test = fetch_noaa_data(
        station_id=test_station,
        start_date='1990-01-01',
        end_date='1990-01-07'
    )
    
    if df_test is not None:
        logging.info(f"\n测试成功！获取到 {len(df_test)} 条小时数据")
        logging.info(f"\n可用变量:")
        for col in df_test.columns:
            non_null = df_test[col].notna().sum()
            logging.info(f"  {col}: {non_null}/{len(df_test)} 非空")
        
        # 保存测试数据
        test_output = output_dir / f'{test_station}_test.csv'
        df_test.to_csv(test_output)
        logging.info(f"测试数据已保存：{test_output}")
        
        # 聚合为日数据
        df_daily = aggregate_to_daily(df_test)
        daily_output = output_dir / f'{test_station}_test_daily.csv'
        df_daily.to_csv(daily_output, index=False)
        logging.info(f"日数据已保存：{daily_output}")
        
        logging.info("\n" + "=" * 60)
        logging.info("测试完成！")
        logging.info("=" * 60)
        logging.info("\n如果测试成功，可以修改代码获取完整数据:")
        logging.info("1. 修改日期范围：start_date='1990-01-01', end_date='2023-12-31'")
        logging.info("2. 循环处理所有站点")
        logging.info("3. 添加延时避免 API 限流")
        
    else:
        logging.error("测试失败，请检查:")
        logging.error("1. 站点 ID 格式是否正确")
        logging.error("2. API 是否可访问")
        logging.error("3. 日期范围是否有数据")


if __name__ == '__main__':
    main()
