# 干旱研究概念与方法笔记

> 本文档用于记录华北平原干旱时空演变研究中的核心概念、计算方法和理论基础，为后续论文写作提供参考。

---

## 📚 目录

- [1. 潜在蒸散 (ET0)](#1-潜在蒸散-et0)
- [2. 标准化降水蒸散指数 (SPEI)](#2-标准化降水蒸散指数-spei)
- [3. 干旱识别与特征分析](#3-干旱识别与特征分析)
- [4. 趋势检测方法](#4-趋势检测方法)
- [5. 深度学习基础](#5-深度学习基础)

---

## 1. 潜在蒸散 (ET0)

### 1.1 定义

**潜在蒸散 (Potential Evapotranspiration, ET0)**：指在充分供水条件下，下垫面（草地或参考作物）的最大可能蒸散量。它是衡量大气蒸发需求的重要指标。

### 1.2 FAO-56 Penman-Monteith 公式

**标准公式**：

$$ET_0 = \frac{0.408\Delta(R_n - G) + \gamma\frac{900}{T + 273}u_2(e_s - e_a)}{\Delta + \gamma(1 + 0.34u_2)}$$

**参数说明**：

| 符号 | 含义 | 单位 |
|------|------|------|
| $ET_0$ | 参考作物蒸散量 | mm/day |
| $R_n$ | 净辐射 | MJ/m²/day |
| $G$ | 土壤热通量 | MJ/m²/day |
| $T$ | 平均气温 | °C |
| $u_2$ | 2m 高度风速 | m/s |
| $e_s - e_a$ | 饱和水汽压差 | kPa |
| $\Delta$ | 饱和水汽压 - 温度关系斜率 | kPa/°C |
| $\gamma$ | 湿度计常数 | kPa/°C |

**计算步骤**：

1. **饱和水汽压**：$e_s = 0.6108 \exp\left(\frac{17.27T}{T + 237.3}\right)$
2. **实际水汽压**：$e_a = e_s \times \frac{RH}{100}$
3. **水汽压差**：$VPD = e_s - e_a$
4. **净短波辐射**：$R_{ns} = R_s(1 - \alpha)$，$\alpha = 0.23$（草地反照率）
5. **净长波辐射**：$R_{nl} = \sigma T^4(0.34 - 0.14\sqrt{e_a})(1.35\frac{R_s}{R_a} - 0.35)$
6. **净辐射**：$R_n = R_{ns} - R_{nl}$

### 1.3 在本研究中的应用

- **数据来源**：基于优化后的网格点气象数据（温度、湿度、风速、辐射）
- **时间分辨率**：日尺度
- **空间分辨率**：0.1° × 0.1°（5751 个网格点）
- **时间跨度**：1990-2023 年（34 年）

---

## 2. 标准化降水蒸散指数 (SPEI)

### 2.1 定义

**SPEI (Standardized Precipitation Evapotranspiration Index)**：是一种基于水分平衡原理的多时间尺度干旱指数，综合考虑了降水和潜在蒸散的作用。

**核心优势**：
- ✅ 对温度敏感，能反映气候变化对干旱的影响
- ✅ 多时间尺度，可识别不同类型的干旱
- ✅ 空间可比性强，适用于不同气候区

### 2.2 计算流程

#### 步骤 1：水分平衡计算

$$D_i = P_i - ET0_i$$

- $P_i$：第 $i$ 时段降水量
- $ET0_i$：第 $i$ 时段潜在蒸散量
- $D_i$：水分盈亏值（正值为盈余，负值为亏损）

#### 步骤 2：时间尺度累积

对于时间尺度 $k$：

$$D_k(i) = \sum_{j=i-k+1}^{i} D_j$$

**常用时间尺度及其含义**：

| 时间尺度 | 名称 | 适用干旱类型 |
|---------|------|-------------|
| SPEI-1 | 1 个月 | 短期干旱、气象干旱 |
| SPEI-3 | 3 个月 | 季节性干旱、农业干旱 |
| SPEI-6 | 6 个月 | 中期干旱 |
| SPEI-12 | 12 个月 | 长期干旱、水文干旱 |

#### 步骤 3：概率分布拟合

采用**三参数 Log-Logistic 分布**拟合累积序列 $D_k$：

**概率密度函数**：

$$f(x) = \frac{\beta}{\alpha}\left(\frac{x-\gamma}{\alpha}\right)^{\beta-1} \left[1 + \left(\frac{x-\gamma}{\alpha}\right)^\beta\right]^{-2}$$

**参数含义**：
- $\alpha$：尺度参数 (scale parameter, $\alpha > 0$)
- $\beta$：形状参数 (shape parameter, $\beta > 0$)
- $\gamma$：位置参数 (location parameter)

**参数估计方法**：L-矩法 (L-moments)

L-矩相比传统矩的优势：
1. 受异常值影响小
2. 估计更稳健
3. 收敛更快

#### 步骤 4：标准化

**累积概率**：

$$F(x) = \left[1 + \left(\frac{\alpha}{x-\gamma}\right)^\beta\right]^{-1}$$

**转换为标准正态分布变量**：

令 $P = 1 - F(x)$，则：

$$
Z = \begin{cases}
-\left(t - \frac{c_0 + c_1t + c_2t^2}{1 + d_1t + d_2t^2 + d_3t^3}\right), & P \leq 0.5 \\
+\left(t - \frac{c_0 + c_1t + c_2t^2}{1 + d_1t + d_2t^2 + d_3t^3}\right), & P > 0.5
\end{cases}
$$

其中：
- $t = \sqrt{-2\ln(P)}$
- 常数：$c_0=2.515517$, $c_1=0.802853$, $c_2=0.010328$
- 常数：$d_1=1.432788$, $d_2=0.189269$, $d_3=0.001308$

**最终 SPEI 值**：$SPEI = Z$

### 2.3 SPEI 干旱分级

| SPEI 值范围 | 干旱等级 | 理论频率 | 特征描述 |
|------------|---------|---------|---------|
| SPEI ≥ 1.5 | 极端湿润 | 6.7% | 降水远多于常年 |
| 1.0 ≤ SPEI < 1.5 | 重度湿润 | 9.2% | 降水明显多于常年 |
| 0.5 ≤ SPEI < 1.0 | 轻度湿润 | 9.2% | 降水略多于常年 |
| -0.5 ≤ SPEI < 0.5 | 正常 | 49.8% | 降水接近常年 |
| -1.0 ≤ SPEI < -0.5 | 轻度干旱 | 9.2% | 降水略少于常年 |
| -1.5 ≤ SPEI < -1.0 | 中度干旱 | 9.2% | 降水明显少于常年 |
| SPEI < -1.5 | 极端干旱 | 6.7% | 降水远少于常年 |

### 2.4 干旱特征提取

基于 SPEI 时间序列，可识别干旱事件并提取特征：

**干旱事件识别**：
- **干旱开始**：SPEI 由正转负，且持续≤-0.5
- **干旱结束**：SPEI 由负转正
- **干旱过程线**：连续负 SPEI 值序列

**干旱特征变量**：

1. **干旱历时 (Duration)**：单次干旱事件持续的月数/天数
   $$D = t_{end} - t_{start} + 1$$

2. **干旱强度 (Intensity)**：干旱期间 SPEI 累积值
   $$I = \sum_{t=t_{start}}^{t_{end}} |SPEI_t|$$

3. **干旱烈度 (Severity)**：干旱期间 SPEI 最小值
   $$S = \min(SPEI_t)$$

4. **干旱峰值 (Peak)**：干旱期间 SPEI 的最低值
   $$P = \min_{t \in [t_{start}, t_{end}]} SPEI_t$$

5. **干旱影响范围 (Areal Extent)**：受干旱影响的区域面积比例

---

## 3. 干旱识别与特征分析

### 3.1 游程理论 (Run Theory)

**基本原理**：将连续的时间序列转换为干旱事件序列。

**定义**：
- **游程 (Run)**：连续满足特定条件的序列段
- **截断水平 (Threshold)**：通常为 SPEI = 0 或 SPEI = -0.5
- **游程长度**：干旱持续时间
- **游程和**：干旱强度

### 3.2 干旱频率分析

**经验频率公式**：

$$P(X \geq x) = \frac{m}{n+1} \times 100\%$$

- $m$：大于等于$x$ 的排序号
- $n$：样本总数

**重现期 (Return Period)**：

$$T = \frac{n+1}{m}$$

表示某一级别干旱事件平均多少年出现一次。

---

## 4. 趋势检测方法

### 4.1 Mann-Kendall 趋势检验

**适用场景**：非参数检验，不要求数据服从正态分布，对异常值不敏感。

**原假设 $H_0$**：时间序列无趋势

**统计量计算**：

$$S = \sum_{i=1}^{n-1}\sum_{j=i+1}^{n} \text{sgn}(x_j - x_i)$$

其中：
$$
\text{sgn}(\theta) = \begin{cases}
1, & \theta > 0 \\
0, & \theta = 0 \\
-1, & \theta < 0
\end{cases}
$$

**标准化统计量**：

$$Z = \begin{cases}
\frac{S-1}{\sqrt{Var(S)}}, & S > 0 \\
0, & S = 0 \\
\frac{S+1}{\sqrt{Var(S)}}, & S < 0
\end{cases}$$

**显著性判断**：
- $|Z| > 1.645$：90% 置信水平显著
- $|Z| > 1.96$：95% 置信水平显著
- $|Z| > 2.576$：99% 置信水平显著

### 4.2 Sen's Slope 估计

**目的**：计算趋势的斜率（变化速率）

**公式**：

$$\beta = \text{Median}\left(\frac{x_j - x_i}{j - i}\right), \quad \forall i < j$$

**含义**：
- $\beta > 0$：上升趋势
- $\beta < 0$：下降趋势
- $|\beta|$：变化速率

---

## 5. 深度学习基础

### 5.1 卷积神经网络 (CNN)

**核心思想**：利用卷积核提取局部特征。

**关键组件**：

1. **卷积层 (Convolutional Layer)**
   - 局部连接
   - 权值共享
   - 特征提取

2. **池化层 (Pooling Layer)**
   - 降维
   - 平移不变性
   - 常用：Max Pooling, Average Pooling

3. **全连接层 (Fully Connected Layer)**
   - 特征整合
   - 分类/回归

**在本研究中的应用**：
- 提取干旱时空特征
- 识别干旱传播模式

### 5.2 长短期记忆网络 (LSTM)

**解决的问题**：传统 RNN 的梯度消失问题，适合捕捉长距离依赖。

**核心结构**：

1. **遗忘门 (Forget Gate)**：决定丢弃什么信息
   $$f_t = \sigma(W_f \cdot [h_{t-1}, x_t] + b_f)$$

2. **输入门 (Input Gate)**：决定更新什么信息
   $$i_t = \sigma(W_i \cdot [h_{t-1}, x_t] + b_i)$$
   $$\tilde{C}_t = \tanh(W_C \cdot [h_{t-1}, x_t] + b_C)$$

3. **细胞状态更新**：
   $$C_t = f_t \odot C_{t-1} + i_t \odot \tilde{C}_t$$

4. **输出门 (Output Gate)**：决定输出什么信息
   $$o_t = \sigma(W_o \cdot [h_{t-1}, x_t] + b_o)$$
   $$h_t = o_t \odot \tanh(C_t)$$

**符号说明**：
- $x_t$：t 时刻输入
- $h_t$：t 时刻隐藏状态
- $C_t$：t 时刻细胞状态
- $\sigma$：sigmoid 激活函数
- $\odot$：逐元素乘法

**在本研究中的应用**：
- 干旱时间序列预测
- 干旱传播滞后效应分析

### 5.3 卷积 LSTM (ConvLSTM)

**核心思想**：将 CNN 的空间特征提取能力与 LSTM 的时间序列建模能力结合。

**公式**：将 LSTM 中的全连接替换为卷积：

$$
\begin{aligned}
i_t &= \sigma(W_{xi} * X_t + W_{hi} * H_{t-1} + b_i) \\
f_t &= \sigma(W_{xf} * X_t + W_{hf} * H_{t-1} + b_f) \\
o_t &= \sigma(W_{xo} * X_t + W_{ho} * H_{t-1} + b_o) \\
C_t &= f_t \odot C_{t-1} + i_t \odot \tanh(W_{xc} * X_t + W_{hc} * H_{t-1} + b_c) \\
H_t &= o_t \odot \tanh(C_t)
\end{aligned}
$$

其中 $*$ 表示卷积操作。

**优势**：
- ✅ 同时捕捉时空特征
- ✅ 适合网格化数据（如气象场）
- ✅ 能建模时空传播过程

**在本研究中的应用**：
- 干旱时空传播模拟
- 干旱发展趋势预测
- 干旱影响范围预测

### 5.4 评估指标

#### 回归问题评估：

1. **均方根误差 (RMSE)**：
   $$RMSE = \sqrt{\frac{1}{n}\sum_{i=1}^{n}(y_i - \hat{y}_i)^2}$$

2. **平均绝对误差 (MAE)**：
   $$MAE = \frac{1}{n}\sum_{i=1}^{n}|y_i - \hat{y}_i|$$

3. **决定系数 ($R^2$)**：
   $$R^2 = 1 - \frac{\sum(y_i - \hat{y}_i)^2}{\sum(y_i - \bar{y})^2}$$

#### 分类问题评估：

1. **准确率 (Accuracy)**：
   $$Accuracy = \frac{TP + TN}{TP + TN + FP + FN}$$

2. **精确率 (Precision)**：
   $$Precision = \frac{TP}{TP + FP}$$

3. **召回率 (Recall)**：
   $$Recall = \frac{TP}{TP + FN}$$

4. **F1 分数**：
   $$F1 = 2 \times \frac{Precision \times Recall}{Precision + Recall}$$

---

## 6. SPEI 计算实施记录

### 6.1 数据准备

**时间**：2025-03-20

**数据来源**：
- ET0 数据：`optimized_et0_grid_data` 表
- 降水数据：`precipitation_used` 列（与 ET0 同表）

**数据规模**：
- 总记录数：约 3800 万条
- 时间范围：1990-01-01 到 2023-12-31
- 网格点数：5751 个（81×71，0.1°分辨率）
- 时间跨度：34 年（12,418 天）

### 6.2 计算流程

**步骤 1：水分平衡计算**
```python
D_i = P_i - ET0_i
```

**步骤 2：时间尺度累积**
- SPEI-1：1 个月尺度
- SPEI-3：3 个月尺度
- SPEI-6：6 个月尺度
- SPEI-12：12 个月尺度

**步骤 3：Log-Logistic 分布拟合**
- 参数估计方法：L-矩法
- 参数：α (尺度), β (形状), γ (位置)

**步骤 4：标准化**
- 转换为标准正态分布变量 Z

### 6.3 技术细节

**计算策略**：
- 按网格点逐点计算
- 批量处理，每批处理一个网格点的所有时间序列
- 断点续传，保存进度到 JSON 文件

**异常处理**：
- 分布拟合失败时回退到正态分布
- 记录失败的网格点，后续手动检查

### 6.4 进度追踪

**进度文件**：`spei_progress.json`

**记录内容**：
- 最后处理的网格点索引
- 已完成的网格点数量
- 当前批次信息

---

## 📝 待补充内容

- [ ] 干旱传播机制理论
- [ ] 机器学习方法（随机森林、XGBoost 等）
- [ ] 注意力机制与 Transformer
- [ ] 可解释性 AI 方法
- [ ] 不确定性分析方法

---

## 📚 参考文献

1. Vicente-Serrano, S. M., Beguería, S., & López-Moreno, J. I. (2010). A multiscalar drought index sensitive to global warming: The standardized precipitation evapotranspiration index. *Journal of Climate*, 23(7), 1696-1718.

2. Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). Crop evapotranspiration-Guidelines for computing crop water requirements-FAO Irrigation and drainage paper 56. *FAO, Rome*, 300(9), D05109.

3. Mann, H. B. (1945). Nonparametric tests against trend. *Econometrica*, 13(3), 245-259.

4. Kendall, M. G. (1975). Rank correlation methods. *Charles Griffin, London*.

5. Hochreiter, S., & Schmidhuber, J. (1997). Long short-term memory. *Neural computation*, 9(8), 1735-1780.

6. Shi, X., Chen, Z., Wang, H., Yeung, D. Y., Wong, W. K., & Woo, W. C. (2015). Convolutional LSTM network: A machine learning approach for precipitation nowcasting. *Advances in neural information processing systems*, 28.

---

**文档维护**：
- 创建时间：2025-03-20
- 最后更新：2025-03-20
- 维护者：研究团队

**使用建议**：
- 论文写作时可直接引用本文档中的公式和定义
- 建议定期更新补充新的概念和方法
- 可与 `dev-log.md` 配合使用，后者记录具体实现细节
