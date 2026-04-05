import os
import logging
import time
import pandas as pd
import numpy as np
import joblib
from xgboost import XGBRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.cluster import KMeans

# ================= 核心配置区 =================
# 注意：请根据实际运行目录调整路径
DATA_PATH = 'data/processed/ml_feature_table.parquet'
TELE_DATA_PATH = 'teleconnection_features.parquet'

# 创建独立的结果保存目录
EXPERIMENT_DIR = 'xgb_experiment_results'
MODELS_DIR = os.path.join(EXPERIMENT_DIR, 'models')
LOGS_DIR = os.path.join(EXPERIMENT_DIR, 'logs')
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# 统一的、释放性能的超参数 (榨取表格数据的非线性极限)
XGB_PARAMS = {
    'n_estimators': 300,            # 迭代次数 (树的数量)
    'learning_rate': 0.05,          # 学习率
    'max_depth': 10,                # 相比RF较浅，但通过boosting进行复杂组合
    'subsample': 0.8,               # 样本采样率，防止过拟合
    'colsample_bytree': 0.8,        # 特征采样率，防止过拟合
    'tree_method': 'hist',          # 针对大数据量高度优化的直方图算法
    'device': 'cuda',               # 强制使用 GPU 加速
    'random_state': 42
}

N_CLUSTERS = 15

# 不需要作为特征输入的列（动态目标列会在运行时被移除）
BASE_EXCLUDE_COLS = [
    'year', 'month', 'latitude', 'longitude',
    'target_spei_1m_ahead', 'target_spei_3m_ahead', 'target_spei_6m_ahead'
]

# 实验策略配置矩阵：只进行 2 组极限测试
EXPERIMENTS = [
    {
        'id': 'xgb_exp1',
        'target_col': 'target_spei_1m_ahead',
        'use_tele': False,
        'desc': '短期极限预测 (未来1个月) - 仅使用局地特征',
        'model_name': 'xgb_1m_no_tele.joblib'
    },
    {
        'id': 'xgb_exp2',
        'target_col': 'target_spei_3m_ahead',
        'use_tele': True,
        'desc': '长期极限预测 (未来3个月) - 包含大尺度遥相关特征',
        'model_name': 'xgb_3m_tele.joblib'
    }
]
# ==========================================

def setup_logger(exp_id):
    """为每个实验设置独立的日志记录器"""
    logger = logging.getLogger(exp_id)
    logger.setLevel(logging.INFO)
    
    if logger.hasHandlers():
        logger.handlers.clear()
        
    log_file = os.path.join(LOGS_DIR, f'{exp_id}_{time.strftime("%Y%m%d_%H%M%S")}.log')
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(formatter)
    
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger

