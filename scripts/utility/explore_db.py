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

def explore_database():
    print("正在连接数据库探查表结构...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 查询 public 模式下的所有表名
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cur.fetchall()
        
        print("\n数据库中存在以下表：")
        for table in tables:
            table_name = table[0]
            # 查询每个表的数据量
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]
            print(f"- {table_name}: {count} 条记录")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"数据库探查失败: {e}")

if __name__ == "__main__":
    explore_database()
