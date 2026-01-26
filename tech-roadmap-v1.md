
论文题目 基于气象数据抓取的华北平原水资源干枯状态分析及可视化系统的设计与实现               
一、选题背景与意义
1 华北平原的水文气候挑战
华北平原作为中国政治、经济和农业的核心区域，其水资源安全直接关系到国家粮食安全与区域生态稳定。然而，该地区面临着严峻的水资源危机。华北平原位于暖温带半湿润-半干旱季风气候区，降水季节分配极不均匀，年际变化大，且近年来在气候变暖的大背景下，极端天气事件频发。自20世纪80年代以来，由于地表水资源的匮乏，该地区长期超采地下水，导致地下水位持续下降，形成了世界上最大的地下水漏斗区。
气候变化进一步加剧了这一矛盾。研究表明，尽管降水量的变化趋势在不同子区域存在差异，但气温的显著升高导致潜在蒸散量（Potential Evapotranspiration, PET）大幅增加。这意味着即便在降水量正常的年份，由于大气需水量的增加，土壤和植被仍可能遭受严重的“农业干旱”或“气象干旱”。因此，传统的仅基于降水量的干旱监测指标（如标准化降水指数 SPI）已难以全面反映该地区的真实水分亏缺状况。引入同时考虑降水与蒸散的标准化降水蒸散指数（SPEI），对于科学评估华北平原的干枯状态至关重要 。

2 自动化监测与智能化预测的必要性
目前，针对华北平原的干旱监测多依赖于官方发布的定期通报，存在一定的时效滞后性，且公众或特定行业用户（如农户、小型水利管理者）难以获取定制化的实时分析数据。构建一个能够利用网络爬虫技术自动抓取公开气象数据，并结合机器学习算法进行实时分析与预测的系统，具有重要的现实意义。
该系统不仅能够填补官方数据发布的时间空隙，还能通过引入随机森林等机器学习模型，挖掘气象要素与干旱等级之间的非线性关系，实现从“事后监测”向“事前预警”的转变。此外，通过可视化技术将晦涩的数据转化为直观的图表与地图，能够极大地降低信息理解门槛，提升水资源信息的社会服务价值。


