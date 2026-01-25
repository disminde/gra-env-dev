# 基于气象数据抓取的华北平原水资源干枯状态分析及可视化系统的设计与实现：技术路线与设计方案

## 第一章 绪论

### 1.1 研究背景与意义

#### 1.1.1 华北平原水资源危机的宏观背景
华北平原（North China Plain, NCP），作为中国政治、经济和文化的腹地，涵盖了北京、天津、河北、河南及山东等关键省市，是中国最为重要的小麦和玉米生产基地，承载着保障国家粮食安全的重任。然而，该区域长期深受资源性缺水的困扰，是全球水资源压力最大的地区之一。受东亚夏季风不稳定性及全球气候变暖的双重驱动，华北平原的降水时空分布极不均匀，且呈现出明显的年代际减少趋势。与此同时，气温的显著升高导致潜在蒸散发（Potential Evapotranspiration, PET）持续增加，加剧了土壤水分的亏缺与地表径流的衰减。

历史数据显示，华北平原曾多次遭遇灾难性的干旱事件。例如，1997年至2002年期间发生的连年持续干旱，导致黄河下游频繁断流，严重制约了区域社会经济发展；2010年至2011年的冬春连旱更是对冬小麦越冬造成了巨大威胁。近年来，随着气候极端性增强，旱涝急转现象频发，如2024年夏季华北平原在经历严重气象干旱后迅速转为洪涝，这种复合型极端事件对水资源管理的预警能力提出了前所未有的挑战。因此，构建一套高精度、高时空分辨率且具备情景推演能力的干旱监测与预警系统，对于指导农业灌溉调度、优化水资源配置具有重要的现实意义。

#### 1.1.2 再分析数据与观测数据的融合需求
传统的干旱监测主要依赖于地面气象站点的观测数据。尽管实测数据精度高，但华北平原站点分布密度有限，难以捕捉局地尺度的干旱空间异质性。随着大气科学的发展，以ERA5-Land为代表的第五代大气再分析资料提供了高分辨率（约9km）、长历史序列（1950年至今）的格点化气象数据，填补了观测站点的空间空白。然而，再分析数据是通过数值天气预报模型同化观测资料生成的，受模型物理参数化方案和地形平滑效应的影响，往往存在系统性偏差（Systematic Bias），如在山区低估降水或在平原高估气温。

鉴于此，本研究提出一种融合多源数据的技术路径：以Open-Meteo API提供的ERA5-Land再分析数据为主力数据源，以保证空间连续性；同时利用RP5（Reliable Prognosis）获取的地面气象站实测数据（SYNOP/METAR）作为“真值”基准，构建偏差校正模型。这种“格点+站点”的融合策略，旨在兼顾数据的空间覆盖度与物理真实性。

#### 1.1.3 从“黑箱”预测到可解释性决策
在干旱预测算法层面，虽然长短期记忆网络（LSTM）、极端梯度提升树（XGBoost）等机器学习模型在水文时间序列预测中展现出优越的性能，但其复杂的内部结构往往导致“黑箱”效应，使得决策者难以理解预测结果背后的驱动机制。例如，某次干旱预警是由降水亏缺主导，还是由高温导致的蒸散发增强主导？缺乏解释性的模型难以建立用户信任。因此，本研究引入SHAP（SHapley Additive exPlanations）博弈论解释框架，对模型进行归因分析，量化各气象因子的边际贡献，从而实现从单纯的“预测状态”向“解析成因”的跨越。

### 1.2 国内外研究现状

#### 1.2.1 气象干旱指数与监测技术
目前，标准化降水指数（SPI）和标准化降水蒸散指数（SPEI）是应用最为广泛的气象干旱指标。SPI仅考虑降水单一变量，计算简便但忽略了温度升高的影响；而SPEI引入了水分平衡方程（降水减去潜在蒸散发），能够更敏锐地捕捉全球变暖背景下的干旱特征。针对华北平原的研究表明，SPEI在表征该地区长期干旱化趋势方面具有更好的适用性。在数据获取方面，Open-Meteo API因其开放性、无需API密钥及提供多种物理量（如 $ET_0$、土壤湿度）的特性，正逐渐成为气象数据挖掘领域的重要工具。

