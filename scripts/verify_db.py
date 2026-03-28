"""
数据库验证脚本
用于验证迁移结果
"""

import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

def verify_database():
    """验证数据库"""
    try:
        # 连接数据库
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            dbname=os.getenv("POSTGRES_DB", "gra_env_db"),
            user=os.getenv("POSTGRES_USER", "admin"),
            password=os.getenv("POSTGRES_PASSWORD", "secure_password_dev")
        )
        
        print("=" * 80)
        print("🔍 数据库验证报告")
        print("=" * 80)
        print(f"验证时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        with conn.cursor() as cur:
            # 1. 总行数
            print("1️⃣ 总行数统计")
            cur.execute("SELECT COUNT(*) FROM grid_weather_data;")
            count = cur.fetchone()[0]
            print(f"   数据库行数：{count:,}")
            print(f"   预期行数：~176,000,000")
            if count >= 170000000:
                print("   ✅ 行数正常")
            else:
                print("   ⚠️  行数偏少")
            print()
            
            # 2. 时间范围
            print("2️⃣ 时间范围")
            cur.execute("""
                SELECT MIN(timestamp), MAX(timestamp) 
                FROM grid_weather_data;
            """)
            time_range = cur.fetchone()
            print(f"   最早时间：{time_range[0]}")
            print(f"   最晚时间：{time_range[1]}")
            print()
            
            # 3. 网格点数量
            print("3️⃣ 网格点统计")
            cur.execute("""
                SELECT COUNT(DISTINCT (latitude, longitude)) 
                FROM grid_weather_data;
            """)
            grid_count = cur.fetchone()[0]
            print(f"   唯一网格点数：{grid_count:,}")
            print()
            
            # 4. 数据完整性
            print("4️⃣ 数据完整性检查")
            cur.execute("""
                SELECT 
                    SUM(CASE WHEN temperature IS NULL THEN 1 ELSE 0 END) as temp_null,
                    SUM(CASE WHEN precipitation IS NULL THEN 1 ELSE 0 END) as precip_null,
                    SUM(CASE WHEN et0_fao_evapotranspiration IS NULL THEN 1 ELSE 0 END) as et0_null,
                    SUM(CASE WHEN soil_moisture_0_to_7cm IS NULL THEN 1 ELSE 0 END) as soil_null,
                    SUM(CASE WHEN relative_humidity_2m IS NULL THEN 1 ELSE 0 END) as humid_null,
                    SUM(CASE WHEN wind_speed_10m IS NULL THEN 1 ELSE 0 END) as wind_null,
                    SUM(CASE WHEN shortwave_radiation IS NULL THEN 1 ELSE 0 END) as rad_null
                FROM grid_weather_data;
            """)
            null_stats = cur.fetchone()
            
            print(f"   温度 NULL 值：{null_stats[0]:,}")
            print(f"   降水 NULL 值：{null_stats[1]:,}")
            print(f"   ET0 NULL 值：{null_stats[2]:,}")
            print(f"   土壤湿度 NULL 值：{null_stats[3]:,}")
            print(f"   相对湿度 NULL 值：{null_stats[4]:,}")
            print(f"   风速 NULL 值：{null_stats[5]:,}")
            print(f"   短波辐射 NULL 值：{null_stats[6]:,}")
            
            total_nulls = sum(null_stats)
            total_cells = count * 10  # 10 个数据列
            null_percent = (total_nulls / total_cells * 100) if total_cells > 0 else 0
            print(f"\n   总缺失率：{null_percent:.4f}%")
            
            if null_percent < 1:
                print("   ✅ 数据完整性良好")
            else:
                print("   ⚠️  缺失率偏高")
            print()
            
            # 5. 数据质量检查
            print("5️⃣ 数据质量抽样")
            cur.execute("""
                SELECT 
                    MIN(temperature), MAX(temperature), AVG(temperature),
                    MIN(precipitation), MAX(precipitation), AVG(precipitation)
                FROM grid_weather_data;
            """)
            stats = cur.fetchone()
            print(f"   温度范围：{stats[0]:.1f}℃ ~ {stats[1]:.1f}℃ (平均：{stats[2]:.1f}℃)")
            print(f"   降水范围：{stats[3]:.1f} ~ {stats[4]:.1f} (平均：{stats[5]:.2f})")
            print()
            
            # 6. 索引状态
            print("6️⃣ 索引状态")
            cur.execute("""
                SELECT indexname, indexdef 
                FROM pg_indexes 
                WHERE tablename = 'grid_weather_data';
            """)
            indexes = cur.fetchall()
            for idx in indexes:
                print(f"   ✅ {idx[0]}")
            print()
        
        conn.close()
        
        print("=" * 80)
        print("✅ 验证完成")
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ 验证失败：{e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_database()
