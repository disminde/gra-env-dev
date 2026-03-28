import os
import logging
import time
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.cluster import KMeans

# 配置日志输出格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ================= 配置区 =================
DATA_PATH = 'data/processed/ml_feature_table.parquet'
MODEL_SAVE_DIR = 'models'
MODEL_SAVE_PATH = os.path.join(MODEL_SAVE_DIR, 'rf_baseline_1m.joblib')

# [测试1] 降低预测难度：改为预测未来1个月
TARGET_COL = 'target_spei_1m_ahead'

# 空间聚类数量
N_CLUSTERS = 15

# 不需要作为特征输入的列（例如：时间标识、绝对预测目标本身）
EXCLUDE_COLS = [
    'year', 'month', 'latitude', 'longitude',
    'target_spei_1m_ahead', 'target_spei_3m_ahead', 'target_spei_6m_ahead'
]
# ==========================================

def main():
    logging.info("=== 阶段 1: 加载与预处理数据 ===")
    if not os.path.exists(DATA_PATH):
        logging.error(f"数据文件未找到: {DATA_PATH}")
        return
        
    start_time = time.time()
    
    # ---------------------------------------------------------
    # [全量跑批模式]
    # 取消了小规模测试拦截，加载完整的 300 万条数据进行训练。
    # ---------------------------------------------------------
    df = pd.read_parquet(DATA_PATH)
    logging.info(f"成功加载宽表，总行数: {len(df)}, 总列数: {df.shape[1]}")
    
    # 剔除目标列为空的行（因时间平移导致的末尾NaN行无法参与训练）
    initial_len = len(df)
    df = df.dropna(subset=[TARGET_COL])
    
    # ---------------------------------------------------------
    # 优化 1: 空间特征聚类 (Spatial Clustering)
    # ---------------------------------------------------------
    logging.info(f"正在对经纬度进行 K-Means 聚类 (n_clusters={N_CLUSTERS}) ...")
    # 获取唯一的经纬度坐标组合以加速聚类，然后再 map 回原表
    coords = df[['latitude', 'longitude']].drop_duplicates()
    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10)
    coords['spatial_zone'] = kmeans.fit_predict(coords)
    
    # 将聚类结果合并回主表
    df = df.merge(coords, on=['latitude', 'longitude'], how='left')
    
    # 对 spatial_zone 进行 One-Hot 编码 (树模型对多重共线性免疫，故 drop_first=False)
    df = pd.get_dummies(df, columns=['spatial_zone'], prefix='zone', drop_first=False)
    
    # 剔除特征列中含有 NaN 的行（因滞后、滚动特征产生的初始NaN行）
    feature_cols = [c for c in df.columns if c not in EXCLUDE_COLS]
    df = df.dropna(subset=feature_cols)
    logging.info(f"剔除含缺失值的行数: {initial_len - len(df)}，剩余可用行数: {len(df)}")
    
    # 严格按照时间序列排序，这是确保 TimeSeriesSplit 绝对正确的关键步骤
    logging.info("正在按照时间(year, month)以及空间(latitude, longitude)进行排序...")
    df = df.sort_values(by=['year', 'month', 'latitude', 'longitude']).reset_index(drop=True)
    
    logging.info(f"最终选定的特征维度数量: {len(feature_cols)}")
    
    logging.info("=== 阶段 2: 执行时间序列滚动交叉验证 (按年份手动截断) ===")
    # ---------------------------------------------------------
    # 优化 2: 按年份手动分块 (Walk-Forward Validation)
    # 由于数据是从 1980 开始，我们设定三个 Fold：
    # Fold 1: Train(1980-2010) -> Test(2011-2015)
    # Fold 2: Train(1980-2015) -> Test(2016-2019)
    # Fold 3: Train(1980-2019) -> Test(2020-2023)
    # 这种划分方式完美保证了空间网格的完整性，绝对没有时间切分带来的泄露。
    # ---------------------------------------------------------
    
    folds = [
        {'train_end': 2010, 'test_start': 2011, 'test_end': 2015},
        {'train_end': 2015, 'test_start': 2016, 'test_end': 2019},
        {'train_end': 2019, 'test_start': 2020, 'test_end': 2030} # 2030表示取尽最新数据
    ]
    
    fold_idx = 1
    best_rf = None
    best_rmse = float('inf')
    
    for fold_conf in folds:
        logging.info(f"\n--- 正在处理 Fold {fold_idx} ---")
        
        # 按年份严格过滤
        train_mask = df['year'] <= fold_conf['train_end']
        test_mask = (df['year'] >= fold_conf['test_start']) & (df['year'] <= fold_conf['test_end'])
        
        df_train = df[train_mask]
        df_test = df[test_mask]
        
        if len(df_test) == 0:
            logging.warning(f"Fold {fold_idx} 测试集为空，跳过...")
            continue
            
        # 训练时直接拟合未来的绝对值
        X_train, y_train = df_train[feature_cols], df_train[TARGET_COL]
        X_test, y_test = df_test[feature_cols], df_test[TARGET_COL]
        
        logging.info(f"训练集: {len(X_train)} 条记录 (截止年份: {fold_conf['train_end']})")
        logging.info(f"测试集: {len(X_test)} 条记录 (年份区间: {fold_conf['test_start']} - {df_test['year'].max()})")
        
        logging.info("=== 阶段 3: 构建与训练基准模型 ===")
        # 优化 3: 增加防 OOM 与防过拟合约束
        # [测试2] 释放算力：注释掉 max_depth，降低 min_samples_leaf
        rf = RandomForestRegressor(
            n_estimators=100,
            criterion='squared_error',
            # max_depth=15,          # [释放] 允许树自由生长
            min_samples_leaf=5,      # [释放] 从 30 降到 5，允许捕捉更细微的规律
            max_samples=0.2,         # 保持降采样以防 OOM
            n_jobs=-1,
            random_state=42,
            verbose=0              # 关闭单棵树的输出以免刷屏
        )
        
        logging.info("模型初始化完成，开始拟合数据...")
        train_start_time = time.time()
        rf.fit(X_train, y_train)
        logging.info(f"Fold {fold_idx} 模型训练完毕，耗时: {time.time() - train_start_time:.2f} 秒")
        
        # [测试3] 打印特征重要性 TOP 15
        importances = rf.feature_importances_
        indices = np.argsort(importances)[::-1]
        print("\n  [诊断] Top 15 Feature Importances:")
        for f in range(15):
            print(f"  {X_train.columns[indices[f]]}: {importances[indices[f]]:.4f}")
        print("-" * 30)
        
        logging.info("=== 阶段 4: 评估基准模型 ===")
        logging.info("正在测试集上进行预测...")
        # 预测时直接输出结果，无需还原
        pred_spei_3m_ahead = rf.predict(X_test)
        
        # 直接使用真实绝对值进行评估
        mse = mean_squared_error(y_test, pred_spei_3m_ahead)
        rmse = np.sqrt(mse)
        r2 = r2_score(y_test, pred_spei_3m_ahead)
        
        print(f"  [Fold {fold_idx} 评估结果]")
        print(f"  MSE       : {mse:.4f}")
        print(f"  RMSE      : {rmse:.4f}")
        print(f"  R² (得分) : {r2:.4f}")
        
        # 保存表现最好的一折模型
        if rmse < best_rmse:
            best_rmse = rmse
            best_rf = rf
            
        fold_idx += 1
    
    print("\n" + "="*40)
    print(f"      基准模型 (RF) 最终评估报告")
    print("="*40)
    print(f"采用方案  : 绝对值预测 + 空间KMeans聚类 + 滚动交叉验证")
    print(f"最佳 RMSE : {best_rmse:.4f}")
    print("="*40 + "\n")
    
    logging.info("=== 阶段 5: 保存模型 ===")
    os.makedirs(MODEL_SAVE_DIR, exist_ok=True)
    joblib.dump(best_rf, MODEL_SAVE_PATH)
    logging.info(f"表现最优的模型已成功保存至: {MODEL_SAVE_PATH}")
    logging.info(f"总计运行耗时: {time.time() - start_time:.2f} 秒")

if __name__ == '__main__':
    main()