二、设计内容
1 设计内容
本系统旨在构建一个集气象数据自动采集、干旱指数计算、智能预测及可视化展示于一体的综合平台。设计内容涵盖以下三个核心层面：
1.	数据层设计：构建支持多源异构气象数据的存储架构。设计高可用性的数据采集脚本，针对历史数据（NOAA NCEI）与实时数据（Open-Meteo API）分别建立批处理与增量更新通道，确保数据的完整性与时效性。
2.	逻辑运算层设计：核心算法库的设计。包括基于 Penman-Monteith 公式的潜在蒸散量（PET）计算模块、多尺度 SPEI 指数生成模块，以及基于随机森林（Random Forest）的时间序列预测模型。该层负责将原始气象要素转化为具有决策价值的干旱指标 。
3.	应用表现层设计：交互式 Web 仪表盘的设计。依托 Streamlit 框架搭建用户界面，集成 ECharts 地理可视化组件，提供包含时空分布地图、趋势折线图及预测预警信息的动态展示窗口 。
2 总体技术路线
本系统遵循“轻量级、模块化、全栈 Python”的技术路线，以降低开发门槛并提高系统的可维护性。
•	架构模式：采用单体应用架构（Monolithic Application）配合轻量级数据库，通过 Streamlit 实现前后端逻辑的快速统一部署，避免分离架构带来的复杂性 。
•	数据流向：数据从互联网源头经由 Python 爬虫/API 接口进入清洗管道，标准化后存入本地 SQLite/PostgreSQL 数据库；分析引擎定时从数据库读取数据进行 SPEI 计算与模型推理；最终结果以 DataFrame 形式输送至前端进行渲染。
•	模型策略：针对华北平原的非线性气候特征，技术路线放弃传统的线性回归，选择集成学习算法（随机森林）。通过构造“时间滞后特征”（Lag Features），将时间序列预测问题转化为监督学习问题，以提升对干旱突变的捕捉能力 。
3 具体实现手段
1.	数据采集与预处理：
o	利用 Python 的 requests 库构建爬虫，针对 NOAA NCEI 进行历史数据抓取，并使用 BeautifulSoup 解析 HTML 结构 。
o	集成 Open-Meteo 开源 API，通过 httpx 异步请求获取每日最新的气温、湿度、风速等实况数据，作为 SPEI 计算的实时输入 。
o	使用 Pandas 进行数据清洗，采用线性插值法填补缺失值，并利用 IQR（四分位距）法则剔除异常气象数据。
2.	核心算法实现：
o	引入 climate_indices 开源库，配置 Penman-Monteith 参数计算 PET，进而生成 SPEI-1（气象干旱）、SPEI-3（农业干旱）等不同尺度的指数序列 。
o	基于 scikit-learn 库构建随机森林回归模型（RandomForestRegressor）。特征工程阶段，利用 df.shift() 函数构造历史 1-3 个月的 SPEI 值及气象因子作为输入特征，训练模型预测未来 1 个月的干旱等级 。
3.	可视化平台开发：
o	使用 Streamlit 框架搭建 Web 页面，利用其 st.sidebar 实现站点选择与时间范围过滤的交互功能 。
o	集成 streamlit-echarts 组件库，绘制华北平原站点的热力分布地图和动态交互式折线图，实现鼠标悬停显示具体数值、缩放查看历史趋势等功能 。
4 预期实现效果
1.	全自动化运行：系统部署后，能够每日自动更新气象数据，无需人工干预即可完成从采集到 SPEI 计算的全流程，数据库中始终保持最新的干旱监测记录。
2.	高精度干旱监测：通过采用更科学的 Penman-Monteith 算法，系统能准确反映华北平原在气候变暖背景下的真实水分亏缺状况，有效识别“高温主导型”干旱 。
3.	直观的决策支持：
o	时空可视化：用户可以在地图上直观看到华北平原各城市的干旱颜色预警（如红色代表重旱），点击城市即可查看该站点过去 30 年的干旱演变曲线。
o	趋势预测：系统能以 80% 以上的准确率预测未来一个月的干旱趋势 ，并在界面上通过虚线延伸展示预测结果，为农业灌溉和水资源调度提供提前 30 天的预警窗口。



三、设计方案

1, 核心功能模块一：气象数据自动化采集与预处理

1.1 数据源选择
经过相关调研，以下是对数据源的详尽分析。

1.1.1 灰盒数据源：Web爬虫目标
NOAA NCEI (美国国家环境信息中心)
数据质量与权威性： NOAA NCEI 是气象学界和数据科学界公认的高质量数据源之一。它归档了全球各地的机场及气象站发布的METAR（气象终端航空例行天气报告）和SYNOP（地面天气报告）数据。对于中国区域，它覆盖了大量国家级气象站点 。
参数丰富度： 该网站提供的数据颗粒度极高，不仅包含基础的气温、降水，还包含相对湿度、气压、风速、风向、云量等关键参数。这对于计算Penman-Monteith公式下的潜在蒸散量（PET）至关重要，因为PET的计算不能仅依赖温度 。
抓取可行性：NOAA的网页结构相对老旧且稳定，不像现代动态网页那样充满复杂的JavaScript渲染，这使得利用Python的requests库配合BeautifulSoup进行解析变得非常容易。此外，Python社区已存在现成的开源库如NOAA tools 和GitHub项目noaa_weather，这些工具封装了站点ID查询、数据下载和解析的逻辑，极大地降低了开发成本。
数据源应用定位： 历史数据主仓库。系统初始化时，应利用NOAA抓取华北平原各站点过去30-50年的日值或小时值数据，用于SPEI模型的参数率定和随机森林模型的训练。

1.1.2 白盒数据源：开放API
当前学术环境下，单纯依赖爬虫存在网页改版等风险，难度较高，数据源少，也不符合学术道德规范。故引入白盒数据源，即官方或开源社区维护的API是必要的保险措施。

