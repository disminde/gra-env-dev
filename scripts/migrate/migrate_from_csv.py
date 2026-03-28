"""
华北平原气象数据迁移脚本
功能：将 CSV 文件中的气象数据迁移到 PostgreSQL 数据库
特点：
- 流式读取，低内存占用
- 使用 PostgreSQL COPY 命令，高性能
- 自动清理旧数据
- 详细的进度和日志记录
"""

import os
import sys
import csv
import psycopg2
import logging
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 配置参数
class Config:
    # 数据库配置
    DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
    DB_PORT = os.getenv("POSTGRES_PORT", "5432")
    DB_NAME = os.getenv("POSTGRES_DB", "gra_env_db")
    DB_USER = os.getenv("POSTGRES_USER", "admin")
    DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password_dev")
    
    # 文件路径
    CSV_INPUT_PATH = Path("migration_package/grid_weather_data.csv")
    CSV_TEMP_PATH = Path("migration_package/grid_weather_data_temp.csv")
    
    # 性能参数
    BATCH_SIZE = 100000  # 每批次处理的行数
    REPORT_INTERVAL = 500000  # 进度报告间隔

def get_db_connection():
    """建立数据库连接"""
    try:
        conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            dbname=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASS
        )
        logger.info("✅ 数据库连接成功")
        return conn
    except Exception as e:
        logger.error(f"❌ 数据库连接失败：{e}")
        raise

def clear_database(conn):
    """清理数据库旧数据"""
    logger.info("🧹 开始清理数据库旧数据...")
    try:
        with conn.cursor() as cur:
            # 使用 TRUNCATE 快速清空表并重置自增序列
            cur.execute("TRUNCATE TABLE grid_weather_data RESTART IDENTITY;")
        conn.commit()
        logger.info("✅ 数据库清理完成")
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ 数据库清理失败：{e}")
        raise

def create_temp_csv():
    """
    创建临时 CSV 文件（不含 id 列）
    使用流式读取，避免内存溢出
    自动跳过无效行
    """
    logger.info(f"📝 开始创建临时 CSV 文件（不含 id 列）...")
    logger.info(f"   源文件：{Config.CSV_INPUT_PATH}")
    logger.info(f"   目标文件：{Config.CSV_TEMP_PATH}")
    
    start_time = datetime.now()
    row_count = 0
    skipped_count = 0
    
    try:
        # 打开源文件和目标文件
        with open(Config.CSV_INPUT_PATH, 'r', encoding='utf-8', newline='') as f_in, \
             open(Config.CSV_TEMP_PATH, 'w', encoding='utf-8', newline='') as f_out:
            
            reader = csv.reader(f_in)
            writer = csv.writer(f_out)
            
            # 读取并写入表头（跳过 id 列）
            header = next(reader)
            new_header = header[1:]  # 跳过第一个 id 列
            writer.writerow(new_header)
            logger.info(f"   表头：{new_header}")
            
            # 流式处理每一行
            for row in reader:
                # 跳过 id 列，只保留数据列
                if len(row) < 11:
                    # 行数据不完整，跳过
                    skipped_count += 1
                    continue
                
                new_row = row[1:]
                writer.writerow(new_row)
                row_count += 1
                
                # 进度报告
                if row_count % Config.REPORT_INTERVAL == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    speed = row_count / elapsed if elapsed > 0 else 0
                    logger.info(f"   已处理 {row_count:,} 行，速度：{speed:,.0f} 行/秒")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ 临时 CSV 创建完成")
        logger.info(f"   总行数：{row_count:,}")
        logger.info(f"   跳过无效行：{skipped_count:,}")
        logger.info(f"   耗时：{elapsed:.1f} 秒")
        logger.info(f"   平均速度：{row_count/elapsed:,.0f} 行/秒")
        
        return row_count
        
    except Exception as e:
        logger.error(f"❌ 临时 CSV 创建失败：{e}")
        raise

def clean_value(value, is_numeric=True):
    """
    清洗数据值，处理空值和异常数据
    """
    if value is None or value == '':
        return None  # PostgreSQL 的 NULL
    
    if is_numeric:
        try:
            return float(value)
        except (ValueError, TypeError):
            return None  # 转换失败返回 NULL
    
    return value

