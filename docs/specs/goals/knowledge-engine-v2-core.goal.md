# Knowledge Engine v2 Core

> **Status**: Implemented
> **Source Roadmap**: `docs/specs/proposed/knowledge-engine-v2-roadmap.md`

## 1. Goal
实现 DeepMemo Knowledge Engine v2 的本地核心闭环：基于 Knowledge Cards 生成只读 RepoWiki，支持 commit-diff 编译入口，提供 `/knowledge` Chat 命令，并补齐可在 CI 中运行的 Knowledge CLI validate/rebuild 能力。

## 2. Why this goal matters
v1 已经完成 Card 真值层、Card-first RAG、对话沉淀和前端 Card 管理，但人类仍缺少从 Cards 凝练出的连贯项目叙事，代码提交意图也不能进入知识库。v2 Core 先把“不依赖远端服务、本地可验证”的能力做实，为后续团队共享、企业版本裁决、向量检索和语义维护提供稳定基础。

## 3. Related Specs
* **Current Specs**: `constitution.md`, `current/knowledge-engine.md`, `current/ai-chat-rag.md`, `current/fs-watcher.md`, `current/query-routing.md`, `current/test-infrastructure.md`
* **Roadmap**: `proposed/knowledge-engine-v2-roadmap.md`
* **Superseded surface**: `/wiki/*` and deleted `src/wiki/*` remain deprecated and must not be restored.

## 4. Desired Behavior
* RepoWiki generation reads Knowledge Cards only and writes deterministic Markdown pages under `data/knowledge/repowiki/`.
* RepoWiki pages include Card slug/source provenance and never mutate Cards.
* Backend exposes:
  * `POST /api/knowledge/repowiki/rebuild`
  * `GET /api/knowledge/repowiki/pages`
  * `GET /api/knowledge/repowiki/pages/{slug}`
  * `POST /api/knowledge/compile/commit`
* Frontend Knowledge mode exposes a read-only RepoWiki subview alongside Card management, without restoring old Wiki mode or `/wiki/*`.
* Commit compilation accepts a commit ref/hash, reads git metadata and changed files, and creates or updates decision/pattern/lesson Cards with commit hash in sources.
* Commit compilation is idempotent for the same commit and preserves human-edited Card fields.
* Chat handles `/knowledge` commands before normal QA:
  * `/knowledge list`
  * `/knowledge show <slug>`
  * `/knowledge add <title> :: <definition>`
  * `/knowledge update <slug> :: <definition>`
  * `/knowledge pin <slug> <field>`
* `/knowledge update` and `/knowledge pin` mark affected fields as human-edited through the same CardStore path as API/frontend edits.
* CLI entry point `uv run python -m src.knowledge.cli` supports:
  * `compile`
  * `compile-file <path>`
  * `compile-commit <commit>`
  * `maintain`
  * `validate`
  * `repowiki rebuild`
* `validate` exits non-zero for invalid Card YAML, broken source paths, or index drift.

## 5. Non-goals
* 不恢复旧 `/wiki/*` 路由、旧 Wiki 前端模式或 `src/wiki/*`。
* 不默认启用向量检索或远端 embedding 服务。
* 不实现团队共享、权限系统、远端同步、repo+branch 上传锁、企业版本裁决或治理审计。
* 不自动合并语义冲突建议。
* 不要求 LLM 在线调用；所有新增行为必须在无 LLM、无网络的测试环境确定性运行。

## 6. Requirements
* 所有新增文件读写必须限制在 `DEEPMEMO_DATA_DIR` 或当前 git 仓库内，不得访问真实用户数据测试路径。
* RepoWiki slug 必须使用安全 slug，并拒绝路径穿越。
* RepoWiki rebuild 必须可重复运行，结果稳定。
* Commit 编译必须只记录 diff 元数据和摘要片段，不把整份源码复制进 Card。
* `/knowledge` 命令失败时返回可读错误消息，并保存为本次 chat 的 assistant 回复。
* CLI 必须使用现有 `CardStore`、`KnowledgeCardCompiler`、`KnowledgeMaintainer` 和 RepoWiki 服务，不复制业务逻辑。

## 7. Acceptance Criteria
* API 测试覆盖 RepoWiki rebuild/list/detail、commit compile、路径穿越/404、旧 `/wiki/*` 保持 404。
* Chat API 测试覆盖 `/knowledge list/show/add/update/pin` 和非法命令。
* Unit 测试覆盖 RepoWiki 页面生成、commit 编译 idempotency、human edit protection、CLI validate 错误场景。
* Frontend build 通过，Knowledge 模式能切换 Cards/RepoWiki，只读展示 RepoWiki 页面。
* `uv run pytest tests -q --tb=short -m 'not e2e'` 通过。
* `npm run build` in `app/` 通过。
* `uv run python scripts/verify.py --mode quick` 通过。

## 8. Implementation Strategy
* 新增 `src/knowledge/repowiki.py`：Card 分组、Markdown 页面生成、页面存储与读取。
* 新增 `src/knowledge/commit_compiler.py`：通过 `git` 读取 commit metadata/diff summary 并生成 Knowledge Cards。
* 新增 `src/knowledge/chat_commands.py`：解析并执行 `/knowledge` 命令。
* 新增 `src/knowledge/cli.py`：薄 CLI 包装现有服务。
* 扩展 `src/routers/knowledge.py` 暴露 RepoWiki 和 commit compile API。
* 扩展 `src/routers/chat.py` 在普通 QA 前处理 `/knowledge` 命令。
* 扩展 `app/src/api.ts`、`app/src/types.ts`、`app/src/App.tsx` 和 `app/src/styles.css` 提供 RepoWiki 子视图。

## 9. Task Breakdown
- [x] RepoWiki unit tests and implementation.
- [x] RepoWiki API tests and router integration.
- [x] Commit compiler tests and API/CLI integration.
- [x] `/knowledge` command tests and chat integration.
- [x] Frontend RepoWiki subview.
- [x] CLI validate tests.
- [x] Current specs and roadmap sync.
- [x] Targeted tests and quick verification.

## 10. Validation Plan
* `uv run pytest tests/unit/test_knowledge_repowiki.py -q --tb=short`
* `uv run pytest tests/unit/test_knowledge_commit_compiler.py -q --tb=short`
* `uv run pytest tests/unit/test_knowledge_cli.py -q --tb=short`
* `uv run pytest tests/api/test_knowledge.py tests/api/test_chat.py tests/api/test_wiki.py -q --tb=short`
* `uv run pytest tests -q --tb=short -m 'not e2e'`
* `npm run build` in `app/`
* `uv run python scripts/verify.py --mode quick`

## 11. Docs Sync Requirements
* 更新 `docs/specs/current/knowledge-engine.md`，把 v2 Core 行为升为 Current。
* 更新 `docs/specs/proposed/knowledge-engine-v2-roadmap.md`，标记 v2 Core 已完成，保留企业/向量/团队能力为后续 roadmap。
* 实现完成后把本 Goal 状态改为 `Implemented`。
