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
print(f"Database rows: {count:,}")
if count == 0:
    print("✅ Database is EMPTY, ready for migration")
conn.close()
