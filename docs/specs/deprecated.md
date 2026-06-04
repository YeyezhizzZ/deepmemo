# Deprecated Behaviors

本文件记录了经过 Human Review 确认应该废弃的特性（D 类）。后续 AI coding **绝对不能**去实现、依赖或扩展这些行为。

## 1. 废弃的 Auto-Draft 接口
* **Target**: `/api/diary/auto-draft` 路由以及任何调用它的前端代码。
* **Reason**: 仅仅是一个返回 "LLM integration pending" 的占位符，未接通生成逻辑，长期处于死代码状态。
* **Action**: 已决定安全删除。

## 2. 后端路由与模型过度重复 (Backend Duplication Debt)
* **Target**: `src/routers/session.py`（未挂载），重复的 Pydantic Models（`SessionCreate`, `SessionResponse` 等在 `main.py` 和 `schemas.py` 中重复定义），以及多次复制粘贴的 `get_db_connection` 和 `compute_file_hash`。
* **Reason**: Vibe coding 的历史包袱，导致代码极难维护。
* **Action**: 将通过 `legacy-cleanup` 目标被重构和合并，这些重复的实现被彻底废弃。
