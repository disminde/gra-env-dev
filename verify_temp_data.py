import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime

# 加载环境变量
load_dotenv()

print('=' * 60)
print('验证临时表 daily_radiation_temp 数据完整性')
print('=' * 60)

conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', 'localhost'),
    port=os.getenv('POSTGRES_PORT', '5432'),
    dbname=os.getenv('POSTGRES_DB', 'gra_env_dev'),
    user=os.getenv('POSTGRES_USER', 'postgres'),
    password=os.getenv('POSTGRES_PASSWORD', '27148')
)
cur = conn.cursor()

# 1. 检查总记录数
print('\n[1] 检查总记录数...')
cur.execute('SELECT COUNT(*) FROM daily_radiation_temp')
total_count = cur.fetchone()[0]
expected_count = 5751 * 12419
print(f'    实际记录数：{total_count:,}')
print(f'    预期记录数：{expected_count:,}')
print(f'    完成率：{total_count/expected_count*100:.2f}%')

# 2. 检查日期范围
print('\n[2] 检查日期范围...')
cur.execute('SELECT MIN(date), MAX(date) FROM daily_radiation_temp')
min_date, max_date = cur.fetchone()
print(f'    最早日期：{min_date}')
print(f'    最晚日期：{max_date}')
cur.execute('SELECT COUNT(DISTINCT date) FROM daily_radiation_temp')
unique_dates = cur.fetchone()[0]
print(f'    唯一日期数：{unique_dates}')

# 3. 检查网格点数量
print('\n[3] 检查网格点数量...')
cur.execute('SELECT COUNT(DISTINCT latitude, longitude) FROM daily_radiation_temp')
unique_points = cur.fetchone()[0]
print(f'    唯一网格点数：{unique_points}')
print(f'    预期网格点数：5751')

# 4. 检查数据质量
print('\n[4] 检查数据质量...')
cur.execute('SELECT COUNT(*) FROM daily_radiation_temp WHERE radiation_daily IS NULL')
null_count = cur.fetchone()[0]
print(f'    NULL 值数量：{null_count:,}')

cur.execute('SELECT COUNT(*) FROM daily_radiation_temp WHERE radiation_daily < 0')
negative_count = cur.fetchone()[0]
print(f'    负值数量：{negative_count:,}')

cur.execute('SELECT COUNT(*) FROM daily_radiation_temp WHERE radiation_daily > 50')
high_count = cur.fetchone()[0]
print(f'    异常高值数量 (>50 MJ/m²): {high_count:,}')

cur.execute('SELECT AVG(radiation_daily), MIN(radiation_daily), MAX(radiation_daily) FROM daily_radiation_temp')
avg_rad, min_rad, max_rad = cur.fetchone()
print(f'    辐射统计：avg={avg_rad:.2f}, min={min_rad:.2f}, max={max_rad:.2f} MJ/m²')

# 5. 检查每个日期的网格点覆盖率（抽样检查）
print('\n[5] 检查每日网格点覆盖率（抽样检查）...')
cur.execute('SELECT date, COUNT(*) as cnt FROM daily_radiation_temp GROUP BY date ORDER BY date LIMIT 5')
print('    前 5 天样本:')
for date, cnt in cur.fetchall():
    print(f'        {date}: {cnt:,} 个点 ({cnt/5751*100:.1f}%)')

cur.execute('SELECT date, COUNT(*) as cnt FROM daily_radiation_temp GROUP BY date ORDER BY date DESC LIMIT 5')
print('    最后 5 天样本:')
for date, cnt in cur.fetchall():
    print(f'        {date}: {cnt:,} 个点 ({cnt/5751*100:.1f}%)')

cur.close()
conn.close()

print('\n' + '=' * 60)
print('✅ 验证完成！数据已安全保存在临时表 daily_radiation_temp 中')
print('=' * 60)
