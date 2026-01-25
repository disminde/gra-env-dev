# 华北平原水资源干枯状态分析及可视化系统 (NCP Drought Monitor)

## 1. 项目概述

**项目名称**：基于气象数据抓取的华北平原水资源干枯状态分析及可视化系统的设计与实现

**项目背景**：
华北平原作为中国重要的粮食生产基地，长期面临水资源短缺和干旱频发的挑战。传统的监测手段往往难以捕捉高时空分辨率的干旱特征，且缺乏对预测结果的可解释性。本项目旨在构建一个集数据采集、偏差校正、智能预测、归因解释及情景推演于一体的综合分析系统，利用ERA5-Land再分析数据和机器学习技术，为区域水资源管理提供科学决策支持。

**核心功能**：
- **多源数据融合**：整合Open-Meteo再分析数据与RP5站点观测数据，通过分位数映射（QM）进行偏差校正。
- **干旱指数监测**：计算高精度的SPEI（标准化降水蒸散指数），覆盖多时间尺度（气象/农业/水文干旱）。
- **智能趋势预测**：对比LSTM、XGBoost、Random Forest三种模型，实现未来1-6个月的旱情预测。
- **模型可解释性**：引入SHAP框架，量化降水、气温等因子对干旱预测的边际贡献。
- **交互式情景推演**：基于Streamlit构建Web平台，支持用户自定义气候情景（What-If Analysis），动态模拟未来变化。

## 2. 技术架构

本项目采用微服务化、容器化的现代软件架构，主要技术选型如下：

*   **编程语言**: Python 3.9+
*   **Web框架**: Streamlit (用于构建交互式数据应用)
*   **数据存储**: TimescaleDB (基于PostgreSQL的时序数据库)
*   **数据源**:
    *   Open-Meteo API (网格化再分析数据)
    *   RP5 (地面站点观测数据)
*   **核心算法库**:
    *   **数据处理**: Pandas, NumPy, Scipy
    *   **机器学习**: PyTorch/TensorFlow (LSTM), XGBoost, Scikit-learn (RF)
    *   **可解释性**: SHAP (SHapley Additive exPlanations)
*   **可视化**: Plotly, PyDeck/Folium
*   **部署运维**: Docker, Docker Compose

## 3. 环境配置与安装

### 前置要求
- Python 3.9 或更高版本
- Git
- Docker & Docker Compose (可选，用于容器化部署)

### 本地开发环境搭建

1.  **克隆仓库**
    ```bash
    git clone https://github.com/disminde/gra-env-dev.git
    cd gra-env-dev
    ```

2.  **创建虚拟环境**
    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # Linux/Mac
    source venv/bin/activate
    ```

3.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```
    *(注：`requirements.txt` 将在后续开发中生成，初期可手动安装 `streamlit pandas numpy xgboost shap` 等核心库)*

4.  **配置环境变量**
    复制 `.env.example` 为 `.env`，并配置数据库连接信息及API参数。

## 4. 运行指南

### 启动 Web 应用
```bash
streamlit run app.py
```
访问浏览器 `http://localhost:8501` 即可查看系统界面。

### 启动数据采集任务
```bash
python scripts/data_collection.py
```

## 5. 贡献指南

欢迎提交 Issue 和 Pull Request！

1.  Fork 本仓库
2.  新建分支 `git checkout -b feature/AmazingFeature`
3.  提交更改 `git commit -m 'Add some AmazingFeature'`
4.  推送到分支 `git push origin feature/AmazingFeature`
5.  提交 Pull Request

## 6. 联系方式

- **GitHub**: [disminde](https://github.com/disminde)
- **Email**: (请在此处补充您的联系邮箱)
