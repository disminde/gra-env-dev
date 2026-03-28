# QM 偏差校正扩展指南

## 📋 文档目的

本文档说明如何在获取中国气象数据网 (CMA) 的 ET0 观测数据后，扩展当前的 QM 校正系统以包含 ET0 变量的校正。

---

## 🎯 当前状态

### 已实现的功能 (v1.0)

✅ **已校正的变量:**
- 温度 (temperature)
- 降水 (precipitation)
- 风速 (wind_speed)
- 相对湿度 (relative_humidity)

✅ **技术架构:**
- 数据加载模块 (`data_loader.py`)
- QM 核心算法 (`qm_core.py`)
- 校正执行器 (`qm_executor.py`)
- 质量评估 (`quality_assessment.py`)
- 空间插值 (`spatial_interpolation.py`)

⏸️ **预留接口:**
- ET0 校正 (et0_fao_evapotranspiration) - **待 CMA 数据**

---

## 📥 步骤 1: 获取并准备 CMA ET0 数据

### 1.1 数据要求

从**中国气象数据网**获取以下数据:

**数据源:** 
- 产品名：中国地面气象站逐日 ET0 数据集
- 或：中国气象要素逐日值数据集（包含 ET0）

**时间范围:**
- 1990-2023 年（与 NOAA 数据同期）

**站点范围:**
- 华北平原区域内的气象站点
- 最好与 NOAA 站点位置接近或重合

### 1.2 数据格式转换

获取数据后，需要转换为以下格式:

**文件位置:**
```
data/processed/cma_et0/{station_id}_et0_daily.csv
```

**文件格式:**
```csv
date,et0_obs
1990-01-01,2.5
1990-01-02,2.3
1990-01-03,2.8
...
```

**字段说明:**
- `date`: 日期 (YYYY-MM-DD 格式)
- `et0_obs`: 观测的 ET0 值 (单位：mm/day)

### 1.3 站点 ID 映射

创建站点 ID 映射文件（如果需要）:

**文件:** `data/processed/cma_et0/station_id_mapping.csv`

```csv
cma_station_id,noaa_station_id
54511,533520-99999
54662,533910-99999
...
```

---

## 🔧 步骤 2: 修改代码配置

### 2.1 修改主配置文件

**文件:** `scripts/data_processing/qm_correction/run_qm_correction.py`

**修改前:**
```python
CONFIG = {
    'variables_to_correct': [
        'temperature',
        'precipitation',
        'wind_speed',
        'relative_humidity'
        # 'et0_fao_evapotranspiration'  # 注释状态
    ],
    ...
}
```

**修改后:**
```python
CONFIG = {
    'variables_to_correct': [
        'temperature',
        'precipitation',
        'wind_speed',
        'relative_humidity',
        'et0_fao_evapotranspiration'  # ✅ 取消注释
    ],
    ...
}
```

### 2.2 (可选) 调整 ET0 的 QM 参数

**文件:** `scripts/data_processing/qm_correction/qm_executor.py`

ET0 通常服从 Gamma 分布，建议为 ET0 使用 Gamma 分布拟合:

```python
# 在 QMExecutor 类中添加变量特定的分布配置
self.variable_distributions = {
    'temperature': 'normal',
    'precipitation': 'gamma',
    'wind_speed': 'empirical',
    'relative_humidity': 'empirical',
    'et0_fao_evapotranspiration': 'gamma'  # ET0 使用 Gamma 分布
}
```

---

## ▶️ 步骤 3: 运行 ET0 校正

### 3.1 运行主脚本

```bash
# 激活虚拟环境
.\venv\Scripts\activate

# 运行 QM 校正
python scripts\data_processing\qm_correction\run_qm_correction.py
```

### 3.2 验证结果

检查输出文件:

```bash
# 查看生成的文件
data/processed/qm_correction/
├── *_corrected.csv              # 各站点校正结果（包含 ET0）
├── et0_fao_evapotranspiration_all_stations_corrected.csv  # ✅ ET0 合并文件
├── correction_statistics.csv    # 校正统计
├── assessment/                  # 评估图表
│   └── qm_assessment_*.png
└── qm_models/
    └── {station_id}/
        └── et0_fao_evapotranspiration_qm_model.pkl  # ✅ ET0 模型
```

---

## 📊 步骤 4: 结果验证

### 4.1 检查 ET0 校正统计

```python
import pandas as pd

# 读取统计报告
stats = pd.read_csv('data/processed/qm_correction/correction_statistics.csv')

# 查看 ET0 的校正效果
et0_stats = stats[stats['variable'] == 'et0_fao_evapotranspiration']
print(et0_stats)
```

