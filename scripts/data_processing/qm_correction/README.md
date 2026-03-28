# QM 偏差校正模块使用指南

## 📦 模块概述

本模块实现了**分位数映射 (Quantile Mapping, QM)** 偏差校正方法，用于校正 Open-Meteo/ERA5-Land 网格数据相对于 NOAA 站点观测数据的系统偏差。

### 校正变量

| 变量 | 状态 | 分布类型 | 说明 |
|------|------|---------|------|
| 温度 (temperature) | ✅ 已实现 | 正态/经验分布 | 考虑季节性，月度校正 |
| 降水 (precipitation) | ✅ 已实现 | Gamma/经验分布 | 处理零值，偏态分布 |
| 风速 (wind_speed) | ✅ 已实现 | 经验分布 | 考虑季节性 |
| 相对湿度 (relative_humidity) | ✅ 已实现 | 经验分布 | 考虑季节性 |
| 蒸散量 (et0_fao_evapotranspiration) | ⏸️ 预留接口 | Gamma 分布 | **待中国气象数据网数据** |

---

## 🚀 快速开始

### 1. 环境准备

```bash
# 激活虚拟环境
.\venv\Scripts\activate

# 确认依赖已安装
pip install pandas numpy scipy scikit-learn matplotlib seaborn
```

### 2. 运行 QM 校正

```bash
# 进入脚本目录
cd scripts\data_processing\qm_correction

# 运行主脚本
python run_qm_correction.py
```

### 3. 查看结果

校正完成后，结果保存在以下目录:

```
data/processed/qm_correction/
├── {station_id}_corrected.csv          # 各站点校正后数据
├── {variable}_all_stations_corrected.csv  # 按变量合并的数据
├── correction_statistics.csv           # 校正统计报告
├── assessment/                         # 质量评估图表
│   ├── qm_assessment_mae_comparison.png
│   └── qm_assessment_improvement_boxplot.png
└── qm_models/                          # QM 校正模型
    └── {station_id}/
        ├── temperature_qm_model.pkl
        ├── precipitation_qm_model.pkl
        ├── wind_speed_qm_model.pkl
        └── relative_humidity_qm_model.pkl
```

---

## 📁 模块结构

```
qm_correction/
├── __init__.py                    # 模块初始化
├── data_loader.py                 # 数据加载与匹配
├── qm_core.py                     # QM 核心算法
├── qm_executor.py                 # 校正执行器
├── quality_assessment.py          # 质量评估
├── spatial_interpolation.py       # 空间插值
├── run_qm_correction.py           # 主运行脚本
└── README.md                      # 本文档
```

### 核心类说明

| 类名 | 功能 | 主要方法 |
|------|------|---------|
| `DataManager` | 数据加载与管理 | `load_grid_data()`, `load_noaa_station_data()`, `get_matched_pairs()` |
| `QuantileMapper` | QM 算法实现 | `fit()`, `transform()`, `save()`, `load()` |
| `QMExecutor` | 校正流程协调 | `run_correction()`, `get_correction_statistics()` |
| `QualityAssessment` | 质量评估 | `compute_metrics()`, `create_assessment_report()`, `plot_results()` |
| `SpatialInterpolator` | 空间插值 | `interpolate()` (IDW, Kriging) |

---

## ⚙️ 配置说明

### 主配置文件：`run_qm_correction.py`

```python
CONFIG = {
    # 校正变量
    'variables_to_correct': [
        'temperature',
        'precipitation',
        'wind_speed',
        'relative_humidity'
        # 'et0_fao_evapotranspiration'  # 【预留】待 CMA 数据
    ],
    
    # 时间范围
    'start_year': 1990,
    'end_year': 2023,
    
    # QM 参数
    'qm_params': {
        'n_quantiles': 100,      # 分位数数量
        'distribution': 'empirical',  # 分布类型
        'monthly': True          # 月度校正
    }
}
```

### 分布类型选择

| 变量类型 | 推荐分布 | 配置 |
|---------|---------|------|
| 温度 | `'normal'` 或 `'empirical'` | 近似正态分布 |
| 降水 | `'gamma'` 或 `'empirical'` | 偏态分布，有零值 |
| 风速 | `'empirical'` | 无明显分布规律 |
| 相对湿度 | `'empirical'` | 有界变量 (0-100%) |
| ET0 | `'gamma'` | 偏态分布，非负 |

---

## 📊 输出说明

### 1. 校正后数据

**文件:** `{station_id}_corrected.csv`

**字段:**
```csv
date,temperature,temperature_corrected,precipitation,precipitation_corrected,...
1990-01-01,5.2,4.8,0.0,0.0,...
1990-01-02,6.1,5.7,2.5,2.3,...
...
```

