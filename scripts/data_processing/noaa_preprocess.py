"""
NOAA ISD-Lite 数据预处理脚本
功能：
1. 解析 .gz 格式的 NOAA ISD-Lite 原始数据
2. 数据清洗（处理 -9999 缺失值、单位转换）
3. 聚合为日均值
4. 计算相对湿度（从露点温度和气温）
5. 生成数据质量报告
6. 保存处理后的数据

输入：data/raw/noaa/noaa_raw/{station_id}/{station_id}-{year}.gz
输出：data/processed/noaa_daily/{station_id}_daily_data.csv
"""

import os
import sys
import gzip
import pandas as pd
import numpy as np
import json
from datetime import datetime
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scripts/data_processing/noaa_preprocess.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def calculate_relative_humidity(temp_c, dewpoint_c):
    """
    根据气温和露点温度计算相对湿度
    使用 Magnus 公式的简化版本
    
    参数:
        temp_c: 气温 (°C)
        dewpoint_c: 露点温度 (°C)
    
    返回:
        relative_humidity: 相对湿度 (%)
    """
    # 检查有效性
    if pd.isna(temp_c) or pd.isna(dewpoint_c):
        return np.nan
    
    # Magnus 公式常数
    a = 17.27
    b = 237.7
    
    # 计算饱和水汽压 (es) 和实际水汽压 (e)
    es = 6.112 * np.exp((a * temp_c) / (b + temp_c))
    e = 6.112 * np.exp((a * dewpoint_c) / (b + dewpoint_c))
    
    # 计算相对湿度
    rh = (e / es) * 100.0
    
    # 限制在合理范围内 (0-100%)
    rh = np.clip(rh, 0, 100)
    
    return rh


def parse_isd_lite_file(file_path):
    """
    解析单个 ISD-Lite 格式的 .gz 文件
    
    ISD-Lite 格式说明:
    列：Year, Month, Day, Hour, Air Temp, Dew Point, Pressure, Wind Dir, Wind Speed, Sky Cond, Precip-1h, Precip-6h
    单位：温度和露点缩放因子为 10 (例如 321 = 32.1°C)
    缺失值：-9999
    
    参数:
        file_path: .gz 文件路径
    
    返回:
        DataFrame: 解析后的小时数据
    """
    try:
        # 读取压缩文件
        with gzip.open(file_path, 'rt') as f:
            df = pd.read_csv(
                f,
                delim_whitespace=True,
                header=None,
                names=[
                    "Year", "Month", "Day", "Hour",
                    "AirTemp", "DewPoint", "Pressure",
                    "WindDir", "WindSpeed", "SkyCond",
                    "Precip1h", "Precip6h"
                ]
            )
        
        logger.info(f"  ✓ 成功读取 {len(df)} 条记录")
        return df
    
    except Exception as e:
        logger.error(f"  ✗ 读取失败：{e}")
        return None


def clean_isd_lite_data(df):
    """
    清洗 ISD-Lite 数据
    
    处理:
    1. 替换 -9999 为 NaN
    2. 单位转换（温度、露点、风速等除以 10）
    3. 构建时间戳
    4. 去除无效数据
    
    参数:
        df: 原始 DataFrame
    
    返回:
        DataFrame: 清洗后的数据
    """
    if df is None or df.empty:
        return None
    
    df_clean = df.copy()
    
    # 1. 替换缺失值 -9999 为 NaN
    df_clean = df_clean.replace(-9999, np.nan)
    
    # 2. 单位转换（缩放因子为 10 的变量）
    temp_vars = ["AirTemp", "DewPoint"]
    for var in temp_vars:
        if var in df_clean.columns:
            df_clean[var] = df_clean[var] / 10.0
    
    # 风速也是缩放 10 倍
    if "WindSpeed" in df_clean.columns:
        df_clean["WindSpeed"] = df_clean["WindSpeed"] / 10.0
    
    # 降水是 10 倍缩放（单位：mm）
    precip_vars = ["Precip1h", "Precip6h"]
    for var in precip_vars:
        if var in df_clean.columns:
            df_clean[var] = df_clean[var] / 10.0
    
    # 气压是 10 倍缩放（单位：hPa）
    if "Pressure" in df_clean.columns:
        df_clean["Pressure"] = df_clean["Pressure"] / 10.0
    
    # 3. 构建时间戳
    df_clean["timestamp"] = pd.to_datetime(df_clean[["Year", "Month", "Day", "Hour"]])
    
    # 4. 提取日期（用于聚合）
    df_clean["date"] = df_clean["timestamp"].dt.date
    
    # 5. 计算相对湿度
    logger.info("  计算相对湿度...")
    df_clean["RelativeHumidity"] = df_clean.apply(
        lambda row: calculate_relative_humidity(row["AirTemp"], row["DewPoint"]),
        axis=1
    )
    
    return df_clean


