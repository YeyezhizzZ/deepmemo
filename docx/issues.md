# DeepMemo 问题记录

## Issue 模板

```md
## N. 标题

**类型**: Bug / 功能 / 技术债 / 调研
**状态**: 待确认 / 待实现 / 进行中 / 已修复 / 已完成

**问题描述**: 一句话说明要解决什么。

**目标**: 希望达到的结果。

**涉及位置**:
- `path/to/file.py` - 简要说明

**决策人**: gzy
**备注**: 可选补充。
```

## 1. 硬编码问题

**类型**: 技术债
**问题描述**: 后端读取文件时存在写死内容，优先检索固定目录结构。

**涉及位置**:

1. `src/routers/diary.py` - `AutoDraftRequest.output_dir` 默认值为 `"diary"`
2. `src/app/core/fs_manager.py` - `scan_directory_tree` 固定扫描 `data/` 下的 `diary/`, `ideas/`, `memory/`, `raw/` 子目录
3. `src/app/core/watcher.py` - 固定监听 `.md` 文件

**确认方案**:

### 1. 配置文件负责系统默认规则

新增 `config/fs_config.yaml`，用于管理知识库文件系统的默认规则，避免后端散落硬编码。

建议配置项：

```yaml
knowledge_base:
  root: data
  visible_dirs:
    - diary
    - ideas
    - memory
    - raw
  allowed_extensions:
    - .md
  default_search_dirs:
    - diary
    - ideas
    - memory
```

用途：
- `root`：知识库根目录，替代代码里写死的 `data/`
- `visible_dirs`：前端文件树默认展示的目录
- `allowed_extensions`：Watcher 和文件读取允许处理的文件类型
- `default_search_dirs`：问答模式自动检索的默认目录范围

**决策人**: gzy
**状态**: 已确认（2026-05-04）


## 2. 没有多轮对话机制

**类型**: 功能
**现状**: 当前问答更接近单轮 RAG，每次请求主要围绕本轮 `user_message` 做路由、检索和回答，没有稳定地把同一会话内的历史消息纳入上下文。

**问题影响**:
- 用户追问“继续展开”“刚才那个文件”“第二点是什么意思”时，后端缺少上一轮语义上下文，容易答非所问
- 对话无法自然沉淀为连续任务，例如连续改稿、连续研究、逐步整理笔记
- Tool 和引用结果只作用于单轮时，后续追问难以复用前文已经建立的上下文

**实现思路**:

### 1. 会话历史作为独立上下文层

后端 `ChatRequest` 继续保留 `session_id`，处理请求时按 `session_id` 从数据库读取最近若干轮消息，构建 conversation history。

建议策略：
- 默认读取最近 6-10 轮用户 / AI 消息
- 只把对话正文、已选工具和必要的引用摘要纳入 history
- 不把完整 citation 原文反复塞入 prompt，避免 token 膨胀
- 历史消息和本轮检索 evidence 分层组织，最终由 AnswerComposer 统一组装

### 2. 多轮追问先做上下文改写
第一次消息不做query rewrite，之后的消息在进入检索前，新增 query rewrite 步骤，把依赖上下文的追问改写成独立问题。

示例：
- 用户追问：`第二点再展开一下`
- 历史上下文：上一轮回答列出了“导出按钮分享链接方案”的三点
- 改写后查询：`导出按钮分享链接方案中的第二点，即后端生成 share_id 和保存会话快照，应该如何实现？`

实现原则：
- 改写结果只用于检索和回答构建，不替换用户原始消息
- 如果用户问题本身完整，不强行改写
- 改写失败时回退到原始 `user_message`

### 3. 短期/长期/会话记忆分层

多轮对话的上下文体系分为三层：

| 记忆类型 | 内容 | 生命周期 |
|----------|------|----------|
| **短期记忆** (conversation_history) | 最近 6-10 轮用户/AI 消息、已选工具、引用摘要 | 当前会话，存数据库 |
| **会话记忆** (session_topic) | 本轮会话主要围绕的主题/目标，在第一轮时写入 | 当前会话，存数据库 |
| **长期记忆** (user.memory) | 用户偏好、项目规则、长期事实，来源于 MEMORY.md | 跨会话，持久化 |

分层策略：
- `conversation_history`：用于追问、省略指代、连续任务
- `session_topic`：第一轮对话后从用户问题和回答提取，贯穿整个会话，帮助理解本轮在解决什么问题
- `session_summary`：会话变长（10轮以上）后生成滚动摘要，用于压缩较早上下文
- `memory`：后续再考虑，不放进本次 MVP

