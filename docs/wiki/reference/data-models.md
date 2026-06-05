# 数据模型

## SQLite

SQLite 保存运行时元数据。路径由 `DEEPMEMO_DB_PATH` 控制，默认是仓库根目录下的 `data.db`。

| Table | 主要字段 | 用途 |
|:---|:---|:---|
| `session` | `session_id`, `session_name`, `message_ids`, `session_topic`, `session_summary`, `created_at`, `updated_at` | 聊天会话 |
| `message` | `message_id`, `session_id`, `role`, `content`, `citations`, `created_at` | 聊天消息与引用 |
| `file_meta` | `id`, `file_path`, `file_hash`, `sync_status`, `last_modified`, `created_at` | 文件追踪与同步状态 |

`message.role` 只能是 `user` 或 `ai`。`file_meta.sync_status` 只能是 `synced`、`dirty`、`draft`、`processing`、`error`。

## Wiki Frontmatter

Wiki 页面是带 frontmatter 的 Markdown。常见字段：

| Field | Description |
|:---|:---|
| `title` | 页面标题 |
| `type` | `source`、`entity`、`concept`、`synthesis`、`query` |
| `status` | `draft`、`active`、`archived` 等 |
| `tags` | 标签 |
| `sources` | 来源文件或页面 |
| `related` | 相关页面 |
| `aliases` | 别名 |
| `confidence` | 生成或合并置信度 |
| `last_updated` | 更新时间 |

## AI Pipeline 类型

问答流水线中的核心概念包括：

| 类型 | 作用 |
|:---|:---|
| `RouteDecision` | QueryRouter 输出的搜索范围和 Web fallback 判断 |
| `LocalSearchResult` | 本地检索结果、证据和置信度 |
| `SearchEvidence` | 单条可引用证据 |
| `KnowledgeAnswer` | 最终答案、证据和流式 chunk |

这些类型不等同于公共 API 合约。修改时应优先看 current specs 和 tests，而不是把内部字段当长期稳定接口。