#### 1.2.2 机器学习在干旱预测中的应用
机器学习已成为提升干旱预测精度的核心手段。LSTM因其独特的门控机制，能够有效捕捉时间序列中的长期依赖关系，被广泛用于旱情趋势推演；集成学习算法如XGBoost和随机森林（Random Forest, RF）则凭借对非线性特征的强大拟合能力和抗过拟合特性，在处理多变量输入时表现优异。现有研究多集中于单一模型的应用，缺乏针对华北平原特定气候特征的多种机制模型（深度学习 vs 集成学习）的系统性对比与优选。

#### 1.2.3 偏差校正与偏差修正
为提升再分析数据的可用性，偏差校正方法研究活跃。常见的方法包括线性缩放（Linear Scaling）、方差缩放（Variance Scaling）和分位数映射（Quantile Mapping, QM）。其中，分位数映射法通过修正变量的整个累积分布函数（CDF），不仅能校正均值偏差，还能有效改善极端值的模拟精度，是目前公认最为精细的校正手段。

### 1.3 设计目标与主要内容
本毕业设计旨在设计并实现一个集数据采集、清洗校正、智能预测、归因解释及情景推演于一体的干旱分析系统。主要内容包括：
1.  **多源数据工程**：构建基于Open-Meteo API的自动化数据采集流水线，并结合RP5实测数据开发基于分位数映射的偏差校正模块。
2.  **多模型对比研究**：建立LSTM、XGBoost与随机森林三种不同机制的预测模型，评估其在不同预见期（1-6个月）下的SPEI预测性能。
3.  **可解释性增强**：利用SHAP算法解析模型预测结果，识别不同干旱事件的主导气象因子。
4.  **云原生系统开发**：基于Streamlit框架开发具备交互式情景推演（What-If Analysis）功能的Web系统，并通过Docker技术实现Linux云端容器化部署。

## 第二章 总体技术路线与架构设计

### 2.1 设计原则
本系统的架构设计遵循以下核心工程原则：
1.  **数据的准确性与一致性**：将偏差校正置于数据处理链路的首位，确保所有后续分析基于经过校验的高质量数据。
2.  **算法的鲁棒性与先进性**：不预设单一算法，而是通过多模型竞争机制选优，兼顾深度学习的时序捕捉能力与集成学习的特征解释能力。
3.  **系统的可移植性与可扩展性**：采用微服务化的容器部署方案，解除开发环境与生产环境的耦合，便于系统的快速迁移与水平扩展。
4.  **交互的直观性与决策支持**：突破静态报表的局限，提供动态参数调整功能，让用户能够主动探索气候变化对水资源的潜在影响。

### 2.2 系统逻辑架构
系统从逻辑上划分为数据层、算法层、服务层与表现层四个层次，各层之间通过标准化的数据接口进行交互。

![](md-pic\pic-1.jpg)

#### 2.2.1 数据源层
作为系统的基石，该层负责连接外部数据接口。
*   **Open-Meteo API**：提供华北平原全域网格化的降水、气温、风速、辐射及土壤湿度数据。其高时空分辨率（Hourly, 0.1°-0.25°）是计算精细化SPEI的基础。
*   **RP5 气象数据库**：提供北京、天津、石家庄、济南、郑州等关键站点的SYNOP/METAR报文数据，作为偏差校正的参考真值。

#### 2.2.2 数据处理层
该层承担ETL（Extract, Transform, Load）任务，核心功能包括：
*   **数据清洗**：剔除异常值，填补缺失值。
*   **时空匹配**：将站点数据与最近邻网格数据进行配对。
*   **偏差校正**：应用分位数映射算法，修正再分析数据的系统性误差。
*   **指数计算**：基于Penman-Monteith公式计算PET，进而计算多时间尺度的SPEI序列。

#### 2.2.3 核心算法层
该层是系统的“大脑”，包含：
*   **预测引擎**：部署LSTM、XGBoost与随机森林三个并行模型，执行训练与推断任务。
*   **解释引擎**：集成SHAP库，计算特征的Shapley值，生成解释性图表数据。
*   **超参数优化器**：利用网格搜索（Grid Search）或贝叶斯优化（Bayesian Optimization）自动寻优模型参数。

