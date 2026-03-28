"""
QM 偏差校正模块 - 华北平原气象数据偏差校正系统

功能概述:
    本模块实现分位数映射 (Quantile Mapping, QM) 偏差校正方法，用于校正
    Open-Meteo/ERA5-Land 网格数据相对于 NOAA 站点观测数据的系统偏差。

校正变量:
    ✅ 温度 (temperature)
    ✅ 降水 (precipitation)
    ✅ 风速 (wind_speed)
    ✅ 相对湿度 (relative_humidity)
    ⏸️ ET0 (et0_fao_evapotranspiration) - 【预留接口，待中国气象数据网数据】

架构设计:
    1. 数据加载层 (data_loader.py)
       - 从 PostgreSQL 读取网格数据
       - 从 CSV 读取 NOAA 站点日数据
       - 时空匹配（站点 - 网格点对应）
    
    2. QM 校正核心层 (qm_core.py)
       - 分位数映射算法实现
       - 支持多种分布拟合（正态、Gamma、经验分布）
       - 批量处理多个变量
    
    3.校正执行层 (qm_executor.py)
       - 按变量执行 QM 校正
       - 保存校正因子
       - 生成中间结果
    
    4. 质量评估层 (quality_assessment.py)
       - 交叉验证
       - 误差指标计算（MAE, RMSE, Bias）
       - 生成可视化图表
    
    5. 空间插值层 (spatial_interpolation.py)
       - 将站点校正因子插值到全域网格
       - 支持多种插值方法（IDW、Kriging）
    
    6. 扩展接口 (extensions/)
       - 📌 ET0 校正接口（预留）
       - 📌 其他变量校正接口

作者：[Your Name]
日期：2026-03
版本：v1.0
"""

__version__ = "1.0.0"
__author__ = "NCP Drought Monitor Team"

# 模块导入
from .qm_core import QuantileMapper
from .data_loader import DataManager
from .qm_executor import QMExecutor
from .quality_assessment import QualityAssessment
from .spatial_interpolation import SpatialInterpolator

# 配置常量
QM_CONFIG = {
    # 校正变量列表
    'variables_to_correct': [
        'temperature',
        'precipitation',
        'wind_speed',
        'relative_humidity'
        # 'et0_fao_evapotranspiration'  # 【预留】待中国气象数据网数据
    ],
    
    # 时间范围
    'start_year': 1990,
    'end_year': 2023,
    
    # 分位数数量
    'n_quantiles': 100,
    
    # 交叉验证折数
    'cv_folds': 5,
    
    # 输出目录
    'output_dir': 'data/processed/qm_correction',
}

# 扩展性说明
EXTENSION_NOTES = """
【ET0 校正扩展说明】

如果后续获取到中国气象数据网的 ET0 观测数据，可以按以下步骤扩展：

1. 数据准备:
   - 将 ET0 观测数据保存为 CSV 格式（与 NOAA 站点数据格式类似）
   - 文件命名：{station_id}_et0_daily.csv
   - 存放位置：data/processed/cma_et0/

2. 代码修改:
   a) 在 qm_config.py 中:
      - 将 'et0_fao_evapotranspiration' 添加到 variables_to_correct 列表
    
   b) 在 data_loader.py 中:
      - 添加 load_et0_observation() 方法
      - 在 DataManager 类中添加 ET0 数据加载逻辑
   
   c) 在 qm_executor.py 中:
      - ET0 校正逻辑与其他变量类似，无需修改
   
   d) 运行校正:
      - 主脚本会自动检测并执行 ET0 校正

3. 注意事项:
   - ET0 通常服从 Gamma 分布，建议使用 Gamma 分布拟合
   - ET0 存在季节性变化，建议按月或季节分别校正
   - 需要验证 ET0 观测数据的质量（缺失值、异常值）

【联系信息】
如有问题或需要扩展，请联系：[Your Email]
"""

print(f"QM 偏差校正模块 v{__version__} 已加载")
print(f"当前校正变量：{QM_CONFIG['variables_to_correct']}")
print(f"预留扩展变量：et0_fao_evapotranspiration (待中国气象数据网数据)")
