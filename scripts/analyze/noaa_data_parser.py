"""
NOAA 站点数据解析脚本（QM 校正增强版）
功能：
- 解析 69 个 NOAA 站点的小时数据
- 转换为日数据（5 个 QM 校正变量）
- 计算相对湿度和蒸散量
- 生成数据质量报告
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
import gzip
import json
from datetime import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# 导入气象计算模块
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from meteorological_calculations import (
    calculate_relative_humidity,
    calculate_reference_evapotranspiration_simplified
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/noaa_parse.log', encoding='utf-8', mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class NOAADataParser:
    """NOAA 数据解析器"""
    
    def __init__(self):
        self.noaa_dir = Path("data/raw/noaa/noaa_raw")
        self.output_dir = Path("data/processed/noaa_analysis")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 站点列表
        self.stations = [d.name for d in self.noaa_dir.iterdir() if d.is_dir()]
        logger.info(f"发现 {len(self.stations)} 个 NOAA 站点")
    
    def parse_hourly_file(self, gz_file):
        """解析单个 .gz 文件（小时数据）"""
        try:
            year = gz_file.stem.split('.')[0][-4:]
            station_id = gz_file.parent.name
            
            hourly_data = []
            
            with gzip.open(gz_file, 'rt', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 固定宽度格式解析
                    # 年 月 日 时 温度 露点 气压 风向 风速 降水 云量
                    parts = line.split()
                    if len(parts) >= 10:
                        try:
                            year_val = int(parts[0])
                            month_val = int(parts[1])
                            day_val = int(parts[2])
                            hour_val = int(parts[3])
                            
                            # 温度（×10），需要除以 10
                            temp = float(parts[4]) / 10.0 if parts[4] != '-9999' else None
                            dewpoint = float(parts[5]) / 10.0 if parts[5] != '-9999' else None
                            
                            # 气压（hPa × 10），需要除以 10
                            pressure = float(parts[6]) / 10.0 if parts[6] != '-9999' else None
                            
                            # 风向（0-360°）
                            wind_direction = float(parts[7]) if parts[7] != '-9999' else None
                            
                            # 风速（m/s × 10），需要除以 10
                            wind_speed = float(parts[8]) / 10.0 if parts[8] != '-9999' else None
                            
                            # 降水（mm）
                            precip = float(parts[9]) if parts[9] != '-9999' else None
                            
                            record = {
                                'station_id': station_id,
                                'year': year,
                                'datetime': f"{year_val:04d}-{month_val:02d}-{day_val:02d} {hour_val:02d}:00:00",
                                'temperature': temp,
                                'dewpoint': dewpoint,
                                'pressure': pressure,
                                'wind_direction': wind_direction,
                                'wind_speed': wind_speed,
                                'precipitation': precip
                            }
                            hourly_data.append(record)
                        except Exception as e:
                            continue
            
            if hourly_data:
                df_hourly = pd.DataFrame(hourly_data)
                df_hourly['datetime'] = pd.to_datetime(df_hourly['datetime'])
                return df_hourly, year
            else:
                return None, year
                
        except Exception as e:
            logger.error(f"解析文件 {gz_file} 时出错：{e}")
            return None, None
    
    def aggregate_to_daily(self, df_hourly):
        """将小时数据聚合为日数据，并计算 QM 校正所需的 5 个变量"""
        try:
            df_hourly['date'] = df_hourly['datetime'].dt.date
            
            daily_data = []
            
            for date, group in df_hourly.groupby('date'):
                # 基础统计量
                avg_temp = group['temperature'].mean()
                max_temp = group['temperature'].max()
                min_temp = group['temperature'].min()
                avg_dewpoint = group['dewpoint'].mean()
                avg_wind_speed = group['wind_speed'].mean()
                total_precip = group['precipitation'].sum()
                
                # 计算相对湿度（基于平均温度和平均露点）
                if pd.notna(avg_temp) and pd.notna(avg_dewpoint):
                    avg_rh = calculate_relative_humidity(avg_temp, avg_dewpoint)
                else:
                    avg_rh = None
                
                # 计算蒸散量（使用简化公式，假设海拔 50 米）
                if pd.notna(avg_temp) and pd.notna(avg_rh) and pd.notna(avg_wind_speed):
                    avg_et0 = calculate_reference_evapotranspiration_simplified(
                        temp_mean=avg_temp,
                        relative_humidity=avg_rh,
                        wind_speed=avg_wind_speed,
                        elevation_m=50.0
                    )
                else:
                    avg_et0 = None
                
                daily_record = {
                    'station_id': group['station_id'].iloc[0],
                    'date': date,
                    'year': group['year'].iloc[0],
                    
                    # QM 校正的 5 个核心变量
                    'temperature': avg_temp,
                    'precipitation': total_precip,
                    'wind_speed': avg_wind_speed,
                    'relative_humidity': avg_rh,
                    'et0': avg_et0,
                    
                    # 辅助变量（用于质量控制）
                    'max_temperature': max_temp,
                    'min_temperature': min_temp,
                    'avg_dewpoint': avg_dewpoint,
                    'avg_pressure': group['pressure'].mean(),
                    
                    # 数据完整性指标
                    'hours_with_temp': group['temperature'].notna().sum(),
                    'hours_with_precip': group['precipitation'].notna().sum(),
                    'hours_with_wind': group['wind_speed'].notna().sum(),
                    'hours_with_pressure': group['pressure'].notna().sum(),
                    'hours_with_dewpoint': group['dewpoint'].notna().sum()
                }
                daily_data.append(daily_record)
            
            return pd.DataFrame(daily_data)
            
        except Exception as e:
            logger.error(f"聚合日数据时出错：{e}")
            return None
    
    def parse_single_station(self, station_id):
        """解析单个站点的所有年份数据"""
        try:
            station_path = self.noaa_dir / station_id
            gz_files = list(station_path.glob("*.gz"))
            
            if not gz_files:
                logger.warning(f"站点 {station_id} 没有找到 .gz 文件")
                return None
            
            all_daily_data = []
            
            for gz_file in gz_files:
                logger.debug(f"处理文件：{gz_file.name}")
                
                df_hourly, year = self.parse_hourly_file(gz_file)
                
                if df_hourly is not None and not df_hourly.empty:
                    df_daily = self.aggregate_to_daily(df_hourly)
                    if df_daily is not None and not df_daily.empty:
                        all_daily_data.append(df_daily)
            
            if all_daily_data:
                df_combined = pd.concat(all_daily_data, ignore_index=True)
                df_combined = df_combined.sort_values('date').reset_index(drop=True)
                logger.info(f"✓ 站点 {station_id} 解析完成，日数据行数：{len(df_combined)}")
                return df_combined
            else:
                logger.warning(f"站点 {station_id} 没有有效数据")
                return None
                
        except Exception as e:
            logger.error(f"处理站点 {station_id} 时出错：{e}")
            return None
    
    def parse_all_stations(self, max_workers=4):
        """并行解析所有站点"""
        logger.info("开始并行解析 69 个 NOAA 站点数据...")
        logger.info(f"使用 {max_workers} 个线程并行处理")
        
        results = {}
        successful_parsing = 0
        failed_parsing = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_station = {
                executor.submit(self.parse_single_station, station): station 
                for station in self.stations
            }
            
            for future in as_completed(future_to_station):
                station = future_to_station[future]
                try:
                    df = future.result()
                    if df is not None and not df.empty:
                        results[station] = df
                        successful_parsing += 1
                    else:
                        failed_parsing += 1
                        logger.warning(f"✗ 站点 {station} 解析失败或无数据")
                except Exception as e:
                    failed_parsing += 1
                    logger.error(f"✗ 站点 {station} 解析异常：{e}")
        
        logger.info(f"解析完成：成功 {successful_parsing}, 失败 {failed_parsing}")
        return results
    
    def generate_quality_report(self, parsed_data):
        """生成数据质量报告"""
        logger.info("生成数据质量报告...")
        
        report = {
            'summary': {
                'total_stations': len(self.stations),
                'successfully_parsed': len(parsed_data),
                'parse_success_rate': len(parsed_data) / len(self.stations) if self.stations else 0,
                'start_time': datetime.now().isoformat(),
                'end_time': None
            },
            'stations_detail': {},
            'overall_statistics': {}
        }
        
        all_data_combined = []
        
        for station_id, df in parsed_data.items():
            if df is not None and not df.empty:
                station_stats = {
                    'total_records': len(df),
                    'date_range': {
                        'start': str(df['date'].min()),
                        'end': str(df['date'].max())
                    },
                    'years_coverage': sorted(df['year'].unique().tolist()),
                    'data_completeness': {},
                    'missing_data': {}
                }
                
                # QM 校正的 5 个核心变量
                qm_variables = ['temperature', 'precipitation', 'wind_speed', 'relative_humidity', 'et0']
                
                for col in qm_variables:
                    if col in df.columns:
                        total = len(df)
                        valid = df[col].notna().sum()
                        missing = df[col].isna().sum()
                        
                        station_stats['data_completeness'][col] = round(valid / total * 100, 2) if total > 0 else 0
                        station_stats['missing_data'][col] = int(missing)
                
                report['stations_detail'][station_id] = station_stats
                all_data_combined.append(df)
        
        if all_data_combined:
            all_df = pd.concat(all_data_combined, ignore_index=True)
            
            overall_stats = {
                'total_records': len(all_df),
                'date_range': {
                    'start': str(all_df['date'].min()),
                    'end': str(all_df['date'].max())
                },
                'total_years': len(all_df['year'].unique()),
                'stations_with_data': len(all_df['station_id'].unique()),
                'average_completeness': {}
            }
            
            # QM 校正的 5 个核心变量
            qm_variables = ['temperature', 'precipitation', 'wind_speed', 'relative_humidity', 'et0']
            
            for col in qm_variables:
                if col in all_df.columns:
                    total = len(all_df)
                    valid = all_df[col].notna().sum()
                    overall_stats['average_completeness'][col] = round(valid / total * 100, 2) if total > 0 else 0
            
            report['overall_statistics'] = overall_stats
        
        report['summary']['end_time'] = datetime.now().isoformat()
        
        # 保存 JSON 报告
        report_path = self.output_dir / "noaa_quality_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        # 生成 CSV 报告
        self._generate_csv_report(report)
        
        logger.info(f"数据质量报告已保存：{report_path}")
        return report
    
    def _generate_csv_report(self, report):
        """生成 CSV 格式的详细报告"""
        station_rows = []
        for station_id, stats in report['stations_detail'].items():
            row = {
                'station_id': station_id,
                'total_records': stats['total_records'],
                'start_date': stats['date_range']['start'],
                'end_date': stats['date_range']['end'],
                'years_count': len(stats['years_coverage']),
                
                # QM 校正的 5 个核心变量
                'temperature_completeness': stats['data_completeness'].get('temperature', 0),
                'precipitation_completeness': stats['data_completeness'].get('precipitation', 0),
                'wind_speed_completeness': stats['data_completeness'].get('wind_speed', 0),
                'relative_humidity_completeness': stats['data_completeness'].get('relative_humidity', 0),
                'et0_completeness': stats['data_completeness'].get('et0', 0),
                
                'temperature_missing': stats['missing_data'].get('temperature', 0),
                'precipitation_missing': stats['missing_data'].get('precipitation', 0),
                'wind_speed_missing': stats['missing_data'].get('wind_speed', 0),
                'relative_humidity_missing': stats['missing_data'].get('relative_humidity', 0),
                'et0_missing': stats['missing_data'].get('et0', 0)
            }
            station_rows.append(row)
        
        df_stations = pd.DataFrame(station_rows)
        csv_path = self.output_dir / "noaa_station_quality.csv"
        df_stations.to_csv(csv_path, index=False, encoding='utf-8')
        
        logger.info(f"CSV 质量报告已保存：{csv_path}")
    
    def save_processed_data(self, parsed_data):
        """保存处理后的日数据"""
        logger.info("保存处理后的日数据...")
        
        for station_id, df in parsed_data.items():
            if df is not None and not df.empty:
                output_path = self.output_dir / f"{station_id}_daily_data.csv"
                df.to_csv(output_path, index=False, encoding='utf-8')
        
        logger.info(f"处理后的数据已保存到：{self.output_dir}")
    
    def run(self):
        """运行完整解析流程"""
        start_time = datetime.now()
        logger.info("="*80)
        logger.info("开始 NOAA 站点数据解析流程（修正版）")
        logger.info(f"总站点数：{len(self.stations)}")
        logger.info(f"开始时间：{start_time}")
        logger.info("="*80)
        
        # 解析数据
        parsed_data = self.parse_all_stations()
        
        # 生成质量报告
        quality_report = self.generate_quality_report(parsed_data)
        
        # 保存处理后的数据
        self.save_processed_data(parsed_data)
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        logger.info("="*80)
        logger.info("NOAA 站点数据解析完成!")
        logger.info(f"结束时间：{end_time}")
        logger.info(f"总耗时：{duration}")
        logger.info(f"成功解析站点：{len(parsed_data)}/{len(self.stations)}")
        logger.info(f"输出目录：{self.output_dir}")
        logger.info("="*80)
        
        return parsed_data, quality_report

def main():
    """主函数"""
    parser = NOAADataParser()
    parsed_data, quality_report = parser.run()
    
    # 打印简要汇总
    print("\n" + "="*50)
    print("NOAA 数据解析结果汇总")
    print("="*50)
    print(f"总站点数：{quality_report['summary']['total_stations']}")
    print(f"成功解析：{quality_report['summary']['successfully_parsed']}")
    print(f"解析成功率：{quality_report['summary']['parse_success_rate']*100:.1f}%")
    
    if 'overall_statistics' in quality_report:
        overall = quality_report['overall_statistics']
        print(f"总记录数：{overall.get('total_records', 0):,}")
        print(f"时间跨度：{overall['date_range']['start']} 至 {overall['date_range']['end']}")
        print(f"站点数量：{overall.get('stations_with_data', 0)}")
    
    print("="*50)
    print("详细报告已保存至:")
    print(f"- JSON: data/processed/noaa_analysis/noaa_quality_report.json")
    print(f"- CSV:  data/processed/noaa_analysis/noaa_station_quality.csv")
    print("="*50)

if __name__ == "__main__":
    main()
