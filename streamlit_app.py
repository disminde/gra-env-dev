import streamlit as st
import os
import pandas as pd
import numpy as np
import joblib
from sklearn.cluster import KMeans
import plotly.express as px
import shap
import matplotlib.pyplot as plt
from matplotlib import rcParams

# 配置 Matplotlib 中文字体，防止 SHAP 图表中文字符显示为方块
rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'sans-serif']
rcParams['axes.unicode_minus'] = False

# 必须是第一条命令
st.set_page_config(
    page_title="华北平原干旱推演与归因系统",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="collapsed" # 折叠侧边栏，因为我们用双标签页，主视口更大
)

# ================= 核心缓存数据与模型加载区 =================
@st.cache_resource
def load_xgboost_model():
    """加载核心 XGBoost 预测模型"""
    model_path = 'xgb_experiment_results/models/xgb_1m_no_tele.joblib'
    if os.path.exists(model_path):
        model = joblib.load(model_path)
        # 修复 XGBoost 在推理时的 CPU/GPU 错位警告，并提升稳定性
        model.set_params(device="cpu")
        return model
    st.error(f"❌ 模型文件未找到: {model_path}")
    return None

@st.cache_resource
def load_shap_explainer(_model, _X_background):
    """
    初始化 SHAP TreeExplainer。
    为了提升性能并提供 Expected Value (基准值)，我们需要传入一个背景数据集 (Background Dataset)。
    这个 Explainer 只需要在系统启动时被初始化一次。
    """
    return shap.TreeExplainer(_model, _X_background)

@st.cache_data
def load_historical_metadata():
    """
    极速加载历史大宽表的元数据（时间范围和空间网格列表），供用户在下拉菜单中选择。
    绝不加载完整的 1.2GB 数据！只加载必要的列并去重。
    """
    hist_path = 'data/processed/ml_feature_table.parquet'
    if not os.path.exists(hist_path):
        return None, None
        
    # 只读取必需的 4 列，速度极快
    df_meta = pd.read_parquet(hist_path, columns=['year', 'month', 'latitude', 'longitude'])
    
    # 提取时间列表 (如 "2023-08")
    df_meta['date_str'] = df_meta['year'].astype(str) + "-" + df_meta['month'].astype(str).str.zfill(2)
    time_list = df_meta['date_str'].unique().tolist()
    time_list.sort(reverse=True) # 最近的时间排在前面
    
    # 提取独特的空间网格列表
    grid_list = df_meta[['latitude', 'longitude']].drop_duplicates().sort_values(by=['latitude', 'longitude']).values.tolist()
    grid_str_list = [f"Lat: {lat:.2f}, Lon: {lon:.2f}" for lat, lon in grid_list]
    
    return time_list, grid_str_list

@st.cache_data
def fetch_single_point_data(selected_year, selected_month, selected_lat, selected_lon):
    """
    根据用户选择的时空节点，利用 Parquet 的 predicate pushdown（谓词下推）机制，
    从 1.2GB 的历史大宽表中，极速捞出唯一对应的那一行特征数据。
    """
    hist_path = 'data/processed/ml_feature_table.parquet'
    
    # 过滤器：精准定位一行
    filters = [
        ('year', '==', selected_year),
        ('month', '==', selected_month),
        ('latitude', '==', selected_lat),
        ('longitude', '==', selected_lon)
    ]
    
    df_single = pd.read_parquet(hist_path, filters=filters)
    return df_single
    """
    加载离线流水线 (update_latest_data.py) 生成的最新特征宽表
    用于 Tab 1 的实时干旱状态展示与 What-If 推演
    """
    data_path = 'latest_inference_features.parquet'
    if not os.path.exists(data_path):
        st.error(f"❌ 最新推理数据未找到: {data_path}。请先运行 update_latest_data.py")
        return None, None, None
        
    df = pd.read_parquet(data_path)
    
    # 自动定位到数据集中最新的月份
    latest_year = df['year'].max()
    latest_month = df[df['year'] == latest_year]['month'].max()
    
    # 提取最新这一个月的全华北平原网格点
    df_latest = df[(df['year'] == latest_year) & (df['month'] == latest_month)].copy()
    
    # 重新构建空间聚类 (为了对齐训练时的 15 个 spatial_zone One-Hot 特征)
    coords = df_latest[['latitude', 'longitude']].drop_duplicates()
    kmeans = KMeans(n_clusters=15, random_state=42, n_init=10)
    coords['spatial_zone'] = kmeans.fit_predict(coords)
    df_latest = df_latest.merge(coords, on=['latitude', 'longitude'], how='left')
    df_latest = pd.get_dummies(df_latest, columns=['spatial_zone'], prefix='zone', drop_first=False)
    
    # 识别出模型推理所需的特征列
    base_exclude = ['year', 'month', 'latitude', 'longitude', 'target_spei_1m_ahead', 'target_spei_3m_ahead', 'target_spei_6m_ahead']
    feature_cols = [c for c in df_latest.columns if c not in base_exclude]
    
    return df_latest, feature_cols, f"{latest_year}年{latest_month}月"

