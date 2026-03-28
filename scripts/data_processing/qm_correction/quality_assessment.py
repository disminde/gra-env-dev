"""
质量评估模块 - 评估 QM 校正效果

功能:
    1. 计算多种误差指标（MAE, RMSE, Bias, Correlation）
    2. 生成交叉验证结果
    3. 创建可视化图表
    4. 生成评估报告

扩展性:
    - 预留 ET0 评估指标
    - 支持自定义评估指标
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import logging
from typing import Dict, List, Optional
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from scipy import stats

logger = logging.getLogger(__name__)


class QualityAssessment:
    """质量评估类"""
    
    def __init__(self, output_dir: str = 'data/processed/qm_correction/assessment'):
        """
        初始化质量评估器
        
        Args:
            output_dir: 输出目录
        """
        self.base_dir = Path(__file__).parent.parent.parent
        self.output_dir = self.base_dir / output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"质量评估器初始化完成")
        logger.info(f"输出目录：{self.output_dir}")
    
    def compute_metrics(
        self,
        observed: pd.Series,
        simulated: pd.Series,
        corrected: pd.Series,
        variable_name: str
    ) -> Dict:
        """
        计算校正前后的误差指标
        
        Args:
            observed: 观测数据
            simulated: 模拟数据（校正前）
            corrected: 校正后数据
            variable_name: 变量名
        
        Returns:
            Dict: 包含各种误差指标的字典
        """
        # 数据对齐
        common_index = observed.index.intersection(simulated.index).intersection(corrected.index)
        obs = observed.loc[common_index]
        sim = simulated.loc[common_index]
        corr = corrected.loc[common_index]
        
        # 移除缺失值
        mask = obs.notna() & sim.notna() & corr.notna()
        obs_clean = obs.loc[mask]
        sim_clean = sim.loc[mask]
        corr_clean = corr.loc[mask]
        
        # 计算校正前指标
        bias_before = sim_clean.mean() - obs_clean.mean()
        mae_before = mean_absolute_error(obs_clean, sim_clean)
        rmse_before = np.sqrt(mean_squared_error(obs_clean, sim_clean))
        r2_before = r2_score(obs_clean, sim_clean)
        corr_before, _ = stats.pearsonr(obs_clean, sim_clean)
        
        # 计算校正后指标
        bias_after = corr_clean.mean() - obs_clean.mean()
        mae_after = mean_absolute_error(obs_clean, corr_clean)
        rmse_after = np.sqrt(mean_squared_error(obs_clean, corr_clean))
        r2_after = r2_score(obs_clean, corr_clean)
        corr_after, _ = stats.pearsonr(obs_clean, corr_clean)
        
        # 计算改进百分比
        bias_improvement = (1 - abs(bias_after) / abs(bias_before)) * 100 if abs(bias_before) > 0 else 0
        mae_improvement = (1 - mae_after / mae_before) * 100 if mae_before > 0 else 0
        rmse_improvement = (1 - rmse_after / rmse_before) * 100 if rmse_before > 0 else 0
        
        metrics = {
            'variable': variable_name,
            'n_samples': len(obs_clean),
            'bias_before': bias_before,
            'bias_after': bias_after,
            'bias_improvement': bias_improvement,
            'mae_before': mae_before,
            'mae_after': mae_after,
            'mae_improvement': mae_improvement,
            'rmse_before': rmse_before,
            'rmse_after': rmse_after,
            'rmse_improvement': rmse_improvement,
            'r2_before': r2_before,
            'r2_after': r2_after,
            'correlation_before': corr_before,
            'correlation_after': corr_after
        }
        
        return metrics
    
    def create_assessment_report(
        self,
        all_metrics: List[Dict],
        output_file: str = 'assessment_report.csv'
    ):
        """
        生成评估报告
        
        Args:
            all_metrics: 所有站点的指标列表
            output_file: 输出文件名
        """
        df = pd.DataFrame(all_metrics)
        
        # 保存 CSV 报告
        output_path = self.output_dir / output_file
        df.to_csv(output_path, index=False)
        logger.info(f"评估报告已保存：{output_path}")
        
        # 打印摘要
        print("\n" + "="*60)
        print("QM 校正质量评估摘要")
        print("="*60)
        
        for var in df['variable'].unique():
            var_data = df[df['variable'] == var]
            print(f"\n{var.upper()} (n={len(var_data)} 站点):")
            print(f"  偏差改进：{var_data['bias_improvement'].mean():.1f}% ± {var_data['bias_improvement'].std():.1f}%")
            print(f"  MAE 改进： {var_data['mae_improvement'].mean():.1f}% ± {var_data['mae_improvement'].std():.1f}%")
            print(f"  RMSE 改进：{var_data['rmse_improvement'].mean():.1f}% ± {var_data['rmse_improvement'].std():.1f}%")
        
        return df
    
    def plot_results(
        self,
        all_metrics: List[Dict],
        output_prefix: str = 'qm_assessment'
    ):
        """
        绘制评估结果图
        
        Args:
            all_metrics: 所有站点的指标列表
            output_prefix: 输出文件前缀
        """
        df = pd.DataFrame(all_metrics)
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 1. 校正前后 MAE 对比
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        variables = df['variable'].unique()
        
        for idx, var in enumerate(variables):
            if idx >= 4:
                break
            
            ax = axes[idx // 2, idx % 2]
            var_data = df[df['variable'] == var]
            
            # 绘制散点图
            ax.scatter(var_data['mae_before'], var_data['mae_after'], alpha=0.6, edgecolors='k')
            ax.plot([0, var_data['mae_before'].max()], [0, var_data['mae_before'].max()], 'r--', label='1:1 line')
            
            ax.set_xlabel('MAE Before Correction')
            ax.set_ylabel('MAE After Correction')
            ax.set_title(f'{var.upper()}: MAE Comparison')
            ax.legend()
            ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        output_file = self.output_dir / f'{output_prefix}_mae_comparison.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        logger.info(f"图表已保存：{output_file}")
        plt.close()
        
        # 2. 改进百分比箱线图
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        
        metrics_to_plot = ['bias_improvement', 'mae_improvement', 'rmse_improvement']
        titles = ['Bias Improvement', 'MAE Improvement', 'RMSE Improvement']
        
        for idx, (metric, title) in enumerate(zip(metrics_to_plot, titles)):
            ax = axes[idx]
            
            # 准备数据
            plot_data = []
            labels = []
            for var in df['variable'].unique():
                var_data = df[df['variable'] == var]
                plot_data.append(var_data[metric].values)
                labels.append(var)
            
            # 绘制箱线图
            bp = ax.boxplot(plot_data, patch_artist=True, labels=labels)
            
            # 设置颜色
            colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A']
            for patch, color in zip(bp['boxes'], colors):
                patch.set_facecolor(color)
            
            ax.set_ylabel('Improvement (%)')
            ax.set_title(title)
            ax.axhline(y=0, color='r', linestyle='--', alpha=0.5)
            ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        output_file = self.output_dir / f'{output_prefix}_improvement_boxplot.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        logger.info(f"图表已保存：{output_file}")
        plt.close()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)
    
    # 生成测试数据
    np.random.seed(42)
    n_samples = 1000
    
    obs = pd.Series(np.random.normal(15, 5, n_samples))
    sim = pd.Series(np.random.normal(17, 5, n_samples))  # 有偏差
    corr = pd.Series(np.random.normal(15.2, 4.8, n_samples))  # 校正后
    
    dates = pd.date_range('2020-01-01', periods=n_samples, freq='D')
    obs.index = dates
    sim.index = dates
    corr.index = dates
    
    # 测试评估
    qa = QualityAssessment()
    metrics = qa.compute_metrics(obs, sim, corr, 'temperature')
    
    print("\n测试指标:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
