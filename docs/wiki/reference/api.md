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

## Knowledge

| Method | Path | Description |
|:---|:---|:---|
| GET | `/api/knowledge/cards` | 列出 Knowledge Cards，可按类型或标签过滤 |
| GET | `/api/knowledge/cards/{slug}` | 获取单张 Card |
| PUT | `/api/knowledge/cards/{slug}` | 更新 Card 并保护人工编辑字段 |
| DELETE | `/api/knowledge/cards/{slug}` | 删除 Card |
| POST | `/api/knowledge/compile` | 编译全部支持的 Markdown |
| POST | `/api/knowledge/compile/file` | 编译指定 Markdown |
| POST | `/api/knowledge/compile/commit` | 从 Git commit 编译知识 |
| POST | `/api/knowledge/search` | 检索 Cards |
| GET | `/api/knowledge/stats` | 获取索引统计 |
| GET | `/api/knowledge/health` | 获取健康状态 |
| POST | `/api/knowledge/maintain` | 执行确定性维护 |
| POST | `/api/knowledge/repowiki/rebuild` | 从 Cards 重建 RepoWiki |
| GET | `/api/knowledge/repowiki/pages` | 列出 RepoWiki 页面 |
| GET | `/api/knowledge/repowiki/pages/{slug}` | 获取 RepoWiki 页面 |
| GET | `/api/knowledge/view` | 获取 Knowledge 前端 ViewModel |
| GET | `/api/knowledge/view/pages/{slug}` | 获取结构化只读页面 |
| GET | `/api/knowledge/view/review` | 获取审阅队列 |
| POST | `/api/knowledge/view/review/{item_id}/confirm` | 确认审阅项 |
| POST | `/api/knowledge/view/review/{item_id}/hide` | 隐藏审阅项 |
| POST | `/api/knowledge/view/review/{item_id}/rewrite` | 请求重写审阅项 |
| POST | `/api/knowledge/view/review/{item_id}/apply` | 应用重写结果 |
| POST | `/api/knowledge/view/cards/{slug}/pin` | 固定 Card 字段 |

## Pulse

| Method | Path | Description |
|:---|:---|:---|
| GET | `/api/pulse/today` | 聚合今日视图 |

## Deprecated

旧 `/wiki/*` 路由未挂载，主应用应返回 404。`/api/diary/auto-draft` 仍可在历史代码中看到，但它已在 `docs/specs/deprecated.md` 中被标记为废弃占位接口。不要在新代码或新工作流中依赖这些接口。
