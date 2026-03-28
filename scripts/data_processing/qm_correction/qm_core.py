"""
分位数映射 (Quantile Mapping, QM) 校正核心算法

功能:
    1. 实现标准 QM 算法
    2. 支持多种分布拟合（正态、Gamma、经验分布）
    3. 支持月度/季节性校正
    4. 提供校正因子保存和加载

数学原理:
    QM 校正的基本思想是建立模拟数据（GCM/Reanalysis）和观测数据
    的分位数映射关系：
    
    X_corrected = F_obs^(-1)(F_sim(X_sim))
    
    其中:
    - F_sim: 模拟数据的累积分布函数 (CDF)
    - F_obs: 观测数据的累积分布函数 (CDF)
    - F_obs^(-1): 观测数据的逆 CDF
    - X_sim: 待校正的模拟数据
    - X_corrected: 校正后的数据

扩展性:
    - 预留 ET0 校正支持
    - 支持自定义分布函数
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, List, Tuple, Optional, Union
import pickle
import json
from pathlib import Path
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class QuantileMapper:
    """分位数映射校正类"""
    
    def __init__(
        self,
        n_quantiles: int = 100,
        distribution: str = 'empirical',
        monthly: bool = True
    ):
        """
        初始化 QM 校正器
        
        Args:
            n_quantiles: 分位数数量（经验分布时使用）
            distribution: 分布类型
                - 'empirical': 经验分布（推荐，适用于所有变量）
                - 'normal': 正态分布（适用于温度）
                - 'gamma': Gamma 分布（适用于降水、ET0）
            monthly: 是否按月分别校正（考虑季节性）
        """
        self.n_quantiles = n_quantiles
        self.distribution = distribution
        self.monthly = monthly
        
        # 存储校正参数
        self.mapping_params = {}
        
        logger.info(f"QM 校正器初始化完成")
        logger.info(f"  - 分位数数量：{n_quantiles}")
        logger.info(f"  - 分布类型：{distribution}")
        logger.info(f"  - 月度校正：{monthly}")
    
    def fit(
        self,
        sim_data: pd.Series,
        obs_data: pd.Series,
        variable_name: str = 'variable'
    ):
        """
        拟合 QM 校正模型
        
        Args:
            sim_data: 模拟数据（待校正的数据，如 ERA5）
            obs_data: 观测数据（参考数据，如 NOAA）
            variable_name: 变量名
        """
        logger.info(f"拟合 {variable_name} 的 QM 模型...")
        
        # 数据对齐
        common_index = sim_data.index.intersection(obs_data.index)
        sim_aligned = sim_data.loc[common_index]
        obs_aligned = obs_data.loc[common_index]
        
        # 移除缺失值
        mask = sim_aligned.notna() & obs_aligned.notna()
        sim_clean = sim_aligned[mask]
        obs_clean = obs_aligned[mask]
        
        logger.info(f"  有效样本数：{len(sim_clean)}")
        
        if len(sim_clean) < 10:
            logger.warning(f"  样本数不足，跳过 {variable_name} 的校正")
            return
        
        if self.monthly:
            # 按月分别拟合
            self._fit_monthly(sim_clean, obs_clean, variable_name)
        else:
            # 整体拟合
            self._fit_all(sim_clean, obs_clean, variable_name)
    
    def _fit_monthly(
        self,
        sim_data: pd.Series,
        obs_data: pd.Series,
        variable_name: str
    ):
        """按月拟合 QM 模型"""
        logger.info("  按月拟合...")
        
        self.mapping_params[variable_name] = {}
        
        for month in range(1, 13):
            # 提取该月的数据
            sim_month = sim_data[sim_data.index.month == month]
            obs_month = obs_data[obs_data.index.month == month]
            
            if len(sim_month) < 5 or len(obs_month) < 5:
                logger.warning(f"    月份 {month}: 样本不足，跳过")
                continue
            
            # 拟合该月的 QM 模型
            params = self._compute_mapping(sim_month, obs_month, variable_name)
            
            if params is not None:
                self.mapping_params[variable_name][month] = params
                logger.info(f"    月份 {month}: 拟合完成 (样本数={len(sim_month)})")
    
    def _fit_all(
        self,
        sim_data: pd.Series,
        obs_data: pd.Series,
        variable_name: str
    ):
        """整体拟合 QM 模型"""
        logger.info("  整体拟合...")
        
        params = self._compute_mapping(sim_data, obs_data, variable_name)
        
        if params is not None:
            self.mapping_params[variable_name] = {'all': params}
            logger.info(f"  整体拟合完成 (样本数={len(sim_data)})")
    
    def _compute_mapping(
        self,
        sim_data: pd.Series,
        obs_data: pd.Series,
        variable_name: str
    ) -> Dict:
        """
        计算分位数映射关系
        
        Returns:
            Dict: 包含分布参数的字典
        """
        sim_values = sim_data.values
        obs_values = obs_data.values
        
        if self.distribution == 'empirical':
            # 经验分布方法
            return self._compute_empirical_mapping(sim_values, obs_values)
        
        elif self.distribution == 'normal':
            # 正态分布
            return self._compute_normal_mapping(sim_values, obs_values)
        
        elif self.distribution == 'gamma':
            # Gamma 分布
            return self._compute_gamma_mapping(sim_values, obs_values)
        
        else:
            raise ValueError(f"未知的分布类型：{self.distribution}")
    
    def _compute_empirical_mapping(
        self,
        sim_values: np.ndarray,
        obs_values: np.ndarray
    ) -> Dict:
        """
        经验分布的分位数映射
        
        使用分位数 - 分位数对应关系
        """
        # 计算分位数
        quantiles = np.linspace(0, 1, self.n_quantiles)
        
        # 模拟数据的分位数
        sim_quantiles = np.percentile(sim_values, quantiles * 100)
        
        # 观测数据的分位数
        obs_quantiles = np.percentile(obs_values, quantiles * 100)
        
        # 存储映射关系
        mapping = {
            'method': 'empirical',
            'quantiles': quantiles,
            'sim_quantiles': sim_quantiles,
            'obs_quantiles': obs_quantiles,
            'sim_mean': np.mean(sim_values),
            'sim_std': np.std(sim_values),
            'obs_mean': np.mean(obs_values),
            'obs_std': np.std(obs_values)
        }
        
        return mapping
    
    def _compute_normal_mapping(
        self,
        sim_values: np.ndarray,
        obs_values: np.ndarray
    ) -> Dict:
        """
        正态分布假设下的分位数映射
        
        适用于温度等近似正态分布的变量
        """
        # 拟合正态分布
        sim_mean, sim_std = stats.norm.fit(sim_values)
        obs_mean, obs_std = stats.norm.fit(obs_values)
        
        mapping = {
            'method': 'normal',
            'sim_mean': sim_mean,
            'sim_std': sim_std,
            'obs_mean': obs_mean,
            'obs_std': obs_std
        }
        
        return mapping
    
    def _compute_gamma_mapping(
        self,
        sim_values: np.ndarray,
        obs_values: np.ndarray
    ) -> Dict:
        """
        Gamma 分布假设下的分位数映射
        
        适用于降水、ET0 等非负偏态分布变量
        """
        # 处理零值（Gamma 分布要求正值）
        sim_positive = sim_values[sim_values > 0]
        obs_positive = obs_values[obs_values > 0]
        
        # 计算零值概率
        sim_zero_prob = np.mean(sim_values == 0)
        obs_zero_prob = np.mean(obs_values == 0)
        
        # 拟合 Gamma 分布
        if len(sim_positive) > 10 and len(obs_positive) > 10:
            sim_shape, sim_loc, sim_scale = stats.gamma.fit(sim_positive)
            obs_shape, obs_loc, obs_scale = stats.gamma.fit(obs_positive)
            
            gamma_params = {
                'sim_shape': sim_shape,
                'sim_loc': sim_loc,
                'sim_scale': sim_scale,
                'obs_shape': obs_shape,
                'obs_loc': obs_loc,
                'obs_scale': obs_scale
            }
        else:
            gamma_params = None
        
        mapping = {
            'method': 'gamma',
            'sim_zero_prob': sim_zero_prob,
            'obs_zero_prob': obs_zero_prob,
            'gamma_params': gamma_params,
            'sim_mean_pos': np.mean(sim_positive) if len(sim_positive) > 0 else 0,
            'obs_mean_pos': np.mean(obs_positive) if len(obs_positive) > 0 else 0
        }
        
        return mapping
    
    def transform(
        self,
        sim_data: pd.Series,
        variable_name: str
    ) -> pd.Series:
        """
        应用 QM 校正
        
        Args:
            sim_data: 待校正的模拟数据
            variable_name: 变量名
        
        Returns:
            pd.Series: 校正后的数据
        """
        if variable_name not in self.mapping_params:
            logger.warning(f"变量 {variable_name} 没有校正参数，返回原始数据")
            return sim_data
        
        logger.info(f"对 {variable_name} 应用 QM 校正...")
        
        if self.monthly and isinstance(self.mapping_params[variable_name], dict):
            # 按月校正
            return self._transform_monthly(sim_data, variable_name)
        else:
            # 整体校正
            return self._transform_all(sim_data, variable_name)
    
    def _transform_monthly(
        self,
        sim_data: pd.Series,
        variable_name: str
    ) -> pd.Series:
        """按月应用 QM 校正"""
        corrected_data = sim_data.copy()
        
        for month in range(1, 13):
            if month not in self.mapping_params[variable_name]:
                continue
            
            # 提取该月的数据
            mask = sim_data.index.month == month
            sim_month = sim_data[mask]
            
            if len(sim_month) == 0:
                continue
            
            # 应用校正
            params = self.mapping_params[variable_name][month]
            corrected_month = self._apply_mapping(sim_month, params)
            
            # 存回
            corrected_data.loc[mask] = corrected_month
        
        return corrected_data
    
    def _transform_all(
        self,
        sim_data: pd.Series,
        variable_name: str
    ) -> pd.Series:
        """整体应用 QM 校正"""
        if 'all' in self.mapping_params[variable_name]:
            params = self.mapping_params[variable_name]['all']
        else:
            params = self.mapping_params[variable_name]
        
        return self._apply_mapping(sim_data, params)
    
    def _apply_mapping(
        self,
        sim_data: pd.Series,
        params: Dict
    ) -> pd.Series:
        """
        应用具体的映射关系
        
        Args:
            sim_data: 待校正数据
            params: 映射参数
        
        Returns:
            corrected_data: 校正后数据
        """
        sim_values = sim_data.values
        
        if params['method'] == 'empirical':
            corrected_values = self._apply_empirical_transform(sim_values, params)
        
        elif params['method'] == 'normal':
            corrected_values = self._apply_normal_transform(sim_values, params)
        
        elif params['method'] == 'gamma':
            corrected_values = self._apply_gamma_transform(sim_values, params)
        
        else:
            raise ValueError(f"未知的映射方法：{params['method']}")
        
        return pd.Series(corrected_values, index=sim_data.index)
    
    def _apply_empirical_transform(
        self,
        sim_values: np.ndarray,
        params: Dict
    ) -> np.ndarray:
        """
        应用经验分布映射
        
        使用线性插值实现分位数映射
        """
        sim_quantiles = params['sim_quantiles']
        obs_quantiles = params['obs_quantiles']
        
        # 线性插值
        corrected_values = np.interp(
            sim_values,
            sim_quantiles,
            obs_quantiles,
            left=obs_quantiles[0],
            right=obs_quantiles[-1]
        )
        
        return corrected_values
    
    def _apply_normal_transform(
        self,
        sim_values: np.ndarray,
        params: Dict
    ) -> np.ndarray:
        """
        应用正态分布映射
        
        X_corrected = mean_obs + (X_sim - mean_sim) * (std_obs / std_sim)
        """
        sim_mean = params['sim_mean']
        sim_std = params['sim_std']
        obs_mean = params['obs_mean']
        obs_std = params['obs_std']
        
        # 标准化 + 重新缩放
        standardized = (sim_values - sim_mean) / sim_std
        corrected_values = obs_mean + standardized * obs_std
        
        return corrected_values
    
    def _apply_gamma_transform(
        self,
        sim_values: np.ndarray,
        params: Dict
    ) -> np.ndarray:
        """
        应用 Gamma 分布映射
        
        1. 计算模拟数据的累积概率
        2. 使用逆 CDF 得到观测数据的值
        """
        gamma_params = params.get('gamma_params')
        
        if gamma_params is None:
            # 如果没有 Gamma 参数，使用均值校正
            sim_mean_pos = params['sim_mean_pos']
            obs_mean_pos = params['obs_mean_pos']
            
            if sim_mean_pos > 0:
                ratio = obs_mean_pos / sim_mean_pos
                corrected_values = sim_values * ratio
            else:
                corrected_values = sim_values.copy()
            
            return corrected_values
        
        # 处理零值
        zero_mask = sim_values <= 0
        sim_positive = sim_values[~zero_mask]
        
        if len(sim_positive) == 0:
            return sim_values.copy()
        
        # 计算模拟数据的累积概率
        sim_cdf = stats.gamma.cdf(
            sim_positive,
            gamma_params['sim_shape'],
            loc=gamma_params['sim_loc'],
            scale=gamma_params['sim_scale']
        )
        
        # 使用逆 CDF 得到观测数据的值
        corrected_positive = stats.gamma.ppf(
            sim_cdf,
            gamma_params['obs_shape'],
            loc=gamma_params['obs_loc'],
            scale=gamma_params['obs_scale']
        )
        
        # 构建完整的结果
        corrected_values = np.zeros_like(sim_values)
        corrected_values[~zero_mask] = corrected_positive
        
        # 处理零值（根据零值概率调整）
        if params['obs_zero_prob'] > params['sim_zero_prob']:
            # 观测数据零值更多，随机将部分校正值设为零
            n_zeros = int(len(corrected_values) * (params['obs_zero_prob'] - params['sim_zero_prob']))
            if n_zeros > 0:
                zero_indices = np.random.choice(len(corrected_values), n_zeros, replace=False)
                corrected_values[zero_indices] = 0
        
        return corrected_values
    
    def save(self, filepath: str):
        """保存校正模型"""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'wb') as f:
            pickle.dump({
                'params': self.mapping_params,
                'config': {
                    'n_quantiles': self.n_quantiles,
                    'distribution': self.distribution,
                    'monthly': self.monthly
                }
            }, f)
        
        logger.info(f"QM 模型已保存：{filepath}")
    
    def load(self, filepath: str):
        """加载校正模型"""
        filepath = Path(filepath)
        
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
            self.mapping_params = data['params']
            self.n_quantiles = data['config']['n_quantiles']
            self.distribution = data['config']['distribution']
            self.monthly = data['config']['monthly']
        
        logger.info(f"QM 模型已加载：{filepath}")


# 测试代码
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    # 生成测试数据
    np.random.seed(42)
    n_samples = 1000
    
    # 模拟数据（有偏差）
    sim_temp = np.random.normal(15, 5, n_samples) + 2  # 温度偏高 2 度
    sim_precip = np.random.gamma(2, 2, n_samples)  # 降水
    
    # 观测数据（无偏差）
    obs_temp = np.random.normal(15, 5, n_samples)
    obs_precip = np.random.gamma(2, 2.5, n_samples)
    
    # 创建时间索引
    dates = pd.date_range('2020-01-01', periods=n_samples, freq='D')
    
    sim_temp_series = pd.Series(sim_temp, index=dates)
    obs_temp_series = pd.Series(obs_temp, index=dates)
    
    # 测试温度校正（正态分布）
    qm_temp = QuantileMapper(distribution='normal', monthly=False)
    qm_temp.fit(sim_temp_series, obs_temp_series, 'temperature')
    
    corrected_temp = qm_temp.transform(sim_temp_series, 'temperature')
    
    print("\n温度校正结果:")
    print(f"  原始模拟：mean={sim_temp.mean():.2f}, std={sim_temp.std():.2f}")
    print(f"  观测数据：mean={obs_temp.mean():.2f}, std={obs_temp.std():.2f}")
    print(f"  校正后：  mean={corrected_temp.mean():.2f}, std={corrected_temp.std():.2f}")
    
    # 测试降水校正（Gamma 分布）
    sim_precip_series = pd.Series(sim_precip, index=dates)
    obs_precip_series = pd.Series(obs_precip, index=dates)
    
    qm_precip = QuantileMapper(distribution='gamma', monthly=False)
    qm_precip.fit(sim_precip_series, obs_precip_series, 'precipitation')
    
    corrected_precip = qm_precip.transform(sim_precip_series, 'precipitation')
    
    print("\n降水校正结果:")
    print(f"  原始模拟：mean={sim_precip.mean():.2f}, std={sim_precip.std():.2f}")
    print(f"  观测数据：mean={obs_precip.mean():.2f}, std={obs_precip.std():.2f}")
    print(f"  校正后：  mean={corrected_precip.mean():.2f}, std={corrected_precip.std():.2f}")
    
    # 保存模型
    qm_temp.save('test_qm_temp.pkl')
    qm_precip.save('test_qm_precip.pkl')
