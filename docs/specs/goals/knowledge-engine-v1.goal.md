# Knowledge Engine v1

> **Status**: Implemented
> **Source Design**: `docs/design/knowledge-engine-v1.md`

## 1. Goal
实现 DeepMemo 自迭代知识引擎 v1：以 YAML Knowledge Card 为 Agent 检索中间层，并让 Markdown、Chat、RAG、Watcher、维护任务和前端管理界面形成闭环。

## 2. Why this goal matters
旧 Wiki 直接从 Diary 生成页面，既服务人类阅读又服务 Agent 检索，结构化程度不足且维护链路割裂。Knowledge Engine v1 把知识先编译成可索引、可合并、可人工编辑的 Cards，再作为 RAG evidence 和前端管理真值，降低重复提取和上下文检索成本。

## 3. Related Specs
* **Current Specs**: `constitution.md`, `current/knowledge-engine.md`, `current/wiki-ingestion.md`, `current/wiki-graph.md`, `current/ai-chat-rag.md`, `current/query-routing.md`, `current/fs-watcher.md`, `current/test-infrastructure.md`
* **Design Draft**: `docs/design/knowledge-engine-v1.md`
* **Conflict Resolution**: 本 Goal 已获人工确认，以 Knowledge Engine v1 当前设计覆盖旧 Wiki/current spec 中未维护的冲突行为。

## 4. Desired Behavior
* Markdown 来源 `data/diary/` 与 `data/raw/` 可编译为 `data/knowledge/cards/{slug}.yaml`。
* `data/knowledge/index.json` 维护 Card、tag、type 和统计索引。
* Chat 对话在达到提取阈值时写入 `raw/conversations/` 并沉淀 decision/lesson/pattern/concept Card。
* LocalSearch 在 ripgrep 前先查 Knowledge Cards，并把 Card 内容作为 evidence 返回。
* Watcher 在 diary/raw Markdown 变更后防抖触发 Card 增量编译。
* Knowledge maintenance 更新 staleness、孤儿 Card、冲突和合并建议。
* 前端提供 Knowledge Card 列表、搜索、详情、编辑、编译和维护入口。
* 旧 Wiki 前端模式和 `/wiki/*` 主应用路由不再作为产品面。

## 5. Non-goals
* 不引入向量检索；v1 维持关键词/BM25-lite/Card index 检索。
* 不强制默认 LLM 编译；默认启发式，`DEEPMEMO_KNOWLEDGE_USE_LLM=1` 可启用 LLM 提取。
* 不引入新的 Wiki 展示、Wiki 图谱或 Wiki 页面编辑工作流。
* 不实现 Qoder 2.0 完整企业级能力，包括 RepoWiki、人机共建 `/knowledge` 命令、commit-diff 飞轮、团队共享、版本锁裁决、向量检索和企业治理。这些能力进入 `docs/specs/proposed/knowledge-engine-v2-roadmap.md`。

## 6. Requirements
* Card YAML 必须包含设计文档定义的核心字段。
* 自动合并不得覆盖 `human_edited_fields` 标记的人类编辑字段。
* 所有文件解析必须限制在 `DEEPMEMO_DATA_DIR` 下，拒绝路径穿越。
* `/api/knowledge/maintain` 必须返回 stats、orphan_cards、conflict_pairs、merge_suggestions。
* 主应用不得继续挂载旧 `/wiki/*` 路由。
* LocalSearch Card miss 时必须保留原有 ripgrep fallback。
* 测试必须使用临时 data 目录，不污染真实 `data/`。

## 7. Acceptance Criteria
* `POST /api/knowledge/compile/file` 生成 YAML Card 并更新 `index.json`。
* 手动 `PUT /api/knowledge/cards/{slug}` 修改字段后，后续编译不覆盖该字段。
* `POST /api/knowledge/maintain` 返回维护报告。
* Chat 达到阈值后生成 conversation Card。
* LocalSearch 命中 Card 时 `searched_paths == ["knowledge/cards"]`，未命中时 fallback 到 Markdown。
* 前端 build 通过并包含 Knowledge 模式。
* 前端 build 产物不依赖 Wiki mode/API。
* `uv run python scripts/verify.py --mode quick` 通过。

## 8. Implementation Strategy
* `src/knowledge/` 提供模型、存储、编译、检索、对话提取、维护和调度。
* `src/routers/knowledge.py` 提供 Card API。
* `src/ai/local_search_agent.py` 接入 Card-first retrieval。
* `src/routers/chat.py` 在消息持久化后触发轻量 conversation extraction。
* `src/app/core/watcher.py` 对 diary/raw Markdown 变更进行防抖编译。
* `app/src/` 新增 Knowledge 管理视图。

## 9. Task Breakdown
- [x] Knowledge Card 模型、YAML 存储和 JSON 索引。
- [x] Markdown Card 编译、可选 LLM 提取和 human edit merge 保护。
- [x] Conversation memory extraction。
- [x] Maintenance report 和 `/api/knowledge/maintain`。
- [x] Card-first LocalSearch + ripgrep fallback。
- [x] 旧 Wiki 前端模式和主应用 `/wiki/*` 路由下线。
- [x] Watcher 防抖编译和维护 scheduler。
- [x] 前端 Knowledge 管理视图。
- [x] Current specs 同步。
- [x] Targeted tests 与 quick verification。

## 10. Validation Plan
* `uv run pytest tests -q --tb=short -m 'not e2e'`
* `npm run build` in `app/`
* `uv run python scripts/verify.py --mode quick`

## 11. Docs Sync Requirements
* 更新 `current/knowledge-engine.md`。
* 更新 `current/wiki-ingestion.md`。
* 更新 `current/wiki-graph.md`。
* 更新 `current/ai-chat-rag.md`。
* 更新 `current/fs-watcher.md`。
* 后续扩展必须先从 `proposed/knowledge-engine-v2-roadmap.md` 拆分新的 Ready Goal，不能直接在 v1 上追加实现。
