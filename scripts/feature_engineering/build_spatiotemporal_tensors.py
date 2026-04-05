import os
import time
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
from sklearn.preprocessing import StandardScaler
import joblib

# ================= 核心配置区 =================
# 输入文件路径 (由于您在容器的 /app 目录下运行，直接使用相对项目根目录的路径)
DATA_PATH = 'data/processed/ml_feature_table.parquet'
TELE_DATA_PATH = 'teleconnection_features.parquet'

# 输出张量保存路径
OUTPUT_DIR = 'data/processed/spatiotemporal_tensors'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 空间网格分辨率 (由于是 Open-Meteo ERA5-Land，分辨率通常为 0.1 度)
GRID_RES = 0.1

# 序列长度 (Lookback window): 过去12个月
SEQ_LEN = 12

# 我们需要升维的局地特征通道 (Channels)
SELECTED_FEATURES = [
    'p_sum', 'temp_mean', 'et0_sum', 'radiation_sum', 
    'spei_1', 'spei_3', 'spei_12',
    'p_sum_rolling3_mean', 'temp_mean_rolling3_max'
]

MACRO_FEATURES = ['nino34', 'pdo', 'nao', 'wpsh_area', 'wpsh_intensity', 'wpsh_ridge', 'wpsh_ext']

# 所有特征的合并列表
ALL_FEATURES = SELECTED_FEATURES

# 预测目标
TARGET_COL = 'target_spei_1m_ahead'  # 降维测试基准线，先证明模型能力
# ==========================================

def get_grid_dimensions(df):
    """
    分析经纬度边界，构建二维网格映射表
    """
    print(">>> 正在分析空间网格拓扑结构...")
    
    # 提取所有唯一的经纬度坐标
    coords = df[['latitude', 'longitude']].drop_duplicates()
    
    lat_min, lat_max = coords['latitude'].min(), coords['latitude'].max()
    lon_min, lon_max = coords['longitude'].min(), coords['longitude'].max()
    
    print(f"    纬度范围: [{lat_min}, {lat_max}]")
    print(f"    经度范围: [{lon_min}, {lon_max}]")
    
    # 计算网格的高(H)和宽(W)
    # 加上极小值 epsilon 防止浮点数精度导致的边界溢出
    H = int(np.ceil((lat_max - lat_min) / GRID_RES)) + 1
    W = int(np.ceil((lon_max - lon_min) / GRID_RES)) + 1
    
    print(f"    推导出的图像分辨率 (H x W): {H} x {W}")
    print(f"    总像素点数: {H * W}，实际有效网格点数: {len(coords)}")
    print(f"    (无效的背景像素将用 NaN 或 0 填充)")
    
    # 构建坐标到矩阵索引的映射字典
    # 注意：纬度越高通常在地图上越靠北（图像的上方，即索引0），所以我们把 lat_max 映射为索引 0
    def lat_to_row(lat):
        return int(np.round((lat_max - lat) / GRID_RES))
        
    def lon_to_col(lon):
        return int(np.round((lon - lon_min) / GRID_RES))
        
    coords['row_idx'] = coords['latitude'].apply(lat_to_row)
    coords['col_idx'] = coords['longitude'].apply(lon_to_col)
    
    return H, W, coords, lat_max, lon_min

