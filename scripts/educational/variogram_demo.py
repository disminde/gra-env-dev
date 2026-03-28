#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
变异函数（Variogram）计算演示
============================
目的：用实际代码展示变异函数是如何从站点数据计算的

作者：GRA 团队
日期：2026-03-11
"""

import numpy as np
from itertools import combinations


def calculate_distance(point1, point2):
    """计算两点间的欧氏距离"""
    return np.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)


def calculate_empirical_variogram(locations, values, n_lags=10):
    """
    计算经验变异函数
    
    参数:
        locations: 站点位置列表 [(x1, y1), (x2, y2), ...]
        values: 站点观测值列表 [v1, v2, ...]
        n_lags: 距离分箱数量
    
    返回:
        lags: 每个 bin 的平均距离
        gamma: 对应的半方差值
    """
    n_points = len(locations)
    
    # 1. 计算所有点对的距离和半方差
    pairs = []
    for i, j in combinations(range(n_points), 2):
        dist = calculate_distance(locations[i], locations[j])
        half_variogram = 0.5 * (values[i] - values[j])**2
        pairs.append({
            'distance': dist,
            'half_var': half_variogram,
            'point1': locations[i],
            'point2': locations[j]
        })
    
    # 2. 按距离分箱（Binning）
    max_dist = max(p['distance'] for p in pairs)
    lag_width = max_dist / n_lags
    
    lags = []
    gamma = []
    counts = []
    
    for i in range(n_lags):
        lag_min = i * lag_width
        lag_max = (i + 1) * lag_width
        
        # 找出落在当前 bin 的所有点对
        bin_pairs = [p for p in pairs if lag_min <= p['distance'] < lag_max]
        
        if len(bin_pairs) > 0:
            # 计算该 bin 的平均距离和平均半方差
            avg_dist = np.mean([p['distance'] for p in bin_pairs])
            avg_gamma = np.mean([p['half_var'] for p in bin_pairs])
            
            lags.append(avg_dist)
            gamma.append(avg_gamma)
            counts.append(len(bin_pairs))
    
    return np.array(lags), np.array(gamma), counts


def fit_spherical_model(lags, gamma):
    """
    拟合球状变异函数模型
    
    模型：γ(h) = c × [1.5(h/r) - 0.5(h/r)³]  (当 h < r)
                  = c                        (当 h ≥ r)
    
    使用简单网格搜索估计参数
    """
    # 参数搜索范围
    sill_candidates = np.linspace(max(gamma) * 0.5, max(gamma) * 1.5, 20)
    range_candidates = np.linspace(max(lags) * 0.5, max(lags) * 1.5, 20)
    
    best_sill = max(gamma)
    best_range = max(lags)
    best_mse = float('inf')
    
    # 网格搜索最优参数
    for sill in sill_candidates:
        for r in range_candidates:
            # 计算模型预测值
            predicted = []
            for h in lags:
                if h < r:
                    h_r = h / r
                    pred = sill * (1.5 * h_r - 0.5 * h_r**3)
                else:
                    pred = sill
                predicted.append(pred)
            
            # 计算均方误差
            mse = np.mean((np.array(predicted) - gamma)**2)
            
            if mse < best_mse:
                best_mse = mse
                best_sill = sill
                best_range = r
    
    return best_sill, best_range


def spherical_model(h, sill, range_param):
    """球状模型计算"""
    result = np.zeros_like(h)
    mask = h < range_param
    h_r = h[mask] / range_param
    result[mask] = sill * (1.5 * h_r - 0.5 * h_r**3)
    result[~mask] = sill
    return result


def main():
    print("=" * 60)
    print("变异函数（Variogram）计算演示")
    print("=" * 60)
    
    # ==================== 示例 1: 简单数据集 ====================
    print("\n【示例 1: 6 个站点的简单数据】")
    
    # 创建示例数据
    locations_simple = [
        (0, 0), (10, 0), (20, 0),
        (0, 30), (10, 30), (20, 30)
    ]
    temperatures = [25, 26, 27, 24, 25, 26]
    
    print(f"\n站点数据:")
    for i, (loc, temp) in enumerate(zip(locations_simple, temperatures)):
        print(f"  站点 {chr(65+i)}: 位置{loc}, 温度{temp}°C")
    
    # 计算经验变异函数
    lags, gamma, counts = calculate_empirical_variogram(
        locations_simple, temperatures, n_lags=5
    )
    
    print(f"\n经验变异函数计算结果:")
    print(f"  {'距离 (km)':<12} {'半方差':<10} {'点对数':<8}")
    print(f"  {'-'*30}")
    for i in range(len(lags)):
        print(f"  {lags[i]:<12.1f} {gamma[i]:<10.3f} {counts[i]:<8}")
    
    # 拟合理论模型
    sill, range_param = fit_spherical_model(lags, gamma)
    print(f"\n球状模型拟合结果:")
    print(f"  基台值 (Sill): {sill:.3f}")
    print(f"  变程 (Range): {range_param:.1f} km")
    
    # ==================== 示例 2: 真实场景数据 ====================
    print("\n\n【示例 2: 模拟的真实气象站点网络】")
    
    # 生成更真实的站点数据
    np.random.seed(42)
    n_stations = 30
    
    # 随机生成站点位置（100x100 km 区域）
    locations_real = np.random.uniform(0, 100, (n_stations, 2))
    
    # 生成具有空间相关性的温度场
    # 使用高斯过程模拟空间相关性
    from scipy.spatial.distance import pdist, squareform
    
    # 计算距离矩阵
    dist_matrix = squareform(pdist(locations_real))
    
    # 生成空间相关的温度（指数协方差）
    range_true = 30  # 真实变程 30km
    cov_matrix = np.exp(-dist_matrix / range_true)
    
    # 生成随机场
    L = np.linalg.cholesky(cov_matrix)
    random_field = L @ np.random.randn(n_stations)
    
    # 转换为温度（均值 25°C，标准差 3°C）
    temperatures_real = 25 + 3 * random_field
    
    print(f"生成了 {n_stations} 个模拟气象站点")
    print(f"温度范围：{temperatures_real.min():.1f}°C - {temperatures_real.max():.1f}°C")
    print(f"真实变程：{range_true} km")
    
    # 计算经验变异函数
    lags_real, gamma_real, counts_real = calculate_empirical_variogram(
        locations_real.tolist(), temperatures_real.tolist(), n_lags=15
    )
    
    print(f"\n经验变异函数（前 10 个 lag）:")
    print(f"  {'距离 (km)':<12} {'半方差':<10} {'点对数':<8}")
    print(f"  {'-'*30}")
    for i in range(min(10, len(lags_real))):
        print(f"  {lags_real[i]:<12.1f} {gamma_real[i]:<10.3f} {counts_real[i]:<8}")
    
    # 拟合模型
    sill_real, range_real = fit_spherical_model(lags_real, gamma_real)
    print(f"\n拟合结果:")
    print(f"  估计基台值：{sill_real:.3f}")
    print(f"  估计变程：{range_real:.1f} km (真实值：{range_true} km)")
    
    # ==================== 可视化 ====================
    print("\n【变异函数曲线示意图】")
    print("由于 matplotlib 未安装，这里用文字描述曲线形状:")
    print(f"""
    半方差 γ(h)
      ↑
    {max(gamma):.1f}|{' '*30}● ({lags[-1]:.0f}, {gamma[-1]:.2f})
      |{' '*20}●
      |
    {max(gamma)/2:.1f}|{' '*10}●
      |{' '*5}●
      |
    {0}|●
      +----+----+----+----+----→ 距离 h (km)
         {int(max(lags)/5)}   {int(max(lags)*2/5)}   {int(max(lags)*3/5)}   {int(max(lags)*4/5)}   {int(max(lags))}
    
    红色曲线 = 拟合的球状模型
    蓝色点 = 经验变异函数计算值
    """)
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)
    print("\n关键要点:")
    print("1. 变异函数通过计算不同距离的点对温差得到")
    print("2. 距离越远，半方差越大（空间相关性越弱）")
    print("3. 变程 (Range) 是空间相关性消失的距离")
    print("4. 基台值 (Sill) 是最大半方差（方差上限）")
    print("5. 块金值 (Nugget) 是距离为 0 时的方差（测量误差）")


if __name__ == '__main__':
    main()