**短期记忆**只保留对话正文和必要引用，不含完整 citation 原文，避免 token 膨胀。

**会话记忆**在第一轮时写入，`session_topic` 可以是"用户询问项目架构"、"用户请求代码审查"等，贯穿整个会话帮助维持上下文一致性。

### 4. 前端先不做复杂交互

MVP 阶段前端保持现有对话 UI，只需要确保每轮请求都带上稳定的 `session_id`。

后续增强：
- 新建对话时生成新的 `session_id`
- 切换历史会话时恢复完整消息列表
- Tool 可以支持 `session` 级固定，但默认仍是 `next_message`
- 在调试模式显示“本轮使用了最近 N 条历史消息”

**涉及位置**:
- `src/routers/chat.py` - 接收请求并根据 `session_id` 调用多轮问答服务
- `src/app/chat/service.py` - 读取会话历史、保存消息、协调 query rewrite 和 answer compose
- `src/ai/query_router.py` 或新增 `src/ai/query_rewriter.py` - 根据历史上下文改写追问
- `src/ai/answer_composer.py` - 组装 history、evidence、本轮问题和最终引用
- `app/src/App.tsx` - 确保请求携带稳定 `session_id`，切换会话时恢复历史消息

**已完成（MVP，2026-05-08）**:
- 后端按 `session_id` 读取会话历史，默认只取最近 20 条消息
- 历史消息进入 prompt 前移除完整引用块，只保留轻量引用摘要
- 新增 `src/ai/query_rewriter.py`，在检索前把多轮追问改写成独立查询
- `KnowledgeQAService` 使用改写后的 `retrieval_query` 做路由、本地检索和外部搜索，用户原始问题仍用于回答展示
- `AnswerComposer` 分层组装原始问题、改写查询、会话历史、本轮 evidence 和外部补充
- 本轮没有新 evidence 时，可以基于会话历史回答追问，并提示没有新增本地引用
- `session` 表新增 `session_topic` 和 `session_summary` 字段，支持会话主题和较早上下文摘要
- 前端 session 类型和 API 映射同步支持 `session_topic` / `session_summary`

**未完成 / 后续增强**:
- `src/app/chat/service.py` 还未拆分，当前会话历史读取、保存和摘要逻辑仍在 `src/routers/chat.py`
- `session_topic` 目前是轻量规则生成，尚未用 LLM 从首轮问答中提取稳定主题
- `session_summary` 目前是轻量滚动摘录，尚未做 LLM 语义摘要和压缩策略
- 历史上下文尚未持久化已选 Tool 元数据，`message` 表还没有 `tool_id` / `metadata_json`
- 长期记忆 `MEMORY.md` / `user.memory` 尚未纳入本次 MVP
- 前端还未支持 `session` 级固定 Tool，也未在调试模式显示“本轮使用了最近 N 条历史消息”

**决策人**: gzy
**状态**: MVP 已完成（2026-05-08），剩余增强待实现


## 3. 工程博客更新自动生成日记

**类型**: 功能
**问题描述**: 目前工程博客链接需要手动查看、摘录和写入日记。希望维护一组工程博客/RSS/网页链接，每天晚上自动判断是否有新内容；如果有更新，就抓取正文、生成摘要，并合并生成当天日记草稿。

**实现思路**:

### 1. 订阅源配置

新增配置文件保存工程博客来源，例如 `config/blog_sources.yaml`。

建议字段：
- `name`：来源名称
- `url`：博客首页、RSS、Atom 或文章列表页
- `type`：`rss` / `atom` / `html` / `sitemap`
- `tags`：如 `engineering`、`ai`、`infra`
- `enabled`：是否启用

### 2. 每晚定时检查更新

新增定时任务服务，默认每天晚上运行一次。

执行流程：
- 读取 `config/blog_sources.yaml`
- 对每个来源调用 `src/ai/web_search_agent.py` 或其 provider 能力获取最新文章列表
- 和本地状态表比对 URL、标题、发布时间或内容 hash
- 只处理未见过或已变化的文章
- 把抓取结果落到 `data/raw/`，保留来源、发布时间、URL 和摘要

### 3. 抓取正文与摘要

