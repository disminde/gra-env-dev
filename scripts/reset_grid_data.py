import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "15432")
DB_NAME = os.getenv("POSTGRES_DB", "gra_env_db")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password_dev")

def reset_db():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        print("正在清理旧数据...")
        cur.execute("TRUNCATE TABLE grid_weather_data;")
        conn.commit()
        print("✅ 数据库表格 'grid_weather_data' 已清空。")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ 重置数据库失败: {e}")

if __name__ == "__main__":
    reset_db()
