# Project Wiki Generation

> **Status**: Deprecated / Superseded by `knowledge-engine-v1.goal.md`
> **Decision**: 旧 Wiki 生成、图谱和公开产品面已经下线；不得再以本 Goal 作为实现入口。

## 1. Goal
已废弃：基于用户 Markdown 日记语料生成双链 Wiki 和图谱的旧目标，不再是当前产品方向。

## 2. Why this goal matters
Knowledge Engine v1 已用 Knowledge Cards 取代旧 Wiki 作为结构化知识中间层、RAG evidence 和前端管理真值。

## 3. Related Specs
* **Replacement Goal**: `knowledge-engine-v1.goal.md`
* **Deprecated Record**: `docs/specs/deprecated.md`

## 4. Desired Behavior
无。旧 Wiki 目标不得实现、依赖或扩展。

## 5. Non-goals
* 不恢复 Wiki 前端展示。
* 不恢复 `/wiki/*` 公开 API。
* 不恢复 `src/wiki/*` 生成管道。

## 6. Requirements
* 需要结构化知识时，必须使用 `data/knowledge/cards/*.yaml` 和 `/api/knowledge/*`。

## 7. Acceptance Criteria
* `/wiki/*` 在主应用中返回 404。
* 前端 build 不包含 Wiki mode/API/types。

## 8. Implementation Strategy
无。该 Goal 已废弃。

## 9. Task Breakdown
- [x] 由 Knowledge Engine v1 取代。
- [x] 旧 Wiki 公开路由、前端模式、脚本和源码管道删除。

## 10. Validation Plan
* `uv run pytest tests/api/test_wiki.py -q --tb=short`
* `npm run build`

## 11. Docs Sync Requirements
* `current/wiki-ingestion.md` 与 `current/wiki-graph.md` 标记为废弃。
