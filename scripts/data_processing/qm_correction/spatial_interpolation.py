"""
空间插值模块 - 将站点校正因子插值到全域网格

功能:
    1. 实现反距离加权插值 (IDW)
    2. 实现克里金插值 (Kriging)
    3. 将站点校正因子插值到所有网格点
    4. 生成全域校正后的数据

扩展性:
    - 预留 ET0 校正因子插值
    - 支持多种插值方法
"""

import numpy as np
import pandas as pd
from pathlib import Path
import logging
from typing import Dict, List, Tuple, Optional
from scipy.spatial import distance_matrix
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel as C

logger = logging.getLogger(__name__)


class SpatialInterpolator:
    """空间插值类"""
    
    def __init__(self, method: str = 'idw', **kwargs):
        """
        初始化空间插值器
        
        Args:
            method: 插值方法 ('idw' 或 'kriging')
            **kwargs: 插值方法的额外参数
        """
        self.method = method
        self.params = kwargs
        
        logger.info(f"空间插值器初始化完成 (方法：{method})")
    
    def interpolate(
        self,
        station_coords: np.ndarray,
        station_values: np.ndarray,
        grid_coords: np.ndarray,
        **kwargs
    ) -> np.ndarray:
        """
        空间插值主函数
        
        Args:
            station_coords: 站点坐标 [(lat, lon), ...]
            station_values: 站点值 [value1, value2, ...]
            grid_coords: 网格点坐标 [(lat, lon), ...]
            **kwargs: 额外参数
        
        Returns:
            np.ndarray: 插值后的网格点值
        """
        if self.method == 'idw':
            return self._idw_interpolate(station_coords, station_values, grid_coords, **kwargs)
        
        elif self.method == 'kriging':
            return self._kriging_interpolate(station_coords, station_values, grid_coords, **kwargs)
        
        else:
            raise ValueError(f"未知的插值方法：{self.method}")
    
    def _idw_interpolate(
        self,
        station_coords: np.ndarray,
        station_values: np.ndarray,
        grid_coords: np.ndarray,
        power: float = 2.0
    ) -> np.ndarray:
        """
        反距离加权插值 (Inverse Distance Weighting)
        
        公式:
        Z(p) = Σ(Zi / d_i^p) / Σ(1 / d_i^p)
        
        Args:
            station_coords: 站点坐标
            station_values: 站点值
            grid_coords: 网格点坐标
            power: 距离的幂次（通常取 2）
        
        Returns:
            np.ndarray: 插值结果
        """
        # 计算距离矩阵
        dist_matrix = distance_matrix(grid_coords, station_coords)
        
        # 处理零距离（网格点与站点重合）
        epsilon = 1e-10
        dist_matrix = np.maximum(dist_matrix, epsilon)
        
        # 计算权重
        weights = 1.0 / (dist_matrix ** power)
        
        # 归一化权重
        weights_normalized = weights / weights.sum(axis=1, keepdims=True)
        
        # 插值
        interpolated_values = np.dot(weights_normalized, station_values)
        
        logger.info(f"IDW 插值完成：{len(grid_coords)} 个网格点")
        
        return interpolated_values
    
    def _kriging_interpolate(
        self,
        station_coords: np.ndarray,
        station_values: np.ndarray,
        grid_coords: np.ndarray,
        **kwargs
    ) -> np.ndarray:
        """
        克里金插值 (Ordinary Kriging)
        
        使用高斯过程回归实现
        
        Args:
            station_coords: 站点坐标
            station_values: 站点值
            grid_coords: 网格点坐标
        
        Returns:
            np.ndarray: 插值结果
        """
        logger.info("开始克里金插值...")
        
        # 定义核函数
        kernel = C(1.0, (1e-3, 1e3)) * RBF(length_scale=1.0, length_scale_bounds=(1e-2, 1e2))
        
        # 创建高斯过程回归模型
        gpr = GaussianProcessRegressor(
            kernel=kernel,
            alpha=0.1,
            normalize_y=True,
            n_restarts_optimizer=5
        )
        
        # 拟合模型
        gpr.fit(station_coords, station_values)
        
        # 预测
        interpolated_values, std = gpr.predict(grid_coords, return_std=True)
        
        logger.info(f"克里金插值完成：{len(grid_coords)} 个网格点")
        
        return interpolated_values


