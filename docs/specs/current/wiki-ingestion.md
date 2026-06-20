# Wiki Ingestion

* **Status**: Deprecated / Superseded by Knowledge Engine

## 1. Scope
旧 Wiki ingestion 管道，包括直接从 Diary/Raw 生成 Wiki 页面、Card-to-Wiki rebuild、单文件两阶段 `/wiki/ingest`，均不再是当前产品行为。

## 2. Preserved Behaviors
* **不再公开挂载**：主应用不再暴露 `/wiki/rebuild`、`/wiki/ingest`、`/wiki/pages`、`/wiki/page`、`/wiki/graph`、`/wiki/health`、`/wiki/policy`。
* **不再作为前端工作流**：前端不再提供 Wiki 图谱、页面列表、页面详情或重建按钮。
* **Knowledge Cards 为真值**：需要知识索引、检索、编辑和维护时使用 `data/knowledge/cards/*.yaml` 与 `/api/knowledge/*`。

## 3. Evidence
* `docs/specs/deprecated.md`
* `src/knowledge/card_compiler.py`
* `src/knowledge/card_store.py`
* `src/routers/knowledge.py`

## 4. Current Flow
无当前运行流。旧 Wiki ingestion 属于 D 类行为，不得作为新需求依赖或扩展。
