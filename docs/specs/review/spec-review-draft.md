# Spec Review Draft

## 0. Purpose

* 这是从当前代码库反推得到的 spec recovery draft
* 它不是最终 spec
* 它已完成人工 review (2026-06-04)
* 当前代码中经确认的 A 类行为将作为后续基线 Spec 的基础。

## 1. Classification Rules

### A: Implemented and Accepted
已经实现，并且可能是应该保留的核心行为。但最终仍需 Human Review 确认。

### B: Implemented but Uncertain
已经实现，但设计质量、产品意图、长期维护价值不确定。这类内容不能直接进入正式 current spec。它们需要进入 open questions 或 refactor candidates。

### C: Proposed or Missing
当前未完整实现，但从 TODO、UI、命名、文档、代码结构或产品方向中可以看出未来可能需要。这类内容只能作为 proposed spec 候选，不能声称已经实现。

### D: Deprecated or Accidental
已经实现，但可能是临时代码、废弃逻辑、重复逻辑、dead code、实验代码或 vibe coding 产生的偶然结果。这类内容后续可能应该删除或忽略。

### Unknown
证据不足，无法判断。

## 2. Feature Inventory

| Feature | Observed Behavior | Evidence | Confidence | Suggested Category | Risk / Notes |
| ------- | ----------------- | -------- | ---------- | ------------------ | ------------ |
| File System Watcher | 通过 Watchdog 监听 `data/` 下的 `.md` 文件，利用 MD5 判断修改，写入 `data.db` 标记 `dirty` | `src/app/core/watcher.py` | High | A | 依赖外部事件，需确保重启或漏扫时的可靠性 |
| Asset Manager | 接收图片上传，依据 markdown 路径决定 assets 存放位置，返回 Vditor 格式 | `src/app/core/asset_manager.py` | High | A | 10MB 限制硬编码 |
| Query Routing | 基于硬编码关键词（`今天`, `ideas`, `memory`, `mock`）决定检索范围及是否使用 Web Search | `src/ai/query_router.py` | High | A | 人工已确认：`mock` 逻辑需保留，用于 Github 展示 |
| AI Chat & RAG | SSE 流式回复，经过改写、路由、本地检索（及 Web 降级）、生成，附带本地文件引用 | `src/ai/service.py` | High | A | Web Search 仅在需要且 Local Search 信心不足时触发 |
| Chat Tools (Skills) | 加载 `.agents/skills/` 执行，支持 `hv-analysis` 等工具注入系统 Prompt。 | `src/ai/chat_tools.py` | High | B | MVP 注明“不会自动执行脚本”，部分功能未实现 |
| Wiki Graph | 生成复杂的双链 Wiki 图谱，包含 PageRank 变种、社区发现 (Louvain) 和桥接节点检测 | `src/wiki/graph.py` | High | A | |
| Wiki Ingestion | 支持增量构建，使用文件 MD5 缓存、LLM 解析提取实体/概念、及 FILE 块生成输出 | `src/wiki/ingest_pipeline.py` | High | A | |
| Blog Fetcher | 抓取微信公众号/RSS 并解析正文，用 LLM 总结成 JSON，是个巨大的单文件 CLI 工具 | `src/app/core/blog_fetcher.py` | High | B | 人工确认暂不重构 |
| Diary Auto-Draft | API 路由存在，读取 `data/raw/` 但直接返回占位字符串并标注 "LLM integration pending" | `src/routers/diary.py` | High | D | 人工确认：废弃并删除 |
| Monolithic Frontend | `App.tsx` 管理所有会话、文件树、编辑状态和 UI 渲染，长达近 3000 行 | `app/src/App.tsx` | High | B | 人工确认暂不重构，等待 spec 稳定 |
| AI Hot Agent | 独立的新闻聚合器，请求外部 API 并在 `data/raw/` 生成每日 AI 新闻 Markdown | `src/ai/ai_hot_agent.py` | High | B | 内部存在 `sys.path` hack，更像独立脚本 |
| Web Search Agent | 提供 Open-WebSearch 和 Tavily Provider。但 `extract/crawl/map` 方法硬编码直连 Tavily | `src/ai/web_search_agent.py` | High | B | 人工确认：技术选型未定，维持现状 |

## 3. Detailed Review Items

### Feature: Backend Route & Model Duplication (Dead Code & Accidental Redundancy)
#### Observed Behavior
系统后端出现了大量的重复代码和未挂载的路由：
1. `src/routers/session.py` 完整定义了 Session CRUD 路由，但**从未被 `main.py` 挂载**。相反，`main.py` 自己重复实现了一遍 `/sessions` 的所有 CRUD 端点。
2. 基础 Pydantic Models 同时在 `src/models/schemas.py` 和 `main.py` 中被定义了两次。
3. 获取 DB 连接的方法 `get_db_connection` 被复制粘贴在多处。
#### Suggested Category
D (Deprecated or Accidental)
#### Human Review
* Final Category: **D**
* Product intent confirmed: 应当作为代码清理项目（`legacy-cleanup`）优先解决。

---

### Feature: Query Routing
#### Observed Behavior
使用硬编码的词汇表包含 `mock_terms` 进行路由。
#### Suggested Category
A (已从 B 晋升)
#### Human Review
* Final Category: **A**
* Product intent confirmed: 保留，因为要传到 Github 给别人看，这部分数据是做展示的。

---

### Feature: Web Search Agent & Provider Abstraction
#### Observed Behavior
系统实现了 Provider 模式，但在高级功能中绕过了抽象硬编码连入 Tavily。
#### Suggested Category
B
#### Human Review
* Final Category: **B**
* Product intent confirmed: 这个还没做好，技术选型也没定。保留现状。

---

### Feature: Blog Fetcher & Monolithic Frontend App
#### Observed Behavior
这两个模块极其庞大且逻辑耦合严重。
#### Suggested Category
B
#### Human Review
* Final Category: **B**
* Product intent confirmed: 先不管，我想确定 spec 后再重构。

---

### Feature: Diary Auto-Draft
#### Observed Behavior
未实现的 LLM integration pending 占位符接口。
#### Suggested Category
D (已从 C 降级)
#### Human Review
* Final Category: **D**
* Product intent confirmed: 删掉。

## 4. Cross-cutting Concerns

* **死代码与重复代码 (Dead Code & Duplication)**: (将被 `legacy-cleanup` 处理)
* **抽象泄漏 (Abstraction Leakage)**: 在 `Web Search Agent` 中维持现状。
* **概念边界模糊 (Boundary Unclear)**: Wiki 与 LocalSearch 依然平行演进，暂不处理。

## 5. Next Steps (Confirmed)

1. **执行清理 (Execution)**: 发起 `legacy-cleanup` 的 OpenSpec 提案，目标是删除 D 类代码（Diary Auto-Draft 路由、重复的 Session 路由、重复的 Schemas）。
2. **沉淀基线 Spec (Documentation)**: 基于已确认为 A 类的行为，生成系统当前的 Canonical Behavior Specs 存入 `openspec/specs/`。
