#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
单站点分位数映射（QM）偏差校正
================================
功能：
1. 加载 NOAA 站点观测数据
2. 从数据库提取对应格点的 Open-Meteo 模拟数据
3. 构建经验累积分布函数（eCDF）
4. 应用分位数映射校正
5. 生成校正前后对比分析报告

作者：GRA 团队
日期：2026-03-11
"""

import pandas as pd
import numpy as np
import psycopg2
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
from pathlib import Path
import logging
from datetime import datetime

# 配置日志
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'qm_correction.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 数据库配置
import os
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': os.getenv("POSTGRES_DB", "gra_env_db"),
    'user': os.getenv("POSTGRES_USER", "admin"),
    'password': os.getenv("POSTGRES_PASSWORD", "secure_password_dev")
}


class QuantileMapping:
    """分位数映射偏差校正器"""
    
    def __init__(self, reference_data, simulation_data):
        """
        初始化 QM 校正器
        
        Parameters
        ----------
        reference_data : pd.Series
            参考数据（NOAA 观测）
        simulation_data : pd.Series
            模拟数据（Open-Meteo）
        """
        self.reference = reference_data.dropna()
        self.simulation = simulation_data.dropna()
        
        # 计算分位数映射关系
        self.quantiles = np.linspace(0, 1, 1001)  # 0% 到 100%，步长 0.1%
        self.ref_quantiles = np.quantile(self.reference, self.quantiles)
        self.sim_quantiles = np.quantile(self.simulation, self.quantiles)
        
        logging.info(f"QM 初始化完成：参考数据{len(self.reference)}条，模拟数据{len(self.simulation)}条")
    
    def correct(self, sim_values):
        """
        对模拟数据应用分位数映射校正
        
        Parameters
        ----------
        sim_values : pd.Series or np.ndarray
            需要校正的模拟数据值
        
        Returns
        -------
        corrected : pd.Series or np.ndarray
            校正后的数据
        """
        sim_values = np.asarray(sim_values)
        corrected = np.interp(
            sim_values,
            self.sim_quantiles,
            self.ref_quantiles,
            left=self.ref_quantiles[0],
            right=self.ref_quantiles[-1]
        )
        return corrected
    
    def get_mapping_table(self):
        """返回分位数映射表"""
        return pd.DataFrame({
            'quantile': self.quantiles,
            'simulation': self.sim_quantiles,
            'reference': self.ref_quantiles
        })


def load_noaa_data(station_id, data_dir='data/processed/noaa_analysis'):
    """
    加载 NOAA 站点数据
    
    Parameters
    ----------
    station_id : str
        站点 ID（如 '533520'）
    
    Returns
    -------
    df : pd.DataFrame
        包含日期和温度、降水等变量的 DataFrame
    """
    file_path = Path(data_dir) / f'{station_id}_daily_data.csv'
    if not file_path.exists():
        raise FileNotFoundError(f"未找到站点数据文件：{file_path}")
    
    df = pd.read_csv(file_path, parse_dates=['date'])
    df = df.set_index('date')
    
    logging.info(f"加载 NOAA 站点 {station_id} 数据：{len(df)}条记录")
    return df


def get_openmeteo_data(lat, lon, start_date, end_date, conn=None):
    """
    从数据库获取 Open-Meteo 网格点数据
    
    Parameters
    ----------
    lat : float
        纬度
    lon : float
        经度
    start_date : str or datetime
        起始日期
    end_date : str or datetime
        结束日期
    conn : psycopg2 connection, optional
        数据库连接
    
    Returns
    -------
    df : pd.DataFrame
        日平均温度的 DataFrame
    """
    if conn is None:
        conn = psycopg2.connect(**DB_CONFIG)
        close_conn = True
    else:
        close_conn = False
    
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
        
        logging.info(f"加载 Open-Meteo 数据 ({lat}, {lon})：{len(df)}条记录")
        
        if close_conn:
            conn.close()
        
        return df
    except Exception as e:
        logging.error(f"数据库查询失败：{e}")
        if close_conn:
            conn.close()
        raise


def find_nearest_grid_point(station_lat, station_lon, conn=None):
    """
    查找距离站点最近的网格点
    
    Parameters
    ----------
    station_lat : float
        站点纬度
    station_lon : float
        站点经度
    
    Returns
    -------
    (lat, lon) : tuple
        最近网格点的经纬度
    """
    if conn is None:
        conn = psycopg2.connect(**DB_CONFIG)
        close_conn = True
    else:
        close_conn = False
    
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
            distance = np.sqrt(dist)
            logging.info(f"最近网格点：({lat}, {lon}), 距离：{distance:.4f}°")
            
            if close_conn:
                conn.close()
            
            return lat, lon
        else:
            raise ValueError("数据库中未找到匹配的网格点")
    except Exception as e:
        logging.error(f"查找网格点失败：{e}")
        if close_conn:
            conn.close()
        raise


def evaluate_correction(noaa_data, sim_data, corrected_data, variable_name='temperature'):
    """
    评估校正效果
    
    Parameters
    ----------
    noaa_data : pd.Series
        NOAA 观测数据
    sim_data : pd.Series
        原始模拟数据
    corrected_data : pd.Series
        校正后的数据
    variable_name : str
        变量名称
    
    Returns
    -------
    metrics : dict
        包含各种评估指标的字典
    """
    # 确保数据对齐
    df = pd.DataFrame({
        'noaa': noaa_data,
        'sim': sim_data,
        'corrected': corrected_data
    }).dropna()
    
    noaa = df['noaa']
    sim = df['sim']
    corr = df['corrected']
    
    # 计算统计指标
    metrics = {
        'variable': variable_name,
        'sample_size': len(df),
        
        # 偏差（Bias）
        'bias_original': (sim - noaa).mean(),
        'bias_corrected': (corr - noaa).mean(),
        
        # 均方根误差（RMSE）
        'rmse_original': np.sqrt(((sim - noaa)**2).mean()),
        'rmse_corrected': np.sqrt(((corr - noaa)**2).mean()),
        
        # 平均绝对误差（MAE）
        'mae_original': np.abs(sim - noaa).mean(),
        'mae_corrected': np.abs(corr - noaa).mean(),
        
        # 相关系数
        'correlation_original': stats.pearsonr(sim, noaa)[0] if SCIPY_AVAILABLE else np.corrcoef(sim, noaa)[0, 1],
        'correlation_corrected': stats.pearsonr(corr, noaa)[0] if SCIPY_AVAILABLE else np.corrcoef(corr, noaa)[0, 1],
        
        # 标准差比
        'std_ratio_original': sim.std() / noaa.std(),
        'std_ratio_corrected': corr.std() / noaa.std(),
    }
    
    # 计算改进百分比
    metrics['bias_improvement'] = (1 - abs(metrics['bias_corrected']) / abs(metrics['bias_original'])) * 100
    metrics['rmse_improvement'] = (1 - metrics['rmse_corrected'] / metrics['rmse_original']) * 100
    
    return metrics


def plot_comparison(noaa_data, sim_data, corrected_data, station_id, variable_name, output_dir):
    """
    绘制校正前后对比图
    
    Parameters
    ----------
    noaa_data : pd.Series
        NOAA 观测数据
    sim_data : pd.Series
        原始模拟数据
    corrected_data : pd.Series
        校正后的数据
    station_id : str
        站点 ID
    variable_name : str
        变量名称
    output_dir : Path
        输出目录
    """
    # 创建图表
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. 时间序列对比（最近 3 年）
    ax1 = axes[0, 0]
    df_plot = pd.DataFrame({
        'NOAA': noaa_data,
        'Open-Meteo (原始)': sim_data,
        'QM 校正后': corrected_data
    }).dropna()
    
    # 只显示最近 3 年
    recent = df_plot[df_plot.index >= (df_plot.index.max() - pd.Timedelta(days=3*365))]
    ax1.plot(recent.index, recent['NOAA'], 'k-', linewidth=2, label='NOAA 观测')
    ax1.plot(recent.index, recent['Open-Meteo (原始)'], 'r--', linewidth=1.5, label='Open-Meteo (原始)', alpha=0.7)
    ax1.plot(recent.index, recent['QM 校正后'], 'b-', linewidth=1.5, label='QM 校正后', alpha=0.7)
    ax1.set_xlabel('Date')
    ax1.set_ylabel(f'{variable_name}')
    ax1.set_title(f'Time Series Comparison (Recent 3 Years) - Station {station_id}')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. 散点图：原始 vs 观测
    ax2 = axes[0, 1]
    df_scatter = pd.DataFrame({'noaa': noaa_data, 'sim': sim_data}).dropna()
    ax2.scatter(df_scatter['noaa'], df_scatter['sim'], s=1, alpha=0.3, color='red', label='Original')
    
    # 1:1 线
    min_val = min(df_scatter['noaa'].min(), df_scatter['sim'].min())
    max_val = max(df_scatter['noaa'].max(), df_scatter['sim'].max())
    ax2.plot([min_val, max_val], [min_val, max_val], 'k-', linewidth=2, label='1:1 Line')
    
    # 拟合线
    z = np.polyfit(df_scatter['noaa'], df_scatter['sim'], 1)
    p = np.poly1d(z)
    ax2.plot(df_scatter['noaa'], p(df_scatter['noaa']), 'r--', linewidth=2, label=f'Fit: y={z[0]:.2f}x+{z[1]:.2f}')
    
    ax2.set_xlabel('NOAA Observation')
    ax2.set_ylabel('Open-Meteo Simulation')
    ax2.set_title(f'Original Simulation vs Observation')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. 散点图：校正后 vs 观测
    ax3 = axes[1, 0]
    df_scatter_corr = pd.DataFrame({'noaa': noaa_data, 'corrected': corrected_data}).dropna()
    ax3.scatter(df_scatter_corr['noaa'], df_scatter_corr['corrected'], s=1, alpha=0.3, color='blue', label='Corrected')
    ax3.plot([min_val, max_val], [min_val, max_val], 'k-', linewidth=2, label='1:1 Line')
    
    z_corr = np.polyfit(df_scatter_corr['noaa'], df_scatter_corr['corrected'], 1)
    p_corr = np.poly1d(z_corr)
    ax3.plot(df_scatter_corr['noaa'], p_corr(df_scatter_corr['noaa']), 'b--', linewidth=2, label=f'Fit: y={z_corr[0]:.2f}x+{z_corr[1]:.2f}')
    
    ax3.set_xlabel('NOAA Observation')
    ax3.set_ylabel('QM Corrected')
    ax3.set_title(f'Corrected Simulation vs Observation')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # 4. CDF 对比
    ax4 = axes[1, 1]
    ax4.hist(noaa_data, bins=50, density=True, cumulative=True, histtype='step', linewidth=2, color='black', label='NOAA')
    ax4.hist(sim_data, bins=50, density=True, cumulative=True, histtype='step', linewidth=2, color='red', label='Open-Meteo (原始)', alpha=0.7)
    ax4.hist(corrected_data, bins=50, density=True, cumulative=True, histtype='step', linewidth=2, color='blue', label='QM 校正后', alpha=0.7)
    
    ax4.set_xlabel(f'{variable_name}')
    ax4.set_ylabel('Cumulative Probability')
    ax4.set_title('Cumulative Distribution Function (CDF) Comparison')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # 保存图片
    if MATPLOTLIB_AVAILABLE:
        output_path = output_dir / f'{station_id}_{variable_name}_qm_comparison.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        logging.info(f"对比图已保存：{output_path}")
    else:
        logging.warning("Matplotlib 不可用，跳过图表生成")


def main():
    """主函数"""
    logging.info("=" * 60)
    logging.info("单站点分位数映射（QM）偏差校正")
    logging.info("=" * 60)
    
    # 配置参数
    STATION_ID = '533520'  # 北京站
    VARIABLE = 'temperature'  # 先对温度进行校正
    
    # 输出目录
    output_dir = Path('data/processed/qm_correction')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 加载 NOAA 数据
    logging.info(f"\n[1/6] 加载 NOAA 站点 {STATION_ID} 数据...")
    # 使用完整站点 ID（包含 -99999 后缀）
    full_station_id = f"{STATION_ID}-99999"
    noaa_df = load_noaa_data(full_station_id)
    
    # 获取站点坐标（从文件名推断，或从 station_grid_mapping.csv 读取）
    try:
        mapping_df = pd.read_csv('station_grid_mapping.csv')
        station_info = mapping_df[mapping_df['station_id'] == f'{STATION_ID}-99999']
        if not station_info.empty:
            station_lat = station_info['station_lat'].values[0]
            station_lon = station_info['station_lon'].values[0]
            logging.info(f"站点坐标：({station_lat}, {station_lon})")
        else:
            raise ValueError("站点信息未找到")
    except Exception as e:
        logging.warning(f"无法读取站点映射文件，使用默认坐标：{e}")
        station_lat, station_lon = 39.93, 116.28  # 北京站近似坐标
    
    # 2. 查找最近网格点
    logging.info(f"\n[2/6] 查找最近网格点...")
    conn = psycopg2.connect(**DB_CONFIG)
    grid_lat, grid_lon = find_nearest_grid_point(station_lat, station_lon, conn)
    
    # 3. 获取 Open-Meteo 数据
    logging.info(f"\n[3/6] 提取 Open-Meteo 模拟数据...")
    start_date = noaa_df.index.min()
    end_date = noaa_df.index.max()
    om_df = get_openmeteo_data(grid_lat, grid_lon, start_date, end_date, conn)
    conn.close()
    
    # 4. 数据对齐
    logging.info(f"\n[4/6] 数据对齐与预处理...")
    df_aligned = pd.DataFrame({
        'noaa': noaa_df[f'avg_{VARIABLE}'],
        'om': om_df['om_temp']
    }).dropna()
    
    logging.info(f"对齐后有效数据量：{len(df_aligned)}条")
    
    if len(df_aligned) < 100:
        logging.error("数据量过少，无法进行 QM 校正")
        return
    
    # 5. 应用分位数映射
    logging.info(f"\n[5/6] 应用分位数映射校正...")
    qm = QuantileMapping(df_aligned['noaa'], df_aligned['om'])
    df_aligned['om_corrected'] = qm.correct(df_aligned['om'])
    
    # 保存校正后的数据
    output_csv = output_dir / f'{STATION_ID}_{VARIABLE}_corrected.csv'
    df_aligned.to_csv(output_csv)
    logging.info(f"校正后数据已保存：{output_csv}")
    
    # 保存分位数映射表
    mapping_table = qm.get_mapping_table()
    mapping_csv = output_dir / f'{STATION_ID}_{VARIABLE}_qm_mapping.csv'
    mapping_table.to_csv(mapping_csv, index=False)
    logging.info(f"分位数映射表已保存：{mapping_csv}")
    
    # 6. 评估与可视化
    logging.info(f"\n[6/6] 评估校正效果...")
    metrics = evaluate_correction(
        df_aligned['noaa'],
        df_aligned['om'],
        df_aligned['om_corrected'],
        VARIABLE
    )
    
    # 打印评估结果
    logging.info("\n" + "=" * 60)
    logging.info(f"站点：{STATION_ID} ({VARIABLE})")
    logging.info("=" * 60)
    logging.info(f"样本量：{metrics['sample_size']}")
    logging.info(f"\n偏差 (Bias):")
    logging.info(f"  原始：{metrics['bias_original']:+.3f} °C")
    logging.info(f"  校正后：{metrics['bias_corrected']:+.3f} °C")
    logging.info(f"  改进：{metrics['bias_improvement']:.1f}%")
    logging.info(f"\nRMSE:")
    logging.info(f"  原始：{metrics['rmse_original']:.3f} °C")
    logging.info(f"  校正后：{metrics['rmse_corrected']:.3f} °C")
    logging.info(f"  改进：{metrics['rmse_improvement']:.1f}%")
    logging.info(f"\nMAE:")
    logging.info(f"  原始：{metrics['mae_original']:.3f} °C")
    logging.info(f"  校正后：{metrics['mae_corrected']:.3f} °C")
    logging.info(f"\n相关系数:")
    logging.info(f"  原始：{metrics['correlation_original']:.3f}")
    logging.info(f"  校正后：{metrics['correlation_corrected']:.3f}")
    logging.info(f"\n标准差比:")
    logging.info(f"  原始：{metrics['std_ratio_original']:.3f}")
    logging.info(f"  校正后：{metrics['std_ratio_corrected']:.3f}")
    logging.info("=" * 60)
    
    # 保存评估指标
    metrics_df = pd.DataFrame([metrics])
    metrics_csv = output_dir / f'{STATION_ID}_{VARIABLE}_metrics.csv'
    metrics_df.to_csv(metrics_csv, index=False)
    
    # 绘制对比图
    plot_comparison(
        df_aligned['noaa'],
        df_aligned['om'],
        df_aligned['om_corrected'],
        STATION_ID,
        VARIABLE,
        output_dir
    )
    
    logging.info(f"\nQM 校正完成！结果已保存至：{output_dir}")
    logging.info("=" * 60)


if __name__ == '__main__':
    main()
