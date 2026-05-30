## Why

当前项目无任何容器化方案，部署依赖本地手动配置 Python 3.11+、Node.js 18+、MySQL 及 weasyprint 系统依赖（cairo/pango）。新机器/新开发者环境搭建成本高且不可复现。通过 Docker Compose 实现一键部署，消除环境差异。

## What Changes

- 新增 `Dockerfile.backend` — Python 3.11-slim 镜像，安装 weasyprint 系统依赖 + pip 依赖
- 新增 `Dockerfile.frontend` — 多阶段构建（Node 22 → Nginx 静态托管）
- 新增 `docker-compose.yml` — 编排 3 个服务：backend（8000）、frontend（80）、mysql（3306）
- 新增 `.dockerignore` — 排除 .venv、node_modules、.git、测试文件等
- Nginx 配置反向代理 `/api/` 和 `/ws/` 到 backend，统一端口消除 CORS

## Capabilities

### New Capabilities

- `docker-deployment`: 通过 Docker Compose 一键启动后端、前端、MySQL 的容器化部署方案

### Modified Capabilities

<!-- 纯基础设施新增，不修改任何现有能力的需求 -->

## Impact

- **新增文件**: Dockerfile.backend、Dockerfile.frontend、docker-compose.yml、.dockerignore
- **不影响**现有代码逻辑、API 端点、Agent 行为、测试
- **回归风险**: 无 — 纯新增基础设施
- **环境变量**: 通过 `.env` 注入，与现有 `.env.example` 完全兼容
