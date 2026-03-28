# 🚀 数据迁移执行指南

**更新时间**: 2026-03-10 10:00 AM  
**系统配置**: 32GB RAM + 16GB GPU  
**迁移方案**: 激进模式（全程并行）

---

## 📋 一、快速启动（推荐）

### 最简单方式：双击运行

```
start_migration.bat
```

这个批处理文件会自动：
1. ✅ 检查 Python 和 Docker 环境
2. ✅ 检查 CSV 文件和磁盘空间
3. ✅ 询问确认
4. ✅ 启动自动化迁移
5. ✅ 显示桌面通知
6. ✅ 生成详细报告

---

## 🛠️ 二、手动启动方式

### 步骤 1: 检查环境

```bash
# 确认 Docker 容器运行
docker-compose ps

# 确认 CSV 文件存在
dir migration_package\grid_weather_data.csv
```

### 步骤 2: 清理数据库（可选）

如果数据库中有旧数据：

```bash
python scripts/clear_db.py
```

### 步骤 3: 启动迁移

```bash
python scripts/auto_migrate.py
```

### 步骤 4: 验证结果

```bash
python scripts/verify_db.py
```

---

## 📊 三、自动化功能详解

### `auto_migrate.py` 功能清单

1. **前置条件检查**
   - CSV 文件存在性
   - 磁盘空间（> 50GB）
   - 内存状态
   - Docker 容器状态

2. **实时监控**
   - 迁移脚本内存占用
   - PostgreSQL 内存占用
   - 系统总内存使用率
   - CPU 使用率
   - 每 10 秒更新一次

3. **日志记录**
   - 控制台实时输出
   - 文件日志（`auto_migration.log`）
   - 迁移详细日志（`migration.log`）

4. **完成通知**
   - Windows 系统提示音
   - 桌面气泡通知
   - 生成迁移报告

5. **错误处理**
   - 支持 Ctrl+C 安全中断
   - 自动回滚事务
   - 详细错误日志

---

## ⏱️ 四、时间线预测

```
10:00 - 启动迁移脚本
        ├─ 检查环境（30 秒）
        └─ 启动监控

10:01 - 开始迁移
        ├─ 清理数据库（1 分钟）
        ├─ 创建临时 CSV（15-25 分钟）
        │   └─ 内存：~80 MB
        │
        ├─ PostgreSQL COPY（20-40 分钟）⭐峰值
        │   └─ 内存：~550 MB
        │
        └─ 验证和清理（5-10 分钟）
            └─ 内存：~250 MB

11:00-11:15 - 完成
        ├─ 播放提示音
        ├─ 显示桌面通知
        └─ 生成报告
```

**总耗时**: 60-75 分钟

---

## 💾 五、资源监控

### 32GB RAM 配置下的预期

| 阶段 | Python 内存 | PostgreSQL 内存 | 系统总内存 | 可用内存 |
|------|-----------|---------------|-----------|---------|
| 初始化 | 50 MB | 150 MB | 200 MB | 31.8 GB |
| 临时 CSV | 80 MB | 200 MB | 280 MB | 31.7 GB |
| COPY 导入 | 30 MB | 500 MB | 530 MB | 31.5 GB |
| 验证清理 | 50 MB | 250 MB | 300 MB | 31.7 GB |

**结论**: 对于 32GB 系统，内存占用 < 2%，完全可以忽略不计

### GPU 占用

- **全程**: 0%（迁移不使用 GPU）
- **显存**: 0 MB
- **影响**: 无

---

## 🎯 六、并行运行建议

### 激进方案（推荐 32GB RAM）

```
10:00 - 同时启动:
        - 数据迁移（~550 MB 峰值）
        - 模型训练（~8-12 GB）
        
全程无需暂停，系统仍有 > 18 GB 可用内存
```

### 监控建议

```bash
# 新开终端窗口监控内存
python monitor_memory.py
```

或者使用 Windows 任务管理器：
- 监控 `python.exe`（迁移脚本）
- 监控 `postgres.exe`（数据库容器）
- 监控 GPU 显存（应无变化）

---

## 📁 七、文件清单

### 核心脚本
- ✅ `start_migration.bat` - 一键启动（推荐）
- ✅ `scripts/auto_migrate.py` - 自动化托管
- ✅ `scripts/migrate_from_csv.py` - 迁移核心逻辑
- ✅ `scripts/clear_db.py` - 数据库清理
- ✅ `scripts/verify_db.py` - 数据验证

