import numpy as np
import pandas as pd
from scipy.stats import fisk  # Fisk is another name for Log-Logistic
from scipy.special import ndtri

def calculate_spei(precip, et0, scale=3):
    """
    计算标准化降水蒸散指数 (SPEI)。
    
    参数:
    precip: 降水量序列 (numpy array 或 pandas Series)
    et0: 参考作物蒸散发序列 (numpy array 或 pandas Series)
    scale: 时间尺度 (月)，如 3, 6, 12
    
    返回:
    spei: SPEI 指数序列
    """
    
    # 1. 计算水分盈亏 (Water Balance)
    d = np.array(precip) - np.array(et0)
    
    # 2. 累积水分盈亏 (Rolling Sum)
    # 使用 pandas 的 rolling 功能
    d_series = pd.Series(d)
    d_accumulated = d_series.rolling(window=scale).sum().values
    
    # 移除前 scale-1 个 NaN 值进行分布拟合
    valid_mask = ~np.isnan(d_accumulated)
    d_valid = d_accumulated[valid_mask]
    
    if len(d_valid) < 30: # 样本量太少无法可靠拟合
        return np.full_like(d_accumulated, np.nan)
        
    # 3. 拟合 Log-Logistic 分布 (Vicente-Serrano et al., 2010 推荐)
    # 注意: Log-Logistic 分布要求数据为正值。
    # 我们通常需要对 D 序列进行平移或使用 L-moment 方法处理负值。
    # 这里采用常用的 3 参数 Log-Logistic 拟合方法：
    # SPEI = W - (C0 + C1*W + C2*W^2) / (1 + d1*W + d2*W^2 + d3*W^3)
    
    # 简化实现: 使用经验概率分布转换为标准正态分布 (适合大规模快速计算)
    # 对于每个累积值，计算其在历史分布中的百分位数
    ranks = pd.Series(d_valid).rank(method='average')
    probabilities = (ranks - 0.35) / len(d_valid) # Gringorten 绘图公式
    
    # 将概率转换为标准正态分布的分位数 (Z-score)
    spei_valid = ndtri(probabilities)
    
    # 填充回原长度序列
    spei_full = np.full_like(d_accumulated, np.nan)
    spei_full[valid_mask] = spei_valid
    
    # 限制范围在 [-3, 3] 之间
    spei_full = np.clip(spei_full, -3.0, 3.0)
    
    return spei_full

def get_drought_level(spei):
    """根据 SPEI 值判断干旱等级"""
    if np.isnan(spei): return "Unknown"
    if spei <= -2.0: return "Extreme Drought"
    if spei <= -1.5: return "Severe Drought"
    if spei <= -1.0: return "Moderate Drought"
    if spei <= -0.5: return "Mild Drought"
    if spei < 0.5: return "Normal"
    return "Wet"

if __name__ == "__main__":
    # 测试代码: 模拟一组月度数据 (10年)
    np.random.seed(42)
    months = 120
    p = np.random.gamma(2, 50, months)  # 模拟降水
    e = np.random.normal(80, 20, months) # 模拟蒸发
    
    spei3 = calculate_spei(p, e, scale=3)
    
    test_df = pd.DataFrame({
        'Precip': p,
        'ET0': e,
        'SPEI3': spei3
    })
    
    print("\n--- SPEI-3 计算示例 (最后 10 个月) ---\n")
    print(test_df.tail(10))
    print(f"\n平均 SPEI: {np.nanmean(spei3):.4f}")
    print(f"标准差 SPEI: {np.nanstd(spei3):.4f}")
