import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=os.getenv("POSTGRES_PORT", "5432"),
    dbname=os.getenv("POSTGRES_DB", "gra_env_db"),
    user=os.getenv("POSTGRES_USER", "admin"),
    password=os.getenv("POSTGRES_PASSWORD", "secure_password_dev")
)

cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM grid_weather_data;")
count = cur.fetchone()[0]
print(f"数据库行数：{count:,}")

cur.execute("SELECT MIN(timestamp), MAX(timestamp) FROM grid_weather_data;")
time_range = cur.fetchone()
print(f"时间范围：{time_range[0]} 至 {time_range[1]}")

conn.close()
