# Knowledge Engine v3 HTML Layer

> **Status**: Implemented
> **Source Design**: `docs/design/knowledge-engine-v3-html-layer.md`
> **Source Proposal**: `docs/specs/proposed/knowledge-engine-v3-html-layer.md`

## 1. Goal
完整实现 Knowledge Engine v3A-D：把当前人类阅读层从 Markdown-shaped RepoWiki 升级为 React/TypeScript 渲染的交互式 HTML Knowledge View，包含 ViewModel/Reader、Review Queue、Relation Canvas 和 Rewrite Loop。

## 2. Why this goal matters
v1/v2 已经形成 Agent 可用的 Knowledge Cards 和基础 RepoWiki，但人类层仍是线性 Markdown 阅读体验。v3 要提升人参与知识判断的带宽，让用户能在同一 Knowledge 工作区中快速浏览、审阅、确认、隐藏、固定、请求重写，并理解知识之间的关系和来源。

## 3. Related Specs
* **Current Specs**: `constitution.md`, `current/knowledge-engine.md`, `current/ai-chat-rag.md`, `current/test-infrastructure.md`
* **Design**: `docs/design/knowledge-engine-v3-html-layer.md`
* **Proposed**: `docs/specs/proposed/knowledge-engine-v3-html-layer.md`
* **Superseded surface**: old `/wiki/*`, deleted `src/wiki/*`, and old Wiki frontend mode remain deprecated and must not be restored.

## 4. Desired Behavior
* Backend exposes `KnowledgeViewModel` APIs under `/api/knowledge/view`.
* Frontend `Knowledge` mode exposes `Overview`, `Reader`, `Review`, and `Cards` subviews.
* Reader renders structured HTML/React sections from Cards and RepoWiki data rather than raw Markdown blocks.
* Review queue lists open human-decision items for new Cards, stale Cards, conflicts, merge suggestions, and generated page sections.
* Review actions are explicit:
  * confirm review item
  * hide review item
  * pin Card field
  * request rewrite
* Review state is stored in generated metadata under `data/knowledge/review-state.json`.
* Relation Canvas visualizes Cards as nodes and relations as edges using Card links, shared tags, and shared sources.
* Rewrite Loop creates a proposed rewrite in review state and only applies it to Card fields when explicitly confirmed.
* Human actions may update Card metadata or Card fields through the existing CardStore path.
* Original diary/raw Markdown must never be edited by this v3 UI.

## 5. Non-goals
* Do not restore old `/wiki/*`.
* Do not restore old `src/wiki/*`.
* Do not make generated HTML or review state a new source truth.
* Do not introduce a new frontend framework or UI component library.
* Do not implement enterprise team permissions, remote sync, repo+branch upload locks, or governance audit.
* Do not make vector retrieval mandatory.
* Do not auto-apply rewrite or merge suggestions without explicit human confirmation.

## 6. API Requirements
All new APIs live under `/api/knowledge`:

* `GET /api/knowledge/view`
* `GET /api/knowledge/view/pages`
* `GET /api/knowledge/view/pages/{slug}`
* `GET /api/knowledge/view/review`
* `POST /api/knowledge/view/review/{item_id}/confirm`
* `POST /api/knowledge/view/review/{item_id}/hide`
* `POST /api/knowledge/view/review/{item_id}/rewrite`
* `POST /api/knowledge/view/review/{item_id}/apply`
* `POST /api/knowledge/view/cards/{slug}/pin`

## 7. Frontend Requirements
* Use existing React + TypeScript + Vite stack.
* Use existing lucide-react icons and current DeepMemo operational visual style.
* Prefer focused files under `app/src/knowledge/` instead of continuing to grow `App.tsx`.
* Preserve Cards editing behavior from v2.
* Do not add a new top-level Wiki mode.
* Do not call old `/wiki/*` APIs.
* Relation Canvas may use SVG/HTML without adding a graph library.

## 8. Data Requirements
* `data/knowledge/cards/*.yaml` remains the Agent-facing knowledge truth layer.
* `data/knowledge/repowiki/*.md` may remain a generated intermediate input.
* `data/knowledge/review-state.json` stores generated review/action metadata.
* `review-state.json` must be loaded/saved under `DEEPMEMO_DATA_DIR` in tests and runtime.

## 9. Task Breakdown
- [x] v3A: ViewModel API and structured HTML Reader.
- [x] v3B: Review state, Review Queue APIs, confirm/hide/pin actions.
- [x] v3C: Relation Canvas graph model and frontend graph view.
- [x] v3D: Rewrite request/apply loop with deterministic fallback and mockable LLM path.
- [x] Frontend Knowledge workspace split into React/TS components.
- [x] Docs sync for current/proposed specs and design status.
- [x] Targeted tests, build, quick verification, and runtime/browser check.

## 10. Acceptance Criteria
* API tests cover view, pages, review queue, confirm, hide, rewrite, apply, pin, unsafe IDs/slugs, and `/wiki/*` 404.
* Unit tests cover deterministic ViewModel generation, relation graph generation, review state persistence, and rewrite action behavior.
* Frontend build passes with React/TS components for Overview, Reader, Review, Relation Canvas, and Cards.
* Browser/runtime checks verify Knowledge subviews render without obvious layout overlap.
* `uv run pytest tests -q --tb=short -m 'not e2e'` passes.
* `npm run build` in `app/` passes.
* `uv run python scripts/verify.py --mode quick` passes.

## 11. Validation Plan
* `uv run pytest tests/unit/test_knowledge_view_model.py -q --tb=short`
* `uv run pytest tests/api/test_knowledge_view.py tests/api/test_wiki.py -q --tb=short`
* `uv run pytest tests -q --tb=short -m 'not e2e'`
* `npm run build` in `app/`
* `uv run python scripts/verify.py --mode quick`
* Runtime check:
  * frontend root returns 200
  * `/api/knowledge/view` returns ViewModel JSON
  * `/api/knowledge/view/review` returns review queue JSON
  * `/wiki/graph` returns 404

## 12. Docs Sync Requirements
* Update `docs/specs/current/knowledge-engine.md` after implementation.
* Update `docs/specs/proposed/knowledge-engine-v3-html-layer.md` to mark implemented scope.
* Update this Goal status to `Implemented` after verification.