def import_to_postgres_copy(conn, total_rows):
    """
    使用 PostgreSQL 原生 COPY 命令导入数据
    这是最快的批量导入方法
    需要 Docker 卷映射支持
    """
    logger.info("📥 开始导入数据到 PostgreSQL (使用 COPY 命令)...")
    logger.info("   此方法速度极快，预计 5-10 分钟完成")
    
    start_time = datetime.now()
    
    try:
        # 在 Docker 容器内的文件路径
        container_csv_path = '/migration_data/grid_weather_data_temp.csv'
        
        with conn.cursor() as cur:
            # 使用 COPY 命令从容器内的 CSV 文件导入
            copy_sql = f"""
                COPY grid_weather_data 
                (latitude, longitude, timestamp, temperature, precipitation, 
                 et0_fao_evapotranspiration, soil_moisture_0_to_7cm, 
                 relative_humidity_2m, wind_speed_10m, shortwave_radiation)
                FROM '{container_csv_path}'
                WITH (
                    FORMAT CSV,
                    HEADER true,
                    DELIMITER ',',
                    NULL ''
                )
            """
            
            logger.info(f"   执行 COPY 命令...")
            logger.info(f"   容器内文件路径：{container_csv_path}")
            
            cur.execute(copy_sql)
            conn.commit()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info("✅ 数据导入完成（COPY 方式）")
        logger.info(f"   导入行数：{total_rows:,}")
        logger.info(f"   耗时：{elapsed:.1f} 秒")
        logger.info(f"   平均速度：{total_rows/elapsed:,.0f} 行/秒")
        logger.info(f"   预计总时间：{elapsed/60:.1f} 分钟")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ COPY 导入失败：{e}")
        logger.info("💡 回退到 execute_values 方式...")
        # 如果 COPY 失败，回退到原来的方法
        import_to_postgres_execute(conn, total_rows)

