# QM 偏差校正系统架构文档

## 🏗️ 系统概述

本系统实现了完整的**分位数映射 (Quantile Mapping, QM)** 偏差校正流程，用于校正华北平原气象再分析数据的系统偏差。

### 设计目标

1. ✅ **准确性**: 显著降低 ERA5-Land 数据的系统偏差
2. ✅ **可扩展性**: 预留 ET0 校正接口，支持后续扩展
3. ✅ **模块化**: 清晰的模块划分，易于维护和测试
4. ✅ **可重复性**: 完整的日志和配置管理
5. ✅ **用户友好**: 一键运行，自动生成报告

---

## 📐 架构设计

### 分层架构

```
┌─────────────────────────────────────────┐
│          应用层 (Application)            │
│  ┌─────────────────────────────────┐   │
│  │ run_qm_correction.py            │   │
│  │ - 主运行脚本                     │   │
│  │ - 配置管理                       │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         协调层 (Coordination)            │
│  ┌─────────────────────────────────┐   │
│  │ QMExecutor                      │   │
│  │ - 流程控制                       │   │
│  │ - 资源调度                       │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         核心层 (Core)                    │
│  ┌───────────┐  ┌───────────┐          │
│  │ DataManager│  │QuantileMapper│       │
│  │ - 数据加载 │  │ - QM 算法   │          │
│  │ - 时空匹配 │  │ - 分布拟合  │          │
│  └───────────┘  └───────────┘          │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         工具层 (Utilities)               │
│  ┌───────────┐  ┌───────────┐          │
│  │ Quality    │  │ Spatial    │          │
│  │ Assessment │  │ Interpolator│         │
│  │ - 评估指标 │  │ - IDW      │          │
│  │ - 可视化   │  │ - Kriging  │          │
│  └───────────┘  └───────────┘          │
└─────────────────────────────────────────┘
```

---

## 📦 模块详细说明

### 1. 数据加载层 (`data_loader.py`)

**职责:** 
- 从 PostgreSQL 加载网格数据
- 从 CSV 加载 NOAA 站点数据
- 【预留】从 CMA 加载 ET0 数据
- 时空匹配（站点 - 网格点对应）

**关键方法:**
```python
class DataManager:
    def load_grid_data(...)           # 加载网格数据
    def load_noaa_station_data(...)   # 加载 NOAA 数据
    def load_cma_et0_data(...)        # 【预留】加载 CMA ET0
    def get_matched_pairs(...)        # 获取匹配的数据对
```

**扩展点:**
- `load_cma_et0_data()`: 已预留，待 CMA 数据

---

### 2. QM 核心层 (`qm_core.py`)

**职责:**
- 实现分位数映射算法
- 支持多种分布拟合
- 支持月度/季节性校正

**关键方法:**
```python
class QuantileMapper:
    def fit(...)                      # 拟合 QM 模型
    def transform(...)                # 应用校正
    def save() / load()              # 模型持久化
```

**分布类型:**
- `empirical`: 经验分布（通用）
- `normal`: 正态分布（温度）
- `gamma`: Gamma 分布（降水、ET0）

---

### 3. 协调层 (`qm_executor.py`)

**职责:**
- 协调整个校正流程
- 批量处理多个站点和变量
- 保存结果和模型

**关键方法:**
```python
class QMExecutor:
    def run_correction(...)           # 执行完整流程
    def _save_correction_results()    # 保存结果
    def _save_qm_models()             # 保存模型
    def get_correction_statistics()   # 生成统计
```

---

### 4. 质量评估层 (`quality_assessment.py`)

**职责:**
- 计算误差指标（MAE, RMSE, Bias）
- 生成交叉验证结果
- 创建可视化图表

**关键方法:**
```python
class QualityAssessment:
    def compute_metrics(...)          # 计算指标
    def create_assessment_report()    # 生成报告
    def plot_results()                # 绘制图表
```

**评估指标:**
- Bias (偏差)
- MAE (平均绝对误差)
- RMSE (均方根误差)
- R² (决定系数)
- Correlation (相关系数)

---

### 5. 空间插值层 (`spatial_interpolation.py`)

**职责:**
- 将站点校正因子插值到全域网格
- 支持 IDW 和 Kriging 方法
- 【预留】ET0 校正因子插值

**关键方法:**
```python
class SpatialInterpolator:
    def interpolate(...)              # 执行插值
    def _idw_interpolate()           # IDW 方法
    def _kriging_interpolate()       # Kriging 方法

class QMFieldInterpolator:
    def interpolate_correction_factors()  # 插值校正因子
    def apply_field_correction()         # 应用场校正
```

---

## 🔄 数据流

### 校正流程

```
1. 数据加载
   ├─ PostgreSQL → 网格数据 (ERA5-Land)
   ├─ CSV → NOAA 站点数据
   └─ 【预留】CSV → CMA ET0 数据
   
2. 时空匹配
   └─ 站点 - 网格点对齐
   
3. QM 拟合
   ├─ 计算经验/理论分布
   └─ 建立分位数映射关系
   
4. 应用校正
   ├─ 对每个变量应用 QM 变换
   └─ 生成校正后数据
   
5. 质量评估
   ├─ 计算误差指标
   └─ 生成可视化图表
   
6. 空间插值
   ├─ 插值站点校正因子
   └─ 应用到全域网格
```

---

## 🔌 扩展性设计

### 已实现的扩展点

#### 1. ET0 校正接口

**位置:** `data_loader.py::load_cma_et0_data()`

**触发条件:** 
- 获取到中国气象数据网的 ET0 数据
- 数据放置在 `data/processed/cma_et0/` 目录

