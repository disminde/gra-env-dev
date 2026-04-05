# 数据工程与特征构建技术文档
**Data Engineering and Feature Construction Technical Document**

本文档详细记录了本项目从原始日级气象数据（1.76亿条）到最终机器学习宽表（约305万条）的完整数据流转过程、表结构演变及关键技术决策。该文档旨在为后续的深度学习模型开发（如 XGBoost、ConvLSTM）以及学术论文写作提供权威的数据结构参考。

---

## 1. 原始数据层 (Raw Data Layer)

### 1.1 `high_res_daily_weather_et0` (日级高分辨率气象表)
这是整个系统最底层、最原始的“原材料”表，数据来源于 Open-Meteo API 的高分辨率再分析数据集。

*   **数据规模**：约 1.76 亿条记录。
*   **空间范围**：覆盖整个华北平原（约 8050 个 $0.1^\circ \times 0.1^\circ$ 网格点）。
*   **时间跨度**：1980年1月1日 至今（日级步长）。
*   **核心字段**：
    *   `latitude` (NUMERIC): 纬度坐标。
    *   `longitude` (NUMERIC): 经度坐标。
    *   `date` (DATE): 日期。
    *   `temperature` (NUMERIC): 日平均气温 (℃)。
    *   `precipitation` (NUMERIC): 日总降水量 (mm)。
    *   `wind_speed` (NUMERIC): 日平均风速 (m/s)。
    *   `relative_humidity` (NUMERIC): 日平均相对湿度 (%)。
    *   `shortwave_radiation` (NUMERIC): 日总短波辐射 ($MJ/m^2$)。
    *   `et0` (NUMERIC): 日参考作物蒸散发量 (mm)，基于 Penman-Monteith 公式在入库时计算生成。

---

## 2. 指数计算层 (Index Calculation Layer)

### 2.1 `monthly_spei_features` (月度干旱指数与盈亏表)
该表是将日级数据按月聚合，并运用气象学分布拟合算法计算出的多尺度标准化降水蒸散指数 (SPEI)。

*   **数据规模**：约 410 万条记录 (8050 个网格点 $\times$ 约 510 个月)。
*   **空间维度**：保留原有的高分辨率网格 (`latitude`, `longitude`)。
*   **时间维度**：`year` (INT), `month` (INT)。
*   **基础聚合特征**：
    *   `p_sum` (NUMERIC): 月总降水量。
    *   `et0_sum` (NUMERIC): 月总蒸散发量。
    *   `d_value` (NUMERIC): 当前月度水分盈亏 ($P - ET_0$)。
*   **多尺度累积盈亏**：
    *   `d_1`, `d_3`, `d_12` (NUMERIC): 分别代表过去 1个月、3个月、12个月的累积水分盈亏，用于后续概率分布拟合。
*   **标准化干旱指数 (核心变量)**：
    *   `spei_1` (NUMERIC): 1个月尺度 SPEI，反映短期气象干旱。
    *   `spei_3` (NUMERIC): 3个月尺度 SPEI，反映农业干旱（如作物关键生长期缺水），是本系统的主要预测目标。
    *   `spei_12` (NUMERIC): 12个月尺度 SPEI，反映长期水文干旱（地下水、水库蓄水）。

---

## 3. 机器学习特征层 (Machine Learning Feature Layer)

为了将上述时间序列数据转化为可供监督学习模型（如随机森林、XGBoost、LSTM）训练的格式，我们执行了极其复杂的特征工程，并将结果持久化。

### 3.1 `ml_feature_table.parquet` (最终机器学习大宽表)
*   **持久化格式**：Parquet（列式存储，保留数据类型，读取速度极快）。
*   **数据规模**：3,059,000 行（由于计算历史滞后和未来目标，剔除了前12个月和末尾6个月的边缘 `NaN` 行）。
*   **特征维度**：90 列（不含动态生成的聚类标签）。
*   **构建策略**：采用**分块处理 (Chunking)** 与 PostgreSQL Window Functions 结合，成功规避了 Pandas 在处理千万级滑动窗口时的内存溢出 (OOM) 危机。

#### 表结构详情 (90列)

**1. 时空标识 (4列)**
*   `latitude`, `longitude`, `year`, `month`