class QMFieldInterpolator:
    """QM 校正因子场插值类"""
    
    def __init__(
        self,
        output_dir: str = 'data/processed/qm_correction/interpolated',
        interpolation_method: str = 'idw'
    ):
        """
        初始化 QM 场插值器
        
        Args:
            output_dir: 输出目录
            interpolation_method: 插值方法
        """
        self.base_dir = Path(__file__).parent.parent.parent
        self.output_dir = self.base_dir / output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.interpolator = SpatialInterpolator(method=interpolation_method)
        
        logger.info(f"QM 场插值器初始化完成")
        logger.info(f"输出目录：{self.output_dir}")
    
    def interpolate_correction_factors(
        self,
        station_correction_factors: Dict[str, Dict],
        all_grid_points: pd.DataFrame,
        variable_name: str
    ) -> pd.DataFrame:
        """
        将站点校正因子插值到所有网格点
        
        Args:
            station_correction_factors: 站点校正因字典
                {
                    'station_id': {
                        'lat': float,
                        'lon': float,
                        'bias_correction': float,  # 偏差校正值
                        'scale_factor': float      # 缩放因子
                    }
                }
            all_grid_points: 所有网格点 DataFrame
                包含 'latitude', 'longitude' 列
            variable_name: 变量名
        
        Returns:
            pd.DataFrame: 包含插值后校正因子的网格点数据
        """
        logger.info(f"\n对变量 {variable_name} 进行校正因子插值...")
        
        # 提取站点坐标和校正值
        station_ids = list(station_correction_factors.keys())
        station_lats = [station_correction_factors[sid]['lat'] for sid in station_ids]
        station_lons = [station_correction_factors[sid]['lon'] for sid in station_ids]
        
        # 使用偏差校正值进行插值
        station_values = np.array([
            station_correction_factors[sid]['bias_correction']
            for sid in station_ids
        ])
        
        station_coords = np.column_stack([station_lats, station_lons])
        grid_coords = all_grid_points[['latitude', 'longitude']].values
        
        # 插值
        interpolated_bias = self.interpolator.interpolate(
            station_coords,
            station_values,
            grid_coords
        )
        
        # 添加到网格点数据
        result = all_grid_points.copy()
        result[f'{variable_name}_bias_correction'] = interpolated_bias
        
        logger.info(f"  插值完成：{len(result)} 个网格点")
        
        return result
    
    def apply_field_correction(
        self,
        grid_data: pd.DataFrame,
        correction_factors: pd.DataFrame,
        variable_name: str
    ) -> pd.DataFrame:
        """
        应用场校正到网格数据
        
        Args:
            grid_data: 原始网格数据
            correction_factors: 校正因子 DataFrame
            variable_name: 变量名
        
        Returns:
            pd.DataFrame: 校正后的网格数据
        """
        logger.info(f"应用 {variable_name} 的场校正...")
        
        # 合并数据
        merged = grid_data.merge(
            correction_factors[['latitude', 'longitude', f'{variable_name}_bias_correction']],
            on=['latitude', 'longitude'],
            how='left'
        )
        
        # 应用校正
        var_col = variable_name
        corrected_col = f'{variable_name}_corrected'
        
        if var_col in merged.columns:
            # 简单的偏差校正
            merged[corrected_col] = merged[var_col] - merged[f'{variable_name}_bias_correction']
            
            logger.info(f"  校正完成：{len(merged)} 条记录")
        
        return merged


# 主函数 - 预留 ET0 接口
def main():
    """测试和演示"""
    logging.basicConfig(level=logging.INFO)
    
    # 生成测试数据
    np.random.seed(42)
    
    # 站点数据
    n_stations = 20
    station_lats = np.random.uniform(35, 42, n_stations)
    station_lons = np.random.uniform(110, 120, n_stations)
    station_values = np.random.normal(0, 2, n_stations)  # 偏差校正值
    
    # 网格数据
    n_grids = 100
    grid_lats = np.random.uniform(35, 42, n_grids)
    grid_lons = np.random.uniform(110, 120, n_grids)
    
    # 测试 IDW 插值
    interpolator = SpatialInterpolator(method='idw')
    
    station_coords = np.column_stack([station_lats, station_lons])
    grid_coords = np.column_stack([grid_lats, grid_lons])
    
    interpolated = interpolator.interpolate(
        station_coords,
        station_values,
        grid_coords,
        power=2
    )
    
    print(f"\nIDW 插值结果:")
    print(f"  站点数：{n_stations}")
    print(f"  网格点数：{n_grids}")
    print(f"  插值范围：[{interpolated.min():.3f}, {interpolated.max():.3f}]")
    
    # 【预留】ET0 校正因子插值接口
    print("\n" + "="*60)
    print("【预留接口】ET0 校正因子插值")
    print("="*60)
    print("当获取到中国气象数据网的 ET0 观测数据后:")
    print("1. 计算各站点的 ET0 校正因子")
    print("2. 使用相同的插值方法插值到全域网格")
    print("3. 应用校正到 ERA5 ET0 数据")
    print("\n代码位置：qm_correction/spatial_interpolation.py")
    print("方法：QMFieldInterpolator.interpolate_correction_factors()")


if __name__ == "__main__":
    main()
