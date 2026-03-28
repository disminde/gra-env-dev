# 时间单位分析与对齐策略

## 1. 数据时间单位

### NOAA 站点数据

| 属性 | 值 |
|------|-----|
| **时间单位** | 日 (Day) |
| **时间戳格式** | `YYYY-MM-DD 00:00:00` |
| **数据粒度** | 每天 1 条记录 |
| **总记录数** | 12,399 天 (1990-2023) |
| **列名示例** | `date`, `temp_mean`, `precip_daily` |

**数据示例:**
```
        date  temp_mean  precip_daily
0 1990-01-01 -18.342857           0.0
1 1990-01-02 -15.457143           0.0
2 1990-01-03 -11.066667           0.0
```

### 网格点数据 (ERA5-Land)

#### 原始数据 (grid_weather_data 表)

| 属性 | 值 |
|------|-----|
| **时间单位** | 小时 (Hour) |
| **时间戳格式** | `TIMESTAMPTZ` (带时区的时间戳) |
| **数据粒度** | 每小时 1 条记录 |
| **每天记录数** | 24 条 |
| **总记录数** | 1.76 亿条 |

#### 聚合视图 (v_grid_daily_data)

| 属性 | 值 |
|------|-----|
| **时间单位** | 日 (Day) |
| **日期格式** | `DATE` (仅日期，无时间部分) |
| **数据粒度** | 每天 1 条记录 |
| **聚合方法** | AVG(温度), SUM(降水), AVG(风速), AVG(湿度) |

**视图定义:**
```sql
CREATE VIEW v_grid_daily_data AS
SELECT 
    latitude, longitude,
    DATE(timestamp) as date,
    AVG(temperature) as temperature,
    SUM(precipitation) as precipitation,
    AVG(wind_speed_10m) as wind_speed,
    AVG(relative_humidity_2m) as relative_humidity
FROM grid_weather_data
GROUP BY latitude, longitude, DATE(timestamp)
```

---

## 2. 时间对齐最佳实践

### 方案 A：使用视图 + INNER JOIN（推荐）⭐

**优点:**
- ✅ 数据库层面完成聚合，性能最优
- ✅ 避免 Python 中的大内存操作
- ✅ 保持最高精度（无插值）
- ✅ 代码简洁，易于维护

**实现步骤:**

```python
# 1. 加载 NOAA 数据
station_df = pd.read_csv('data/processed/noaa_daily/533520-99999_daily_data.csv')
station_df['date'] = pd.to_datetime(station_df['date'])

# 2. 从视图加载网格数据
grid_df = pd.read_sql_query("""
    SELECT * FROM v_grid_daily_data
    WHERE latitude = %s AND longitude = %s
    AND date BETWEEN %s AND %s
""", conn, params=[lat, lon, start_date, end_date])

# 3. 日期对齐（INNER JOIN）
merged = pd.merge(
    station_df[['date', 'temperature', 'precipitation']],
    grid_df[['date', 'temperature', 'precipitation']],
    on='date',
    how='inner',
    suffixes=('_obs', '_sim')
)

# 4. 验证对齐
print(f"对齐后记录数：{len(merged)}")
print(f"日期范围：{merged['date'].min()} - {merged['date'].max()}")
```

**精确度保证:**
- 视图聚合使用 SQL 标准函数，精度最高
- INNER JOIN 确保只有完全匹配的日期才被保留
- 无插值、无外推，保持数据真实性

---

### 方案 B：原始数据 + Python 聚合（备选）

**适用场景:**
- 需要自定义聚合逻辑（如特殊的质量控制）
- 需要处理缺失值的具体策略

**实现步骤:**

```python
# 1. 加载 NOAA 数据
station_df = pd.read_csv(...)
station_df['date'] = pd.to_datetime(station_df['date'])

# 2. 加载原始小时数据
grid_hourly = pd.read_sql_query("""
    SELECT timestamp, temperature, precipitation
    FROM grid_weather_data
    WHERE latitude = %s AND longitude = %s
    AND timestamp BETWEEN %s AND %s
""", conn, params=[lat, lon, start_ts, end_ts])

# 3. Python 层面聚合到日尺度
grid_daily = grid_hourly.groupby(grid_hourly['timestamp'].dt.date).agg({
    'temperature': 'mean',
    'precipitation': 'sum'
}).reset_index()
grid_daily['date'] = pd.to_datetime(grid_daily['date'])

# 4. 日期对齐
merged = pd.merge(station_df, grid_daily, on='date', how='inner')
```

**缺点:**
- ❌ 需要加载大量小时数据（内存占用高）
- ❌ Python 聚合速度慢于数据库
- ❌ 增加代码复杂度

---

## 3. 日期格式转换注意事项

### pandas 日期类型

```python
# NOAA 数据：datetime64[ns]
df_noaa['date'] = pd.to_datetime(df_noaa['date'])
# 结果：1990-01-01 00:00:00

# 数据库视图：DATE 对象
# pandas 会自动转换为 datetime64[ns]，时间部分为 00:00:00

# 确保两者完全匹配的关键
df_noaa['date'] = pd.to_datetime(df_noaa['date']).dt.normalize()  # 去掉时间部分
df_view['date'] = pd.to_datetime(df_view['date'])  # 转换 DATE 为 datetime
```