def build_monthly_images(df, H, W, coords_map, feature_cols, target_col):
    """
    将一维表格按月份转换为二维图像矩阵
    """
    print("\n>>> 正在将表格数据像素化 (Pixelation)...")
    
    # 获取所有时间截面
    time_steps = df[['year', 'month']].drop_duplicates().sort_values(['year', 'month']).reset_index(drop=True)
    T = len(time_steps)
    C = len(feature_cols)
    
    print(f"    总时间步 (T): {T} 个月")
    print(f"    特征通道数 (C): {C}")
    
    # 初始化 4D 张量 (T, C, H, W)，使用 NaN 填充背景
    X_images = np.full((T, C, H, W), 0.0, dtype=np.float32) # 背景填充0，因为有效区域已被标准化
    Y_images = np.full((T, 1, H, W), 0.0, dtype=np.float32) # 背景填充0
    
    # 将行列索引合并回主表以加速赋值
    df = df.merge(coords_map[['latitude', 'longitude', 'row_idx', 'col_idx']], on=['latitude', 'longitude'], how='left')
    
    start_time = time.time()
    
    # 按月遍历填充张量
    for t_idx, row in time_steps.iterrows():
        year, month = row['year'], row['month']
        month_data = df[(df['year'] == year) & (df['month'] == month)]
        
        # 提取当前月的像素坐标
        rows = month_data['row_idx'].values
        cols = month_data['col_idx'].values
        
        # 填充特征通道
        for c_idx, feat in enumerate(feature_cols):
            X_images[t_idx, c_idx, rows, cols] = month_data[feat].values
            
        # 填充目标标签
        # 提取目标，注意保留 NaN 以便后续滑动窗口过滤，或者这里先填充，并在滑动窗口使用单独的标记
        Y_images[t_idx, 0, rows, cols] = month_data[target_col].fillna(np.nan).values
        
        if (t_idx + 1) % 60 == 0:
            print(f"    已处理 {t_idx + 1}/{T} 个月... (耗时: {time.time() - start_time:.2f}s)")
            
    print(f"    像素化完成！X_images 形状: {X_images.shape}")
    return X_images, Y_images, time_steps

def create_sliding_windows(X_images, Y_images, seq_len, tele_ts_scaled):
    """
    沿时间轴滑动窗口，构建用于 ConvLSTM 的 (Batch, Seq_Len, C, H, W) 张量和 (Batch, Seq_Len, C_macro)
    """
    print(f"\n>>> 正在构建滑动时间窗口 (Sequence Length = {seq_len})...")
    
    T, C, H, W = X_images.shape
    num_samples = T - seq_len
    
    X_seq = np.zeros((num_samples, seq_len, C, H, W), dtype=np.float32)
    X_macro_seq = np.zeros((num_samples, seq_len, tele_ts_scaled.shape[1]), dtype=np.float32)
    Y_seq = np.zeros((num_samples, 1, H, W), dtype=np.float32)
    
    valid_indices = []
    
    for i in range(num_samples):
        # 取过去 seq_len 个月作为输入序列
        x_window = X_images[i : i + seq_len]
        x_macro_window = tele_ts_scaled[i : i + seq_len]
        
        # 目标值：序列最后一个月对应的未来目标 (因为目标在宽表中已经通过 LEAD 函数对齐了)
        y_target = Y_images[i + seq_len - 1]
        
        # 检查 target 是否全为 NaN 
        if not np.all(np.isnan(y_target)):
            # 替换 NaN 为 0，方便网络计算（后续通过 mask 过滤）
            y_target = np.nan_to_num(y_target)
            
            X_seq[i] = x_window
            X_macro_seq[i] = x_macro_window
            Y_seq[i] = y_target
            valid_indices.append(i)
            
    # 过滤掉无效的末尾样本
    X_final = X_seq[valid_indices]
    X_macro_final = X_macro_seq[valid_indices]
    Y_final = Y_seq[valid_indices]
    
    print(f"    滑动窗口构建完成！")
    print(f"    最终输入张量 X_final 形状: {X_final.shape} -> (Samples, Seq_Len, Channels, Height, Width)")
    print(f"    最终输入张量 X_macro_final 形状: {X_macro_final.shape} -> (Samples, Seq_Len, C_macro)")
    print(f"    最终标签张量 Y_final 形状: {Y_final.shape} -> (Samples, 1, Height, Width)")
    
    return X_final, X_macro_final, Y_final

