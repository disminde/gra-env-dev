
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "gra_env_db")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password_dev")

def check_distribution():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()

        print("--- Checking Year 1990 (Even Year - High Data) ---")
        cur.execute("""
            SELECT count(DISTINCT (latitude, longitude)) as locations, count(*) as total_rows
            FROM grid_weather_data
            WHERE extract(year from timestamp) = 1990;
        """)
        locs_1990, rows_1990 = cur.fetchone()
        print(f"1990: {locs_1990} locations, {rows_1990} rows")
        if locs_1990 > 0:
            print(f"Avg rows per location: {rows_1990 / locs_1990:.1f} (Expected ~8760)")

        print("\n--- Checking Year 1991 (Odd Year - Low Data) ---")
        cur.execute("""
            SELECT count(DISTINCT (latitude, longitude)) as locations, count(*) as total_rows
            FROM grid_weather_data
            WHERE extract(year from timestamp) = 1991;
        """)
        locs_1991, rows_1991 = cur.fetchone()
        print(f"1991: {locs_1991} locations, {rows_1991} rows")
        if locs_1991 > 0:
            print(f"Avg rows per location: {rows_1991 / locs_1991:.1f} (Expected ~8760)")

        # Check if locations in 1991 are a subset of 1990
        # This confirms if we are missing *locations* or *time periods*
        
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_distribution()
