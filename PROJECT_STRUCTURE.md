# 华北平原水资源干枯状态分析 - 项目结构说明

**更新时间**: 2026-03-10  
**重构完成时间**: 2026-03-10 17:45

---

## 📁 项目目录结构

```
gra_env_dev/
├── 📁 data/                          # 数据目录
│   ├── raw/                          # 原始数据
│   │   ├── noaa/                     # NOAA 站点数据（69 个站点，1990-2023）
│   │   ├── grid_weather_data.csv    # Open-Meteo 网格数据（1.76 亿行）
│   │   └── grid_weather_data_temp.csv # 临时 CSV（迁移用）
│   ├── processed/                    # 处理后的数据
│   └── external/                     # 外部数据源
│
├── 📁 src/                           # 源代码目录
│   ├── data_processing/              # 数据处理脚本
│   │   ├── calc_et0.py              # 计算 PET/ET0
│   │   ├── calc_spei.py             # 计算 SPEI 指数
│   │   ├── match_noaa_stations.py   # NOAA 站点匹配
│   │   └── ...
│   ├── models/                       # 机器学习模型
│   ├── visualization/                # 可视化脚本
│   └── utils/                        # 工具函数
│
├── 📁 scripts/                       # 可执行脚本
│   ├── migrate/                      # 数据迁移脚本
│   │   ├── migrate_from_csv.py      # CSV 迁移主脚本
│   │   ├── fast_import_optimized.py # 优化的快速导入
│   │   └── auto_migrate.py          # 自动化迁移管理
│   ├── analyze/                      # 数据分析脚本
│   │   ├── analyze_csv.py           # CSV 文件分析
│   │   └── ...
│   ├── utility/                      # 实用工具
│   │   ├── monitor_memory.py        # 内存监控
│   │   ├── check_status.py          # 状态检查
│   │   └── clear_db.py              # 数据库清理
│   └── data_processing/              # 数据处理脚本（旧）
│       └── fetch_weather.py         # 天气数据爬取
│
├── 📁 docs/                          # 文档目录
│   ├── guides/                       # 使用指南
│   │   ├── MEMORY_ANALYSIS.md       # 内存消耗分析
│   │   ├── MIGRATION_GUIDE.md       # 数据迁移指南
│   │   ├── MIGRATION_SUMMARY.md     # 迁移摘要
│   │   ├── OPTIMIZATION_NOTES.md    # 优化笔记
│   │   └── START_HERE.md            # 快速开始
│   ├── specs/                        # 技术规格
│   └── reports/                      # 实验报告
│
├── 📁 tests/                         # 测试目录
│   └── test_db_connection.py        # 数据库连接测试
│
├── 📁 notebooks/                     # Jupyter 笔记本
│   ├── 01_data_exploration/         # 数据探索
│   ├── 02_bias_correction/          # 偏差校正
│   └── 03_model_training/           # 模型训练
│
├── 📁 docker/                        # Docker 配置
│   └── postgres/
│       └── init/
│           └── 01-init.sql          # 数据库初始化脚本
│
├── 📁 logs/                          # 日志文件
│
├── 📁 assets/                        # 静态资源
│   └── md-pic/                      # 文档图片
│       ├── pic-1.jpg
│       └── ...
│
├── .env.example                      # 环境变量示例
├── .gitignore                        # Git 忽略文件
├── docker-compose.yml                # Docker 编排配置
├── app.py                            # Flask Web 应用
├── requirements.txt                  # Python 依赖
├── README.md                         # 项目主文档
├── dev-log.md                        # 开发日志
├── tech-roadmap-v2.md                # 技术路线图
├── project-plan.md                   # 项目计划
└── PROJECT_STRUCTURE.md              # 本文件
```

---

## 📋 主要变更（2026-03-10 重构）

### **重构前问题**：
- ❌ 根目录有 20+ 个临时脚本文件
- ❌ 6 个 .md 文档散落在根目录
- ❌ 数据文件（27GB）直接在根目录
- ❌ 图片文件在 md-pic/ 目录

