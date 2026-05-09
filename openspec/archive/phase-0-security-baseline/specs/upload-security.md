# Spec: 文件上传安全

## 描述

文件上传接口必须防止路径遍历攻击，确保文件只能保存到目标目录内。

## 需求

### REQ-1: 文件名净化

**Given** 一个文件上传请求  
**When** 服务端接收文件时  
**Then** 系统必须使用 `Path(file.filename).name` 提取纯文件名  
**And** 拒绝包含路径分隔符的原始文件名

### REQ-2: 路径遍历防御

**Given** 一个恶意文件名 `../../../etc/passwd`  
**When** 调用 `POST /api/upload`  
**Then** 文件必须被保存为 `passwd`（或拒绝请求）  
**And** 文件必须保存到目标目录 `updated/session_{thread_id}/` 内  
**And** 不得在目标目录外创建任何文件

**Given** 一个包含绝对路径的文件名 `/etc/shadow`  
**When** 调用 `POST /api/upload`  
**Then** 文件必须被保存为 `shadow`（或拒绝请求）

### REQ-3: 边界场景 - 空文件名

**Given** 一个空文件名的上传请求  
**When** 调用 `POST /api/upload`  
**Then** 系统必须返回 400 错误："文件名不能为空"

**Given** 一个纯分隔符的文件名 `../`  
**When** 调用 `POST /api/upload`  
**Then** 系统必须返回 400 错误："无效的文件名"

### REQ-4: 边界场景 - 超长文件名

**Given** 一个文件名超过操作系统限制（255 字符）的上传请求  
**When** 调用 `POST /api/upload`  
**Then** 系统必须返回 400 错误："文件名过长"  

**Note**: 文件名冲突处理（时间戳重命名）属于 UX 功能，不属于 Phase 0 安全修复范围，将在后续 Phase 实现。