优先复用现有 Web Search 能力：
- `WebSearchAgent.extract(urls)`：抓取指定文章正文
- `WebSearchAgent.map(url)`：必要时从站点生成 URL 列表
- Open-WebSearch MCP provider：用于搜索/发现更新
- Tavily API provider：用于 extract/crawl/map 等网页读取能力

摘要输出建议包含：
- 标题
- 原文 URL
- 发布时间或发现时间
- 核心观点
- 对工程实践的启发
- 是否适合写入 `## 工程博客`

### 4. 生成当天日记草稿

在抓取完成后调用现有日记生成链路：
- 如果当天日记不存在，创建 `data/diary/<月日>.md`
- 如果当天日记已存在，只追加或更新 `## 工程博客` 段落
- 条目格式保持当前模板：`[标题](URL)：一句话摘要`
- 原始抓取内容保留在 `data/raw/`，日记中只写精炼摘要

### 5. 去重和可追踪

需要保存抓取状态，避免每天重复写入同一篇文章。

可选方案：
- 新增 SQLite 表，如 `blog_source_state` / `blog_article`
- 或先用 `data/raw/blog_index.json` 做 MVP 状态文件

状态字段建议：
- `source_name`
- `article_url`
- `title`
- `published_at`
- `content_hash`
- `first_seen_at`
- `last_seen_at`
- `diary_path`

**涉及位置**:
- `src/ai/web_search_agent.py` - 复用 web search / extract / crawl / map 能力
- `src/ai/providers/open_websearch.py` - 通过 MCP 搜索或发现更新
- `src/routers/diary.py` - 复用或扩展日记草稿生成能力
- `src/app/database.py` - 可选：新增博客抓取状态表
- `config/blog_sources.yaml` - 新增工程博客订阅源配置
- `data/raw/` - 保存抓取正文和摘要素材
- `data/diary/` - 生成或更新当日日记

**决策人**: gzy
**状态**: 待确认

## 4. 切换为 OpenAI Agent SDK

**类型**: 技术债 / 架构升级
**问题描述**: 当前 DeepMemo 的 chat 模块使用 `openai` Python SDK，主要面向单轮 API 调用。本地知识库的问答助手本质上是 **Agent**——需要 Tool Use、循环推理、多步骤执行，当前架构无法自然支持。

**现状**:
- 当前 chat 模块是典型的单轮 RAG + LLM 调用
- 没有 Tool Use、Function Calling 能力
- 会话管理、Query Rewrite、Answer Compose 等逻辑散落在各处，缺乏统一调度
- 如果要扩展 Agent 能力（如多次检索、反思验证、工具组合），需要重构底层

**目标**: 切换到 `openai-agents` SDK（OpenAI Agent SDK），将 DeepMemo chat 重构为真正的 **Agent** 架构。

**涉及位置**:
- `src/routers/chat.py` - 改为 Agent 入口，暴露 Agent Runner 接口
- `src/app/chat/service.py` - 拆分为 Agent Handler / Tool 定义
- `src/ai/query_router.py` - 作为 Agent Tool 或用于 Routing Agent
- `src/ai/answer_composer.py` - 作为 Agent 输出处理
- `src/ai/web_search_agent.py` - 作为 Agent Tool
- `src/ai/providers/` - 各类 Tool Provider

**实现思路**:

### 1. 安装 openai-agents SDK

```bash
uv add openai-agents
```

### 2. 定义 Agent 和 Tool

核心 Agent（用于知识库问答）：
- `knowledge_agent`：接收用户问题，调用检索工具，返回回答
- 内置 Tool：`retriever`（检索知识库）、`web_search`（网页搜索）、`memory`（读用户偏好）

路由 Agent（决定走哪个流程）：
- 根据用户问题判断是否需要搜索、是否需要生成日记、是否只是闲聊

### 3. 会话状态迁移

现有 `session_id` 机制映射到 Agent SDK 的 Session：
- 每次对话创建一个 `Session`（对应现有 `session_id`）
- 历史消息通过 SDK 的 history 管理，不再手动拼接
- `session_topic` 和 `session_summary` 可以通过 Agent 的 instructions 或 Memory Tool 实现

### 4. 渐进式迁移

MVP 阶段保持现有 API 接口不变，内部替换为 Agent SDK：
- `POST /chat` → 触发 `knowledge_agent.run(user_message, session_id=...)`
- 响应格式保持兼容，前端无感知
- 后续逐步增强 Tool 和 Agent 能力

**决策人**: gzy
**状态**: 待确认