### 2. 校正统计报告

**文件:** `correction_statistics.csv`

**字段:**
```csv
station_id,variable,bias_before,bias_after,bias_reduction,mae_before,mae_after,mae_reduction,...
533520-99999,temperature,1.23,0.15,87.8,1.45,0.52,64.1,...
```

### 3. 质量评估图表

- **MAE 对比图**: 校正前后 MAE 散点对比
- **改进百分比箱线图**: Bias/MAE/RMSE 改进的分布
- **时间序列图**: (可选) 校正前后对比

---

## 🔧 高级用法

### 1. 自定义 QM 参数

```python
from qm_correction import QuantileMapper

# 创建 QM 模型
qm = QuantileMapper(
    n_quantiles=50,      # 减少分位数（更快但精度略降）
    distribution='gamma', # 使用 Gamma 分布
    monthly=False        # 整体校正（不考虑季节性）
)

# 拟合模型
qm.fit(sim_data, obs_data, 'variable_name')

# 应用校正
corrected = qm.transform(sim_data, 'variable_name')
```

### 2. 加载已保存的模型

```python
from qm_correction import QuantileMapper

# 创建模型
qm = QuantileMapper()

# 加载模型
qm.load('data/processed/qm_correction/qm_models/533520-99999/temperature_qm_model.pkl')

# 应用校正
corrected = qm.transform(new_data, 'temperature')
```

### 3. 空间插值

```python
from qm_correction import SpatialInterpolator

# 创建插值器
interpolator = SpatialInterpolator(method='idw')  # 或 'kriging'

# 插值
interpolated = interpolator.interpolate(
    station_coords=station_coords,
    station_values=correction_factors,
    grid_coords=grid_coords,
    power=2.0  # IDW 的幂次
)
```

---

## 📈 预期效果

根据文献和实践经验，QM 校正的典型效果:

| 变量 | 偏差减少 | MAE 减少 | RMSE 减少 |
|------|---------|---------|----------|
| 温度 | 70-90% | 40-60% | 35-55% |
| 降水 | 50-80% | 20-40% | 15-35% |
| 风速 | 60-85% | 25-45% | 20-40% |
| 相对湿度 | 65-90% | 30-50% | 25-45% |

**注意:** 实际效果取决于:
- 站点数据质量
- 时间序列长度
- 分布类型选择
- 是否考虑季节性

---

## 🐛 故障排查

### 问题 1: 数据库连接失败

**错误:** `psycopg2.OperationalError: connection refused`

**解决:**
1. 检查 PostgreSQL 服务是否运行
2. 确认 `.env` 文件中的数据库配置正确
3. 检查防火墙设置

### 问题 2: 站点数据文件不存在

**错误:** `FileNotFoundError: 站点数据文件不存在`

**解决:**
1. 确认 NOAA 数据预处理已完成
2. 检查 `data/processed/noaa_daily/` 目录
3. 验证站点 ID 格式是否正确

### 问题 3: 内存不足

**错误:** `MemoryError`

**解决:**
1. 减少时间范围（如先测试 1 年数据）
2. 减少分位数数量（如 50 代替 100）
3. 分批处理站点

---

## 📚 技术参考

### QM 方法原理

分位数映射的基本思想:

```
X_corrected = F_obs^(-1)(F_sim(X_sim))
```

其中:
- `F_sim`: 模拟数据的累积分布函数
- `F_obs^(-1)`: 观测数据的逆累积分布函数

### 参考文献

1. **方法学**:
   - Teutschbein, C., & Seibert, J. (2012). Bias correction of regional climate model simulations for hydrological climate-change impact studies. *Journal of Hydrology*, 412-413, 12-29.

2. **应用**:
   - Maraun, D. (2013). Bias correction, quantile mapping, and downscaling: Revisiting the inflation issue. *Journal of Climate*, 26(6), 2137-2143.

---

## 🔮 扩展计划

### 近期 (如果获取到 CMA ET0 数据)

- [ ] 添加 ET0 变量校正
- [ ] 实现 ET0 的 Gamma 分布拟合
- [ ] 生成 ET0 校正评估报告

### 远期

- [ ] 并行化处理（加速大规模数据处理）
- [ ] 支持更多分布类型
- [ ] 交互式可视化界面
- [ ] 自动最优分位数选择

---

## 📞 联系

如有问题或建议，请联系:
- 项目仓库：[Your Repo]
- 邮箱：[Your Email]

---

**最后更新:** 2026-03-14  
**版本:** v1.0  
**状态:** ✅ 生产就绪 | ⏸️ ET0 扩展待实现
