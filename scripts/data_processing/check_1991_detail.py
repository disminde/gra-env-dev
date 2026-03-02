
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "gra_env_db")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password_dev")

def check_detail():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()

        # Check the max date for 1991 for a few locations
        print("--- Checking Max Date for 1991 ---")
        cur.execute("""
            SELECT latitude, longitude, min(timestamp), max(timestamp), count(*)
            FROM grid_weather_data
            WHERE extract(year from timestamp) = 1991
            GROUP BY latitude, longitude
            LIMIT 5;
        """)
        rows = cur.fetchall()
        for row in rows:
            print(f"Loc ({row[0]:.2f}, {row[1]:.2f}): {row[2]} to {row[3]} (Count: {row[4]})")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_detail()