def aggregate_to_daily(df_clean):
    """
    将小时数据聚合为日均值
    
    聚合规则:
    - 温度、露点、相对湿度、气压、风速：日平均
    - 降水：日累积
    - 风向：日主导风向（众数）
    
    参数:
        df_clean: 清洗后的小时数据
    
    返回:
        DataFrame: 日均值数据
    """
    if df_clean is None or df_clean.empty:
        return None
    
    logger.info(f"  聚合前小时数据：{len(df_clean)} 条")
    
    # 按日期分组
    daily_data = []
    
    for date, group in df_clean.groupby("date"):
        # 计算有效观测次数
        valid_hours = group["AirTemp"].notna().sum()
        
        # 日平均温度
        temp_mean = group["AirTemp"].mean()
        
        # 日最高/最低温度
        temp_max = group["AirTemp"].max()
        temp_min = group["AirTemp"].min()
        
        # 日平均露点
        dewpoint_mean = group["DewPoint"].mean()
        
        # 日平均相对湿度
        rh_mean = group["RelativeHumidity"].mean()
        
        # 日平均气压
        pressure_mean = group["Pressure"].mean()
        
        # 日平均风速
        wind_speed_mean = group["WindSpeed"].mean()
        
        # 日主导风向（众数）
        wind_dir_mode = group["WindDir"].mode()
        wind_dir_mode = wind_dir_mode.iloc[0] if len(wind_dir_mode) > 0 else np.nan
        
        # 日累积降水（取 6 小时累积的最大值*4，或 1 小时累积的和）
        # 这里使用 6 小时累积降水
        precip_6h_max = group["Precip6h"].max()
        if pd.notna(precip_6h_max) and precip_6h_max > 0:
            precip_daily = precip_6h_max * 4  # 近似估算
        else:
            # 使用 1 小时累积
            precip_daily = group["Precip1h"].sum()
        
        daily_data.append({
            "date": pd.to_datetime(date),
            "temp_mean": temp_mean,
            "temp_max": temp_max,
            "temp_min": temp_min,
            "dewpoint_mean": dewpoint_mean,
            "rh_mean": rh_mean,
            "pressure_mean": pressure_mean,
            "wind_speed_mean": wind_speed_mean,
            "wind_dir_mode": wind_dir_mode,
            "precip_daily": precip_daily,
            "valid_hours": valid_hours
        })
    
    df_daily = pd.DataFrame(daily_data)
    
    logger.info(f"  ✓ 聚合后日数据：{len(df_daily)} 天")
    
    return df_daily


