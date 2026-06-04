# Legacy Cleanup Goal

## 1. Goal
安全彻底地删除被归类为 D 类的废弃接口和重复代码逻辑，降低技术债务。

## 2. Why this goal matters
当前的后端存在路由未挂载、模型重复定义以及死代码占位符。这些冗余不仅增加了维护成本，还会对后续 Codex AI 的代码理解和修改产生严重的幻觉干扰。必须立即扫除。

## 3. Related Specs
* **Current Specs**: 无，纯删除操作。
* **Open Questions**: [巨石单体组件重构] 依然保留，不在本次清理范围。

## 4. Desired Behavior
* 系统不再对外提供 `/api/diary/auto-draft` 路由。
* Session 的 CRUD 逻辑只有唯一的一份代码实现（`main.py` 或 `session.py`，建议保留 `main.py` 里的实现并删除独立的未挂载 router）。
* `schemas.py` 与 `main.py` 之间不再存在重复名称的 Pydantic 数据模型。
* `get_db_connection` 全局仅存在一个权威实现。

## 5. Non-goals
* 不重构前端的 `App.tsx` 巨型组件。
* 不重构 `blog_fetcher.py`。
* 不修改任何前端功能。

## 6. Requirements
* 所有删除动作必须伴随着测试用例的成功运行。如果某些用例测试了被废弃的路由，应该同步删除测试用例。
* 重复代码抽取为公共函数时，确保所有调用方的 import 路径正确更新。

## 7. Acceptance Criteria
* 访问 `/api/diary/auto-draft` 必须返回 404 Not Found。
* 执行 `uv run python scripts/verify.py --mode quick` 必须通过，无编译/导入错误。

## 8. Implementation Strategy
* 分支与重构并行。首先处理死代码（Auto-draft 和未使用 Router），然后再处理依赖整理（Schemas 和 DB 连接），最后跑全量测试。

## 9. Task Breakdown
- [ ] 删除 `src/routers/diary.py` 及相关的 `AutoDraftRequest`。
- [ ] 从 `main.py` 移除对 `diary_router` 的引用。
- [ ] 删除 `src/routers/session.py` 文件（因为它本来就没被挂载）。
- [ ] 在 `main.py` 中删除重复本地定义的 `SessionCreate` / `SessionResponse`，统一从 `schemas.py` 导入。
- [ ] 删除 `fs_manager.py` 和 `watcher.py` 中重复的 `get_db_connection`，统一 `from src.app.database import get_db_connection`。

## 10. Validation Plan
在本地执行 `uv run python scripts/verify.py --mode quick`，确保 FastAPI 正确启动，测试全绿。

## 11. Docs Sync Requirements
* 清空 `docs/specs/deprecated.md` 中对应的条目，因为已经执行完毕。