# ================= 页面全局 UI 构建 =================
st.title("🌍 华北平原水资源干旱分析与推演平台")
st.markdown("基于高分辨率再分析气象数据与 XGBoost 机器学习模型的智能决策支持系统。")

# 加载基础资源
model = load_xgboost_model()
df_latest, feature_cols, latest_date_str = load_latest_inference_data()

# 核心双标签页设计
tab1_live_map, tab2_shap_analysis = st.tabs([
    "📍 实时旱情与情景推演 (Live What-If Map)", 
    "🔍 时空溯源与归因分析 (On-Demand SHAP)"
])

# ---------------------------------------------------------
# Tab 1: 实时推演地图
# ---------------------------------------------------------
with tab1_live_map:
    if model is not None and df_latest is not None:
        st.info(f"📅 当前基准气象数据时间: **{latest_date_str}**")
        
        # 页面划分为左右两栏 (1:3 比例)
        col_controls, col_map = st.columns([1, 3])
        
        with col_controls:
            st.subheader("🎛️ 气候扰动滑块")
            st.markdown("自定义未来 3 个月的气候情景：")
            
            # 使用 form 避免滑块每次轻微拖动就触发全局重绘，导致前端卡死和 Connection Error
            with st.form(key='whatif_form'):
                temp_delta = st.slider("🌡️ 气温偏离 (℃)", min_value=-3.0, max_value=5.0, value=0.0, step=0.1, help="华北平原整体平均气温升高或降低的幅度")
                precip_delta = st.slider("🌧️ 降水偏离 (%)", min_value=-80, max_value=80, value=0, step=5, help="华北平原整体降水量的增减百分比")
                et0_delta = st.slider("💨 潜在蒸散发偏离 (%)", min_value=-30, max_value=50, value=0, step=5, help="受风速、辐射等影响的蒸发量变化")
                submit_button = st.form_submit_button(label='🚀 应用气候扰动', use_container_width=True)
            
            st.markdown("---")
            st.markdown("### 📊 全局宏观统计")
            
            # 计算基准状态 (未扰动)
            df_base = df_latest.copy()
            # 补齐可能缺失的 One-Hot 特征 (zone_x) 以防报错
            for col in model.feature_names_in_:
                if col not in df_base.columns:
                    df_base[col] = 0
            X_base = df_base[model.feature_names_in_]
            base_preds = model.predict(X_base)
            base_preds = np.clip(base_preds, -3.0, 3.0) # 截断处理
            
            # 计算扰动状态
            df_whatif = df_base.copy()
            if 'temp_mean' in df_whatif.columns:
                df_whatif['temp_mean'] += temp_delta
            if 'p_sum' in df_whatif.columns:
                df_whatif['p_sum'] = df_whatif['p_sum'] * (1 + precip_delta / 100.0)
            if 'et0_sum' in df_whatif.columns:
                df_whatif['et0_sum'] = df_whatif['et0_sum'] * (1 + et0_delta / 100.0)
                
            X_whatif = df_whatif[model.feature_names_in_]
            whatif_preds = model.predict(X_whatif)
            whatif_preds = np.clip(whatif_preds, -3.0, 3.0) # 截断处理
            
            base_spei_mean = base_preds.mean()
            whatif_spei_mean = whatif_preds.mean()
            delta_spei_mean = whatif_spei_mean - base_spei_mean
            
            st.metric("原平均 SPEI-3", f"{base_spei_mean:.2f}")
            st.metric("推演后平均 SPEI-3", f"{whatif_spei_mean:.2f}", delta=f"{delta_spei_mean:.2f}", delta_color="normal")
            
            drought_grids_count = (whatif_preds <= -1.0).sum()
            st.metric("中度及以上干旱网格数", f"{drought_grids_count} / {len(whatif_preds)}", help="SPEI <= -1.0 即为干旱")
            
        with col_map:
            st.subheader("🗺️ 华北平原农业干旱 (SPEI-3) 空间热力图")
            
            # 准备绘图数据
            df_plot = df_latest[['latitude', 'longitude']].copy()
            df_plot['WhatIf_SPEI'] = whatif_preds
            df_plot['SPEI_Change'] = whatif_preds - base_preds
            
            # 动态调整标题以反映滑块状态
            title_suffix = ""
            if temp_delta != 0 or precip_delta != 0:
                title_suffix = f" (情景: 气温{temp_delta:+.1f}℃, 降水{precip_delta:+d}%)"
                
            fig = px.scatter_mapbox(
                df_plot,
                lat="latitude",
                lon="longitude",
                color="WhatIf_SPEI",
                color_continuous_scale=px.colors.diverging.RdYlBu, # 红黄蓝发散色带：红干蓝湿
                range_color=[-2.5, 2.5], # 固定色带范围，避免滑块变化时地图颜色跳跃
                hover_name="WhatIf_SPEI",
                hover_data={
                    "latitude": ':.2f', 
                    "longitude": ':.2f', 
                    "WhatIf_SPEI": ':.2f', 
                    "SPEI_Change": ':.2f'
                },
                zoom=5.5,
                center={"lat": 37.5, "lon": 116.0}, # 华北平原视觉中心
                mapbox_style="carto-positron",
                height=650,
                title=f"实时预测干旱状态{title_suffix}"
            )
            
            fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
            # 修复 Streamlit 警告: 将 use_container_width 替换为 width='stretch'
            st.plotly_chart(fig, width='stretch')

    else:
        st.warning("系统初始化未完成，请检查依赖文件。")

