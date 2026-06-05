# REST API

后端入口是 `src/app/main.py` 中的 FastAPI app，默认监听 `http://localhost:8000`。前端开发时由 Vite 代理转发 API 请求。

## Sessions

| Method | Path | Description |
|:---|:---|:---|
| POST | `/sessions` | 创建新会话 |
| GET | `/sessions` | 按创建时间倒序列出会话 |
| GET | `/sessions/{session_id}` | 获取单个会话 |
| DELETE | `/sessions/{session_id}` | 删除会话及其消息 |

## Chat

| Method | Path | Description |
|:---|:---|:---|
| POST | `/chat/` | 同步问答，保存用户消息和 AI 消息 |
| POST | `/chat/stream` | SSE 流式问答，事件类型为 `token`、`done`、`error` |
| GET | `/chat/{session_id}/messages` | 获取某会话消息 |
| GET | `/chat/tools` | 列出可用聊天工具 |
| GET | `/chat/file-references` | 查询引用指定文件的消息 |
| GET | `/api/chat/file-references` | 查询引用指定文件的消息，带 data-relative 路径规范化 |
| GET | `/api/chat/citations` | 获取消息引用详情 |

## File System

这些接口只面向 `data/` 根目录内的内容。

| Method | Path | Description |
|:---|:---|:---|
| GET | `/api/fs/tree` | 获取 `data/` 文件树 |
| GET | `/api/fs/content` | 读取文件内容 |
| POST | `/api/fs/write` | 写入 Markdown 并更新 `file_meta` |
| POST | `/api/fs/move` | 移动或重命名文件 |
| PATCH | `/api/fs/sync-status` | 更新同步状态 |
| POST | `/api/fs/create-file` | 创建新文件 |
| POST | `/api/fs/create-directory` | 创建新目录 |
| POST | `/api/fs/upload-asset` | 上传图片资源，返回 Vditor 格式 JSON |

## Wiki

| Method | Path | Description |
|:---|:---|:---|
| GET | `/wiki/tree` | 获取 Wiki 文件树 |
| GET | `/wiki/graph` | 获取知识图谱 |
| GET | `/wiki/health` | 获取健康报告 |
| POST | `/wiki/rebuild` | 重建 Wiki，body 支持 `{ "clean": false }` |
| POST | `/wiki/ingest` | 对单个源文件执行 ingest |
| GET | `/wiki/pages` | 列出 Wiki 页面，可用 `page_type` 过滤 |
| GET | `/wiki/page` | 读取单个 Wiki 页面 |
| POST | `/wiki/page` | 创建 Wiki 页面 |
| PUT | `/wiki/page` | 覆盖写入 Wiki 页面 |
| DELETE | `/wiki/page` | 删除 Wiki 页面 |
| POST | `/wiki/move` | 移动 Wiki 路径 |
| POST | `/wiki/directory` | 创建 Wiki 目录 |
| GET | `/wiki/policy` | 获取策略包 |

## Pulse

| Method | Path | Description |
|:---|:---|:---|
| GET | `/api/pulse/today` | 聚合今日视图 |

## Deprecated

`/api/diary/auto-draft` 仍可在历史代码中看到，但它已在 `docs/specs/deprecated.md` 中被标记为废弃占位接口。不要在新代码或新工作流中依赖它。
