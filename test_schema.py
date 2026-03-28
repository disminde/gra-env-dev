import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', 'localhost'),
    dbname=os.getenv('POSTGRES_DB', 'gra_env_db'),
    user=os.getenv('POSTGRES_USER', 'admin'),
    password=os.getenv('POSTGRES_PASSWORD', 'secure_password_dev')
)
cur = conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'high_res_daily_weather_et0';")
print("high_res_daily_weather_et0:")
for row in cur.fetchall():
    print(row)
    
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'monthly_spei_features';")
print("\nmonthly_spei_features:")
for row in cur.fetchall():
    print(row)
