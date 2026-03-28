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
    
    # 检查行数
    cur.execute("SELECT COUNT(*) FROM grid_weather_data;")
    count = cur.fetchone()[0]
    print(f"Database rows: {count:,}")
    
    # 检查时间范围
    cur.execute("SELECT MIN(timestamp), MAX(timestamp) FROM grid_weather_data;")
    time_range = cur.fetchone()
    print(f"Time range: {time_range[0]} to {time_range[1]}")
    
    conn.close()
    
    if count > 0:
        print("✅ MIGRATION SUCCESSFUL!")
    else:
        print("⚠️  Database is still empty")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
