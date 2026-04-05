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
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'rf_training_{time.strftime("%Y%m%d_%H%M%S")}.log')

# 同时输出到控制台和文件
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ================= 配置区 =================
DATA_PATH = 'data/processed/ml_feature_table.parquet'
TELE_DATA_PATH = 'teleconnection_features.parquet'

MODEL_SAVE_DIR = 'models'
MODEL_SAVE_PATH = os.path.join(MODEL_SAVE_DIR, 'rf_baseline_1m_tele.joblib')

# 锁定预测目标：预测未来1个月的绝对值 (取消差分法)
TARGET_COL = 'target_spei_1m_ahead'

# 空间聚类数量
N_CLUSTERS = 15

# [新增] 策略描述，用于日志记录
STRATEGY_DESC = "使用大尺度遥相关特征 - 预测未来1个月 (释放性能版)"

# 不需要作为特征输入的列（例如：时间标识、绝对预测目标本身）
EXCLUDE_COLS = [
    'year', 'month', 'latitude', 'longitude',
    'target_spei_1m_ahead', 'target_spei_3m_ahead', 'target_spei_6m_ahead'
]
# ==========================================

def main():
    # 记录本次训练的核心策略信息
    logging.info("=" * 60)
    logging.info(f"🚀 开始全新训练任务")
    logging.info(f"📋 训练策略: {STRATEGY_DESC}")
    logging.info(f"🎯 预测目标: {TARGET_COL}")
    logging.info(f"💾 模型保存: {MODEL_SAVE_PATH}")
    logging.info("=" * 60)

    logging.info("=== 阶段 1: 加载与预处理数据 ===")
    start_time = time.time()
    
    if not os.path.exists(DATA_PATH):
        logging.error(f"主特征表未找到: {DATA_PATH}")
        return
    if not os.path.exists(TELE_DATA_PATH):
        logging.error(f"遥相关特征表未找到: {TELE_DATA_PATH}")
        return
        
    # 1.1 加载数据并合并
    df_main = pd.read_parquet(DATA_PATH)
    df_tele = pd.read_parquet(TELE_DATA_PATH)
    
    logging.info(f"成功加载主特征表，总行数: {len(df_main)}, 总列数: {df_main.shape[1]}")
    logging.info(f"成功加载遥相关特征表，总行数: {len(df_tele)}, 总列数: {df_tele.shape[1]}")
    
    # 按照 year 和 month 进行左连接，将大尺度气候特征合并到每一个网格点上
    df = pd.merge(df_main, df_tele, on=['year', 'month'], how='left')
    logging.info(f"合并后数据集维度: {df.shape}")
    
    # 1.2 剔除目标列为空的行
    initial_len = len(df)
    df = df.dropna(subset=[TARGET_COL])
    
    # ---------------------------------------------------------
    # 新增要求 1: 构造高阶宏观特征 (交叉/滑动特征)
    # ---------------------------------------------------------
    logging.info("正在构造高阶宏观特征...")
    
    # 因为遥相关特征 (nino34, pdo, wpsh等) 在同一个时间截面 (year, month) 上全局是相同的
    # 我们可以先按时间进行去重，计算好滑动窗口特征，再合并回主表，这样能极大节省内存和时间
    tele_time_series = df[['year', 'month', 'nino34', 'pdo', 'wpsh_ridge', 'nino34_lag3', 'wpsh_ridge_lag1']].drop_duplicates().sort_values(['year', 'month'])
    
    # 计算过去 3 个月的滑动平均 (包含当前月)
    tele_time_series['nino34_rolling3_mean'] = tele_time_series['nino34'].rolling(window=3, min_periods=1).mean()
    tele_time_series['pdo_rolling3_mean'] = tele_time_series['pdo'].rolling(window=3, min_periods=1).mean()
    tele_time_series['wpsh_ridge_rolling3_mean'] = tele_time_series['wpsh_ridge'].rolling(window=3, min_periods=1).mean()
    
    # 构造交叉特征: nino34_lag3 * wpsh_ridge_lag1
    tele_time_series['nino_x_wpsh'] = tele_time_series['nino34_lag3'] * tele_time_series['wpsh_ridge_lag1']
    
    # 提取新增的特征列并合并回主表
    new_features_df = tele_time_series[['year', 'month', 'nino34_rolling3_mean', 'pdo_rolling3_mean', 'wpsh_ridge_rolling3_mean', 'nino_x_wpsh']]
    df = pd.merge(df, new_features_df, on=['year', 'month'], how='left')
    
    # ---------------------------------------------------------
    # 保持原有优秀设计: 空间特征聚类 (Spatial Clustering)
    # ---------------------------------------------------------
    logging.info(f"正在对经纬度进行 K-Means 聚类 (n_clusters={N_CLUSTERS}) ...")
    coords = df[['latitude', 'longitude']].drop_duplicates()
    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10)
    coords['spatial_zone'] = kmeans.fit_predict(coords)
    
    df = df.merge(coords, on=['latitude', 'longitude'], how='left')
    df = pd.get_dummies(df, columns=['spatial_zone'], prefix='zone', drop_first=False)
    
    # 1.3 剔除特征列中含有 NaN 的行
    feature_cols = [c for c in df.columns if c not in EXCLUDE_COLS]
    df = df.dropna(subset=feature_cols)
    logging.info(f"剔除含缺失值的行数: {initial_len - len(df)}，剩余可用行数: {len(df)}")
    
    # 1.4 严格按照时间序列排序 (保证时间切分绝对正确)
    logging.info("正在按照时间(year, month)以及空间(latitude, longitude)进行排序...")
    df = df.sort_values(by=['year', 'month', 'latitude', 'longitude']).reset_index(drop=True)
    
    logging.info(f"最终选定的特征维度数量: {len(feature_cols)}")
    
    logging.info("=== 阶段 2: 执行时间序列滚动交叉验证 (按年份手动截断) ===")
    folds = [
        {'train_end': 2010, 'test_start': 2011, 'test_end': 2015},
        {'train_end': 2015, 'test_start': 2016, 'test_end': 2019},
        {'train_end': 2019, 'test_start': 2020, 'test_end': 2030} # 取尽最新数据
    ]
    
    fold_idx = 1
    best_rf = None
    best_rmse = float('inf')
    best_fold_idx = 1
    
    for fold_conf in folds:
        logging.info(f"\n--- 正在处理 Fold {fold_idx} ---")
        
        # 按年份严格过滤
        train_mask = df['year'] <= fold_conf['train_end']
        test_mask = (df['year'] >= fold_conf['test_start']) & (df['year'] <= fold_conf['test_end'])
        
        df_train = df[train_mask]
        df_test = df[test_mask]
        
        if len(df_test) == 0:
            logging.warning(f"Fold {fold_idx} 测试集为空，跳过...")
            fold_idx += 1
            continue
            
        # 训练时直接拟合未来的绝对值
        X_train, y_train = df_train[feature_cols], df_train[TARGET_COL]
        X_test, y_test = df_test[feature_cols], df_test[TARGET_COL]
        
        logging.info(f"训练集: {len(X_train)} 条记录 (截止年份: {fold_conf['train_end']})")
        logging.info(f"测试集: {len(X_test)} 条记录 (年份区间: {fold_conf['test_start']} - {df_test['year'].max()})")
        
        logging.info("=== 阶段 3: 构建与训练基准模型 ===")
        # 释放性能配置：允许模型学习更复杂的规律，同时留有部分余地保证系统不卡死
        rf = RandomForestRegressor(
            n_estimators=100,
            criterion='squared_error',
            max_depth=25,          # [释放] 从15提升到25，允许树生长的更深
            min_samples_leaf=10,   # [释放] 从30降低到10，允许捕捉更细微的局部规律
            max_samples=0.4,       # [释放] 从0.2提升到0.4，每棵树使用40%的数据，同时留出内存余量
            n_jobs=-1,             # 仍然使用所有CPU核心
            random_state=42,
            verbose=0
        )
        
        logging.info("模型初始化完成，开始拟合数据...")
        train_start_time = time.time()
        rf.fit(X_train, y_train)
        logging.info(f"Fold {fold_idx} 模型训练完毕，耗时: {time.time() - train_start_time:.2f} 秒")
        
        # 【核心要求】打印本折特征重要性 TOP 20
        importances = rf.feature_importances_
        indices = np.argsort(importances)[::-1]
        
        diag_msg = f"\n  [诊断] Fold {fold_idx} - Top 20 Feature Importances:\n"
        for f in range(min(20, len(feature_cols))):
            diag_msg += f"  {f+1:2d}. {X_train.columns[indices[f]]:<30}: {importances[indices[f]]:.4f}\n"
        diag_msg += "-" * 40
        logging.info(diag_msg)
        
        logging.info("=== 阶段 4: 评估基准模型 ===")
        # 预测时直接输出结果，无需还原
        pred = rf.predict(X_test)
        
        mse = mean_squared_error(y_test, pred)
        rmse = np.sqrt(mse)
        r2 = r2_score(y_test, pred)
        
        eval_msg = (
            f"  [Fold {fold_idx} 评估结果]\n"
            f"  MSE       : {mse:.4f}\n"
            f"  RMSE      : {rmse:.4f}\n"
            f"  R² (得分) : {r2:.4f}"
        )
        logging.info(eval_msg)
        
        # 保存表现最好的一折模型
        if rmse < best_rmse:
            best_rmse = rmse
            best_rf = rf
            best_fold_idx = fold_idx
            
        fold_idx += 1
    
    final_report = (
        "\n" + "="*50 + "\n"
        f"      RF 模型最终报告\n"
        + "="*50 + "\n"
        f"训练策略  : {STRATEGY_DESC}\n"
        f"预测目标  : {TARGET_COL}\n"
        f"最佳折数  : Fold {best_fold_idx}\n"
        f"最佳 RMSE : {best_rmse:.4f}\n"
        + "="*50
    )
    logging.info(final_report)
    
    # 打印全局最优模型的 Top 20 特征
    if best_rf is not None:
        best_msg = "\n  [全局最优模型] Top 20 Feature Importances:\n"
        importances = best_rf.feature_importances_
        indices = np.argsort(importances)[::-1]
        for f in range(min(20, len(feature_cols))):
            best_msg += f"  {f+1:2d}. {feature_cols[indices[f]]:<30}: {importances[indices[f]]:.4f}\n"
        best_msg += "="*50 + "\n"
        logging.info(best_msg)
    
    logging.info("=== 阶段 5: 保存模型 ===")
    os.makedirs(MODEL_SAVE_DIR, exist_ok=True)
    joblib.dump(best_rf, MODEL_SAVE_PATH)
    logging.info(f"表现最优的模型已成功保存至: {MODEL_SAVE_PATH}")
    logging.info(f"总计运行耗时: {time.time() - start_time:.2f} 秒")

if __name__ == '__main__':
    main()