#### 2.2.4 应用交互层
该层直接面向用户，基于Streamlit框架构建：
*   **仪表盘**：展示实时旱情。
*   **分析台**：提供模型对比与SHAP分析视图。
*   **推演室**：提供交互式滑块，支持用户自定义气候情景。

### 2.3 技术选型
*   **编程语言**：Python 3.9+，因其在数据科学与气象领域的丰富生态。
*   **Web框架**：Streamlit，因其对数据应用的快速开发能力与原生交互组件支持。
*   **容器化引擎**：Docker，确保开发环境与云端运行环境的一致性。
*   **数据库**：TimescaleDB（基于PostgreSQL），专为时序数据优化，支持高效的时间窗口查询与聚合。

## 第三章 关键技术方案与实现细节

### 3.1 数据获取与偏差校正模块

#### 3.1.1 Open-Meteo API 数据采集策略
Open-Meteo API 是一个基于ERA5-Land再分析数据集的高性能接口。相比于传统的爬虫抓取，API方式具有合规性高、稳定性强、数据结构化好的优势。
*   **请求构建**：利用Python的`requests`库构建RESTful API请求。请求参数包括经纬度范围（华北平原：32°N-42°N, 110°E-123°E）、时间范围（1980年至今）、所需变量（`temperature_2m`, `precipitation`, `et0_fao_evapotranspiration`, `soil_moisture_0_to_7cm`等）。
*   **网格化处理**：由于API支持多点请求，系统将华北平原划分为0.25°×0.25°的网格，批量获取每个格点的历史序列。
*   **增量更新**：设计定时任务（Cron Job），每日凌晨自动拉取前一日的最新数据，保证数据库的实时性。

#### 3.1.2 基于RP5的分位数映射（QM）偏差校正
再分析数据虽然覆盖面广，但往往存在系统性偏差。本设计采用分位数映射法（Quantile Mapping, QM），这是一种非参数偏差校正方法，旨在使模拟数据（ERA5）的累积分布函数（CDF）与观测数据（RP5）的CDF相匹配。

**校正算法步骤：**
1.  **时空匹配（Spatial Matching）**：
    首先，需要将格点数据映射到站点位置。虽然最简单的方法是最近邻法（Nearest Neighbor），但为了提高精度，本系统采用**双线性插值（Bilinear Interpolation）**。对于任意RP5站点 $S$，选取包围该站点的四个Open-Meteo格点 $G_1, G_2, G_3, G_4$，根据距离权重计算该位置的模拟值 $M_{raw}$。
2.  **构建经验累积分布函数（eCDF）**：
    选取历史基准期（如1990-2020年），分别计算站点观测降水序列 $O$ 和插值后的模拟降水序列 $M$ 的经验累积分布函数 $F_O$ 和 $F_M$。
3.  **建立映射函数**：
    对于任意概率 $p$，存在关系：$O_p = F_O^{-1}(p)$ 且 $M_p = F_M^{-1}(p)$。偏差校正的核心在于寻找变换函数 $Transfer(\cdot)$，使得校正后的模拟值 $M_{corr}$ 的分布逼近 $O$。
    公式为：
    $$M_{corr} = F_O^{-1}(F_M(M_{raw}))$$
    其中，$F_M(\cdot)$ 将原始模拟值转换为其在模拟分布中的累积概率，$F_O^{-1}(\cdot)$ 则查询该概率在观测分布中对应的物理量值。
4.  **全域推广**：
    在完成站点位置的校正参数计算后，利用**反距离权重插值（IDW）**或**克里金插值（Kriging）**将校正因子（如不同分位数下的差值或比率）推广至整个华北平原的无站点格点，从而实现全域数据的质量提升。

![](md-pic\pic-2.jpg)

### 3.2 干旱特征工程与指数计算

