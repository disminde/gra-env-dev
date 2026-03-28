from dotenv import load_dotenv
import os
load_dotenv()
import psycopg2

print('=' * 80)
print('辐射数据验证报告')
print('=' * 80)

conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST'),
    port=os.getenv('POSTGRES_PORT'),
    dbname=os.getenv('POSTGRES_DB'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD')
)
cur = conn.cursor()

# ==================== 问题 1: 验证步骤 2 的数据是否已经持久化保存 ====================
print('\n【问题 1】验证步骤 2 的数据是否已经持久化保存')
print('-' * 80)

print('\n1.1 检查临时表 daily_radiation_temp...')
cur.execute('SELECT COUNT(*) FROM daily_radiation_temp')
temp_count = cur.fetchone()[0]
print(f'    临时表记录数：{temp_count:,} 条')

cur.execute('SELECT COUNT(DISTINCT latitude, longitude) FROM daily_radiation_temp')
temp_points = cur.fetchone()[0]
print(f'    临时表网格点数：{temp_points} 个')

cur.execute('SELECT MIN(date), MAX(date) FROM daily_radiation_temp')
min_date, max_date = cur.fetchone()
print(f'    日期范围：{min_date} 到 {max_date}')

expected_count = 5751 * 12419
print(f'\n    预期记录数：5751 点 × 12419 天 = {expected_count:,} 条')
print(f'    完成率：{temp_count/expected_count*100:.2f}%')

if temp_count == expected_count:
    print('    ✅ 步骤 2 数据已完整保存')
else:
    print(f'    ⚠️  数据不完整，缺少 {expected_count - temp_count:,} 条记录')

# ==================== 问题 2: 验证数据格式是否一致 ====================
print('\n【问题 2】验证临时表与主表的数据格式是否一致')
print('-' * 80)

print('\n2.1 临时表 daily_radiation_temp 结构...')
cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name = 'daily_radiation_temp'
    ORDER BY ordinal_position
""")
for col in cur.fetchall():
    print(f'    {col[0]}: {col[1]} (NULL: {col[2]})')

print('\n2.2 主表 interpolated_grid_data 结构...')
cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name = 'interpolated_grid_data'
    AND column_name IN ('latitude', 'longitude', 'timestamp', 'radiation_daily')
    ORDER BY ordinal_position
""")
for col in cur.fetchall():
    print(f'    {col[0]}: {col[1]} (NULL: {col[2]})')

print('\n2.3 临时表数据样例...')
cur.execute("""
    SELECT latitude, longitude, date, radiation_daily
    FROM daily_radiation_temp
    WHERE radiation_daily IS NOT NULL
    LIMIT 3
""")
for row in cur.fetchall():
    print(f'    lat={row[0]}, lon={row[1]}, date={row[2]}, rad={row[3]:.2f} MJ/m²')

print('\n2.4 主表辐射数据现状...')
cur.execute("""
    SELECT COUNT(*) as total, COUNT(radiation_daily) as with_rad
    FROM interpolated_grid_data
""")
row = cur.fetchone()
print(f'    主表总记录：{row[0]:,} 条')
print(f'    已有辐射值：{row[1]:,} 条 ({row[1]/row[0]*100:.1f}%)')

# ==================== 问题 3: 验证底层代码逻辑 ====================
print('\n【问题 3】验证底层代码逻辑')
print('-' * 80)

print('\n3.1 检查 JOIN UPDATE 的匹配条件...')
print('    临时表键：latitude, longitude, date')
print('    主表键：latitude, longitude, DATE(timestamp)')

print('\n3.2 测试 JOIN 查询...')
cur.execute("""
    SELECT COUNT(*)
    FROM daily_radiation_temp temp
    INNER JOIN interpolated_grid_data main
        ON main.latitude = temp.latitude
        AND main.longitude = temp.longitude
        AND DATE(main.timestamp) = temp.date
    WHERE temp.radiation_daily IS NOT NULL
""")
match_count = cur.fetchone()[0]
print(f'    可匹配的记录数：{match_count:,} 条')

cur.execute('SELECT COUNT(*) FROM interpolated_grid_data')
main_count = cur.fetchone()[0]
print(f'    主表总记录数：{main_count:,} 条')
print(f'    匹配率：{match_count/main_count*100:.1f}%')

if match_count == main_count:
    print('    ✅ 所有主表记录都能匹配到临时表数据')
else:
    print(f'    ⚠️  有 {main_count - match_count:,} 条记录无法匹配')

# ==================== 问题 4: 确认数据植入指令 ====================
print('\n【问题 4】确认数据植入指令')
print('-' * 80)

print('\n4.1 正确的 UPDATE 语句应该是：')
print('''
    UPDATE interpolated_grid_data AS main
    SET radiation_daily = temp.radiation_daily
    FROM daily_radiation_temp AS temp
    WHERE main.latitude = temp.latitude
      AND main.longitude = temp.longitude
      AND DATE(main.timestamp) = temp.date
      AND temp.radiation_daily IS NOT NULL
''')

print('\n4.2 测试小批量更新...')
try:
    cur.execute("""
        UPDATE interpolated_grid_data AS main
        SET radiation_daily = temp.radiation_daily
        FROM daily_radiation_temp AS temp
        WHERE main.latitude = temp.latitude
          AND main.longitude = temp.longitude
          AND DATE(main.timestamp) = temp.date
          AND temp.radiation_daily IS NOT NULL
          AND main.timestamp = '1990-01-01 00:00:00+00'
    """)
    updated = cur.rowcount
    conn.rollback()  # 回滚测试
    print(f'    单条记录测试：成功更新 {updated} 行 (已回滚)')
    print('    ✅ UPDATE 语句正确')
except Exception as e:
    print(f'    ❌ UPDATE 语句错误：{e}')

print('\n4.3 检查主表 timestamp 格式...')
cur.execute("""
    SELECT timestamp, DATE(timestamp)
    FROM interpolated_grid_data
    LIMIT 3
""")
for row in cur.fetchall():
    print(f'    timestamp={row[0]}, date={row[1]}')

cur.close()
conn.close()

print('\n' + '=' * 80)
print('验证完成！')
print('=' * 80)
