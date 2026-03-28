import psycopg2
import os
from dotenv import load_dotenv

def get_db_connection():
    load_dotenv()
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        dbname=os.getenv('POSTGRES_DB', 'gra_env_db'),
        user=os.getenv('POSTGRES_USER', 'admin'),
        password=os.getenv('POSTGRES_PASSWORD', 'secure_password_dev')
    )

def explore_columns():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'grid_weather_data';
        """)
        columns = cur.fetchall()
        
        print("\ngrid_weather_data 表的列：")
        for col in columns:
            print(f"- {col[0]} ({col[1]})")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"探查失败: {e}")

if __name__ == "__main__":
    explore_columns()