### 监控工具
- ✅ `monitor_memory.py` - 内存监控

### 文档
- ✅ `MIGRATION_SUMMARY.md` - 快速摘要
- ✅ `MEMORY_ANALYSIS.md` - 详细内存分析
- ✅ `MIGRATION_GUIDE.md` - 本文件

### 日志文件（运行后生成）
- 📄 `auto_migration.log` - 自动化日志
- 📄 `migration.log` - 迁移详细日志
- 📄 `migration_report.txt` - 最终报告

---

## ⚠️ 八、注意事项

### 迁移前
1. ✅ 确保 Docker Desktop 已启动
2. ✅ 检查 C 盘可用空间 > 50 GB
3. ✅ 关闭不必要的程序（释放内存）
4. ✅ 保存所有工作（以防万一）

### 迁移中
1. ✅ 可以正常使用电脑
2. ✅ 可以运行模型训练
3. ✅ 可以玩游戏（GPU 不受影响）
4. ⚠️ 避免大量文件操作（可能影响 I/O）

### 迁移后
1. ✅ 验证数据库行数
2. ✅ 检查日志文件
3. ✅ 确认临时文件已删除
4. ✅ 备份重要数据

---

## 🐛 九、常见问题

### Q1: Docker 容器未运行
```bash
# 解决方案
docker-compose up -d
```

### Q2: 磁盘空间不足
```bash
# 清理临时文件
del /F migration_package\grid_weather_data_temp.csv

# 清理 Docker 无用数据
docker system prune -a
```

### Q3: 迁移中断
```bash
# 清理数据库
python scripts/clear_db.py

# 重新运行
python scripts/auto_migrate.py
```

### Q4: 内存使用率过高
```bash
# 降低模型训练 batch_size
# 或暂停训练等待迁移完成
```

### Q5: PostgreSQL 连接失败
```bash
# 检查端口
netstat -ano | findstr 5432

# 重启容器
docker-compose restart db
```

---

## 📊 十、验证步骤

### 快速验证
```bash
python scripts/verify_db.py
```

### 手动验证
```sql
-- 1. 检查总行数
SELECT COUNT(*) FROM grid_weather_data;
-- 预期：~176,000,000

-- 2. 检查时间范围
SELECT MIN(timestamp), MAX(timestamp) 
FROM grid_weather_data;
-- 预期：1990-01-01 至 2023-12-31

-- 3. 检查网格点
SELECT COUNT(DISTINCT (latitude, longitude)) 
FROM grid_weather_data;
-- 预期：数千个

-- 4. 检查数据质量
SELECT 
    AVG(temperature), AVG(precipitation),
    AVG(et0_fao_evapotranspiration)
FROM grid_weather_data;
```

---

## 🎉 十一、成功标志

迁移完成后，您应该看到：

```
================================================================================
✅ 数据迁移全部完成！
   总耗时：65.3 分钟
   总行数：176,000,000
   平均速度：2,695,385 行/分钟
================================================================================

🎉 迁移成功完成！
📄 报告已保存至：migration_report.txt
```

数据库验证：
```
================================================================================
🔍 数据库验证报告
================================================================================

1️⃣ 总行数统计
   数据库行数：176,234,567
   预期行数：~176,000,000
   ✅ 行数正常

2️⃣ 时间范围
   最早时间：1990-01-01 00:00:00
   最晚时间：2023-12-31 23:00:00

3️⃣ 网格点统计
   唯一网格点数：5,432

4️⃣ 数据完整性检查
   总缺失率：0.0123%
   ✅ 数据完整性良好

✅ 验证完成
```

---

## 🚀 十二、立即开始

### 方式 1：最简单（推荐）
```bash
start_migration.bat
```

### 方式 2：手动控制
```bash
# 1. 清理数据库（可选）
python scripts/clear_db.py

# 2. 启动迁移
python scripts/auto_migrate.py

# 3. 验证结果
python scripts/verify_db.py
```

---

## 📞 十三、后续工作

迁移完成后，您可以：

1. ✅ 使用 `app.py` 查看数据
2. ✅ 开始模型训练（数据已就绪）
3. ✅ 进行数据分析
4. ✅ 计算 SPEI 指数
5. ✅ 运行偏差校正

---

**准备好后，运行 `start_migration.bat` 开始迁移！** 🎉

**预计完成时间**: 11:15 AM 左右
