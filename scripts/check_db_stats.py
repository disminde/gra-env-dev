import psycopg2
import os
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

def check_radiation_stats():
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', '5432'),
            user=os.getenv('POSTGRES_USER', 'admin'),
            password=os.getenv('POSTGRES_PASSWORD', 'secure_password_dev'),
            dbname=os.getenv('POSTGRES_DB', 'gra_env_db')
        )
        
        # 1. 检查总行数
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM grid_weather_data;")
        total_rows = cur.fetchone()[0]
        print(f"Total rows: {total_rows}")
        
        # 2. 检查辐射为 NULL 的行数
        cur.execute("SELECT count(*) FROM grid_weather_data WHERE shortwave_radiation IS NULL;")
        null_rad = cur.fetchone()[0]
        print(f"Radiation IS NULL: {null_rad} ({null_rad/total_rows*100:.2f}%)")
        
        # 3. 检查辐射为 0 的行数
        cur.execute("SELECT count(*) FROM grid_weather_data WHERE shortwave_radiation = 0;")
        zero_rad = cur.fetchone()[0]
        print(f"Radiation = 0: {zero_rad} ({zero_rad/total_rows*100:.2f}%)")
        
        # 4. 检查白天 (10:00-14:00) 辐射为 0 的情况（这才是真正的问题）
        cur.execute("""
            SELECT count(*) 
            FROM grid_weather_data 
            WHERE shortwave_radiation = 0 
            AND extract(hour from timestamp) BETWEEN 10 AND 14;
        """)
        daytime_zero_rad = cur.fetchone()[0]
        print(f"Daytime (10-14h) Radiation = 0: {daytime_zero_rad}")
        
        # 5. 检查 ET0 为 NULL 的情况
        cur.execute("SELECT count(*) FROM grid_weather_data WHERE et0_fao_evapotranspiration IS NULL;")
        null_et0 = cur.fetchone()[0]
        print(f"ET0 IS NULL: {null_et0} ({null_et0/total_rows*100:.2f}%)")
        
        # 6. 按年份统计缺失率
        print("\n--- Missing Radiation by Year ---")
        cur.execute("""
            SELECT 
                extract(year from timestamp) as year,
                count(*) as total,
                count(shortwave_radiation) as non_null_rad,
                sum(case when shortwave_radiation is null then 1 else 0 end) as null_rad
            FROM grid_weather_data
            GROUP BY 1
            ORDER BY 1;
        """)
        rows = cur.fetchall()
        for row in rows:
            print(f"Year {int(row[0])}: Total {row[1]}, Null Rad {row[3]}")

        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_radiation_stats()
