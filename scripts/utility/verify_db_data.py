import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv

def get_db_connection():
    # .env 文件在项目根目录
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    # 强制重新加载以覆盖系统可能存在的默认空变量
    load_dotenv(dotenv_path, override=True)
    
    db_name = os.getenv("POSTGRES_DB")
    db_user = os.getenv("POSTGRES_USER")
    db_password = os.getenv("POSTGRES_PASSWORD")
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    
    print(f"DEBUG: 尝试连接数据库: user={db_user}, dbname={db_name}")
    
    return psycopg2.connect(
        dbname=db_name,
        user=db_user,
        password=db_password,
        host=db_host,
        port=db_port
    )

def verify_data():
    conn = get_db_connection()
    cur = conn.cursor()

    print("================ 数据库数据持久化验证 ================")

    # 1. 验证总行数
    print("\n1. 正在统计总行数 (这可能需要几秒钟)...")
    cur.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'high_res_daily_weather_et0';")
    estimated_count = cur.fetchone()[0]
    print(f"   表 'high_res_daily_weather_et0' 的预估行数为: {estimated_count:,}")
    if estimated_count < 90000000:
         print("   正在进行精确计数 (较慢)...")
         cur.execute("SELECT COUNT(*) FROM high_res_daily_weather_et0;")
         exact_count = cur.fetchone()[0]
         print(f"   精确行数为: {exact_count:,}")

    # 2. 验证时间跨度
    print("\n2. 正在验证时间跨度...")
    cur.execute("SELECT MIN(date), MAX(date) FROM high_res_daily_weather_et0;")
    min_date, max_date = cur.fetchone()
    print(f"   数据的起始日期: {min_date}")
    print(f"   数据的结束日期: {max_date}")

    # 3. 验证空间维度 (唯一网格点数量)
    print("\n3. 正在验证空间维度 (网格点数量) (这可能需要几分钟)...")
    try:
        cur.execute("SELECT COUNT(*) FROM (SELECT DISTINCT latitude, longitude FROM high_res_daily_weather_et0 LIMIT 1000000) AS subquery;")
        unique_points = cur.fetchone()[0]
        print(f"   【注意: 使用限制样本统计】表内包含的唯一经纬度坐标点数量大约为: {unique_points:,} 个")
    except Exception as e:
        print(f"   验证空间维度失败: {e}")
        conn.rollback()

    # 4. 验证数据质量 (随机抽取数据检查是否存在异常值/空值)
    print("\n4. 正在进行数据质量抽样检查...")
    # 抽取特定一天的统计信息
    sample_date = '2000-07-15'
    cur.execute(f"""
        SELECT 
            MIN(temperature) as min_t, MAX(temperature) as max_t, AVG(temperature) as avg_t,
            MIN(precipitation) as min_p, MAX(precipitation) as max_p, AVG(precipitation) as avg_p,
            MIN(wind_speed) as min_w, MAX(wind_speed) as max_w, AVG(wind_speed) as avg_w,
            MIN(relative_humidity) as min_rh, MAX(relative_humidity) as max_rh, AVG(relative_humidity) as avg_rh,
            MIN(shortwave_radiation) as min_rad, MAX(shortwave_radiation) as max_rad, AVG(shortwave_radiation) as avg_rad,
            MIN(et0) as min_et0, MAX(et0) as max_et0, AVG(et0) as avg_et0,
            COUNT(*) as points_count
        FROM high_res_daily_weather_et0
        WHERE date = '{sample_date}';
    """)
    stats = cur.fetchone()
    columns = [desc[0] for desc in cur.description]
    
    print(f"   抽样日期 [{sample_date}] 包含了 {stats[-1]} 个网格点的数据。")
    print(f"   该日各变量统计特征:")
    print(f"     - 温度 (℃): 范围 [{stats[0]:.2f}, {stats[1]:.2f}], 平均 {stats[2]:.2f}")
    print(f"     - 降水 (mm): 范围 [{stats[3]:.2f}, {stats[4]:.2f}], 平均 {stats[5]:.2f}")
    print(f"     - 风速 (m/s): 范围 [{stats[6]:.2f}, {stats[7]:.2f}], 平均 {stats[8]:.2f}")
    print(f"     - 湿度 (%): 范围 [{stats[9]:.2f}, {stats[10]:.2f}], 平均 {stats[11]:.2f}")
    print(f"     - 辐射 (MJ/m2): 范围 [{stats[12]:.2f}, {stats[13]:.2f}], 平均 {stats[14]:.2f}")
    print(f"     - ET0 (mm): 范围 [{stats[15]:.2f}, {stats[16]:.2f}], 平均 {stats[17]:.2f}")

    # 检查是否存在空值
    print("\n5. 正在检查是否存在 NULL 字段...")
    cur.execute("""
        SELECT COUNT(*) FROM high_res_daily_weather_et0
        WHERE temperature IS NULL OR precipitation IS NULL 
           OR wind_speed IS NULL OR relative_humidity IS NULL 
           OR shortwave_radiation IS NULL OR et0 IS NULL;
    """)
    null_count = cur.fetchone()[0]
    if null_count == 0:
        print("   完美！数据表中没有任何 NULL 缺失值。")
    else:
        print(f"   警告：发现了 {null_count} 条包含 NULL 的记录！")

    cur.close()
    conn.close()
    print("\n================ 验证结束 ================")

if __name__ == "__main__":
    verify_data()