#### 3.2.1 SPEI 指数计算
标准化降水蒸散指数（SPEI）是本系统的核心预测目标。与仅考虑降水的SPI不同，SPEI结合了水分收入（降水）与支出（蒸散发），更适合变暖背景下的干旱监测。
*   **PET计算**：利用Open-Meteo提供的气温、湿度、风速和辐射数据，基于FAO-56 Penman-Monteith公式计算参考作物蒸散发（$ET_0$）。
    $$ET_0 = \frac{0.408\Delta(R_n - G) + \gamma \frac{900}{T+273} u_2 (e_s - e_a)}{\Delta + \gamma(1 + 0.34u_2)}$$
    该公式物理机制明确，精度优于仅依赖温度的Thornthwaite方法。
*   **水分盈亏序列**：计算月降水量 $P$ 与潜在蒸散发 $PET$ 之差 $D = P - PET$。
*   **分布拟合与标准化**：对累积的 $D$ 序列采用Log-Logistic概率分布进行拟合，并将累计概率转换为标准正态分布变量，即得SPEI值。系统将计算SPEI-1（气象干旱）、SPEI-3（农业干旱）、SPEI-12（水文干旱）等多尺度指数。

#### 3.2.2 机器学习特征库构建
为训练高精度的预测模型，需构建包含多维信息的特征矩阵：
1.  **滞后特征（Lagged Features）**：这是时间序列预测的关键。构建 $t-1, t-2, \dots, t-12$ 个月的SPEI值、降水量、温度作为输入特征，使模型能够“记忆”历史状态。研究表明，12个月的回溯窗口（Lookback Window）能有效捕捉年际周期性。
2.  **滑动窗口统计量（Rolling Statistics）**：计算过去3个月、6个月的降水均值、方差、最大值，捕捉短期气候波动特征。
3.  **时间编码**：将月份（Month）和季节（Season）进行正弦/余弦变换（Cyclical Encoding）或One-Hot编码，使模型感知季节循环。
4.  **辅助物理量**：引入土壤湿度（Soil Moisture）、相对湿度等辅助变量，增强物理约束。

### 3.3 多机制预测模型构建与对比

本研究选取三种代表性算法进行对比，旨在探究不同数学机制对华北平原干旱预测的适应性。

#### 3.3.1 长短期记忆网络（LSTM）
LSTM是一种特殊的循环神经网络（RNN），通过引入“门控”机制（遗忘门、输入门、输出门）解决了长序列训练中的梯度消失问题，特别适合捕捉干旱演变的长期时间依赖性。
*   **网络架构**：
    *   **输入层**：形状为 `(Batch_Size, Lookback_Steps, Features)`，其中Lookback设为12。
    *   **LSTM层**：双层堆叠结构。第一层128个神经元（`return_sequences=True`），捕捉高维时序特征；第二层64个神经元，提取抽象语义。
    *   **Dropout层**：设置0.2的丢弃率，防止过拟合。
    *   **输出层**：全连接层（Dense），输出未来1个月或3个月的SPEI预测值。
*   **训练策略**：采用Adam优化器，均方误差（MSE）作为损失函数，引入早停机制（Early Stopping）。

#### 3.3.2 极端梯度提升树（XGBoost）
XGBoost是一种基于决策树的集成算法，通过梯度提升（Gradient Boosting）策略不断拟合残差。其优势在于对表格数据的高效处理能力和强大的正则化抗过拟合能力。
*   **参数调优**：利用网格搜索（Grid Search）针对以下参数进行寻优：
    *   `learning_rate`（学习率）：0.01-0.1，控制模型收敛速度。
    *   `max_depth`（树深）：3-6，控制模型复杂度。
    *   `n_estimators`（迭代次数）：100-1000。
    *   `subsample` / `colsample_bytree`：0.8，引入随机性以增强鲁棒性。
*   **数据适配**：需将时间序列转换为监督学习格式（Supervised Learning Format），即每一个样本包含 $t-n$ 到 $t-1$ 时刻的所有特征平铺向量。

#### 3.3.3 随机森林（Random Forest）
随机森林基于Bagging思想，并行构建多棵决策树并取平均值。它对噪声具有较强的鲁棒性，且天然不易过拟合，适合作为本研究的基准模型（Baseline）。
*   **配置**：构建200棵决策树，采用MSE准则进行分裂。

![](md-pic\pic-3.jpg)

### 3.4 模型可解释性分析（SHAP）