def process_station(station_id, raw_dir, output_dir, start_year=1990, end_year=2023):
    """
    处理单个站点的所有年份数据
    
    参数:
        station_id: 站点 ID (格式：USAF-WBAN)
        raw_dir: 原始数据目录
        output_dir: 输出数据目录
        start_year: 起始年份
        end_year: 结束年份
    
    返回:
        dict: 处理统计信息
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"处理站点：{station_id}")
    logger.info(f"{'='*60}")
    
    station_dir = Path(raw_dir) / station_id
    
    if not station_dir.exists():
        logger.warning(f"  ✗ 站点目录不存在：{station_dir}")
        return None
    
    # 查找所有年份文件
    year_files = sorted([
        f for f in station_dir.glob("*.gz")
        if f.stem.split("-")[-1].isdigit()
    ])
    
    if not year_files:
        logger.warning(f"  ✗ 未找到数据文件")
        return None
    
    logger.info(f"  找到 {len(year_files)} 个年份文件")
    
    # 处理每个年份
    all_daily_data = []
    stats = {
        "station_id": station_id,
        "years_processed": [],
        "total_days": 0,
        "data_completeness": {}
    }
    
    for file_path in year_files:
        # 提取年份
        year = int(file_path.stem.split("-")[-1])
        
        # 检查年份范围
        if year < start_year or year > end_year:
            continue
        
        logger.info(f"\n  处理年份：{year}")
        
        # 1. 解析文件
        df_hourly = parse_isd_lite_file(file_path)
        if df_hourly is None:
            continue
        
        # 2. 清洗数据
        logger.info("  清洗数据...")
        df_clean = clean_isd_lite_data(df_hourly)
        if df_clean is None:
            continue
        
        # 3. 聚合为日均值
        logger.info("  聚合为日均值...")
        df_daily = aggregate_to_daily(df_clean)
        if df_daily is None or df_daily.empty:
            continue
        
        # 4. 添加站点信息
        df_daily["station_id"] = station_id
        
        all_daily_data.append(df_daily)
        stats["years_processed"].append(year)
        stats["total_days"] += len(df_daily)
        
        # 5. 计算数据完整性（该年份期望天数 vs 实际天数）
        expected_days = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
        actual_days = len(df_daily)
        completeness = (actual_days / expected_days) * 100
        stats["data_completeness"][year] = {
            "expected": expected_days,
            "actual": actual_days,
            "completeness": round(completeness, 2)
        }
        
        logger.info(f"  ✓ {year} 年完成：{actual_days}/{expected_days} 天 ({completeness:.1f}%)")
    
    if not all_daily_data:
        logger.warning(f"  ✗ 没有成功处理任何数据")
        return None
    
    # 合并所有年份数据
    logger.info("\n  合并所有年份数据...")
    df_all = pd.concat(all_daily_data, ignore_index=True)
    df_all = df_all.sort_values("date").reset_index(drop=True)
    
    # 保存结果
    output_path = Path(output_dir) / f"{station_id}_daily_data.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"  保存数据到：{output_path}")
    df_all.to_csv(output_path, index=False, encoding='utf-8')
    
    logger.info(f"  ✓ 站点 {station_id} 处理完成！")
    logger.info(f"    - 总天数：{stats['total_days']}")
    logger.info(f"    - 年份范围：{min(stats['years_processed'])}-{max(stats['years_processed'])}")
    
    return stats


def generate_quality_report(all_stats, output_dir):
    """
    生成数据质量报告
    
    参数:
        all_stats: 所有站点的处理统计信息
        output_dir: 输出目录
    """
    logger.info("\n" + "="*60)
    logger.info("生成数据质量报告")
    logger.info("="*60)
    
    if not all_stats:
        logger.warning("  没有统计数据，无法生成报告")
        return
    
    # 转换为 DataFrame
    df_stats = []
    for stats in all_stats:
        if stats is None:
            continue
        
        # 计算平均完整性
        completeness_values = [v["completeness"] for v in stats["data_completeness"].values()]
        avg_completeness = np.mean(completeness_values) if completeness_values else 0
        
        df_stats.append({
            "station_id": stats["station_id"],
            "total_days": stats["total_days"],
            "years_count": len(stats["years_processed"]),
            "year_range": f"{min(stats['years_processed'])}-{max(stats['years_processed'])}",
            "avg_completeness": round(avg_completeness, 2),
            "min_completeness": round(min(completeness_values), 2) if completeness_values else 0,
            "max_completeness": round(max(completeness_values), 2) if completeness_values else 0
        })
    
    df_quality = pd.DataFrame(df_stats)
    
    # 保存 CSV 报告
    csv_path = Path(output_dir) / "noaa_station_quality.csv"
    df_quality.to_csv(csv_path, index=False, encoding='utf-8')
    logger.info(f"  ✓ 站点质量报告：{csv_path}")
    
    # 生成 JSON 详细报告
    json_report = {
        "report_date": datetime.now().isoformat(),
        "total_stations": len(df_quality),
        "summary": {
            "avg_days_per_station": round(df_quality["total_days"].mean(), 1),
            "avg_completeness": round(df_quality["avg_completeness"].mean(), 2),
            "stations_with_high_quality": int((df_quality["avg_completeness"] >= 90).sum()),
            "stations_with_medium_quality": int(((df_quality["avg_completeness"] >= 70) & (df_quality["avg_completeness"] < 90)).sum()),
            "stations_with_low_quality": int((df_quality["avg_completeness"] < 70).sum())
        },
        "stations": df_quality.to_dict(orient="records")
    }
    
    json_path = Path(output_dir) / "noaa_quality_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)
    logger.info(f"  ✓ 质量报告 JSON: {json_path}")
    
    # 打印摘要
    logger.info("\n" + "="*60)
    logger.info("数据质量摘要")
    logger.info("="*60)
    logger.info(f"  处理站点总数：{json_report['total_stations']}")
    logger.info(f"  平均每站天数：{json_report['summary']['avg_days_per_station']}")
    logger.info(f"  平均数据完整性：{json_report['summary']['avg_completeness']}%")
    logger.info(f"  高质量站点 (>90%): {json_report['summary']['stations_with_high_quality']}")
    logger.info(f"  中等质量站点 (70-90%): {json_report['summary']['stations_with_medium_quality']}")
    logger.info(f"  低质量站点 (<70%): {json_report['summary']['stations_with_low_quality']}")


def main():
    """
    主函数：批量处理所有 NOAA 站点数据
    """
    logger.info("\n" + "="*60)
    logger.info("NOAA ISD-Lite 数据预处理开始")
    logger.info("="*60)
    
    # 路径配置
    base_dir = Path(__file__).parent.parent.parent
    raw_dir = base_dir / "data" / "raw" / "noaa" / "noaa_raw"
    output_dir = base_dir / "data" / "processed" / "noaa_daily"
    
    # 检查原始数据目录
    if not raw_dir.exists():
        logger.error(f"原始数据目录不存在：{raw_dir}")
        return
    
    # 获取所有站点目录
    station_dirs = [d for d in raw_dir.iterdir() if d.is_dir()]
    logger.info(f"发现 {len(station_dirs)} 个站点目录")
    
    # 处理每个站点
    all_stats = []
    
    for i, station_dir in enumerate(station_dirs, 1):
        station_id = station_dir.name
        logger.info(f"\n[{i}/{len(station_dirs)}] 处理站点 {station_id}")
        
        stats = process_station(station_id, raw_dir, output_dir)
        if stats:
            all_stats.append(stats)
    
    # 生成质量报告
    generate_quality_report(all_stats, output_dir)
    
    logger.info("\n" + "="*60)
    logger.info("NOAA 数据预处理全部完成！")
    logger.info("="*60)
    logger.info(f"输出目录：{output_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"处理过程中发生错误：{e}", exc_info=True)
        sys.exit(1)
