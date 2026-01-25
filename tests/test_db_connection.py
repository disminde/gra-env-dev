import os
import psycopg2
from psycopg2 import OperationalError
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

def create_connection():
    """Create a database connection based on environment variables."""
    connection = None
    try:
        connection = psycopg2.connect(
            database=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
        )
        print("Connection to PostgreSQL DB successful")
    except OperationalError as e:
        print(f"The error '{e}' occurred")
    return connection

def test_query(connection):
    """Execute a simple query to verify database is working."""
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT version();")
        record = cursor.fetchone()
        print(f"PostgreSQL Version: {record[0]}")
        
        cursor.execute("SELECT * FROM system_health_check LIMIT 1;")
        record = cursor.fetchone()
        print(f"Health Check Record: {record}")
        
    except OperationalError as e:
        print(f"The error '{e}' occurred")
    finally:
        cursor.close()

if __name__ == "__main__":
    print("Waiting for database to be ready...")
    # Simple retry logic
    max_retries = 5
    for i in range(max_retries):
        conn = create_connection()
        if conn:
            test_query(conn)
            conn.close()
            break
        else:
            print(f"Connection failed. Retrying in 2 seconds... ({i+1}/{max_retries})")
            time.sleep(2)