为解决“黑箱”问题，本系统引入SHAP（SHapley Additive exPlanations）方法。SHAP基于合作博弈论，将模型预测值分解为各个特征的贡献之和，具有唯一性、一致性和局部精确性等数学性质。

#### 3.4.1 全局解释性（Global Interpretability）
通过计算测试集中所有样本的SHAP值，生成**SHAP摘要图（Summary Plot）**。
*   **分析目标**：识别影响华北平原干旱的主导因子。预期结果是，前期降水（Precipitation_lag）和温度（Temperature_lag）将具有最高的特征重要性。
*   **可视化含义**：图中每一个点代表一个样本，X轴位置代表SHAP值（正值表示促进SPEI增加/湿润，负值表示促进SPEI减少/干旱），颜色代表特征值大小。通过观察颜色的分布，可以直观得出“高温是否导致了干旱”的结论。

![](md-pic\pic-4.png)

#### 3.4.2 局部解释性（Local Interpretability）
针对特定的干旱事件（如2024年6月的极端干旱），使用**SHAP力图（Force Plot）**或**瀑布图（Waterfall Plot）**进行个例分析。
*   **情景**：当模型预测某月SPEI为-2.0（极端干旱）时，SHAP分析能具体指出：该预测值中有-1.5的贡献来自“过去3个月降水严重偏少”，有-0.8的贡献来自“上个月气温异常偏高”，而“风速偏小”提供了+0.3的正向贡献（减缓了蒸发）。
*   **价值**：这为精细化的抗旱决策提供了科学依据——是应该重点解决水源短缺，还是应对高温热害。

### 3.5 交互式可视化与情景推演系统

#### 3.5.1 Streamlit 架构设计
系统前端采用Streamlit框架，利用其数据驱动的响应式编程模型，快速构建Web应用。
*   **状态管理（Session State）**：这是实现交互式情景推演的核心。通过 `st.session_state` 存储用户的配置参数（如“假设气温升高2℃”），确保在页面重绘时状态不丢失。
*   **组件化开发**：
    *   `Sidebar`：放置参数控制滑块。
    *   `Map Container`：集成`pydeck`或`folium`，展示干旱指数的空间热力图。
    *   **Chart Container**：集成`Plotly`，展示交互式时间序列曲线。

#### 3.5.2 情景推演（What-If Analysis）功能实现
这是本系统相对传统监测系统的最大创新点。功能逻辑如下：
1.  **基准线计算**：首先加载最新的气象数据，利用训练好的模型（如XGBoost）预测未来6个月的“基准SPEI轨迹”（Baseline Scenario）。
2.  **用户干预**：用户在侧边栏调整滑块，例如设置“未来气温偏离值 = +2.0℃”，“未来降水偏离值 = -30%”。
3.  **动态推演**：
    *   后台Python脚本捕获这些变化量。
    *   对输入特征矩阵进行扰动（Perturbation）：$Feature_{new} = Feature_{base} \times (1 + \Delta P)$ 或 $Feature_{new} = Feature_{base} + \Delta T$。
    *   将扰动后的特征输入模型进行重新预测。
4.  **对比展示**：在同一坐标系下绘制“基准线”与“情景线”，直观展示气候变化对干旱强度的放大效应。

![](md-pic\pic-5.jpg) 

### 3.6 容器化部署方案

为确保系统在不同环境下的稳定运行，本设计采用Docker容器化技术，并将系统部署至Linux云服务器。

#### 3.6.1 Docker镜像构建
编写 `Dockerfile` 定义应用运行环境：
*   **Base Image**：选用 `python:3.9-slim-buster`，兼顾体积小与兼容性好。
*   **依赖安装**：通过 `requirements.txt` 安装 `streamlit`, `xgboost`, `shap`, `openmeteo-requests` 等库。
*   **环境配置**：设置时区为 `Asia/Shanghai`，暴露Streamlit默认端口 `8501`。
*   **启动指令**：`ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]`。

#### 3.6.2 Linux云端部署
1.  **基础设施**：选用阿里云或腾讯云的ECS实例（Ubuntu 20.04 LTS），配置2核4G以上资源。
2.  **持续交付**：
    *   在本地开发完成后，构建镜像：`docker build -t ncp-drought-system:v1.`
    *   推送至镜像仓库（Docker Hub或ACR）。
    *   在云服务器拉取镜像并运行：`docker run -d -p 80:8501 --restart always ncp-drought-system:v1`。
