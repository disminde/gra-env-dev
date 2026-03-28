import psycopg2
import os

try:
    conn = psycopg2.connect(
        host="localhost",
        port="5432",
        dbname="gra_env_db",
        user="admin",
        password="secure_password_dev"
    )
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM grid_weather_data;")
    count = cur.fetchone()[0]
    print(f"IMPORT_COUNT: {count}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"ERROR: {e}")