### 4.2 预期结果

合理的 ET0 校正效果:
- **偏差减少**: >50%
- **MAE 减少**: >30%
- **RMSE 减少**: >25%

如果效果不佳，可能原因:
1. CMA ET0 数据质量问题
2. 站点 - 网格匹配不准确
3. 分布函数选择不当

---

## 🔍 故障排查

### 问题 1: 找不到 CMA ET0 数据文件

**错误信息:**
```
FileNotFoundError: 站点数据文件不存在：data/processed/cma_et0/533520-99999_et0_daily.csv
```

**解决方案:**
1. 检查文件路径是否正确
2. 检查文件名格式：`{station_id}_et0_daily.csv`
3. 确认 station_id 与 NOAA 站点 ID 一致

### 问题 2: ET0 数据量不足

**错误信息:**
```
警告：站点 XXX 数据量不足，跳过
```

**解决方案:**
1. 检查 ET0 数据的时间覆盖范围
2. 确保至少有 100 个共同日期的数据
3. 如果数据确实不足，考虑使用更长的时间序列

### 问题 3: Gamma 分布拟合失败

**错误信息:**
```
RuntimeError: Gamma distribution fitting failed
```

**解决方案:**
1. 检查 ET0 数据中是否有负值（应该都是非负的）
2. 尝试使用经验分布代替 Gamma 分布
3. 检查零值比例是否过高

---

## 📝 代码修改清单

如果需要自定义 ET0 校正逻辑，可能需要修改以下文件:

| 文件 | 修改内容 | 优先级 |
|------|---------|--------|
| `run_qm_correction.py` | 添加 ET0 到 variables_to_correct | **必须** |
| `data_loader.py` | 检查 `load_cma_et0_data()` 方法 | 可选 |
| `qm_executor.py` | 为 ET0 设置 Gamma 分布 | 推荐 |
| `qm_core.py` | 无需修改（已支持 Gamma 分布） | 无需 |
| `spatial_interpolation.py` | 无需修改（通用插值） | 无需 |

---

## 🎓 技术说明

### 为什么 ET0 使用 Gamma 分布？

ET0 (参考作物蒸散量) 具有以下特点:
1. **非负性**: ET0 ≥ 0
2. **右偏分布**: 大部分值较小，少数极端大值
3. **季节性**: 夏季高，冬季低

Gamma 分布能够很好地刻画这些特征，因此被推荐用于 ET0 的 QM 校正。

### QM 校正的数学原理

对于 ET0 变量，QM 校正的公式为:

```
ET0_corrected = F_CMA^(-1)(F_ERA5(ET0_ERA5))
```

其中:
- `F_ERA5`: ERA5 ET0 数据的 CDF
- `F_CMA^(-1)`: CMA 观测 ET0 数据的逆 CDF
- `ET0_ERA5`: 待校正的 ERA5 ET0 值
- `ET0_corrected`: 校正后的 ET0 值

---

## 📚 参考文献

1. **QM 方法**:
   - Teutschbein, C., & Seibert, J. (2012). Bias correction of regional climate model simulations for hydrological climate-change impact studies. *Journal of Hydrology*.

2. **ET0 计算**:
   - Allen, R. G., et al. (1998). Crop evapotranspiration-Guidelines for computing crop water requirements-FAO Paper no. 56. *FAO, Rome*.

3. **ERA5 ET0 验证**:
   - 查找 ERA5 ET0 在中国区域的验证研究（建议引用 2-3 篇）

---

## 📞 联系与支持

如果在扩展过程中遇到问题:

1. 检查日志文件：`logs/qm_correction.log`
2. 查看代码注释（特别是 `data_loader.py` 的 `load_cma_et0_data` 方法）
3. 运行测试脚本验证各模块功能

---

## ✅ 完成检查清单

获取 CMA ET0 数据后，按以下清单操作:

- [ ] 数据已放置在 `data/processed/cma_et0/` 目录
- [ ] 数据格式符合要求（date, et0_obs 列）
- [ ] 文件名格式：`{station_id}_et0_daily.csv`
- [ ] 修改 `run_qm_correction.py` 添加 ET0 到变量列表
- [ ] (推荐) 为 ET0 设置 Gamma 分布
- [ ] 运行校正脚本
- [ ] 检查输出文件是否包含 ET0
- [ ] 验证 ET0 校正效果（统计指标）
- [ ] 保存 ET0 QM 模型
- [ ] 更新论文/报告中的方法描述

---

**最后更新:** 2026-03-14  
**版本:** v1.0  
**状态:** ✅ 核心功能完成 | ⏸️ ET0 扩展待实现