### 常见陷阱

```python
# ❌ 错误：直接比较可能导致不匹配
df_noaa['date']  # 1990-01-01 00:00:00
df_view['date']  # 1990-01-01 (DATE 对象)

# ✅ 正确：统一转换为 datetime
df_noaa['date'] = pd.to_datetime(df_noaa['date'])
df_view['date'] = pd.to_datetime(df_view['date'])

# 或使用 merge 自动处理
merged = pd.merge(df_noaa, df_view, on='date', how='inner')
```

---

## 4. 完整的时间对齐代码示例

```python
import pandas as pd
import psycopg2
from dotenv import load_dotenv
import os

# 加载配置
load_dotenv()
conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', 'localhost'),
    port=os.getenv('POSTGRES_PORT', '5432'),
    database=os.getenv('POSTGRES_DB', 'gra_env_db'),
    user=os.getenv('POSTGRES_USER', 'admin'),
    password=os.getenv('POSTGRES_PASSWORD', 'secure_password_dev')
)

def load_and_align_data(station_id, grid_lat, grid_lon, start_year, end_year):
    """
    加载并对齐 NOAA 站点数据和网格点数据
    
    Args:
        station_id: NOAA 站点 ID
        grid_lat: 网格点纬度
        grid_lon: 网格点经度
        start_year: 起始年份
        end_year: 结束年份
    
    Returns:
        merged: 对齐后的 DataFrame
    """
    # 1. 加载 NOAA 数据
    noaa_file = f'data/processed/noaa_daily/{station_id}_daily_data.csv'
    station_df = pd.read_csv(noaa_file)
    station_df['date'] = pd.to_datetime(station_df['date'])
    
    # 年份过滤
    station_df = station_df[
        (station_df['date'].dt.year >= start_year) & 
        (station_df['date'].dt.year <= end_year)
    ]
    
    # 2. 加载网格点数据（使用视图）
    grid_query = """
        SELECT 
            date, temperature, precipitation, wind_speed, relative_humidity
        FROM v_grid_daily_data
        WHERE latitude = %s AND longitude = %s
        AND EXTRACT(YEAR FROM date) BETWEEN %s AND %s
    """
    grid_df = pd.read_sql_query(
        grid_query, 
        conn, 
        params=[grid_lat, grid_lon, start_year, end_year]
    )
    
    # 转换日期类型
    grid_df['date'] = pd.to_datetime(grid_df['date'])
    
    # 3. 变量重命名（统一标准）
    station_df = station_df.rename(columns={
        'temp_mean': 'temperature',
        'precip_daily': 'precipitation',
        'wind_speed_mean': 'wind_speed',
        'rh_mean': 'relative_humidity'
    })
    
    # 4. 选择共同变量
    common_vars = ['date', 'temperature', 'precipitation', 'wind_speed', 'relative_humidity']
    station_vars = [v for v in common_vars if v in station_df.columns]
    grid_vars = [v for v in common_vars if v in grid_df.columns]
    
    # 5. 日期对齐（INNER JOIN）
    merged = pd.merge(
        station_df[station_vars],
        grid_df[grid_vars],
        on='date',
        how='inner',
        suffixes=('_obs', '_sim')
    )
    
    # 6. 质量检查
    print(f"站点 {station_id}:")
    print(f"  NOAA 原始数据：{len(station_df)} 天")
    print(f"  网格点数据：{len(grid_df)} 天")
    print(f"  对齐后：{len(merged)} 天")
    print(f"  日期范围：{merged['date'].min()} - {merged['date'].max()}")
    
    return merged

# 使用示例
aligned_data = load_and_align_data(
    station_id='533520-99999',
    grid_lat=41.792618,
    grid_lon=110.478256,
    start_year=1990,
    end_year=2023
)
```

---

## 5. 总结

### 时间单位对比

| 数据源 | 时间单位 | 粒度 | 格式 |
|--------|---------|------|------|
| NOAA 站点 | 日 | 1 条/天 | datetime64[ns] |
| 网格点 (原始) | 小时 | 24 条/天 | TIMESTAMPTZ |
| 网格点 (视图) | 日 | 1 条/天 | DATE |

### 最佳对齐策略

1. **使用 v_grid_daily_data 视图** (数据库层面聚合)
2. **INNER JOIN 精确匹配** (无插值)
3. **统一日期格式** (pd.to_datetime)
4. **保留共同日期范围** (自动处理缺失)

### 精确度保证

- ✅ 视图聚合：SQL 标准函数，双精度计算
- ✅ 日期匹配：精确到日，无近似
- ✅ 无插值：只使用实际观测日期
- ✅ 可追溯：每条记录都有明确来源

### 性能优化

- ✅ 数据库索引：年份 + 空间复合索引
- ✅ 批量加载：减少数据库连接次数
- ✅ 内存管理：只加载需要的变量和年份
