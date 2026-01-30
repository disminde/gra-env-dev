import psycopg2
import os
from dotenv import load_dotenv
from tabulate import tabulate

# 加载环境变量
load_dotenv()

# 数据库配置
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "gra_env_db")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password_dev")

def get_db_stats():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()

        print("\n--- 数据库数据采集概况 ---\n")

        # 1. 总体统计
        cur.execute("SELECT COUNT(*) FROM grid_weather_data")
        total_records = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(DISTINCT (latitude, longitude)) FROM grid_weather_data")
        total_grids = cur.fetchone()[0]

        cur.execute("SELECT MIN(timestamp), MAX(timestamp) FROM grid_weather_data")
        min_date, max_date = cur.fetchone()

        summary_data = [
            ["总记录数", f"{total_records:,}"],
            ["已覆盖网格点数", total_grids],
            ["数据起始时间", min_date],
            ["数据截止时间", max_date]
        ]
        print(tabulate(summary_data, headers=["指标", "数值"], tablefmt="grid"))

        # 2. 按年份统计
        print("\n--- 按年份分布 ---\n")
        cur.execute("""
            SELECT EXTRACT(YEAR FROM timestamp) as year, COUNT(*) as count 
            FROM grid_weather_data 
            GROUP BY year 
            ORDER BY year
        """)
        year_stats = cur.fetchall()
        print(tabulate(year_stats, headers=["年份", "记录数"], tablefmt="grid"))

        # 3. 按网格点统计 (前 5 个)
        print("\n--- 网格点分布预览 (前 5 个) ---\n")
        cur.execute("""
            SELECT latitude, longitude, COUNT(*) as count 
            FROM grid_weather_data 
            GROUP BY latitude, longitude 
            LIMIT 5
        """)
        grid_sample = cur.fetchall()
        print(tabulate(grid_sample, headers=["纬度", "经度", "记录数"], tablefmt="grid"))

        cur.close()
        conn.close()
    except Exception as e:
        print(f"查询出错: {e}")

if __name__ == "__main__":
    get_db_stats()