**2. 基础物理量 (13列)**
*   从 `monthly_spei_features` 继承：`p_sum`, `et0_sum`, `d_value`, `d_1`, `d_3`, `d_12`, `spei_1`, `spei_3`, `spei_12`
*   从 `high_res_daily_weather_et0` 通过 SQL 下推聚合的辅助物理量：`temp_mean` (月均温), `humidity_mean` (月均相对湿度), `wind_speed_mean` (月均风速), `radiation_sum` (月总辐射)

**3. 历史滞后特征 (Lagged Features - 60列)**
模型的时间记忆核心，提取了关键变量过去 1~12 个月的状态：
*   `p_sum_lag1` ... `p_sum_lag12`
*   `temp_mean_lag1` ... `temp_mean_lag12`
*   `spei_1_lag1` ... `spei_1_lag12`
*   `spei_3_lag1` ... `spei_3_lag12`
*   `spei_12_lag1` ... `spei_12_lag12`

**4. 滚动统计量 (Rolling Statistics - 8列)**
捕捉短期气候波动的极值和方差：
*   过去 3 个月：`p_sum_rolling3_mean`, `p_sum_rolling3_var`, `temp_mean_rolling3_max`, `temp_mean_rolling3_min`
*   过去 6 个月：`p_sum_rolling6_mean`, `p_sum_rolling6_var`, `temp_mean_rolling6_max`, `temp_mean_rolling6_min`

**5. 时间周期编码 (2列)**
将离散的 `month` 转化为连续的三角函数，供模型学习季节周期性：
*   `month_sin`, `month_cos`

**6. 未来预测目标 (Target Labels - 3列)**
利用 `LEAD()` 函数生成的未来状态标签，用于监督学习：
*   `target_spei_1m_ahead`：未来 1 个月的 SPEI-3（**基准线测试证明可预测，R² > 0.15**）
*   `target_spei_3m_ahead`：未来 3 个月的 SPEI-3（当前纯空间局地特征难以支撑预测，导致 R² < 0）
*   `target_spei_6m_ahead`：未来 6 个月的 SPEI-3

---

## 4. 关键技术决策与诊断记录 (Technical Decisions & Diagnostics)

在基准模型（Random Forest）的构建与验证过程中，我们进行了多次深度的逻辑排雷与技术迭代，这些经验对后续深度学习模型的开发至关重要。

### 4.1 放弃“差分法”，坚持“绝对值拟合”
*   **诊断**：在早期测试中，试图让模型预测 `delta_target` (未来值与当前值的差值)，导致测试集 $R^2$ 严重为负（-0.09）。
*   **物理原因**：以预测未来 3 个月的 SPEI-3 为例，当前时刻的 SPEI-3 (包含 $t, t-1, t-2$) 与未来时刻的 SPEI-3 (包含 $t+3, t+2, t+1$) 在时间滚动窗口上**完全没有交集**。两者自相关性极弱，强制预测差分会导致模型退化为“持续性预测 (Persistence Forecast)”，在数学上必然导致 $R^2$ 成为严重的负数。
*   **决策**：全面放弃预测变化量，模型必须直接根据历史特征去硬性拟合未来的绝对值状态。

### 4.2 空间异质性处理 (Spatial Heterogeneity)
*   **诊断**：华北平原地形气候复杂（沿海、山区、内陆），将 8000 个网格点混合训练全局模型会抹杀局地气候规律。
*   **决策**：不删除经纬度坐标，并引入 `K-Means` 聚类（设 `n_clusters=15`），将经纬度映射为离散的 `spatial_zone` 并进行 One-Hot 编码。这赋予了树模型“感知空间区域”的能力。

### 4.3 滚动交叉验证 (Walk-Forward Validation)
*   **诊断**：由于我们的数据是面板数据（Panel Data，同一时间有8000个截面），使用 `sklearn.model_selection.TimeSeriesSplit` 会强行从矩阵中间切断，破坏单个月份的空间完整性。
*   **决策**：采用**手动按年份截断**的滚动验证策略。
    *   Fold 1: Train(1980-2010) -> Test(2011-2015)
    *   Fold 2: Train(1980-2015) -> Test(2016-2019)
    *   Fold 3: Train(1980-2019) -> Test(2020-至今)
    *   这种方式绝对杜绝了时间泄露（Data Leakage），是评测气候预测模型泛化能力的最严谨标准。

