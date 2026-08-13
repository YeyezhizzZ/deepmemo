# DeepMe Temporary Workspace

* **Status**: Proposed

## 1. Context

DeepMe 已能基于作者公开 scope 问答。MVP 还需要让匿名访客上传 Markdown、TXT 或 PDF，在24小时临时空间内问答，并保证文件、索引、会话和引用不进入公开知识库。

## 2. Intended Behavior

- 匿名访客可以创建一个或多个临时 workspace。
- 每个 workspace 对应一个 temporary scope，并绑定访客 `owner_key`。
- 上传接口流式写盘，限制文件数、单文件大小和总大小。
- Worker 异步解析文件并构建不可变知识版本。
- Markdown 和 TXT 保留行号，PDF 保存页码映射。
- 问答只能读取 workspace 当前 ready 版本。
- 新文件处理失败时保留旧 ready 版本。
- 主动删除先阻断访问，再由 Worker 删除文件、索引、会话和消息。
- 到期 workspace 使用同一删除流程。

## 3. API Contract

- `POST /api/v1/workspaces`
- `GET /api/v1/workspaces/{workspace_id}`
- `POST /api/v1/workspaces/{workspace_id}/files`
- `DELETE /api/v1/workspaces/{workspace_id}`
- `GET /api/v1/workspaces/{workspace_id}/deletion`
- `POST /api/v1/sessions`，temporary 模式要求有效 workspace

无权访问统一返回404。processing 状态问答返回409。expired 状态返回410。

## 4. Alternative Approaches

同步解析会让上传请求长时间占用 API，并放大异常 PDF 的影响。外部任务队列会增加 Redis 和部署成本。MVP 使用 SQLite job 表和单 Worker。

## 5. Risks & Dependencies

- 依赖 `python-multipart` 和 `pypdf`。
- 文件内容会发送给配置的模型服务，前端必须明确提示。
- Worker 必须可重复执行任务，进程重启后不能丢失状态。
- 路径、文件名、符号链接和 PDF 资源使用需要单独防护。
