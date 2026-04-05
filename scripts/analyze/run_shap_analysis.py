import os
import joblib
import pandas as pd
import numpy as np
import shap
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans

# 解决 SHAP 画图时的中文显示问题（如果系统有中文字体）
plt.rcParams['font.sans-serif'] = ['SimHei']  # Windows 用户可以改为 'Microsoft YaHei'
plt.rcParams['axes.unicode_minus'] = False

# ================= 核心配置 =================
# 我们使用 1个月预测（局地特征主导）的最优模型作为分析底座
MODEL_PATH = 'xgb_experiment_results/models/xgb_1m_no_tele.joblib'
DATA_PATH = 'data/processed/ml_feature_table.parquet'
OUTPUT_DIR = 'shap_analysis_results'

os.makedirs(OUTPUT_DIR, exist_ok=True)

N_CLUSTERS = 15
TARGET_COL = 'target_spei_1m_ahead'
BASE_EXCLUDE_COLS = [
    'year', 'month', 'latitude', 'longitude',
    'target_spei_1m_ahead', 'target_spei_3m_ahead', 'target_spei_6m_ahead'
]
# ============================================

def load_and_preprocess_data():
    print(f"1. 正在加载数据: {DATA_PATH} ...")
    df = pd.read_parquet(DATA_PATH)
    
    print("2. 正在执行必要的数据预处理 (保持与训练时一致)...")
    df = df.dropna(subset=[TARGET_COL])
    
    # 重建空间聚类特征 (因为模型输入需要它们)
    coords = df[['latitude', 'longitude']].drop_duplicates()
    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10)
    coords['spatial_zone'] = kmeans.fit_predict(coords)
    
    df = df.merge(coords, on=['latitude', 'longitude'], how='left')
    df = pd.get_dummies(df, columns=['spatial_zone'], prefix='zone', drop_first=False)
    
    # 提取特征列
    feature_cols = [c for c in df.columns if c not in BASE_EXCLUDE_COLS]
    df = df.dropna(subset=feature_cols)
    
    # 为了 SHAP 分析速度，我们不使用全量 300 万条数据，而是随机采样 10000 条
    print("3. 为了 SHAP 计算效率，随机采样 10000 条背景样本...")
    df_sample = df.sample(n=10000, random_state=42)
    X_sample = df_sample[feature_cols]
    
    return X_sample, feature_cols

def generate_shap_plots(model, X_sample):
    print("\n4. 正在初始化 SHAP TreeExplainer...")
    # XGBoost 是树模型，使用 TreeExplainer 计算极快
    explainer = shap.TreeExplainer(model)
    
    print("5. 正在计算 SHAP 值 (这可能需要 1-2 分钟)...")
    shap_values = explainer.shap_values(X_sample)
    
    # ---------------- 画图 1: SHAP Summary Plot (全局解释) ----------------
    print("6. 正在生成并保存 SHAP Summary Plot (全局特征重要性)...")
    plt.figure(figsize=(10, 8))
    # plot_type="dot" 会画出密集的点，展示特征值大小对模型预测的促进/抑制作用
    shap.summary_plot(shap_values, X_sample, show=False, max_display=15)
    plt.title("XGBoost 短期预测 (1个月) 的 SHAP 全局归因分析")
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'shap_summary_plot.png'), dpi=300)
    plt.close()
    
    # ---------------- 画图 2: SHAP Bar Plot (平均绝对重要性) ----------------
    print("7. 正在生成并保存 SHAP Bar Plot (平均特征贡献)...")
    plt.figure(figsize=(10, 8))
    shap.summary_plot(shap_values, X_sample, plot_type="bar", show=False, max_display=15)
    plt.title("特征对 SPEI 预测的平均绝对影响幅度")
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'shap_bar_plot.png'), dpi=300)
    plt.close()
    
    # ---------------- 画图 3: 局部解释 (Waterfall Plot) ----------------
    # 我们挑出一条预测极端干旱的样本来看看
    print("8. 正在生成极端干旱个案的 Waterfall Plot (局部解释)...")
    
    # 让模型预测一遍，找出预测值最低（最干旱）的样本
    preds = model.predict(X_sample)
    extreme_drought_idx = np.argmin(preds)
    
    # 对于 Waterfall，我们需要 Explanation 对象
    shap_exp = explainer(X_sample.iloc[[extreme_drought_idx]])
    
    plt.figure(figsize=(10, 6))
    shap.plots.waterfall(shap_exp[0], show=False, max_display=10)
    plt.title(f"极端干旱预测个案归因 (预测 SPEI: {preds[extreme_drought_idx]:.2f})")
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'shap_waterfall_extreme_drought.png'), dpi=300)
    plt.close()

def main():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"找不到模型文件: {MODEL_PATH}。")
        
    print(f"正在加载预训练模型: {MODEL_PATH}")
    model = joblib.load(MODEL_PATH)
    
    X_sample, feature_cols = load_and_preprocess_data()
    
    generate_shap_plots(model, X_sample)
    
    print("=" * 60)
    print(f"🎉 SHAP 分析完成！")
    print(f"📁 所有的解释神图已经保存至: {OUTPUT_DIR}/ 目录下。")
    print("=" * 60)

if __name__ == '__main__':
    main()