Open-Meteo：
非盈利性： Open-Meteo 是一个开源的非商业天气API，它聚合了包括中国气象局（CMA）、NOAA、ECMWF在内的全球官方气象局数据以及ERA5再分析数据。最重要的是，它不需要API Key，且允许非商业用途的免费调用，非常适合本项目。
核心功能： 提供实时预报，同时能提供回溯至1940年的历史数据。
计算优势： Open-Meteo API 可以直接返回计算好的参考作物蒸散量（ET₀, Reference Evapotranspiration）。自行计算SPEI时，PET（即ET₀）的计算过程（尤其是Penman-Monteith公式）极为繁琐且容易出错。直接获取官方标准算法计算出的ET₀，可以显著提高系统SPEI计算的准确性和开发效率。
数据源应用定位： 实时数据流与ET₀基准。系统应每日定时调用该API获取最新数据，并利用其提供的ET₀数据校准本地计算模型。
数据补充： NASA POWER / TRMM
特点： 提供长序列的卫星遥感气象数据，特别是太阳辐射数据 。
必要性： 如果地面站点缺乏辐射观测数据，NASA POWER是标准的填补来源。

1.2 数据采集与处理流水线设计
综合上述分析，本系统将采用“历史批量导入 + 每日增量更新”的混合数据流水线架构。
1.2.1.	历史数据初始化层：
利用 NOAA bulk download tools 库或编写定制脚本，针对华北平原主要城市（北京、天津、石家庄、济南、郑州等）的气象站点，批量下载过去30年（如1990-2023）的逐日气象记录。
数据涵盖：日最高/最低气温、平均相对湿度、平均风速、日照时数（或辐射）、24小时降水量。
1.2.2.	增量数据更新层：
部署定时任务（Python Schedule库），每日凌晨（如02:00）执行。
首选调用 Open-Meteo API 获取前一日的实况数据及ET₀数据。
备选方案：启动轻量级爬虫抓取 Tianqi.com 的昨日数据作为交叉验证。	
1.2.3.	数据清洗与质控层：
异常值检测： 设定物理阈值（如气温不可能高于50℃或低于-40℃，相对湿度介于0-100%等），剔除明显错误。
缺失值插补： 对于短缺（<3天），采用线性插值；对于长缺，利用邻近站点数据建立回归关系进行插补，或使用NASA POWER的卫星数据填补。
同化处理： 将不同来源的数据（NOAA的CSV、API的JSON）统一格式化为标准的时间序列DataFrame（Pandas），并存入数据库。
1.2.4.	数据持久化层：
初步开发阶段因单文件特性，部署极为简便，准备使用 SQLite
生产阶段或数据量增大后，考虑迁移至 PostgreSQL，以利用其强大的时序数据处理能力。
整个架构采用Python为核心技术栈。数据通过分布式的爬虫和API接口进入系统，经过清洗模块的质量控制后，存入关系型数据库。

2. 核心功能模块二：干旱分析模型的设计

2.1 干旱指数模型：SPEI的适用性与计算优化
审查结论：目前看来，SPEI 是华北平原干旱监测的最佳选择。
科学依据： 华北平原正处于显著的气候变暖进程中。传统的SPI（标准化降水指数）仅考虑降水供给，忽略了气温升高带来的水分需求（蒸散）增加。研究表明，在变暖背景下，SPI往往会低估干旱的严重程度。SPEI（标准化降水蒸散指数）引入了气候水分平衡，能够捕捉到气温升高导致的“需水型干旱”，这与华北平原近年来“暖干化”的趋势高度契合。
关于PET计算方法的选择：Penman-Monteith。

