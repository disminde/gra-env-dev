#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全域网格点偏差校正 - IDW vs Kriging 对比
=======================================
功能：
1. 使用 IDW 和 Kriging 两种方法将站点校正因子插值到网格点
2. 交叉验证精度对比
3. 生成最终校正结果（选择最优方法）

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
from scipy.spatial import KDTree
from sklearn.model_selection import KFold
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import warnings
warnings.filterwarnings('ignore')

# 配置日志
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'domain_qm.log', encoding='utf-8'),
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


class SpatialInterpolator:
    """空间插值器（IDW + Kriging）"""
    
    def __init__(self, station_lats, station_lons, station_values):
        """
        初始化插值器
        
        Parameters
        ----------
        station_lats : array-like
            站点纬度
        station_lons : array-like
            站点经度
        station_values : array-like
            站点校正值（如 bias_correction）
        """
        self.station_lats = np.array(station_lats)
        self.station_lons = np.array(station_lons)
        self.station_values = np.array(station_values)
        self.n_stations = len(station_values)
        
        # 构建 KD 树用于快速搜索
        self.coords = np.column_stack([self.station_lons, self.station_lats])
        self.kdtree = KDTree(self.coords)
        
        # Kriging 所需参数（延迟计算）
        self.variogram_params = None
    
    def idw(self, target_lats, target_lons, power=2):
        """
        反距离权重插值（IDW）
        
        Parameters
        ----------
        target_lats : array-like
            目标点纬度
        target_lons : array-like
            目标点经度
        power : float
            距离的幂次，默认为 2
        
        Returns
        -------
        interpolated : ndarray
            插值结果
        """
        target_lats = np.asarray(target_lats)
        target_lons = np.asarray(target_lons)
        
        interpolated = np.zeros(len(target_lats))
        
        for i in range(len(target_lats)):
            # 计算到所有站点的距离
            dists = np.sqrt((self.station_lats - target_lats[i])**2 + 
                          (self.station_lons - target_lons[i])**2)
            
            # 处理重合点
            if np.any(dists == 0):
                interpolated[i] = self.station_values[dists == 0][0]
            else:
                # IDW 公式
                weights = 1.0 / (dists ** power)
                interpolated[i] = np.sum(weights * self.station_values) / np.sum(weights)
        
        return interpolated
    
    def fit_variogram(self, n_lags=15):
        """
        拟合变异函数（球状模型）
        
        Returns
        -------
        params : dict
            变异函数参数 {nugget, sill, range}
        """
        if self.variogram_params is not None:
            return self.variogram_params
        
        # 计算所有点对的距离和半方差
        from itertools import combinations
        
        lags = []
        gammas = []
        
        for i, j in combinations(range(self.n_stations), 2):
            dist = np.sqrt((self.station_lats[i] - self.station_lats[j])**2 + 
                          (self.station_lons[i] - self.station_lons[j])**2)
            half_var = 0.5 * (self.station_values[i] - self.station_values[j])**2
            
            lags.append(dist)
            gammas.append(half_var)
        
        lags = np.array(lags)
        gammas = np.array(gammas)
        
        # 分箱
        max_dist = np.percentile(lags, 95)
        lag_width = max_dist / n_lags
        
        binned_lags = []
        binned_gammas = []
        
        for i in range(n_lags):
            mask = (lags >= i * lag_width) & (lags < (i + 1) * lag_width)
            if np.sum(mask) >= 5:
                binned_lags.append(np.mean(lags[mask]))
                binned_gammas.append(np.mean(gammas[mask]))
        
        binned_lags = np.array(binned_lags)
        binned_gammas = np.array(binned_gammas)
        
        # 拟合球状模型
        from scipy.optimize import curve_fit
        
        def spherical_model(h, nugget, sill, range_param):
            result = np.ones_like(h) * (nugget + sill)
            mask = h < range_param
            h_r = h[mask] / range_param
            result[mask] = nugget + sill * (1.5 * h_r - 0.5 * h_r**3)
            return result
        
        try:
            # 初始参数猜测
            p0 = [np.min(binned_gammas), np.max(binned_gammas) - np.min(binned_gammas), np.median(binned_lags)]
            
            # 边界约束
            bounds = ([0, 0, 0], [np.max(binned_gammas)*2, np.max(binned_gammas)*2, np.max(binned_lags)*2])
            
            params, _ = curve_fit(spherical_model, binned_lags, binned_gammas, p0=p0, bounds=bounds)
            
            self.variogram_params = {
                'nugget': params[0],
                'sill': params[1],
                'range': params[2]
            }
            
            logging.info(f"变异函数拟合完成：Nugget={params[0]:.3f}, Sill={params[1]:.3f}, Range={params[2]:.2f}°")
            
        except Exception as e:
            logging.warning(f"变异函数拟合失败：{e}，使用默认参数")
            self.variogram_params = {
                'nugget': 0.1,
                'sill': 1.0,
                'range': 1.0
            }
        
        return self.variogram_params
    
    def kriging(self, target_lats, target_lons):
        """
        普通克里金插值（带数值稳定性处理）
        
        Parameters
        ----------
        target_lats : array-like
            目标点纬度
        target_lons : array-like
            目标点经度
        
        Returns
        -------
        interpolated : ndarray
            插值结果
        """
        if self.variogram_params is None:
            self.fit_variogram()
        
        nugget = self.variogram_params['nugget']
        sill = self.variogram_params['sill']
        range_param = self.variogram_params['range']
        
        # 如果变异函数参数异常，回退到 IDW
        if sill < 0.01 or range_param < 0.1:
            logging.warning("变异函数参数异常，Kriging 回退到 IDW")
            return self.idw(target_lats, target_lons)
        
        target_lats = np.asarray(target_lats)
        target_lons = np.asarray(target_lons)
        n_targets = len(target_lats)
        
        interpolated = np.zeros(n_targets)
        
        # 球状模型变异函数
        def variogram(h):
            h_r = np.where(h < range_param, h / range_param, 1.0)
            result = np.where(h < range_param, nugget + sill * (1.5 * h_r - 0.5 * h_r**3), nugget + sill)
            return np.nan_to_num(result, nan=nugget + sill)
        
        # 计算站点间的变异函数矩阵
        gamma_matrix = np.zeros((self.n_stations, self.n_stations))
        for i in range(self.n_stations):
            for j in range(i+1, self.n_stations):
                d = np.sqrt((self.station_lats[i] - self.station_lats[j])**2 + 
                           (self.station_lons[i] - self.station_lons[j])**2)
                gamma_matrix[i, j] = variogram(np.array([d]))[0]
                gamma_matrix[j, i] = gamma_matrix[i, j]
        
        # 普通克里金方程组（带拉格朗日乘子）
        A = np.zeros((self.n_stations + 1, self.n_stations + 1))
        A[:self.n_stations, :self.n_stations] = gamma_matrix
        A[self.n_stations, :self.n_stations] = 1
        A[:self.n_stations, self.n_stations] = 1
        
        # 对每个目标点进行克里金
        for i in range(n_targets):
            # 计算目标点到所有站点的距离
            dists = np.sqrt((self.station_lats - target_lats[i])**2 + 
                          (self.station_lons - target_lons[i])**2)
            
            # 目标点与站点的变异函数
            gamma_vec = variogram(dists)
            
            # 构建方程组右侧
            b = np.zeros(self.n_stations + 1)
            b[:self.n_stations] = gamma_vec
            b[self.n_stations] = 1
            
            # 求解克里金权重
            try:
                # 添加小的正则化项提高数值稳定性
                A_reg = A.copy()
                np.fill_diagonal(A_reg[:self.n_stations, :self.n_stations], 
                                A_reg[i, i] + 1e-8)
                
                w = np.linalg.solve(A_reg, b)
                weights = w[:self.n_stations]
                
                # 检查权重是否合理
                if np.any(np.abs(weights) > 1e6):
                    raise ValueError("权重过大")
                
                interpolated[i] = np.sum(weights * self.station_values)
            except Exception as e:
                # 如果求解失败，回退到 IDW
                interpolated[i] = self.idw([target_lats[i]], [target_lons[i]])[0]
        
        return interpolated


