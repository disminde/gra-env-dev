import numpy as np
import pandas as pd

def calculate_et0_fao56(temp, rel_hum, wind_speed_10m, shortwave_rad, elevation=50):
    """
    使用 FAO-56 Penman-Monteith 公式计算小时级参考作物蒸散发 (ET0)。
    
    参数:
    temp: 气温 (Celsius)
    rel_hum: 相对湿度 (%)
    wind_speed_10m: 10米高风速 (m/s)
    shortwave_rad: 短波辐射 (W/m^2)
    elevation: 海拔高度 (m), 默认 50m (华北平原平均)
    
    返回:
    et0: 蒸散发量 (mm/hour)
    """
    
    # 1. 物理常数
    cp = 1.013e-3  # 空气定压比热 [MJ kg-1 C-1]
    epsilon = 0.622  # 水蒸气与干空气的分子量比
    
    # 2. 气压 (P) 随海拔变化 [kPa]
    pressure = 101.3 * ((293 - 0.0065 * elevation) / 293)**5.26
    
    # 3. 汽化潜热 (lambda) [MJ kg-1]
    latent_heat = 2.45
    
    # 4. 湿度计常数 (gamma) [kPa C-1]
    gamma = (cp * pressure) / (epsilon * latent_heat)
    
    # 5. 饱和水汽压 (es) [kPa]
    es = 0.6108 * np.exp((17.27 * temp) / (temp + 237.3))
    
    # 6. 实际水汽压 (ea) [kPa]
    ea = es * (rel_hum / 100.0)
    
    # 7. 水汽压曲线斜率 (Delta) [kPa C-1]
    delta = (4098 * es) / ((temp + 237.3)**2)
    
    # 8. 风速转换: 10m 高风速转换为 2m 高风速 (u2)
    # 使用 FAO-56 推荐的对数风速剖面公式
    u2 = wind_speed_10m * (4.87 / np.log(67.8 * 10 - 5.42))
    
    # 9. 净辐射 (Rn) 处理 [MJ m-2 hour-1]
    # 注意: Open-Meteo 提供的是 W/m^2 (即 J s-1 m-2)
    # 转换为 MJ m-2 hour-1: W/m^2 * 3600 / 1,000,000
    rn = shortwave_rad * 3600 / 1_000_000
    
    # 10. 土壤热通量 (G)
    # 对于小时级计算，白天 G ≈ 0.1 * Rn, 夜间 G ≈ 0.5 * Rn
    g = np.where(rn > 0, 0.1 * rn, 0.5 * rn)
    
    # 11. FAO-56 Penman-Monteith 小时级公式
    # ET0 = [0.408 * Delta * (Rn - G) + gamma * (37 / (T + 273)) * u2 * (es - ea)] / [Delta + gamma * (1 + 0.34 * u2)]
    
    numerator = 0.408 * delta * (rn - g) + gamma * (37 / (temp + 273)) * u2 * (es - ea)
    denominator = delta + gamma * (1 + 0.34 * u2)
    
    et0 = numerator / denominator
    
    # 蒸散发不能为负
    return np.maximum(et0, 0)

if __name__ == "__main__":
    # 测试代码: 使用一组典型值
    t = 25.0      # 25度
    rh = 60.0     # 60% 湿度
    u10 = 2.0     # 2m/s 风速
    rad = 500.0   # 500 W/m^2 辐射
    
    result = calculate_et0_fao56(t, rh, u10, rad)
    print(f"测试计算结果 (T=25, RH=60%, U10=2, Rad=500):")
    print(f"ET0 = {result:.4f} mm/hour")