**启用步骤:**
1. 准备 CMA ET0 数据
2. 在 `run_qm_correction.py` 中添加 `'et0_fao_evapotranspiration'` 到变量列表
3. 运行主脚本

**代码位置:**
```python
# data_loader.py 第 156-196 行
def load_cma_et0_data(self, station_id, start_year, end_year):
    """【预留接口】加载中国气象数据网的 ET0 观测数据"""
    # 已实现，目前返回 None
    # 获取数据后取消注释
```

#### 2. 新变量支持

**添加新变量的步骤:**
1. 在 `run_qm_correction.py` 的 `variables_to_correct` 中添加变量名
2. 确保数据源包含该变量
3. (可选) 为该变量指定特定分布类型

**示例:**
```python
CONFIG = {
    'variables_to_correct': [
        'temperature',
        'precipitation',
        'wind_speed',
        'relative_humidity',
        'et0_fao_evapotranspiration',
        'solar_radiation'  # 【未来】添加太阳辐射
    ]
}
```

#### 3. 新分布类型支持

**添加新分布的步骤:**
1. 在 `qm_core.py` 中添加新的分布计算方法
2. 在 `_compute_mapping()` 中添加分支
3. 在 `_apply_mapping()` 中添加变换逻辑

**示例:**
```python
def _compute_weibull_mapping(self, sim_values, obs_values):
    """Weibull 分布映射（可用于风速）"""
    # 实现 Weibull 分布拟合
    ...
```

---

## 📊 配置管理

### 配置层次

```
1. 主配置 (run_qm_correction.py)
   └─ CONFIG 字典
   
2. QM 参数配置
   └─ n_quantiles, distribution, monthly
   
3. 变量特定配置 (可选)
   └─ 为不同变量指定不同分布
```

### 配置文件

**当前:** 硬编码在 `run_qm_correction.py` 中

**未来扩展:** 
- 支持 YAML/JSON 配置文件
- 支持命令行参数
- 支持环境变量

---

## 📝 日志系统

### 日志级别

- `INFO`: 正常流程信息
- `WARNING`: 警告（如数据不足）
- `ERROR`: 错误（如文件不存在）
- `DEBUG`: 调试信息（需手动开启）

### 日志输出

1. **控制台:** 实时显示进度
2. **文件:** `logs/qm_correction.log`
3. **结构化:** 时间戳 + 模块名 + 级别 + 消息

---

## 🎯 性能优化

### 当前优化

1. **批量处理:** 一次性加载所有网格点数据
2. **月度校正:** 并行处理 12 个月
3. **内存管理:** 及时释放不用的数据

### 未来优化

1. **并行处理:** 使用 `multiprocessing` 并行处理站点
2. **增量处理:** 支持增量更新（不必重新处理所有数据）
3. **数据库优化:** 使用索引加速查询

---

## 🧪 测试策略

### 单元测试

**位置:** `tests/test_qm_*.py` (待创建)

**测试内容:**
- QM 算法正确性
- 数据加载完整性
- 边界条件处理

### 集成测试

**测试流程:**
1. 使用小数据集（1 年，1 个站点）
2. 运行完整流程
3. 验证输出文件

### 验证测试

**验证内容:**
- 校正后偏差是否减少
- 统计指标是否合理
- 可视化图表是否正确

---

## 📚 依赖管理

### 核心依赖

```txt
pandas>=1.3.0
numpy>=1.20.0
scipy>=1.7.0
scikit-learn>=0.24.0
psycopg2-binary>=2.9.0
matplotlib>=3.4.0
seaborn>=0.11.0
```

### 可选依赖

```txt
# 空间插值（如果使用 Kriging）
scikit-gstat>=1.0.0

# 并行处理
joblib>=1.0.0
```

---

## 🚀 部署指南

### 本地运行

```bash
# 1. 克隆仓库
git clone <repo_url>
cd gra_env_dev

# 2. 创建虚拟环境
python -m venv venv
.\venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置数据库连接

# 5. 运行 QM 校正
python scripts\data_processing\qm_correction\run_qm_correction.py
```

### Docker 部署（未来）

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "scripts/data_processing/qm_correction/run_qm_correction.py"]
```

---

## 📋 检查清单

### 运行前检查

- [ ] PostgreSQL 服务运行正常
- [ ] NOAA 数据预处理完成
- [ ] 数据库连接配置正确
- [ ] 输出目录有写入权限
- [ ] 依赖包已安装

### 运行后验证

- [ ] 校正结果文件已生成
- [ ] QM 模型已保存
- [ ] 统计报告完整
- [ ] 评估图表正常显示
- [ ] 日志无 ERROR 级别错误

---

## 🔮 未来版本计划

### v1.1 (如果获取 CMA ET0 数据)

- [ ] ET0 变量校正
- [ ] ET0 质量评估
- [ ] 更新文档

### v1.2 (性能优化)

- [ ] 并行化处理
- [ ] 内存优化
- [ ] 进度条显示

### v2.0 (功能扩展)

- [ ] 支持更多变量（太阳辐射、气压等）
- [ ] 交互式配置界面
- [ ] 自动化报告生成
- [ ] 时间序列可视化

---

## 📞 技术支持

### 常见问题

参见 `README.md` 的"故障排查"章节

### 联系信息

- 项目仓库：[Your Repo]
- 问题反馈：[Issue Tracker]
- 邮箱：[Your Email]

---

**架构版本:** v1.0  
**最后更新:** 2026-03-14  
**维护状态:** ✅ 活跃维护 | ⏸️ ET0 扩展待实现