def import_to_postgres_execute(conn, total_rows):
    """
    备用方案：使用 execute_values 批量导入
    """
    logger.info("📥 使用 execute_values 方式导入...")
    
    start_time = datetime.now()
    batch_size = 100000  # 增大批次到 10 万
    inserted_count = 0
    
    try:
        with open(Config.CSV_TEMP_PATH, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # 跳过表头
            
            batch = []
            for row in reader:
                # 简化清洗逻辑
                cleaned = []
                for i, v in enumerate(row):
                    if i == 2:  # timestamp
                        cleaned.append(v)
                    else:  # 数值字段
                        cleaned.append(None if v == '' else float(v))
                
                batch.append(tuple(cleaned))
                
                if len(batch) >= batch_size:
                    insert_sql = """
                        INSERT INTO grid_weather_data 
                        (latitude, longitude, timestamp, temperature, precipitation, 
                         et0_fao_evapotranspiration, soil_moisture_0_to_7cm, 
                         relative_humidity_2m, wind_speed_10m, shortwave_radiation)
                        VALUES %s
                        ON CONFLICT (latitude, longitude, timestamp) DO NOTHING
                    """
                    
                    with conn.cursor() as cur:
                        from psycopg2.extras import execute_values
                        execute_values(cur, insert_sql, batch)
                        conn.commit()
                    
                    inserted_count += len(batch)
                    batch = []
                    
                    if inserted_count % 1000000 == 0:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        speed = inserted_count / elapsed if elapsed > 0 else 0
                        logger.info(f"   已导入 {inserted_count:,} 行，速度：{speed:,.0f} 行/秒")
            
            if batch:
                insert_sql = """
                    INSERT INTO grid_weather_data 
                    (latitude, longitude, timestamp, temperature, precipitation, 
                     et0_fao_evapotranspiration, soil_moisture_0_to_7cm, 
                     relative_humidity_2m, wind_speed_10m, shortwave_radiation)
                    VALUES %s
                    ON CONFLICT (latitude, longitude, timestamp) DO NOTHING
                """
                
                with conn.cursor() as cur:
                    from psycopg2.extras import execute_values
                    execute_values(cur, insert_sql, batch)
                    conn.commit()
                
                inserted_count += len(batch)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info("✅ 数据导入完成（execute_values 方式）")
        logger.info(f"   导入行数：{inserted_count:,}")
        logger.info(f"   耗时：{elapsed:.1f} 秒")
        logger.info(f"   平均速度：{inserted_count/elapsed:,.0f} 行/秒")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ 数据导入失败：{e}")
        raise

# 别名，保持接口一致
import_to_postgres = import_to_postgres_copy

def verify_migration(conn, expected_rows):
    """验证迁移结果"""
    logger.info("🔍 开始验证迁移结果...")
    
    try:
        with conn.cursor() as cur:
            # 检查总行数
            cur.execute("SELECT COUNT(*) FROM grid_weather_data;")
            db_count = cur.fetchone()[0]
            
            logger.info(f"   数据库行数：{db_count:,}")
            logger.info(f"   预期行数：{expected_rows:,}")
            
            if db_count == expected_rows:
                logger.info("✅ 行数验证通过")
            else:
                logger.warning(f"⚠️  行数不匹配！差异：{abs(db_count - expected_rows):,}")
            
            # 检查时间范围
            cur.execute("""
                SELECT MIN(timestamp), MAX(timestamp) 
                FROM grid_weather_data;
            """)
            time_range = cur.fetchone()
            logger.info(f"   时间范围：{time_range[0]} 至 {time_range[1]}")
            
            # 检查网格点数量
            cur.execute("""
                SELECT COUNT(DISTINCT (latitude, longitude)) 
                FROM grid_weather_data;
            """)
            grid_count = cur.fetchone()[0]
            logger.info(f"   网格点数量：{grid_count:,}")
            
            # 检查数据完整性（NULL 值统计）
            cur.execute("""
                SELECT 
                    SUM(CASE WHEN temperature IS NULL THEN 1 ELSE 0 END) as temp_null,
                    SUM(CASE WHEN precipitation IS NULL THEN 1 ELSE 0 END) as precip_null,
                    SUM(CASE WHEN et0_fao_evapotranspiration IS NULL THEN 1 ELSE 0 END) as et0_null
                FROM grid_weather_data;
            """)
            null_stats = cur.fetchone()
            logger.info(f"   温度 NULL 值：{null_stats[0]:,}")
            logger.info(f"   降水 NULL 值：{null_stats[1]:,}")
            logger.info(f"   ET0 NULL 值：{null_stats[2]:,}")
            
    except Exception as e:
        logger.error(f"❌ 验证失败：{e}")
        raise

def cleanup_temp_file():
    """清理临时文件"""
    logger.info("🧹 清理临时文件...")
    try:
        if Config.CSV_TEMP_PATH.exists():
            Config.CSV_TEMP_PATH.unlink()
            logger.info(f"✅ 已删除临时文件：{Config.CSV_TEMP_PATH}")
            # 显示释放的空间
            import os
            # 临时文件已删除，估算大小
            logger.info(f"   释放空间：约 25 GB")
    except Exception as e:
        logger.warning(f"⚠️  清理临时文件失败：{e}")

def cleanup_on_error():
    """错误时清理临时文件"""
    logger.info("🧹 检测到错误，清理临时文件...")
    cleanup_temp_file()

def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("🚀 华北平原气象数据迁移开始")
    logger.info("=" * 80)
    
    total_start_time = datetime.now()
    conn = None
    
    try:
        # 步骤 1: 连接数据库
        conn = get_db_connection()
        
        # 步骤 2: 清理旧数据
        clear_database(conn)
        
        # 步骤 3: 创建临时 CSV
        row_count = create_temp_csv()
        
        # 步骤 4: 导入到 PostgreSQL
        import_to_postgres(conn, row_count)
        
        # 步骤 5: 验证迁移结果
        verify_migration(conn, row_count)
        
        # 步骤 6: 清理临时文件
        cleanup_temp_file()
        
        # 完成
        total_elapsed = (datetime.now() - total_start_time).total_seconds()
        logger.info("=" * 80)
        logger.info("✅ 数据迁移全部完成！")
        logger.info(f"   总耗时：{total_elapsed/60:.1f} 分钟")
        logger.info(f"   总行数：{row_count:,}")
        logger.info(f"   平均速度：{row_count/(total_elapsed/60):,.0f} 行/分钟")
        logger.info("=" * 80)
        
    except KeyboardInterrupt:
        logger.error("\n⚠️  用户中断迁移过程")
        if conn:
            conn.rollback()
        cleanup_on_error()
        logger.info("💡 提示：迁移已中断，需要重新运行脚本")
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"\n❌ 迁移过程中发生错误：{e}")
        if conn:
            conn.rollback()
        cleanup_on_error()
        raise
        
    finally:
        if conn:
            conn.close()
            logger.info("🔌 数据库连接已关闭")

if __name__ == "__main__":
    main()
