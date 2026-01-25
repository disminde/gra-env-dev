# 数据库操作指南 (Database Guide)

## 1. 简介
本项目使用 PostgreSQL 16 作为核心数据库，通过 Docker 容器化部署，确保开发环境与生产环境的一致性。

## 2. 快速开始

### 2.1 启动数据库
确保已安装 Docker Desktop 并启动。

在项目根目录下运行：
```powershell
# 启动所有服务（后台运行）
docker-compose up -d

# 查看运行状态
docker-compose ps
```

### 2.2 停止数据库
```powershell
# 停止容器
docker-compose down

# 停止并删除数据卷（慎用！会丢失数据）
docker-compose down -v
```

## 3. 配置说明

### 3.1 环境变量 (.env)
数据库连接配置位于 `.env` 文件中。首次使用请复制 `.env.example`：
```bash
cp .env.example .env
```

| 变量名 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `POSTGRES_USER` | `admin` | 数据库超级管理员用户名 |
| `POSTGRES_PASSWORD` | `secure_password_dev` | 管理员密码（生产环境请修改） |
| `POSTGRES_DB` | `gra_env_db` | 默认创建的数据库名称 |
| `POSTGRES_PORT` | `5432` | 宿主机映射端口 |
| `TZ` | `Asia/Shanghai` | 容器时区 |

### 3.2 初始化脚本
初始化 SQL 脚本位于 `docker/postgres/init/` 目录。容器首次启动时会按文件名顺序自动执行该目录下的 `.sql` 文件。
- `01-init.sql`: 设置时区，创建扩展，创建健康检查表。

## 4. 连接验证

### 4.1 使用 Python 脚本测试
我们提供了一个 Python 脚本来验证数据库连接和基本查询功能。

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 运行测试：
   ```bash
   python tests/test_db_connection.py
   ```
   如果输出 `✅ Connection to PostgreSQL DB successful`，则说明配置成功。

### 4.2 使用数据库客户端
你可以使用 DBeaver, pgAdmin 或 Navicat 连接：
- **Host**: `localhost`
- **Port**: `5432`
- **Database**: `gra_env_db`
- **Username**: `admin`
- **Password**: `secure_password_dev`

## 5. 常见问题

**Q: 端口 5432 被占用？**
A: 修改 `.env` 文件中的 `POSTGRES_PORT` 变量，例如改为 `5433`，然后重启容器。

**Q: 如何查看数据库日志？**
A: 运行 `docker-compose logs -f db`。
