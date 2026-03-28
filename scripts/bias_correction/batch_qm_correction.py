#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量 QM 偏差校正
==============
功能：对所有 69 个 NOAA 站点和所有变量进行分位数映射校正

作者：GRA 团队
日期：2026-03-11
"""

import pandas as pd
import numpy as np
import psycopg2
import os
from pathlib import Path
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# 配置日志
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'batch_qm.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': os.getenv("POSTGRES_DB", "gra_env_db"),
    'user': os.getenv("POSTGRES_USER", "admin"),
    'password': os.getenv("POSTGRES_PASSWORD", "secure_password_dev")
}


class QuantileMapping:
    """分位数映射校正器"""
    
    def __init__(self, reference_data, simulation_data):
        self.reference = reference_data.dropna()
        self.simulation = simulation_data.dropna()
        
        # 计算分位数映射关系（1001 个分位点）
        self.quantiles = np.linspace(0, 1, 1001)
        self.ref_quantiles = np.quantile(self.reference, self.quantiles)
        self.sim_quantiles = np.quantile(self.simulation, self.quantiles)
    
    def correct(self, sim_values):
        """应用分位数映射校正"""
        sim_values = np.asarray(sim_values)
        corrected = np.interp(
            sim_values,
            self.sim_quantiles,
            self.ref_quantiles,
            left=self.ref_quantiles[0],
            right=self.ref_quantiles[-1]
        )
        return corrected


def get_station_list():
    """获取所有 NOAA 站点列表"""
    quality_file = Path('data/processed/noaa_analysis/noaa_station_quality.csv')
    df = pd.read_csv(quality_file)
    return df['station_id'].tolist()


def get_station_coords(station_id):
    """获取站点坐标"""
    try:
        mapping_df = pd.read_csv('station_grid_mapping.csv')
        station_info = mapping_df[mapping_df['station_id'] == station_id]
        if not station_info.empty:
            return station_info['station_lat'].values[0], station_info['station_lon'].values[0]
    except:
        pass
    
    # 默认坐标（北京站）
    return 39.93, 116.28


def find_nearest_grid_point(station_lat, station_lon, conn):
    """查找最近的网格点"""
    try:
        cur = conn.cursor()
        query = """
        SELECT latitude, longitude,
               POW(latitude - %s::DOUBLE PRECISION, 2) + POW(longitude - %s::DOUBLE PRECISION, 2) as dist
        FROM grid_weather_data
        ORDER BY dist
        LIMIT 1
        """
        cur.execute(query, (float(station_lat), float(station_lon)))
        result = cur.fetchone()
        cur.close()
        
        if result:
            lat, lon, dist = result
            return lat, lon, np.sqrt(dist)
    except Exception as e:
        logging.error(f"查找网格点失败：{e}")
    
    return None, None, None


def get_openmeteo_data(lat, lon, start_date, end_date, conn):
    """从数据库获取 Open-Meteo 数据"""
    try:
        query = """
        SELECT 
            DATE(timestamp) as date,
            AVG(temperature) as om_temp,
            SUM(precipitation) as om_precip
        FROM grid_weather_data
        WHERE latitude = %s 
          AND longitude = %s
          AND DATE(timestamp) BETWEEN %s AND %s
        GROUP BY DATE(timestamp)
        ORDER BY date
        """
        
        df = pd.read_sql_query(query, conn, params=[lat, lon, start_date, end_date])
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        
        return df
    except Exception as e:
        logging.error(f"获取 Open-Meteo 数据失败：{e}")
        return None


def process_station(station_id, output_dir):
    """处理单个站点的 QM 校正"""
    try:
        # 1. 加载 NOAA 数据
        noaa_file = Path(f'data/processed/noaa_analysis/{station_id}_daily_data.csv')
        if not noaa_file.exists():
            logging.warning(f"站点数据文件不存在：{station_id}")
            return None
        
        noaa_df = pd.read_csv(noaa_file, parse_dates=['date'])
        noaa_df = noaa_df.set_index('date')
        
        # 2. 获取站点坐标
        station_lat, station_lon = get_station_coords(station_id)
        
        # 3. 连接数据库
        conn = psycopg2.connect(**DB_CONFIG)
        
        # 4. 查找最近网格点
        grid_lat, grid_lon, distance = find_nearest_grid_point(station_lat, station_lon, conn)
        
        if grid_lat is None:
            conn.close()
            logging.warning(f"未找到匹配的网格点：{station_id}")
            return None
        
        # 5. 获取 Open-Meteo 数据
        start_date = noaa_df.index.min()
        end_date = noaa_df.index.max()
        om_df = get_openmeteo_data(grid_lat, grid_lon, start_date, end_date, conn)
        conn.close()
        
        if om_df is None or len(om_df) < 100:
            logging.warning(f"Open-Meteo 数据不足：{station_id}")
            return None
        
        # 6. 处理每个变量
        results = {}
        
        # 温度变量
        for var_name, noaa_col, om_col in [
            ('avg_temp', 'avg_temperature', 'om_temp'),
            ('max_temp', 'max_temperature', 'om_temp'),
            ('min_temp', 'min_temperature', 'om_temp'),
        ]:
            if noaa_col not in noaa_df.columns or om_col not in om_df.columns:
                continue
            
            # 数据对齐
            df_aligned = pd.DataFrame({
                'noaa': noaa_df[noaa_col],
                'om': om_df[om_col]
            }).dropna()
            
            if len(df_aligned) < 100:
                continue
            
            # 应用 QM 校正
            qm = QuantileMapping(df_aligned['noaa'], df_aligned['om'])
            df_aligned['om_corrected'] = qm.correct(df_aligned['om'])
            
            # 计算评估指标
            noaa_vals = df_aligned['noaa'].values
            om_vals = df_aligned['om'].values
            corr_vals = df_aligned['om_corrected'].values
            
            bias_orig = np.mean(om_vals - noaa_vals)
            bias_corr = np.mean(corr_vals - noaa_vals)
            rmse_orig = np.sqrt(np.mean((om_vals - noaa_vals)**2))
            rmse_corr = np.sqrt(np.mean((corr_vals - noaa_vals)**2))
            
            results[var_name] = {
                'bias_original': bias_orig,
                'bias_corrected': bias_corr,
                'rmse_original': rmse_orig,
                'rmse_corrected': rmse_corr,
                'bias_improvement': (1 - abs(bias_corr) / abs(bias_orig)) * 100 if abs(bias_orig) > 0.01 else 0,
                'rmse_improvement': (1 - rmse_corr / rmse_orig) * 100 if rmse_orig > 0 else 0,
                'sample_size': len(df_aligned)
            }
            
            # 保存校正后数据
            output_file = output_dir / f'{station_id}_{var_name}_corrected.csv'
            df_aligned.to_csv(output_file)
        
        # 降水变量（特殊处理，因为有大量 0 值）
        if 'total_precipitation' in noaa_df.columns and 'om_precip' in om_df.columns:
            df_aligned = pd.DataFrame({
                'noaa': noaa_df['total_precipitation'],
                'om': om_df['om_precip']
            }).dropna()
            
            if len(df_aligned) >= 100:
                qm = QuantileMapping(df_aligned['noaa'], df_aligned['om'])
                df_aligned['om_corrected'] = qm.correct(df_aligned['om'])
                
                # 降水校正值不能为负
                df_aligned['om_corrected'] = np.maximum(df_aligned['om_corrected'], 0)
                
                noaa_vals = df_aligned['noaa'].values
                om_vals = df_aligned['om'].values
                corr_vals = df_aligned['om_corrected'].values
                
                results['precipitation'] = {
                    'bias_original': np.mean(om_vals - noaa_vals),
                    'bias_corrected': np.mean(corr_vals - noaa_vals),
                    'rmse_original': np.sqrt(np.mean((om_vals - noaa_vals)**2)),
                    'rmse_corrected': np.sqrt(np.mean((corr_vals - noaa_vals)**2)),
                    'sample_size': len(df_aligned)
                }
                
                output_file = output_dir / f'{station_id}_precipitation_corrected.csv'
                df_aligned.to_csv(output_file)
        
        logging.info(f"✓ 完成站点 {station_id}: {len(results)} 个变量")
        
        return {
            'station_id': station_id,
            'grid_lat': grid_lat,
            'grid_lon': grid_lon,
            'distance': distance,
            'variables': results
        }
        
    except Exception as e:
        logging.error(f"处理站点 {station_id} 失败：{e}")
        return None


def main():
    """主函数"""
    logging.info("=" * 60)
    logging.info("批量 QM 偏差校正 - 69 个 NOAA 站点")
    logging.info("=" * 60)
    
    # 输出目录
    output_dir = Path('data/processed/qm_correction')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取所有站点
    station_ids = get_station_list()
    logging.info(f"找到 {len(station_ids)} 个站点")
    
    # 并行处理站点
    results = []
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        # 提交所有任务
        future_to_station = {
            executor.submit(process_station, station_id, output_dir): station_id
            for station_id in station_ids
        }
        
        # 处理完成的任务
        for future in tqdm(as_completed(future_to_station), total=len(station_ids), desc="处理站点"):
            station_id = future_to_station[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                logging.error(f"站点 {station_id} 处理异常：{e}")
    
    # 生成综合报告
    logging.info("\n生成综合质量报告...")
    
    # 汇总统计
    summary_data = []
    for result in results:
        for var_name, metrics in result['variables'].items():
            summary_data.append({
                'station_id': result['station_id'],
                'grid_lat': result['grid_lat'],
                'grid_lon': result['grid_lon'],
                'distance_deg': round(result['distance'], 4) if result['distance'] else None,
                'variable': var_name,
                'bias_original': round(metrics['bias_original'], 3),
                'bias_corrected': round(metrics['bias_corrected'], 4),
                'bias_improvement': round(metrics.get('bias_improvement', 0), 1),
                'rmse_original': round(metrics['rmse_original'], 3),
                'rmse_corrected': round(metrics['rmse_corrected'], 3),
                'rmse_improvement': round(metrics.get('rmse_improvement', 0), 1),
                'sample_size': metrics['sample_size']
            })
    
    summary_df = pd.DataFrame(summary_data)
    summary_df.to_csv(output_dir / 'qm_correction_summary.csv', index=False)
    
    # 打印统计摘要
    logging.info("\n" + "=" * 60)
    logging.info("QM 校正完成统计")
    logging.info("=" * 60)
    logging.info(f"成功处理站点：{len(results)}/{len(station_ids)}")
    logging.info(f"总变量数：{len(summary_data)}")
    
    if len(summary_data) > 0:
        avg_bias_improvement = np.mean([abs(s['bias_improvement']) for s in summary_data if s['bias_improvement'] != 0])
        avg_rmse_improvement = np.mean([s['rmse_improvement'] for s in summary_data if s['rmse_improvement'] != 0])
        logging.info(f"\n平均 Bias 改进：{avg_bias_improvement:.1f}%")
        logging.info(f"平均 RMSE 改进：{avg_rmse_improvement:.1f}%")
    
    logging.info(f"\n输出目录：{output_dir}")
    logging.info("=" * 60)


if __name__ == '__main__':
    main()
