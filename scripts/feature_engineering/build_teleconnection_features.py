import os
import pandas as pd
import numpy as np
import requests

def fetch_and_parse_noaa(url, value_name):
    """
    获取并解析 NOAA 格式的纯文本数据，转为长表 (year, month, value)
    """
    print(f"正在从 {url} 获取 {value_name} 数据...")
    response = requests.get(url)
    response.raise_for_status()
    
    lines = response.text.strip().split('\n')
    data = []
    
    # 第一行是起始和结束年份，跳过
    for line in lines[1:]:
        parts = line.strip().split()
        if not parts:
            continue
            
        # 判断第一列是否为年份
        if len(parts) >= 13 and parts[0].isdigit():
            year = int(parts[0])
            for month, val_str in enumerate(parts[1:13], start=1):
                val = float(val_str)
                # NOAA 数据中通常用 -99.90, -99.99 等表示缺失值
                if val <= -99.0:
                    val = np.nan
                data.append({'year': year, 'month': month, value_name: val})
                
    return pd.DataFrame(data)

def main():
    # 1. 获取在线 API 数据
    urls = {
        'nino34': 'https://psl.noaa.gov/data/correlation/nina34.data',
        'pdo': 'https://psl.noaa.gov/data/correlation/pdo.data',
        'nao': 'https://psl.noaa.gov/data/correlation/nao.data'
    }
    
    api_dfs = []
    for name, url in urls.items():
        df_index = fetch_and_parse_noaa(url, name)
        api_dfs.append(df_index)
        
    # 合并 API 提取的三个指数
    api_merged_df = api_dfs[0]
    for df in api_dfs[1:]:
        api_merged_df = pd.merge(api_merged_df, df, on=['year', 'month'], how='outer')
        
    # 2. 读取本地 TXT 数据
    # 考虑到脚本可能在任意目录运行，这里指向根目录的 wpsh_index.txt
    wpsh_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'wpsh_index.txt')
    # 如果通过 cwd 执行，则直接用相对路径
    if not os.path.exists(wpsh_path):
        wpsh_path = 'wpsh_index.txt'
        
    if os.path.exists(wpsh_path):
        print(f"正在读取本地文件: {wpsh_path}")
        # 按要求读取文件并重命名列 (使用 sep=r'\s+' 处理任意数量的连续空格)
        wpsh_df = pd.read_csv(wpsh_path, sep=r'\s+', header=None)
        
        # 防止原文件包含多余列，严格截取前6列
        wpsh_df = wpsh_df.iloc[:, :6]
        wpsh_df.columns = ['year', 'month', 'wpsh_area', 'wpsh_intensity', 'wpsh_ridge', 'wpsh_west_point']
    else:
        print(f"警告: 未找到 {wpsh_path} 文件。将创建只含占位结构的 DataFrame 以供合并流程跑通。")
        wpsh_df = pd.DataFrame(columns=['year', 'month', 'wpsh_area', 'wpsh_intensity', 'wpsh_ridge', 'wpsh_west_point'])
        
    # 3. 数据合并
    print("正在进行数据合并...")
    final_df = pd.merge(api_merged_df, wpsh_df, on=['year', 'month'], how='outer')
    
    # 4. 统一时间轴：仅保留 year >= 1980 的记录
    final_df = final_df[final_df['year'] >= 1980].copy()
    
    # 5. 排序与缺失值处理
    # 必须先按时间排序，再做前向填充
    final_df = final_df.sort_values(['year', 'month']).reset_index(drop=True)
    final_df = final_df.ffill()
    
    # 6. 滞后特征构建 (Lag 1~6)
    print("正在构建滞后特征 (Lag 1~6)...")
    target_cols = ['nino34', 'pdo', 'nao', 'wpsh_area', 'wpsh_intensity', 'wpsh_ridge', 'wpsh_west_point']
    
    for col in target_cols:
        if col in final_df.columns:
            for lag in range(1, 7):
                final_df[f'{col}_lag{lag}'] = final_df[col].shift(lag)
                
    # 7. 剔除因滞后产生的空行 (前6个月会因为没有历史数据而产生 NaN)
    final_df = final_df.dropna().reset_index(drop=True)
    
    # 为了数据类型的规范，将 year 和 month 重新转为 int
    final_df['year'] = final_df['year'].astype(int)
    final_df['month'] = final_df['month'].astype(int)
    
    # 8. 保存文件
    out_path = 'teleconnection_features.parquet'
    final_df.to_parquet(out_path, index=False)
    print(f"处理完成！特征表已成功保存至 {out_path}，当前有效数据行数: {len(final_df)} 行。")

if __name__ == "__main__":
    main()
