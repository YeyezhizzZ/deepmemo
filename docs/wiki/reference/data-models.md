# 数据模型

## SQLite

SQLite 保存运行时元数据。路径由 `DEEPMEMO_DB_PATH` 控制，默认是仓库根目录下的 `data.db`。

| Table | 主要字段 | 用途 |
|:---|:---|:---|
| `session` | `session_id`, `session_name`, `message_ids`, `session_topic`, `session_summary`, `created_at`, `updated_at` | 聊天会话 |
| `message` | `message_id`, `session_id`, `role`, `content`, `citations`, `created_at` | 聊天消息与引用 |
| `file_meta` | `id`, `file_path`, `file_hash`, `sync_status`, `last_modified`, `created_at` | 文件追踪与同步状态 |

`message.role` 只能是 `user` 或 `ai`。`file_meta.sync_status` 只能是 `synced`、`dirty`、`draft`、`processing`、`error`。

## Knowledge Card

Knowledge Cards 是 `data/knowledge/cards/{slug}.yaml` 下的结构化 YAML。核心字段：

| Field | Description |
|:---|:---|
| `id`, `slug`, `title` | 稳定身份和标题 |
| `type` | `entity`、`concept`、`decision`、`pattern`、`lesson` |
| `density` | `high`、`medium`、`low` |
| `definition`, `key_facts` | 定义和关键事实 |
| `sources` | 来源路径、证据摘要和置信度 |
| `related_cards` | 关联 Card slug |
| `tags` | 标签 |
| `aliases` | 别名 |
| `created_at`, `updated_at`, `update_count` | 生命周期元数据 |
| `staleness_score` | 陈旧度评分 |
| `human_edited`, `human_edited_fields` | 人工编辑及字段保护状态 |

## AI Pipeline 类型

问答流水线中的核心概念包括：

| 类型 | 作用 |
|:---|:---|
| `RouteDecision` | QueryRouter 输出的搜索范围和 Web fallback 判断 |
| `LocalSearchResult` | 本地检索结果、证据和置信度 |
| `SearchEvidence` | 单条可引用证据 |
| `KnowledgeAnswer` | 最终答案、证据和流式 chunk |

这些类型不等同于公共 API 合约。修改时应优先看 current specs 和 tests，而不是把内部字段当长期稳定接口。