### **重构后改进**：
- ✅ 所有脚本按功能分类到 `scripts/` 和 `src/`
- ✅ 文档统一归档到 `docs/guides/`
- ✅ 数据文件移动到 `data/raw/`
- ✅ 图片资源移动到 `assets/`
- ✅ 创建清晰的目录层次

---

## 🎯 各目录用途说明

### **`data/` - 数据目录**
存放所有数据文件，分为：
- `raw/`: 原始数据（不可变，直接从源获取）
- `processed/`: 处理后的数据（可重新生成）
- `external/`: 外部数据源（第三方数据）

**当前内容**：
- NOAA 站点数据：69 个站点，1990-2023 年
- Open-Meteo 网格数据：1.76 亿行，27.43 GB

### **`src/` - 源代码目录**
核心业务逻辑代码：
- `data_processing/`: 数据处理算法（ET0、SPEI 计算等）
- `models/`: 机器学习模型（LSTM、XGBoost 等）
- `visualization/`: 可视化图表生成
- `utils/`: 通用工具函数

### **`scripts/` - 可执行脚本**
一次性或辅助性脚本：
- `migrate/`: 数据迁移（已完成，可保留）
- `analyze/`: 数据分析
- `utility/`: 实用工具（清理、监控、检查）

### **`docs/` - 文档目录**
项目文档集中管理：
- `guides/`: 操作指南、教程
- `specs/`: 技术规格、API 文档
- `reports/`: 实验报告、分析结果

### **`notebooks/` - Jupyter 笔记本**
交互式分析和实验：
- `01_data_exploration/`: 数据探索性分析
- `02_bias_correction/`: 偏差校正实验
- `03_model_training/`: 模型训练和调参

### **`logs/` - 日志文件**
运行时生成的日志：
- `migration.log`: 迁移日志
- `auto_migration.log`: 自动化日志
- `noaa_fetch.log`: 数据爬取日志

---

## 🔧 路径更新注意事项

### **需要更新的引用**：

1. **CSV 文件路径**：
   ```python
   # 旧路径
   CSV_INPUT_PATH = Path("migration_package/grid_weather_data.csv")
   
   # 新路径
   CSV_INPUT_PATH = Path("data/raw/grid_weather_data.csv")
   ```

2. **NOAA 数据路径**：
   ```python
   # 旧路径
   NOAA_DIR = "migration_package/noaa_raw"
   
   # 新路径
   NOAA_DIR = "data/raw/noaa"
   ```

3. **文档引用**：
   ```markdown
   # 旧引用
   [迁移指南](MIGRATION_GUIDE.md)
   
   # 新引用
   [迁移指南](docs/guides/MIGRATION_GUIDE.md)
   ```

---

## ✅ 验证清单

重构完成后已验证：
- [x] Docker 容器正常运行
- [x] PostgreSQL 数据库可连接
- [x] 数据文件完整移动（27.43 GB）
- [x] NOAA 站点数据完整（69 个站点）
- [ ] 脚本路径更新（待完成）
- [ ] 文档链接更新（待完成）

---

## 📝 使用建议

### **日常开发**：
1. 数据文件放在 `data/` 目录
2. 业务逻辑写在 `src/` 目录
3. 一次性脚本放在 `scripts/` 目录
4. 实验性代码使用 `notebooks/` 目录

### **添加新数据**：
```
data/raw/           # 原始数据（只读）
  └── new_source/   # 新数据源
```

### **添加新文档**：
```
docs/guides/        # 操作指南
  └── new_guide.md
```

### **运行脚本**：
```bash
# 迁移脚本
python scripts/migrate/migrate_from_csv.py

# 分析脚本
python scripts/analyze/analyze_csv.py

# 工具脚本
python scripts/utility/check_status.py
```

---

## 🎉 重构完成

项目结构已优化，更加清晰、易维护！

**下一步**：
1. 更新脚本中的路径引用
2. 开始 NOAA 数据处理工作
3. 继续技术路线图中的下一阶段

---

**重构耗时**: 约 45 分钟  
**文件移动**: 约 100+ 个文件  
**目录整理**: 15 个新目录
