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

## 3. 旧 Wiki 产品面与公开管道
* **Target**: 前端 `Wiki` 模式、`app/src` 中的 Wiki graph/page API 客户端与类型、主应用挂载的 `/wiki/*` 路由、旧单文件 `/wiki/ingest` 两阶段生成入口、手写 Wiki page CRUD、Wiki graph/health/policy public endpoints。
* **Reason**: 旧 Wiki 在 Knowledge Engine v1 之前承担展示、检索中间层和生成管道三种职责，输出质量和维护边界都不稳定。当前人工决策以 Knowledge Cards 作为 Agent 与前端管理真值，不再把 Wiki 作为用户可见产品面或公开 API 合约。
* **Action**: 从主应用和前端删除。后续不得新增依赖或修复这些旧接口；需要知识管理时使用 `/api/knowledge/*` 和 `data/knowledge/cards/*.yaml`。
