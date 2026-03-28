# 🔧 迁移脚本优化说明

**优化时间**: 2026-03-10 10:37 AM  
**优化原因**: 解决空值导致的导入失败问题

---

## 📋 问题诊断

### 问题 1：空值导致导入失败
**错误信息**：
```
invalid input syntax for type double precision: ""
LINE 6: ...,'2022-08-30 06:00:00','19.950000762939453','0.0','','0.3059...
```

**根本原因**：
- CSV 文件中存在空值（空字符串 `''`）
- PostgreSQL 无法将空字符串转换为 `FLOAT` 类型
- 需要转换为 `NULL`

---

### 问题 2：临时文件占用空间
- 临时 CSV 文件约 25 GB
- 迁移失败后未自动删除
- 多次失败会累积占用空间

---

## ✅ 优化内容

### 1. 数据清洗函数

**新增** `clean_value()` 函数：
```python
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
```

**功能**：
- ✅ 将空字符串转换为 `NULL`
- ✅ 自动处理无法转换的数值
- ✅ 保证数据类型正确

---

### 2. 智能数据清洗

**优化** `import_to_postgres()` 函数：

**清洗逻辑**：
```python
cleaned_row = (
    clean_value(row[0], is_numeric=True),   # latitude
    clean_value(row[1], is_numeric=True),   # longitude
    row[2],                                  # timestamp (字符串)
    clean_value(row[3], is_numeric=True),   # temperature
    clean_value(row[4], is_numeric=True),   # precipitation
    clean_value(row[5], is_numeric=True),   # et0_fao_evapotranspiration
    clean_value(row[6], is_numeric=True),   # soil_moisture_0_to_7cm
    clean_value(row[7], is_numeric=True),   # relative_humidity_2m
    clean_value(row[8], is_numeric=True),   # wind_speed_10m
    clean_value(row[9], is_numeric=True)    # shortwave_radiation
)
```

**优势**：
- ✅ 每个字段单独处理
- ✅ 时间戳保持字符串（不需要转换）
- ✅ 数值字段自动清洗

---

### 3. NULL 值统计

**新增** 统计功能：
```python
null_count = 0  # 统计 NULL 值数量

# 统计每行的 NULL 值
null_count += sum(1 for v in cleaned_row if v is None)

# 最后报告
logger.info(f"   NULL 值总数：{null_count:,} ({null_count/inserted_count*100:.2f}%)")
```

**作用**：
- ✅ 了解数据质量
- ✅ 评估缺失值比例
- ✅ 便于后续分析

---

### 4. 无效行跳过

**优化** `create_temp_csv()` 函数：

```python
for row in reader:
    # 跳过 id 列，只保留数据列
    if len(row) < 11:
        # 行数据不完整，跳过
        skipped_count += 1
        continue
    
    new_row = row[1:]
    writer.writerow(new_row)
```

**好处**：
- ✅ 自动跳过损坏的行
- ✅ 避免导入错误
- ✅ 统计跳过的数量

---

### 5. 自动清理机制

**新增** `cleanup_on_error()` 函数：

```python
def cleanup_on_error():
    """错误时清理临时文件"""
    logger.info("🧹 检测到错误，清理临时文件...")
    cleanup_temp_file()
```

**异常处理增强**：
```python
except KeyboardInterrupt:
    logger.error("\n⚠️  用户中断迁移过程")
    if conn:
        conn.rollback()
    cleanup_on_error()  # 清理临时文件
    sys.exit(1)

except Exception as e:
    logger.error(f"\n❌ 迁移过程中发生错误：{e}")
    if conn:
        conn.rollback()
    cleanup_on_error()  # 清理临时文件
    raise
```

**优势**：
- ✅ 失败时自动清理
- ✅ 避免空间浪费
- ✅ 用户友好

---

### 6. 清理报告增强

**优化** 清理信息：
```python
logger.info(f"✅ 已删除临时文件：{Config.CSV_TEMP_PATH}")
logger.info(f"   释放空间：约 25 GB")
```

**效果**：
- ✅ 明确显示释放空间
- ✅ 用户知道空间已回收

---

## 📊 优化效果对比

### 优化前：
```
❌ 问题：空字符串导致导入失败
❌ 失败后：临时文件残留（25 GB）
❌ 数据质量：未知
```

### 优化后：
```
✅ 解决：自动转换空值为 NULL
✅ 失败后：自动清理临时文件
✅ 数据质量：详细统计（NULL 值比例）
```

---

## 🚀 预期性能

### 速度预测：
- **临时 CSV 创建**: 15-25 分钟（20 万行/秒）
- **数据导入**: 40-60 分钟（2-3 万行/秒）
- **总耗时**: 60-80 分钟

### 内存占用：
- **峰值**: < 200 MB（流式处理）
- **平均**: < 100 MB

### 磁盘占用：
- **原始 CSV**: 27.43 GB
- **临时 CSV**: ~25 GB（迁移后自动删除）
- **数据库**: ~30-40 GB

---

## 🎯 下一步

### 准备就绪后执行：
```bash
python scripts/migrate_from_csv.py
```

### 预期输出：
```
📝 开始创建临时 CSV 文件...
   已处理 500,000 行，速度：200,000 行/秒
   ...
✅ 临时 CSV 创建完成
   总行数：176,000,000
   跳过无效行：1,234

📥 开始导入数据到 PostgreSQL...
   已导入 500,000 行，速度：2,500 行/秒
   ...
✅ 数据导入完成
   导入行数：176,000,000
   NULL 值总数：1,234,567 (0.70%)
```

---

## 📈 改进点总结

1. ✅ **数据清洗**: 自动处理空值和异常数据
2. ✅ **错误处理**: 失败时自动清理临时文件
3. ✅ **质量统计**: 详细报告 NULL 值比例
4. ✅ **健壮性**: 跳过无效行，避免中断
5. ✅ **用户友好**: 清晰的进度和状态报告

---

**优化完成，可以开始迁移！** 🎉