def get_station_correction_factors(variable='avg_temp'):
    """
    获取所有站点的校正因子
    
    Returns
    -------
    df : DataFrame
        包含站点坐标和校正因子的 DataFrame
    """
    # 读取校正汇总数据
    summary_file = Path('data/processed/qm_correction/qm_correction_summary.csv')
    df = pd.read_csv(summary_file)
    
    # 筛选指定变量
    var_df = df[df['variable'] == variable].copy()
    
    # 计算校正因子（原始偏差）
    var_df['correction_factor'] = var_df['bias_original']
    
    return var_df


def get_grid_points(conn):
    """从数据库获取所有网格点"""
    query = """
    SELECT DISTINCT latitude, longitude
    FROM grid_weather_data
    ORDER BY latitude, longitude
    """
    
    df = pd.read_sql_query(query, conn)
    return df


def cross_validation(stations_df, variable, n_splits=5):
    """
    交叉验证对比 IDW 和 Kriging
    
    Parameters
    ----------
    stations_df : DataFrame
        站点数据
    variable : str
        变量名
    n_splits : int
        交叉验证折数
    
    Returns
    -------
    results : dict
        精度对比结果
    """
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
    
    idw_rmse, idw_mae, idw_r2 = [], [], []
    krig_rmse, krig_mae, krig_r2 = [], [], []
    
    for fold, (train_idx, test_idx) in enumerate(kf.split(stations_df)):
        # 训练集（用于插值）
        train_df = stations_df.iloc[train_idx]
        # 测试集（用于验证）
        test_df = stations_df.iloc[test_idx]
        
        # 构建插值器
        interpolator = SpatialInterpolator(
            train_df['grid_lat'].values,
            train_df['grid_lon'].values,
            train_df['correction_factor'].values
        )
        
        # 在测试站点位置进行插值
        test_lats = test_df['grid_lat'].values
        test_lons = test_df['grid_lon'].values
        true_values = test_df['correction_factor'].values
        
        # IDW 插值
        idw_pred = interpolator.idw(test_lats, test_lons)
        
        # Kriging 插值
        krig_pred = interpolator.kriging(test_lats, test_lons)
        
        # 计算精度指标
        idw_rmse.append(np.sqrt(mean_squared_error(true_values, idw_pred)))
        idw_mae.append(mean_absolute_error(true_values, idw_pred))
        idw_r2.append(r2_score(true_values, idw_pred))
        
        krig_rmse.append(np.sqrt(mean_squared_error(true_values, krig_pred)))
        krig_mae.append(mean_absolute_error(true_values, krig_pred))
        krig_r2.append(r2_score(true_values, krig_pred))
        
        logging.info(f"Fold {fold+1}: IDW RMSE={idw_rmse[-1]:.3f}, Krig RMSE={krig_rmse[-1]:.3f}")
    
    results = {
        'variable': variable,
        'idw': {
            'rmse_mean': np.mean(idw_rmse),
            'rmse_std': np.std(idw_rmse),
            'mae_mean': np.mean(idw_mae),
            'mae_std': np.std(idw_mae),
            'r2_mean': np.mean(idw_r2),
            'r2_std': np.std(idw_r2)
        },
        'kriging': {
            'rmse_mean': np.mean(krig_rmse),
            'rmse_std': np.std(krig_rmse),
            'mae_mean': np.mean(krig_mae),
            'mae_std': np.std(krig_mae),
            'r2_mean': np.mean(krig_r2),
            'r2_std': np.std(krig_r2)
        }
    }
    
    return results