### 4.5 深度学习阶段 (ConvLSTM) 的数据工程演进与排雷记录

在引入 ConvLSTM 模型尝试进行时空序列预测时，我们对数据形态和特征处理进行了深度的重构与优化。以下是关键的数据工程步骤及其对模型性能（R²）的直接影响：

#### 1. 时空张量构建 (Tabular to 3D Tensor)
*   **操作**：将原本的 2D 机器学习宽表（`ml_feature_table.parquet`）按月份和经纬度映射，重构为 5D 张量 `(Samples, Seq_Len, Channels, Height, Width)`。网格分辨率为 101 x 126，序列长度设为 12 个月。
*   **空间稀疏性处理 (Spatial Masking)**：
    *   华北平原的有效网格点为 8050 个，而生成的 101x126 矩形网格包含 12726 个像素，存在大量无效的背景区域（海洋、非研究区）。
    *   **初始问题**：最初将背景区域填充为 `0` 并让其参与全局 Loss 计算。最终得出的R² 分数为0.15左右（后面的所有优化几乎都在起反作用）
    *   **尝试优化方案**：在 PyTorch Dataset 中引入 `Spatial Mask`（基于目标变量的非 NaN 区域生成），在训练和验证的 `criterion(output[mask], target[mask])` 阶段。
    *   **遥相关数据引入**：试图将 Niño 3.4、PDO、WPSH 等 7 个宏观气候指数加入 ConvLSTM 的特征通道中。由于这些指数在同一时间截面上对所有网格点的值是相同的，我们采用了“平铺 (Tiling)”的方式将其扩展为全图一致的 2D 通道。
    *   **归一化**：为了解决降水（0~300mm）和气温（-10~35℃）尺度差异巨大的问题，引入了 `StandardScaler` 进行 Z-Score 归一化。

     *   **结果**：R² 分数暴跌至-0.0421左右，随后取消遥相关数据引入，R² 分数恢复至约-0.03，随后又尝试用 np.nan_to_num 强行把海洋变成 0，R² 分数无明显上升。


---

## 5. 实时增量数据工程 (Live Inference Data Pipeline)

为了支撑 Streamlit 前端页面展示当前（如2026年）最新的干旱状态及 SHAP 归因分析，我们设计了一套轻量级的增量数据更新策略，以应对 Open-Meteo API 的访问限额问题。

### 5.1 数据获取降维 (Daily vs Hourly)
*   **策略**：在历史模型训练阶段，我们曾依赖高分辨率的小时级数据进行精细化 ET0 计算；但在实时推演阶段，为保证系统的可用性，我们改为拉取**日级 (Daily)** 气象数据。
*   **优势**：数据获取量直接缩减为原来的 1/24，极大降低了触发 API 封禁（Rate Limit）的风险，无需再依赖虚拟 IP 即可稳定获取最新数据。

### 5.2 日级到月级的在线聚合 (Daily to Monthly Aggregation)
获取到最新的日级数据后，需要在线执行与历史数据工程完全一致的聚合逻辑，以对齐 XGBoost 模型的输入特征空间（90维）：
*   **基础聚合**：按 `year` 和 `month` 将日级 `precipitation` 累加为 `p_sum`，将日级 `temperature` 平均为 `temp_mean`。
*   **滞后与滚动特征**：拼接系统已有的历史末尾数据（如2023年底的数据），计算最新的过去 1~12 个月的滞后特征（Lagged Features）以及 3/6 个月的滚动统计量（Rolling Statistics）。

### 5.3 离线与在线解耦架构 (Decoupled Architecture)
*   **离线更新脚本 (`update_latest_data.py`)**：作为一个独立的后台任务运行。它负责请求 API、执行上述日级到月级的聚合计算、生成最新的机器学习特征宽表，并覆盖保存至本地（如 `latest_inference_features.parquet`）。
*   **在线展示前端 (`streamlit_app.py`)**：前端仪表盘完全不参与数据获取，仅负责加载本地的 `.parquet` 文件，将其喂给 XGBoost 模型进行 SPEI 预测、What-If 情景扰动以及生成 SHAP 瀑布图/摘要图。
*   **结果裁剪**：为防止极端异常值影响前端 Mapbox 地图的视觉呈现，预测的 SPEI 结果会在前端进行 `[-3.0, 3.0]` 的截断处理（Clipping）。