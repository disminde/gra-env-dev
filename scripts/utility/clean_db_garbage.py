import psycopg2
import os
from dotenv import load_dotenv

def clean_database():
    load_dotenv()
    print("正在连接数据库清理垃圾表...")
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', '5432'),
            dbname=os.getenv('POSTGRES_DB', 'gra_env_db'),
            user=os.getenv('POSTGRES_USER', 'admin'),
            password=os.getenv('POSTGRES_PASSWORD', 'secure_password_dev')
        )
        cur = conn.cursor()
        
        # 删除上一个 Agent 遗留的垃圾表
        table_to_drop = "daily_radiation_temp"
        print(f"正在删除表: {table_to_drop} ...")
        cur.execute(f"DROP TABLE IF EXISTS {table_to_drop};")
        
        # 顺便检查一下是否还有其他名字奇怪的表（比如之前提到过的 radiation_daily_temp 等）
        cur.execute("DROP TABLE IF EXISTS radiation_daily_temp;")
        cur.execute("DROP TABLE IF EXISTS interpolated_grid_data;")
        cur.execute("DROP TABLE IF EXISTS optimized_et0_grid_data;")
        
        # 清理探查出来的新垃圾
        cur.execute("DROP TABLE IF EXISTS interpolated_grid_data_backup_20260320_173527;")
        cur.execute("DROP TABLE IF EXISTS interpolated_grid_data_backup_20260320_174209;")
        cur.execute("DROP TABLE IF EXISTS qm_corrected_grid_data;")
        cur.execute("DROP VIEW IF EXISTS v_grid_daily_data;")
        
        conn.commit()
        print("清理完成！")
        
        # 再次确认当前表
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cur.fetchall()
        print("\n当前数据库中剩下的表：")
        for table in tables:
            print(f"- {table[0]}")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"清理失败: {e}")

if __name__ == "__main__":
    clean_database()