3.  **服务增强**：配置Nginx反向代理，实现域名访问与HTTPS加密，提升系统安全性和访问速度。

## 第四章 预期成果与可行性分析

### 4.1 预期成果
1.  **高精度数据集**：构建一套覆盖华北平原近40年、经RP5实测数据校正的格点化气象与干旱指数数据集，为后续研究提供数据基础。
2.  **最优预测模型**：通过LSTM、XGBoost与随机森林的系统对比，确定最适合华北平原特征的干旱预测算法，并输出包含SHAP分析的完整模型解释报告。
3.  **在线可视化平台**：交付一套部署于云端的、功能完整的干旱监测与推演系统，支持多端访问与实时交互。
4.  **毕业论文**：完成一篇结构严谨、数据详实、分析深入的毕业设计论文，论证偏差校正的有效性及情景推演的应用价值。

### 4.2 可行性分析
*   **数据获取可行性**：Open-Meteo API免费且无需鉴权，RP5数据公开可得，两者结合的技术路径在气象学界已有成熟应用，不存在法律与技术壁垒。
*   **算法实现可行性**：团队已熟练掌握Python数据科学栈（Pandas, Scikit-learn, PyTorch），且SHAP、XGBoost等库文档完善，社区支持强大。
*   **算力资源可行性**：所选模型（XGBoost, 轻量级LSTM）计算开销适中，普通云服务器或个人高性能PC即可满足训练需求，无需昂贵的超算资源。

### 5 参考文献
参考文献
*   [1] WANG L, et al. Spatiotemporal characteristics of drought in the North China Plain and its impact on winter wheat[J]. Agricultural Water Management, 2021. 
*   [2] ZHANG D, et al. Integrated hydrological modeling of the North China Plain[J]. Hydrology and Earth System Sciences, 2013. 
*   [3] LI Z, et al. Spatiotemporal drought characteristics during growing seasons of the winter wheat and summer maize in the North China Plain[J]. Theoretical and Applied Climatology, 2024. 
*   [4] YANG P, et al. Identification and Spatiotemporal Migration Analysis of Groundwater Drought Events in the North China Plain[J]. Atmosphere, 2021. 
*   [5] QIN Y, et al. Analysis of the spatial and temporal characteristics of drought in the North China Plain based on standardized precipitation evapotranspiration index[J]. Natural Hazards, 2015.      
*   [6] BEGUERÍA S, et al. Standardized precipitation evapotranspiration index (SPEI) revisited: parameter fitting, evapotranspiration models, tools, datasets and drought monitoring[J]. International Journal of Climatology, 2014. 
*   [7] VICENTE-SERRANO S M, et al. A Multiscalar Drought Index Sensitive to Global Warming: The Standardized Precipitation Evapotranspiration Index[J]. Journal of Climate, 2010. 
*   [8] TIRIVAROMBO S, et al. Comparative analysis of drought indicated by the SPI and SPEI at various timescales[J]. Journal of Hydrology, 2018. 
*   [9] XU K, et al. Drought monitoring and analysis in North China based on SPEI[J]. Acta Ecologica Sinica, 2015. 
*   [10] FENG Y, et al. Drought Forecasting Using Random Forests Model at New South Wales, Australia[J]. Applied Sciences, 2020. 
*   [11] DIKSHIT A, et al. Long lead time drought forecasting using machine learning in a changing climate[J]. Journal of Hydrology, 2020.
*   [12] PRODHAN F A, et al. Projection of future drought and its impact on simulated crop yield over South Asia using ensemble machine learning approach[J]. Science of The Total Environment, 2022. 
*   [13] AGHELPOUR P, et al. Drought prediction models driven by meteorological variables: A review[J]. Water Supply, 2023. 
*   [14] SHEN R, et al. Construction of a Drought Monitoring Model Using Deep Learning Based on Multi-Source Remote Sensing Data[J]. Remote Sensing, 2019. 
*   [15] STREAMLIT INC. Streamlit: The fastest way to build and share data apps[J]. Journal of Open Source Software, 2023.
