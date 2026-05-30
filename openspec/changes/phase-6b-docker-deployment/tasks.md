## 1. 后端 Dockerfile

- [x] 1.1 创建 `Dockerfile.backend` — python:3.11-slim 基础镜像 + 工作目录 /app
- [x] 1.2 安装 weasyprint 系统依赖：libglib2.0-dev, libpango1.0-dev, libcairo2-dev, gcc
- [x] 1.3 复制 requirements.txt 并执行 pip install --no-cache-dir
- [x] 1.4 复制项目源码，暴露端口 8000，配置 uvicorn 启动命令
- [x] 1.5 构建验证：`docker build -f Dockerfile.backend -t deep-search-backend .` 成功

## 2. 前端 Dockerfile + Nginx 配置

- [x] 2.1 创建 `nginx.conf` — 静态文件托管 + `/api/` 和 `/ws/` 反向代理到 backend:8000
- [x] 2.2 创建 `Dockerfile.frontend` — 多阶段构建：node:22-alpine 构建 + nginx:alpine 运行
- [x] 2.3 构建验证：`docker build -f Dockerfile.frontend -t deep-search-frontend .` 成功

## 3. Docker Compose 编排

- [x] 3.1 创建 `docker-compose.yml` — 定义 backend、frontend、mysql 三服务
- [x] 3.2 配置 MySQL 服务：mysql:8.0 镜像 + named volume mysql_data + 环境变量
- [x] 3.3 配置服务间依赖和端口映射：backend:8000, frontend:80, mysql:3306

## 4. 构建忽略规则

- [x] 4.1 创建 `.dockerignore` — 排除 .venv, node_modules, .git, __pycache__, .env, .claude, tests, output, updated

## 5. 端到端验证（需 Docker daemon 运行后验证）

- [x] 5.1 从 `.env.example` 复制 `.env`，配置必要变量
- [x] 5.2 执行 `docker compose up -d`，确认 3 个服务全部 running
- [x] 5.3 访问 `http://localhost:80` 验证前端页面正常渲染
- [x] 5.4 验证 Nginx 代理 API：`curl http://localhost/api/task` 返回后端响应
- [x] 5.5 验证 MySQL 连接：后端日志无数据库连接错误
- [x] 5.6 验证数据持久化：`docker compose down && docker compose up -d` 后 MySQL 数据不丢失
