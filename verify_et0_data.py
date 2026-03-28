from dotenv import load_dotenv
import os
load_dotenv()
import psycopg2

conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST'),
    port=os.getenv('POSTGRES_PORT'),
    dbname=os.getenv('POSTGRES_DB'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD')
)

cur = conn.cursor()

print("快速检查 ET0 数据库...")

# 检查总记录
cur.execute("SELECT COUNT(*) FROM optimized_et0_grid_data")
total = cur.fetchone()[0]
print(f"\n总记录数：{total:,}")

# 检查有 ET0 值的记录
cur.execute("SELECT COUNT(*) FROM optimized_et0_grid_data WHERE et0_optimized IS NOT NULL")
with_et0 = cur.fetchone()[0]
print(f"有 ET0 的记录：{with_et0:,} ({with_et0/total*100:.1f}%)")

# 检查有降水的记录
cur.execute("SELECT COUNT(*) FROM optimized_et0_grid_data WHERE precipitation_used IS NOT NULL")
with_precip = cur.fetchone()[0]
print(f"有降水的记录：{with_precip:,} ({with_precip/total*100:.1f}%)")

# 随机抽查 5 条记录
cur.execute("""
    SELECT latitude, longitude, timestamp, et0_optimized, precipitation_used
    FROM optimized_et0_grid_data
    WHERE et0_optimized IS NOT NULL
    LIMIT 5
""")

rows = cur.fetchall()
print(f"\n有 ET0 值的记录示例：{len(rows)} 条")
for row in rows:
    print(f"  ({row[0]:.2f}, {row[1]:.2f}) {row[2]}: ET0={row[3]}, Precip={row[4]}")

# 如果没有数据，检查表结构
if with_et0 == 0:
    print("\n❌ 确实没有 ET0 数据！检查表结构...")
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns
        WHERE table_name = 'optimized_et0_grid_data'
        ORDER BY ordinal_position
    """)
    print("表结构:")
    for col in cur.fetchall():
        print(f"  {col[0]}: {col[1]}")

cur.close()
conn.close()
