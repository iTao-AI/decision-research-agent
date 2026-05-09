# Spec: API 安全配置

## 描述

API 服务器必须正确配置 CORS 策略和异步任务错误处理。

## 需求

### REQ-1: CORS 限制

**Given** 前端运行在 `http://localhost:5173`  
**When** 前端发送请求到后端 API  
**Then** 请求必须被允许（同源或配置的源）

**Given** 一个第三方网站 `http://evil.com`  
**When** 发送跨域预检请求（OPTIONS）到后端 API  
**Then** 请求必须被拒绝，返回 403 或不含 `Access-Control-Allow-Origin` 头

### REQ-2: 异步任务错误处理

**Given** 一个 Agent 任务执行失败  
**When** `run_deep_agent` 抛出异常  
**Then** 异常必须被记录到 task 字典中  
**And** 异常信息必须可通过日志查询（console 输出）  
**And** WebSocket 连接必须收到 error 事件  
**Note**: 新增 `/api/task/{thread_id}/status` 端点不属于 Phase 0 范围，将在后续 Phase 实现

### REQ-3: 边界场景 - CORS 环境变量缺失

**Given** `.env` 中未配置 `FRONTEND_ORIGIN`  
**When** 后端启动  
**Then** 系统必须使用默认值 `http://localhost:5173`（开发环境）  
**And** 必须在日志中输出警告："FRONTEND_ORIGIN 未配置，使用默认值"

### REQ-4: 边界场景 - 并发任务错误

**Given** 两个 Agent 任务同时执行  
**When** 第一个任务失败，第二个任务成功  
**Then** 两个任务的错误状态必须独立记录  
**And** 不得互相覆盖
