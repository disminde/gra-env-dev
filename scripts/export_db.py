import os
import subprocess
import datetime
import shutil
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置信息
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "gra_env_db")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password_dev")

# 备份文件保存路径
BACKUP_DIR = os.path.join(os.getcwd(), "database_backup")
TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_FILE = os.path.join(BACKUP_DIR, f"gra_env_db_backup_{TIMESTAMP}.sql")

def find_pg_dump():
    """尝试自动查找 pg_dump.exe 的路径"""
    # 1. 检查环境变量
    if shutil.which("pg_dump"):
        return "pg_dump"
    
    # 2. 检查常见的 Windows 安装路径
    common_paths = [
        r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\15\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\14\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\13\bin\pg_dump.exe",
        r"C:\Program Files\PostgreSQL\12\bin\pg_dump.exe",
    ]
    for path in common_paths:
        if os.path.exists(path):
            return f'"{path}"' # 添加引号处理空格
            
    return None

def export_database():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        
    pg_dump_cmd = find_pg_dump()
    if not pg_dump_cmd:
        print("❌ 错误: 未找到 pg_dump.exe。请确保 PostgreSQL 已安装，或将其 bin 目录添加到系统环境变量 PATH 中。")
        return

    print(f"📦 开始导出数据库 '{DB_NAME}' ...")
    print(f"📂 目标文件: {BACKUP_FILE}")
    print("⏳ 数据量较大，请耐心等待（可能需要几分钟到几十分钟）...")

    # 设置密码环境变量，避免交互式输入
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASS

    # 构造命令: 导出结构和数据，使用压缩格式
    # -F c: 自定义格式 (最适合迁移，体积最小)
    # -f: 输出文件
    command = f'{pg_dump_cmd} -h {DB_HOST} -p {DB_PORT} -U {DB_USER} -F c -b -v -f "{BACKUP_FILE}" {DB_NAME}'

    try:
        subprocess.run(command, shell=True, env=env, check=True)
        print(f"\n✅ 导出成功！")
        print(f"文件位置: {BACKUP_FILE}")
        print("您可以将此文件复制到新电脑上进行恢复。")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 导出失败: {e}")

if __name__ == "__main__":
    export_database()