def main():
    """主函数"""
    logging.info("=" * 60)
    logging.info("全域网格点偏差校正 - IDW vs Kriging 对比")
    logging.info("=" * 60)
    
    # 输出目录
    output_dir = Path('data/processed/domain_correction')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 连接数据库
    logging.info("\n连接数据库...")
    conn = psycopg2.connect(**DB_CONFIG)
    
    # 获取所有网格点
    logging.info("获取网格点坐标...")
    grid_df = get_grid_points(conn)
    logging.info(f"网格点数量：{len(grid_df)}")
    
    # 处理每个温度变量
    variables = ['avg_temp', 'max_temp', 'min_temp']
    
    all_results = {}
    comparison_results = []
    
    for variable in variables:
        logging.info(f"\n{'='*60}")
        logging.info(f"处理变量：{variable}")
        logging.info(f"{'='*60}")
        
        # 1. 获取站点校正因子
        stations_df = get_station_correction_factors(variable)
        logging.info(f"站点数量：{len(stations_df)}")
        
        if len(stations_df) < 10:
            logging.warning(f"站点数量不足，跳过 {variable}")
            continue
        
        # 2. 交叉验证
        logging.info("\n进行 5 折交叉验证...")
        cv_results = cross_validation(stations_df, variable, n_splits=5)
        
        comparison_results.append(cv_results)
        
        # 打印对比结果
        logging.info(f"\n{variable} 精度对比:")
        logging.info(f"  IDW:    RMSE={cv_results['idw']['rmse_mean']:.3f}±{cv_results['idw']['rmse_std']:.3f}, "
                    f"MAE={cv_results['idw']['mae_mean']:.3f}, R²={cv_results['idw']['r2_mean']:.3f}")
        logging.info(f"  Kriging: RMSE={cv_results['kriging']['rmse_mean']:.3f}±{cv_results['kriging']['rmse_std']:.3f}, "
                    f"MAE={cv_results['kriging']['mae_mean']:.3f}, R²={cv_results['kriging']['r2_mean']:.3f}")
        
        # 3. 选择最优方法
        krig_improvement = (cv_results['idw']['rmse_mean'] - cv_results['kriging']['rmse_mean']) / cv_results['idw']['rmse_mean'] * 100
        
        if krig_improvement > 0:
            best_method = 'kriging'
            logging.info(f"  → 选择 Kriging (RMSE 降低 {krig_improvement:.1f}%)")
        else:
            best_method = 'idw'
            logging.info(f"  → 选择 IDW (Kriging 未改进)")
        
        # 4. 使用最优方法进行全域插值
        logging.info(f"\n使用 {best_method.upper()} 方法进行全域插值...")
        
        interpolator = SpatialInterpolator(
            stations_df['grid_lat'].values,
            stations_df['grid_lon'].values,
            stations_df['correction_factor'].values
        )
        
        grid_lats = grid_df['latitude'].values
        grid_lons = grid_df['longitude'].values
        
        if best_method == 'kriging':
            correction_factors = interpolator.kriging(grid_lats, grid_lons)
        else:
            correction_factors = interpolator.idw(grid_lats, grid_lons)
        
        # 5. 保存插值结果
        result_df = grid_df.copy()
        result_df['correction_factor'] = correction_factors
        result_df['variable'] = variable
        result_df['method'] = best_method
        
        output_file = output_dir / f'{variable}_correction_factors.csv'
        result_df.to_csv(output_file, index=False)
        logging.info(f"校正因子已保存：{output_file}")
        
        all_results[variable] = {
            'best_method': best_method,
            'krig_improvement': krig_improvement,
            'n_grid_points': len(grid_df)
        }
    
    conn.close()
    
    # 6. 生成综合对比报告
    logging.info("\n生成对比报告...")
    
    report_df = []
    for result in comparison_results:
        report_df.append({
            'variable': result['variable'],
            'idw_rmse': result['idw']['rmse_mean'],
            'idw_mae': result['idw']['mae_mean'],
            'idw_r2': result['idw']['r2_mean'],
            'krig_rmse': result['kriging']['rmse_mean'],
            'krig_mae': result['kriging']['mae_mean'],
            'krig_r2': result['kriging']['r2_mean'],
            'best_method': all_results[result['variable']]['best_method'],
            'improvement_pct': all_results[result['variable']]['krig_improvement']
        })
    
    report_df = pd.DataFrame(report_df)
    report_file = output_dir / 'interpolation_comparison_report.csv'
    report_df.to_csv(report_file, index=False)
    
    # 打印最终报告
    logging.info("\n" + "=" * 60)
    logging.info("全域校正完成 - 方法对比总结")
    logging.info("=" * 60)
    logging.info(f"{'变量':<12} {'IDW RMSE':<10} {'Krig RMSE':<10} {'改进':<8} {'选择方法':<10}")
    logging.info("-" * 60)
    
    for _, row in report_df.iterrows():
        improvement_str = f"{row['improvement_pct']:+.1f}%"
        logging.info(f"{row['variable']:<12} {row['idw_rmse']:<10.3f} {row['krig_rmse']:<10.3f} "
                    f"{improvement_str:<8} {row['best_method']:<10}")
    
    logging.info("=" * 60)
    logging.info(f"\n输出目录：{output_dir}")
    logging.info("=" * 60)


if __name__ == '__main__':
    main()