def run_single_experiment(config, logger):
    logger.info("=" * 60)
    logger.info(f"🚀 开始 XGBoost 实验: {config['id']}")
    logger.info(f"📋 策略描述: {config['desc']}")
    logger.info(f"🎯 预测目标: {config['target_col']}")
    logger.info(f"💡 是否使用遥相关: {config['use_tele']}")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    # 1. 加载主数据
    logger.info(f"正在加载主特征表: {DATA_PATH} ...")
    if not os.path.exists(DATA_PATH):
         raise FileNotFoundError(f"未找到主特征表 {DATA_PATH}，请确认运行路径")
    df = pd.read_parquet(DATA_PATH)
    
    # 2. 合并遥相关特征
    if config['use_tele']:
        logger.info(f"正在加载并合并遥相关特征: {TELE_DATA_PATH} ...")
        if not os.path.exists(TELE_DATA_PATH):
             raise FileNotFoundError(f"未找到遥相关特征表 {TELE_DATA_PATH}")
        df_tele = pd.read_parquet(TELE_DATA_PATH)
        df = pd.merge(df, df_tele, on=['year', 'month'], how='left')
        
        logger.info("正在构造遥相关高阶宏观特征...")
        tele_ts = df[['year', 'month', 'nino34', 'pdo', 'wpsh_ridge', 'nino34_lag3', 'wpsh_ridge_lag1']].drop_duplicates().sort_values(['year', 'month'])
        tele_ts['nino34_rolling3_mean'] = tele_ts['nino34'].rolling(window=3, min_periods=1).mean()
        tele_ts['pdo_rolling3_mean'] = tele_ts['pdo'].rolling(window=3, min_periods=1).mean()
        tele_ts['wpsh_ridge_rolling3_mean'] = tele_ts['wpsh_ridge'].rolling(window=3, min_periods=1).mean()
        tele_ts['nino_x_wpsh'] = tele_ts['nino34_lag3'] * tele_ts['wpsh_ridge_lag1']
        
        new_feats = tele_ts[['year', 'month', 'nino34_rolling3_mean', 'pdo_rolling3_mean', 'wpsh_ridge_rolling3_mean', 'nino_x_wpsh']]
        df = pd.merge(df, new_feats, on=['year', 'month'], how='left')
    
    # 3. 剔除目标列为空的行
    target_col = config['target_col']
    df = df.dropna(subset=[target_col])
    
    # 4. 空间聚类
    logger.info(f"正在进行 K-Means 空间聚类 (n_clusters={N_CLUSTERS}) ...")
    coords = df[['latitude', 'longitude']].drop_duplicates()
    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10)
    coords['spatial_zone'] = kmeans.fit_predict(coords)
    
    df = df.merge(coords, on=['latitude', 'longitude'], how='left')
    df = pd.get_dummies(df, columns=['spatial_zone'], prefix='zone', drop_first=False)
    
    # 5. 剔除缺失值并排序
    feature_cols = [c for c in df.columns if c not in BASE_EXCLUDE_COLS]
    df = df.dropna(subset=feature_cols)
    logger.info("正在按照时间(year, month)以及空间排序...")
    df = df.sort_values(by=['year', 'month', 'latitude', 'longitude']).reset_index(drop=True)
    
    logger.info(f"最终特征维度数量: {len(feature_cols)}")
    
    # 6. 滚动交叉验证 (Walk-Forward Validation)
    folds = [
        {'train_end': 2010, 'test_start': 2011, 'test_end': 2015},
        {'train_end': 2015, 'test_start': 2016, 'test_end': 2019},
        {'train_end': 2019, 'test_start': 2020, 'test_end': 2030}
    ]
    
    fold_idx = 1
    best_model = None
    best_rmse = float('inf')
    best_fold_idx = 1
    
    for fold_conf in folds:
        logger.info(f"\n--- 正在处理 Fold {fold_idx} ---")
        
        train_mask = df['year'] <= fold_conf['train_end']
        test_mask = (df['year'] >= fold_conf['test_start']) & (df['year'] <= fold_conf['test_end'])
        
        df_train = df[train_mask]
        df_test = df[test_mask]
        
        if len(df_test) == 0:
            logger.warning(f"Fold {fold_idx} 测试集为空，跳过...")
            fold_idx += 1
            continue
            
        X_train, y_train = df_train[feature_cols], df_train[target_col]
        X_test, y_test = df_test[feature_cols], df_test[target_col]
        
        logger.info(f"训练集: {len(X_train)} 条 | 测试集: {len(X_test)} 条")
        
        # 使用统一超参数初始化 XGBoost 模型
        model = XGBRegressor(**XGB_PARAMS)
        
        logger.info("模型开始拟合数据 (XGBoost 梯度提升中)...")
        train_start = time.time()
        
        # 拟合数据，并通过 eval_set 监控训练和测试集的指标
        model.fit(
            X_train, y_train,
            eval_set=[(X_train, y_train), (X_test, y_test)],
            verbose=50  # 每 50 棵树打印一次进度
        )
        logger.info(f"Fold {fold_idx} 训练完毕，耗时: {time.time() - train_start:.2f} 秒")
        
        # 记录本折特征重要性 (XGBoost 默认以 gain 衡量)
        importances = model.feature_importances_
        indices = np.argsort(importances)[::-1]
        
        diag_msg = f"\n  [诊断] Fold {fold_idx} - Top 20 Feature Importances (Gain):\n"
        for f in range(min(20, len(feature_cols))):
            diag_msg += f"  {f+1:2d}. {X_train.columns[indices[f]]:<30}: {importances[indices[f]]:.4f}\n"
        diag_msg += "-" * 40
        logger.info(diag_msg)
        
        # 评估
        pred = model.predict(X_test)
        mse = mean_squared_error(y_test, pred)
        rmse = np.sqrt(mse)
        r2 = r2_score(y_test, pred)
        
        eval_msg = (
            f"  [Fold {fold_idx} 评估结果]\n"
            f"  MSE       : {mse:.4f}\n"
            f"  RMSE      : {rmse:.4f}\n"
            f"  R² (得分) : {r2:.4f}"
        )
        logger.info(eval_msg)
        
        if rmse < best_rmse:
            best_rmse = rmse
            best_model = model
            best_fold_idx = fold_idx
            
        fold_idx += 1
        
    # 7. 实验总结与保存
    final_report = (
        "\n" + "="*50 + "\n"
        f"      实验 {config['id']} 最终报告\n"
        + "="*50 + "\n"
        f"策略  : {config['desc']}\n"
        f"最佳折: Fold {best_fold_idx}\n"
        f"RMSE  : {best_rmse:.4f}\n"
        + "="*50
    )
    logger.info(final_report)
    
    if best_model is not None:
        best_msg = "\n  [全局最优模型] Top 20 Feature Importances:\n"
        importances = best_model.feature_importances_
        indices = np.argsort(importances)[::-1]
        for f in range(min(20, len(feature_cols))):
            best_msg += f"  {f+1:2d}. {feature_cols[indices[f]]:<30}: {importances[indices[f]]:.4f}\n"
        best_msg += "="*50 + "\n"
        logger.info(best_msg)
        
        model_path = os.path.join(MODELS_DIR, config['model_name'])
        joblib.dump(best_model, model_path)
        logger.info(f"模型已保存至: {model_path}")
        
    logger.info(f"实验 {config['id']} 总耗时: {time.time() - start_time:.2f} 秒\n")

def main():
    print(f"即将依次执行 {len(EXPERIMENTS)} 个 XGBoost 极限探索实验...")
    print(f"统一超参数: n_estimators={XGB_PARAMS['n_estimators']}, max_depth={XGB_PARAMS['max_depth']}, learning_rate={XGB_PARAMS['learning_rate']}")
    print(f"所有结果将保存在 '{EXPERIMENT_DIR}' 目录下。")
    print("-" * 60)
    
    total_start = time.time()
    
    for config in EXPERIMENTS:
        logger = setup_logger(config['id'])
        try:
            run_single_experiment(config, logger)
        except Exception as e:
            logger.error(f"实验 {config['id']} 发生致命错误: {str(e)}", exc_info=True)
            print(f"实验 {config['id']} 失败，请查看日志！继续执行下一个实验...")
            
    total_time = time.time() - total_start
    print("=" * 60)
    print(f"🎉 所有 {len(EXPERIMENTS)} 个实验执行完毕！")
    print(f"⏱️ 总计耗时: {total_time/3600:.2f} 小时")
    print(f"📁 请前往 {EXPERIMENT_DIR}/logs 查看详细日志，前往 {EXPERIMENT_DIR}/models 获取模型文件。")
    print("=" * 60)

if __name__ == '__main__':
    main()
