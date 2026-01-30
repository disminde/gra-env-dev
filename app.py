from flask import Flask, jsonify, render_template
import psycopg2
import os
from dotenv import load_dotenv
import logging
from psycopg2.extras import RealDictCursor

# 加载环境变量
load_dotenv()

app = Flask(__name__)

# 配置日志记录
logging.basicConfig(level=logging.INFO)

# 数据库配置
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "gra_env_db")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secure_password_dev")

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        app.logger.error(f"Error connecting to database: {e}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test')
def test_page():
    return render_template('test_db.html')

@app.route('/api/weather')
def get_weather():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM weather_samples ORDER BY timestamp ASC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        app.logger.error(f"Error querying database: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/grid_recent')
def get_grid_recent():
    """获取最新的网格化天气数据（最近50条）。"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        cur = conn.cursor()
        # 获取最近插入的数据 (按 timestamp 倒序)
        cur.execute("""
            SELECT * FROM grid_weather_data 
            ORDER BY timestamp DESC 
            LIMIT 50
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        app.logger.error(f"Error querying recent grid data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/grid_stats')
def get_grid_stats():
    """获取网格化数据的统计信息。"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        cur = conn.cursor()
        # 获取记录总数
        cur.execute("SELECT COUNT(*) as count FROM grid_weather_data")
        total_count = cur.fetchone()['count']
        
        # 获取数据时间范围
        cur.execute("SELECT MIN(timestamp) as min_date, MAX(timestamp) as max_date FROM grid_weather_data")
        date_range = cur.fetchone()
        
        # 获取覆盖的网格点数量
        cur.execute("SELECT COUNT(DISTINCT (latitude, longitude)) as grid_count FROM grid_weather_data")
        grid_count = cur.fetchone()['grid_count']
        
        cur.close()
        conn.close()
        
        return jsonify({
            "total_records": total_count,
            "min_date": date_range['min_date'],
            "max_date": date_range['max_date'],
            "grid_points": grid_count
        })
    except Exception as e:
        app.logger.error(f"Error querying grid stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/fetch_log')
def get_fetch_log():
    """获取数据爬取日志的最后几行。"""
    log_file = "batch_fetch.log"
    if not os.path.exists(log_file):
        return jsonify({"log": "Log file not found."})
        
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            # 读取最后 20 行
            lines = f.readlines()[-20:]
            return jsonify({"log": "".join(lines)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
