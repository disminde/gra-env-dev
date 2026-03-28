"""
创建 QM 校正后的网格点数据表

功能：
    1. 创建 qm_corrected_grid_data 表存储校正后的全域网格数据
    2. 创建索引优化查询性能
    3. 支持后续模型训练和干旱指数计算
"""

import psycopg2
from dotenv import load_dotenv
import os

# 加载环境变量
load_dotenv()

# 数据库连接
conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', 'localhost'),
    port=os.getenv('POSTGRES_PORT', '5432'),
    database=os.getenv('POSTGRES_DB', 'gra_env_db'),
    user=os.getenv('POSTGRES_USER', 'admin'),
    password=os.getenv('POSTGRES_PASSWORD', 'secure_password_dev')
)

conn.autocommit = True
cur = conn.cursor()

print("="*60)
print("创建 QM 校正网格点数据表")
print("="*60)

try:
    # 1. 删除已存在的表（如果需要重建）
    print("\n[步骤 1] 删除已存在的表...")
    cur.execute("DROP TABLE IF EXISTS qm_corrected_grid_data CASCADE")
    print("✓ 完成")
    
    # 2. 创建新表
    print("\n[步骤 2] 创建 qm_corrected_grid_data 表...")
    create_table_sql = """
    CREATE TABLE qm_corrected_grid_data (
        -- 主键
        id BIGSERIAL PRIMARY KEY,
        
        -- 时空标识
        latitude DECIMAL(10, 6) NOT NULL,
        longitude DECIMAL(10, 6) NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        
        -- QM 校正后的气象变量
        temperature_corrected DECIMAL(6, 2),           -- 温度 (°C)
        precipitation_corrected DECIMAL(8, 2),         -- 降水 (mm)
        wind_speed_corrected DECIMAL(6, 2),            -- 风速 (m/s)
        relative_humidity_corrected DECIMAL(6, 2),     -- 相对湿度 (%)
        et0_corrected DECIMAL(8, 4),                   -- 【预留】蒸散量 (mm)
        
        -- 原始 ERA5 数据（保留参考）
        temperature_original DECIMAL(6, 2),
        precipitation_original DECIMAL(8, 2),
        wind_speed_original DECIMAL(6, 2),
        relative_humidity_original DECIMAL(6, 2),
        et0_original DECIMAL(8, 4),
        
        -- 元数据
        correction_method VARCHAR(50) DEFAULT 'QM',    -- 校正方法
        source_station_id VARCHAR(50),                 -- 用于校正的 NOAA 站点 ID
        quality_flag SMALLINT DEFAULT 1,               -- 质量控制标志 (1=好，2=可疑，3=差)
        created_at TIMESTAMPTZ DEFAULT NOW(),          -- 创建时间
        updated_at TIMESTAMPTZ DEFAULT NOW()           -- 更新时间
        
        -- 添加唯一约束（避免重复）
        -- UNIQUE(latitude, longitude, timestamp)
    ) WITH (fillfactor = 90);  -- 预留空间用于更新
    """
    
    cur.execute(create_table_sql)
    print("✓ 表创建完成")
    
    # 3. 创建索引
    print("\n[步骤 3] 创建索引...")
    
    # 空间索引
    print("  - 创建空间索引 (lat/lon)...")
    cur.execute("""
        CREATE INDEX idx_qm_grid_lat_lon 
        ON qm_corrected_grid_data(latitude, longitude)
    """)
    
    # 时间索引
    print("  - 创建时间索引 (timestamp)...")
    cur.execute("""
        CREATE INDEX idx_qm_grid_timestamp 
        ON qm_corrected_grid_data(timestamp)
    """)
    
    # 时空联合索引（最常用）
    print("  - 创建时空联合索引...")
    cur.execute("""
        CREATE INDEX idx_qm_grid_spatial_time 
        ON qm_corrected_grid_data(latitude, longitude, timestamp)
    """)
    
    # 站点 ID 索引（用于追溯）
    print("  - 创建站点 ID 索引...")
    cur.execute("""
        CREATE INDEX idx_qm_grid_station 
        ON qm_corrected_grid_data(source_station_id)
    """)
    
    print("✓ 索引创建完成")
    
    # 4. 创建注释
    print("\n[步骤 4] 添加表注释...")
    cur.execute("COMMENT ON TABLE qm_corrected_grid_data IS 'QM 偏差校正后的网格点气象数据 - 用于模型训练和干旱监测'")
    cur.execute("COMMENT ON COLUMN qm_corrected_grid_data.temperature_corrected IS 'QM 校正后的温度 (°C)'")
    cur.execute("COMMENT ON COLUMN qm_corrected_grid_data.precipitation_corrected IS 'QM 校正后的降水 (mm)'")
    cur.execute("COMMENT ON COLUMN qm_corrected_grid_data.wind_speed_corrected IS 'QM 校正后的风速 (m/s)'")
    cur.execute("COMMENT ON COLUMN qm_corrected_grid_data.relative_humidity_corrected IS 'QM 校正后的相对湿度 (%)'")
    cur.execute("COMMENT ON COLUMN qm_corrected_grid_data.et0_corrected IS 'QM 校正后的参考作物蒸散量 (mm) - 【预留】'")
    print("✓ 注释添加完成")
    
    # 5. 验证表结构
    print("\n[步骤 5] 验证表结构...")
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'qm_corrected_grid_data'
        ORDER BY ordinal_position
    """)
    
    print("\n表结构:")
    print("-" * 60)
    for row in cur.fetchall():
        nullable = "NULL" if row[2] == "YES" else "NOT NULL"
        print(f"  {row[0]:<40} {row[1]:<20} {nullable}")
    
    # 6. 查看索引
    print("\n索引列表:")
    print("-" * 60)
    cur.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'qm_corrected_grid_data'
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}")
    
    print("\n" + "="*60)
    print("✓ 数据库表创建成功!")
    print("="*60)
    
    # 显示表信息
    cur.execute("""
        SELECT 
            pg_size_pretty(pg_total_relation_size('qm_corrected_grid_data')) as total_size,
            pg_total_relation_size('qm_corrected_grid_data') as total_bytes
    """)
    row = cur.fetchone()
    print(f"\n当前表大小：{row[0]}")
    print(f"预计容量：每网格点每天 ~200 字节")
    print(f"估算：68 网格点 × 34 年 × 365 天 ≈ 84 万条记录 ≈ 167 MB")
    
except Exception as e:
    print(f"\n❌ 错误：{e}")
    import traceback
    traceback.print_exc()
finally:
    cur.close()
    conn.close()