def main():
    print("=" * 60)
    print("🚀 启动时空数据升维任务 (Tabular to 3D Tensor)")
    print("=" * 60)
    
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"找不到数据文件: {DATA_PATH}。请检查路径配置！")
        
    # 1. 加载数据
    print(f"正在加载基础宽表...")
    columns_to_load = ['year', 'month', 'latitude', 'longitude', TARGET_COL] + SELECTED_FEATURES
    df = pd.read_parquet(DATA_PATH, columns=columns_to_load)
    
    # 加载遥相关特征
    print(f"正在加载遥相关特征表...")
    df_tele = pd.read_parquet(TELE_DATA_PATH)
    
    # 2. 特征归一化 (StandardScaler)
    print(f"\n>>> 正在执行特征归一化 (Z-Score Normalization)...")
    scaler = StandardScaler()
    
    # **关键修复**：仅对非空（陆地/有效网格）的数据进行归一化计算，防止背景0值的虚假梯度干扰
    # 假设 'p_sum' 为非空代表这是有效的陆地网格点
    valid_mask = df['p_sum'].notna()
    # 防止由于滑动窗口导致的少量时序 NaN 报错，提前用 0 填充（这里只影响有效陆地网格的早期缺失值）
    df.loc[valid_mask, ALL_FEATURES] = scaler.fit_transform(df.loc[valid_mask, ALL_FEATURES].fillna(0))
    
    # 背景区域补 0 (既然标准化后有效数据的均值为 0，背景补 0 就不会引入剧烈的人造空间梯度)
    df[ALL_FEATURES] = df[ALL_FEATURES].fillna(0)
    
    # 保存 Scaler 以便后续推理时使用
    scaler_path = os.path.join(OUTPUT_DIR, 'feature_scaler.joblib')
    joblib.dump(scaler, scaler_path)
    print(f"    局地特征 Scaler 已保存至: {scaler_path}")
    
    # 处理宏观特征 (Teleconnection) 的归一化
    time_steps = df[['year', 'month']].drop_duplicates().sort_values(['year', 'month']).reset_index(drop=True)
    tele_ts = pd.merge(time_steps, df_tele, on=['year', 'month'], how='left')[MACRO_FEATURES]
    tele_ts = tele_ts.ffill().bfill() # 处理首尾可能存在的 NaN
    
    scaler_macro = StandardScaler()
    tele_ts_scaled = scaler_macro.fit_transform(tele_ts)
    scaler_macro_path = os.path.join(OUTPUT_DIR, 'macro_scaler.joblib')
    joblib.dump(scaler_macro, scaler_macro_path)
    print(f"    宏观特征 Scaler 已保存至: {scaler_macro_path}")
    
    # 3. 获取网格拓扑
    H, W, coords_map, lat_max, lon_min = get_grid_dimensions(df)
    
    # 4. 数据像素化
    X_images, Y_images, time_info = build_monthly_images(df, H, W, coords_map, ALL_FEATURES, TARGET_COL)
    
    # 5. 构建滑动序列
    X_tensor, X_macro_tensor, Y_tensor = create_sliding_windows(X_images, Y_images, SEQ_LEN, tele_ts_scaled)
    
    # 6. 保存结果为 Numpy 压缩数组
    print("\n>>> 正在保存张量到磁盘 (这可能需要几分钟)...")
    out_file = os.path.join(OUTPUT_DIR, 'convlstm_tensors.npz')
    
    # 同时保存网格的元数据，方便后续将预测结果还原回经纬度
    meta_data = {
        'H': H, 'W': W,
        'lat_max': lat_max, 'lon_min': lon_min,
        'grid_res': GRID_RES,
        'features': ALL_FEATURES,
        'macro_features': MACRO_FEATURES,
        'seq_len': SEQ_LEN
    }
    
    np.savez_compressed(
        out_file,
        X=X_tensor,
        X_macro=X_macro_tensor,
        Y=Y_tensor,
        meta=meta_data
    )
    
    # 顺便把空间映射字典存下来
    coords_map.to_csv(os.path.join(OUTPUT_DIR, 'grid_mapping.csv'), index=False)
    
    print("=" * 60)
    print(f"🎉 升维完成！")
    print(f"📁 张量文件已保存至: {out_file}")
    print(f"📁 空间映射表已保存至: {os.path.join(OUTPUT_DIR, 'grid_mapping.csv')}")
    print(f"💡 文件大小较大，在深度学习训练时建议配合 PyTorch 的 Dataset 增量加载或直接加载到 GPU 内存。")
    print("=" * 60)

if __name__ == '__main__':
    main()