# ---------------------------------------------------------
# Tab 2: 按需动态 SHAP 分析
# ---------------------------------------------------------
with tab2_shap_analysis:
    st.info("💡 提示：在此页面，你可以从包含数百万条历史数据的宽表中任选一个时空节点。系统将利用 Parquet 底层下推引擎在毫秒级提取数据，并实时计算该网格点气候异常的核心物理归因。")
    
    time_list, grid_str_list = load_historical_metadata()
    if time_list and grid_str_list and model is not None:
        
        # 构建顶部控制栏
        col_sel1, col_sel2, col_sel3 = st.columns([2, 3, 2])
        
        with col_sel1:
            selected_time = st.selectbox("📅 1. 选择分析时间点", time_list, index=0)
            sel_year = int(selected_time.split("-")[0])
            sel_month = int(selected_time.split("-")[1])
            
        with col_sel2:
            # 提供几个典型城市的快捷选项，或者让用户手动选
            selected_grid_str = st.selectbox("📍 2. 选择空间网格 (默认展示华北平原首个网格)", grid_str_list, index=0)
            # 解析字符串 "Lat: 39.50, Lon: 116.00" 为浮点数
            sel_lat = float(selected_grid_str.split(",")[0].replace("Lat:", "").strip())
            sel_lon = float(selected_grid_str.split(",")[1].replace("Lon:", "").strip())
            
        with col_sel3:
            st.markdown("<br>", unsafe_allow_html=True) # 占位对齐
            btn_analyze = st.button("🔍 执行深度物理归因分析", type="primary", use_container_width=True)

        st.markdown("---")
        
        if btn_analyze:
            with st.spinner("正在从海量历史数据库中极速提取目标数据，并计算 SHAP 瀑布..."):
                # 1. 提取那一行的单点数据
                df_single = fetch_single_point_data(sel_year, sel_month, sel_lat, sel_lon)
                
                if df_single.empty:
                    st.error(f"❌ 找不到该时空节点的数据记录 (可能是海洋或无记录区域)。")
                else:
                    # 准备模型特征输入
                    # 补齐 One-Hot 编码 (如果缺少 zone_x 列)
                    for col in model.feature_names_in_:
                        if col not in df_single.columns:
                            df_single[col] = 0
                            
                    X_single = df_single[model.feature_names_in_]
                    actual_pred = model.predict(X_single)[0]
                    actual_target = df_single['target_spei_1m_ahead'].values[0] if 'target_spei_1m_ahead' in df_single.columns else np.nan
                    
                    # 2. 准备 SHAP 背景数据（这里为了速度，我们就取当前最新的网格数据作为 Background Expected Value）
                    # 实际项目中，你可以抽样 100 条随机历史数据作为背景
                    X_background = df_latest[model.feature_names_in_].sample(n=100, random_state=42, replace=True)
                    
                    # 3. 初始化 Explainer 并计算单条记录的 SHAP 值
                    explainer = load_shap_explainer(model, X_background)
                    shap_values = explainer(X_single)
                    
                    # 构建布局
                    col_chart, col_metric = st.columns([3, 1])
                    
                    with col_metric:
                        st.markdown("### 🎯 预测结果对比")
                        st.metric("基准干旱期望值 (Expected)", f"{explainer.expected_value:.2f}", help="华北平原整体平均干旱程度")
                        
                        # 重点展示从 Expected 变化到 Actual 的过程
                        delta = actual_pred - explainer.expected_value
                        color = "inverse" if delta < 0 else "normal" # 越低越干旱，所以负数为红(差)
                        
                        st.metric(
                            "该网格点最终预测 SPEI", 
                            f"{actual_pred:.2f}", 
                            delta=f"{delta:+.2f} 偏离度", 
                            delta_color=color,
                            help="模型预测下个月该网格的干旱指数"
                        )
                        
                        if not np.isnan(actual_target):
                            st.metric("真实历史观测 SPEI", f"{actual_target:.2f}")
                            
                        st.markdown("---")
                        st.markdown("""
                        **瀑布图阅读指南：**
                        - **E[f(X)]**: 背景数据的平均基准干旱状态
                        - **f(x)**: 当前网格点的最终预测结果
                        - **红色条带 (+)**: 推动气候向“湿润”方向发展的正向物理因子
                        - **蓝色条带 (-)**: 导致气候向“极端干旱”方向恶化的负向物理因子
                        """)
                    
                    with col_chart:
                        # 4. 绘制 SHAP 瀑布图 (Waterfall Plot)
                        st.subheader(f"💧 {selected_time} (Lat:{sel_lat}, Lon:{sel_lon}) 干旱成因物理分解")
                        
                        fig, ax = plt.subplots(figsize=(10, 6))
                        # 设置 max_display 来限制显示的特征数量，防止文字拥挤
                        shap.plots.waterfall(shap_values[0], max_display=12, show=False)
                        plt.tight_layout()
                        st.pyplot(fig)
                        plt.close()
    else:
        st.warning("⚠️ 历史大宽表 `ml_feature_table.parquet` 未找到，无法加载时空选择器。")
