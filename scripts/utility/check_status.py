import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

try:
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
    
    if count == 0:
        print("✅ 数据库已清空")
    else:
        print(f"⚠️  数据库中还有 {count:,} 行数据")
    
    conn.close()
except Exception as e:
    print(f"❌ 错误：{e}")