目前已知的PET计算方法为以下两种：
Thornthwaite法： 这是一个简化的PET计算方法，仅需要月平均气温。虽然数据需求低，但它在干旱、半干旱地区（如华北平原）往往会低估PET，因为它忽略了风速和湿度的影响 11。
Penman-Monteith (P-M) 法： 这是FAO（联合国粮农组织）推荐的标准方法，综合考虑了温度、辐射、风速和湿度。对于季风气候明显的华北平原，风速和湿度在冬春季对蒸发的影响巨大。
实现路径： 介于先前的数据准备中已设定数据采集模块已经能够获取风速、湿度等数据，系统决定采用Penman-Monteith方法计算PET。可以使用Python库 climate_indices，该库内置了两种方法的实现，且经过了广泛的科学验证。

2.2 预测模型：时序化改造的随机森林
审查结论：随机森林适合处理非线性关系，但直接用于时间序列预测存在逻辑缺陷，必须进行特征工程改造。
算法优势： 随机森林作为一种集成学习算法，具有极强的抗过拟合能力和处理高维非线性数据的能力。在干旱预测中，它可以很好地捕捉气温、降水、土壤湿度、大气环流指数之间复杂的非线性交互作用。
•	核心缺陷及其改进：
问题： 随机森林本质上是一个截面数据模型，它不懂“时间”的概念。如果输入“1月数据”预测“2月干旱”，但由于随机森林假设样本独立同分布，它无法利用“过去3个月干旱持续加重”这一趋势信息。
解决方案：构造滞后特征。 必须将时间序列问题转化为监督学习问题。具体做法是采用“滑动窗口”技术，将“过去N个月的数据”作为特征（X），将“未来第M个月的SPEI”作为标签（Y）。
特征工程：
1.	自回归特征： 输入特征中应包含 SPEI_t-1（上个月）、SPEI_t-2、SPEI_t-3。干旱具有极强的持续性（惯性），过去的干旱状态是预测未来状态最强的因子。
2.	气象滞后特征： Precip_t-1, Temp_t-1 等。
3.	时间编码： 加入 Month（1-12）作为特征，帮助模型捕捉华北平原降水的季节性规律（如雨热同期）。
对比分析： 虽然长短期记忆网络（LSTM）在处理时间序列上理论上更强 24，但LSTM对数据量要求极大，且调参复杂（“黑箱”性质更重）。对于本项目而言，经过滞后特征增强的随机森林模型，在训练速度、可解释性和对中小规模数据的适应性上，往往优于深度学习模型，且更符合“低学习成本”的要求 25。
2.3 整体模型工作流
1.	输入： 数据库中的日值气象数据。
2.	预处理： 重采样为月值（Monthly Resampling）。
3.	中间计算： 调用 climate_indices 库，基于 P-M 公式计算 PET，进而计算不同尺度的 SPEI（如 SPEI-3 反映农业干旱，SPEI-12 反映水文干旱）。
4.	特征构造： 生成滞后特征矩阵。
5.	模型训练： 使用 scikit-learn 的 RandomForestRegressor 或 RandomForestClassifier 进行训练。
6.	输出： 未来1-3个月的干旱等级预测（如：无旱、轻旱、中旱、重旱、特旱）。

3. 核心功能模块三：多维动态可视化展示平台的内容设计

3.1	时序演变图： 展示某站点SPEI随时间的变化曲线，直观呈现干旱的发生、持续和缓解过程。背景可根据SPEI阈值（如0到-1.0为轻旱，-1.0到-1.5为中旱等）填充不同深浅的红色背景，辅助识别。
3.2	空间分布图： 利用ECharts的地理坐标系组件，在华北平原地图上绘制各气象站点的实时干旱状态。通过颜色编码（绿-正常，黄-轻旱，红-重旱）实现区域干旱态势的“一图览”。
3.3	预测仪表盘： 展示随机森林模型对未来趋势的预测结果，并给出置信区间或概率分布。

4. 详细设计方案与初步思路
4.1 系统架构设计
系统采用典型的三层架构：
1.	数据层: 
包含 weather_data 表（存储原始日值）和 drought_analysis 表（存储计算后的SPEI和预测结果）。物理载体为 ncp_drought.db (SQLite文件)。
2.	逻辑层:
crawler_service.py: 封装针对NOAA和Open-Meteo的请求逻辑，包含重试机制和异常处理。
model_engine.py: 封装 climate_indices 的SPEI计算函数和 sklearn 的随机森林预测类。
3.	 表现层: 
app.py (Streamlit主程序)，负责页面布局、控件响应和图表渲染。

