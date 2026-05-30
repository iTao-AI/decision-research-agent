## Context

当前项目无任何容器化方案，部署依赖本地环境手动配置 Python、Node.js、MySQL 及 weasyprint 系统依赖。项目由 FastAPI 后端（端口 8000）和 Vue 3 前端（Vite 开发服务器，端口 5173）组成，通过 REST API + WebSocket 通信。

## Goals / Non-Goals

**Goals:**
- 通过 `docker compose up` 一键启动后端、前端、MySQL
- 前端通过 Nginx 托管静态文件并反向代理 API 到后端，统一端口（80）访问
- MySQL 数据通过 named volume 持久化
- 所有配置通过 `.env` 环境变量注入，与现有 `.env.example` 兼容

**Non-Goals:**
- 开发热重载（后续可通过 docker-compose.dev.yml 叠加）
- CI/CD 流水线（GitHub Actions 构建发布）
- RAGFlow 容器化（外部服务，独立部署）
- HTTPS/TLS 配置（生产环境考虑）
- 生产级监控/日志聚合

## Decisions

### 1. 基础镜像选择

| 决策 | 选择 | 理由 |
|------|------|------|
| 后端基础 | `python:3.11-slim` | 体积小（~150MB），与项目 Python 版本精确对齐 |
| 前端构建 | `node:22-alpine` | 轻量构建环境，rolldown-vite 需要 Node 22+（`styleText` export） |
| 前端运行 | `nginx:alpine` | 最小化运行时镜像（~40MB），原生支持反向代理 |
| MySQL | `mysql:8.0` | 官方镜像，与 `.env.example` 兼容 |

### 2. Nginx 反向代理 vs CORS

选择 Nginx 反向代理 `/api/` 和 `/ws/` 到 backend:8000，而非配置 CORS。理由：
- 统一端口（80）消除浏览器跨域限制
- 减少后端 CORS 配置复杂度
- 生产环境标准做法

### 3. weasyprint 系统依赖

weasyprint 需要 cairo/pango/glib 等系统库。在 `Dockerfile.backend` 中通过 `apt-get` 安装，而非改用其他 PDF 方案。理由：
- Phase 6A 已选定 weasyprint 作为跨平台 PDF 方案
- Docker 中安装系统依赖比本地环境更可控

### 4. 单 compose vs 多 compose 文件

首次使用单 `docker-compose.yml`，而非 dev/prod 双配置。理由：
- 最小化文件数量，降低维护成本
- 开发热重载需求后续可通过 overlay 文件叠加

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| `python:3.11-slim` 缺少 weasyprint 系统依赖 | Dockerfile 中显式安装 libcairo2-dev, libpango1.0-dev, libglib2.0-dev, gcc |
| MySQL 首次启动慢（初始化数据目录 ~30s） | `depends_on` 不保证 MySQL ready，后端应有连接重试逻辑（现有代码已处理） |
| 前端静态文件构建后无法热更新 | 开发环境仍用 `npm run dev`（本地 Node.js），Docker 用于生产部署 |
| Nginx 代理 WebSocket 需要特殊 headers | nginx.conf 中配置 `Upgrade` 和 `Connection` headers |
| `.env` 文件未创建时容器可启动但后端报错 | 文档中明确 `.env` 为前置条件，从 `.env.example` 复制 |
