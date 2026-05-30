## ADDED Requirements

### Requirement: Backend Dockerfile 构建
后端镜像 MUST 使用 `python:3.11-slim` 作为基础镜像，安装 weasyprint 系统依赖，并通过 `pip install --no-cache-dir -r requirements.txt` 安装 Python 依赖。启动命令为 `uvicorn api.server:app --host 0.0.0.0 --port 8000`。

#### Scenario: 成功构建后端镜像
- **WHEN** 执行 `docker build -f Dockerfile.backend -t deep-search-backend .`
- **THEN** 镜像构建成功，uvicorn 在容器内监听 8000 端口

#### Scenario: weasyprint 系统依赖缺失导致构建失败
- **WHEN** Dockerfile 中未安装 cairo/pango 系统依赖
- **THEN** `pip install weasyprint` 或 `import weasyprint` 失败，构建报错

### Requirement: Frontend Dockerfile 多阶段构建
前端镜像 MUST 使用多阶段构建：第一阶段 `node:22-alpine` 执行 `npm ci && npm run build`，第二阶段 `nginx:alpine` 托管构建产物。Nginx MUST 配置反向代理 `/api/` 和 `/ws/` 到 `backend:8000`。

#### Scenario: 成功构建前端镜像
- **WHEN** 执行 `docker build -f Dockerfile.frontend -t deep-search-frontend .`
- **THEN** 镜像构建成功，Nginx 在容器内监听 80 端口，静态文件可访问

#### Scenario: Nginx 正确代理 API 请求到后端
- **WHEN** 浏览器访问 `http://localhost/api/task`
- **THEN** 请求被 Nginx 代理到 `backend:8000/api/task`，返回后端响应

#### Scenario: Nginx 正确代理 WebSocket 连接到后端
- **WHEN** 浏览器建立 `ws://localhost/ws/{thread_id}` 连接
- **THEN** WebSocket 连接被 Nginx 代理到 `backend:8000/ws/{thread_id}`，Upgrade headers 正确传递

#### Scenario: 前端构建失败（package.json 格式错误）
- **WHEN** package.json 存在语法错误
- **THEN** `npm ci` 阶段失败，Docker 构建中止并输出 npm 错误信息

### Requirement: Docker Compose 服务编排
`docker-compose.yml` MUST 定义 3 个服务：backend、frontend、mysql。所有服务使用默认 bridge 网络互通。MySQL MUST 使用 named volume `mysql_data` 持久化数据。

#### Scenario: 一键启动所有服务
- **WHEN** 执行 `docker compose up -d`
- **THEN** 3 个服务全部启动，`docker compose ps` 显示 backend/frontend/mysql 均为 running 状态

#### Scenario: 访问前端页面
- **WHEN** 浏览器访问 `http://localhost:80`
- **THEN** 返回 Vue 前端构建产物，页面正常渲染

#### Scenario: 后端可连接 MySQL
- **WHEN** 后端服务启动
- **THEN** 后端通过环境变量中的 MySQL_HOST=mysql 成功连接到 MySQL 容器

#### Scenario: MySQL 数据持久化
- **WHEN** 执行 `docker compose down && docker compose up -d`
- **THEN** MySQL 数据通过 `mysql_data` volume 恢复，已创建的数据不丢失

#### Scenario: 端口冲突
- **WHEN** 主机端口 80、8000 或 3306 已被其他进程占用
- **THEN** `docker compose up` 失败并提示端口冲突错误

#### Scenario: .env 缺失关键环境变量
- **WHEN** `.env` 文件不存在或缺少 OPENAI_API_KEY 等关键变量
- **THEN** 容器正常启动，但后端在处理需要 LLM 的请求时返回错误

### Requirement: .dockerignore 排除规则
`.dockerignore` MUST 排除构建无关文件：`.venv/`、`node_modules/`、`.git/`、`__pycache__/`、`.env`、`.claude/`、`tests/`、`output/`、`updated/`。

#### Scenario: 构建上下文不包含排除文件
- **WHEN** 执行 `docker build` 并查看构建日志中的上下文大小
- **THEN** 构建上下文不包含 .venv、node_modules、.git 等排除目录

#### Scenario: .env 不被打包进镜像
- **WHEN** 容器运行时检查镜像内文件
- **THEN** 镜像内不包含 `.env` 文件（配置通过 docker-compose environment 注入）