4.2 数据库表结构设计 (初步)
为了支持核心功能，初步设计以下关键数据表：

Table 1: stations (站点信息表)
字段名	类型	说明
station_id	VARCHAR	主键，WMO编号 (如 54511)
name_cn	VARCHAR	中文名 (如 北京)
lat	FLOAT	纬度
lon	FLOAT	经度
province	VARCHAR	所属省份
Table 2: daily_weather (日气象数据表)
字段名	类型	说明
id	INTEGER	自增主键
station_id	VARCHAR	外键
date	DATE	日期
t_max	FLOAT	最高温
t_min	FLOAT	最低温
precip	FLOAT	降水量
wind_speed	FLOAT	平均风速
humidity	FLOAT	相对湿度
source	VARCHAR	数据来源 (NOAA/API)
Table 3: spei_results (分析结果表)
字段名	类型	说明
station_id	VARCHAR	外键
date	DATE	月份 (YYYY-MM-01)
spei_1	FLOAT	1个月尺度
spei_3	FLOAT	3个月尺度
spei_12	FLOAT	12个月尺度
drought_level	VARCHAR	干旱等级标签
is_predicted	BOOLEAN	是否为预测值



四、参考文献
[1] WANG L, et al. Spatiotemporal characteristics of drought in the North China Plain and its impact on winter wheat[J]. Agricultural Water Management, 2021. 
[2] ZHANG D, et al. Integrated hydrological modeling of the North China Plain[J]. Hydrology and Earth System Sciences, 2013. 
[3] LI Z, et al. Spatiotemporal drought characteristics during growing seasons of the winter wheat and summer maize in the North China Plain[J]. Theoretical and Applied Climatology, 2024. 
[4] YANG P, et al. Identification and Spatiotemporal Migration Analysis of Groundwater Drought Events in the North China Plain[J]. Atmosphere, 2021. 
[5] QIN Y, et al. Analysis of the spatial and temporal characteristics of drought in the North China Plain based on standardized precipitation evapotranspiration index[J]. Natural Hazards, 2015. 
[6] BEGUERÍA S, et al. Standardized precipitation evapotranspiration index (SPEI) revisited: parameter fitting, evapotranspiration models, tools, datasets and drought monitoring[J]. International Journal of Climatology, 2014. 
[7] VICENTE-SERRANO S M, et al. A Multiscalar Drought Index Sensitive to Global Warming: The Standardized Precipitation Evapotranspiration Index[J]. Journal of Climate, 2010. 
[8] TIRIVAROMBO S, et al. Comparative analysis of drought indicated by the SPI and SPEI at various timescales[J]. Journal of Hydrology, 2018. 
[9] XU K, et al. Drought monitoring and analysis in North China based on SPEI[J]. Acta Ecologica Sinica, 2015. 
[10] FENG Y, et al. Drought Forecasting Using Random Forests Model at New South Wales, Australia[J]. Applied Sciences, 2020. 
[11] DIKSHIT A, et al. Long lead time drought forecasting using machine learning in a changing climate[J]. Journal of Hydrology, 2020.
[12] PRODHAN F A, et al. Projection of future drought and its impact on simulated crop yield over South Asia using ensemble machine learning approach[J]. Science of The Total Environment, 2022. 
[13] AGHELPOUR P, et al. Drought prediction models driven by meteorological variables: A review[J]. Water Supply, 2023. 
[14] SHEN R, et al. Construction of a Drought Monitoring Model Using Deep Learning Based on Multi-Source Remote Sensing Data[J]. Remote Sensing, 2019. 
[15] STREAMLIT INC. Streamlit: The fastest way to build and share data apps[J]. Journal of Open Source Software, 2023.

---
