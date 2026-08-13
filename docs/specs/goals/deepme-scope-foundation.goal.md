# DeepMe Scope Foundation Goal

* **Status**: Complete

## 1. Goal

在保留 DeepMemo 旧接口的前提下，为 DeepMe 建立公开知识 scope、匿名会话、不可变知识版本和 `/api/v1` 问答入口。

## 2. Inputs

- `docs/product/deepme-prd.md`
- `docs/design/deepme-system-architecture.md`
- `docs/specs/proposed/deepme-scope-isolation.md`
- `docs/specs/current/ai-chat-rag.md`
- `docs/specs/constitution.md`

## 3. Required Behavior

1. 启动时可以从公开知识目录构建只读版本。
2. 新 API 会话必须绑定匿名访客和公开 scope。
3. Chat 必须从 session 解析 scope，不能接受客户端覆盖。
4. 问答只读取当前公开版本的 Markdown。
5. 回答消息和 citations 必须保存 scope 与版本。
6. 新 API 不执行 Web Search、Chat Tools、Knowledge Commands 或 Conversation Memory。
7. 旧 API 与现有测试保持可用。

## 4. Non-goals

- 临时文件上传。
- PDF 解析。
- Hybrid Chunk Index。
- Worker 和任务队列消费。
- 新前端。
- 每日自动发布。

## 5. Task Breakdown

- [x] 增加 DeepMe 配置和版本化数据库 migration。
- [x] 增加公开知识快照发布器。
- [x] 实现匿名访客签名 Cookie。
- [x] 实现 `ScopeRegistry` 和 `ScopeResolver`。
- [x] 实现按 scope 构造的 QA 服务。
- [x] 增加 `/api/v1/site`、session、stream chat 和 citations。
- [x] 增加 API contract、所有权和检索隔离测试。
- [x] 运行 quick verification。

## 6. Validation Plan

- `uv run pytest tests/api/test_deepme_v1.py -q`
- `uv run pytest tests/unit/test_deepme_scope.py -q`
- `uv run python scripts/verify.py --mode quick`
- `npm run docs:build`，工作目录为 `docs/wiki`

## 7. Completion Criteria

- 新 API 可以基于公开快照完成流式问答。
- 两个匿名访客不能互相读取会话和引用。
- scope 或版本解析失败时请求停止，不回退到仓库 `data/`。
- 数据库 migration 可重复执行。
- 现有 quick verification 通过。

## 8. Validation Result

- `tests/unit/test_deepme_scope.py` 与 `tests/api/test_deepme_v1.py` 共11项通过。
- Quick verification 共95项通过，2项 E2E 在 quick 模式下排除。
- 独立 E2E 共3项通过。
- 前端生产构建通过。
- VitePress 文档构建通过。
