import psycopg2
import os
from dotenv import load_dotenv
import pandas as pd
from calc_et0 import calculate_et0_fao56
import matplotlib.pyplot as plt

# 加载环境变量
load_dotenv()

# 数据库配置
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "15432")
DB_NAME = os.getenv("POSTGRES_DB", "gra_env_db")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password_dev")

def verify_calculations():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        
        # 获取一个网格点的样本数据
        query = """
        SELECT timestamp, temperature, relative_humidity_2m, wind_speed_10m, 
               shortwave_radiation, et0_fao_evapotranspiration as et0_openmeteo
        FROM grid_weather_data
        WHERE latitude = (SELECT latitude FROM grid_weather_data LIMIT 1)
          AND longitude = (SELECT longitude FROM grid_weather_data LIMIT 1)
        ORDER BY timestamp ASC
        LIMIT 100;
        """
        
        df = pd.read_sql(query, conn)
        conn.close()
        
        if df.empty:
            print("数据库中没有找到数据，请确保采集脚本已运行。")
            return

        # 执行我们的 P-M 计算
        df['et0_custom'] = calculate_et0_fao56(
            df['temperature'],
            df['relative_humidity_2m'],
            df['wind_speed_10m'],
            df['shortwave_radiation']
        )
        
        print("\n--- ET0 计算结果对比 (前 10 行) ---\n")
        print(df[['timestamp', 'et0_openmeteo', 'et0_custom']].head(10))
        
        # 计算相关性
        correlation = df['et0_openmeteo'].corr(df['et0_custom'])
        print(f"\nOpen-Meteo ET0 与 自定义 P-M ET0 的相关性: {correlation:.4f}")
        
        # 简单绘图对比
        plt.figure(figsize=(12, 6))
        plt.plot(df['timestamp'], df['et0_openmeteo'], label='Open-Meteo ET0', alpha=0.7)
        plt.plot(df['timestamp'], df['et0_custom'], label='Custom P-M ET0', linestyle='--', alpha=0.7)
        plt.title('ET0 Calculation Comparison')
        plt.xlabel('Time')
        plt.ylabel('ET0 (mm/hour)')
        plt.legend()
        plt.grid(True)
        
        # 保存图表
        output_plot = "et0_comparison.png"
        plt.savefig(output_plot)
        print(f"\n对比图表已保存至: {output_plot}")

    except Exception as e:
        print(f"验证过程中出错: {e}")

if __name__ == "__main__":
    verify_calculations()
