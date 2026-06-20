# Knowledge Engine v3 HTML Layer

> **Status**: Proposed / Implemented Locally
> **Design**: `docs/design/knowledge-engine-v3-html-layer.md`
> **Implemented Goal**: `docs/specs/goals/knowledge-engine-v3-html-layer.goal.md`

## 1. Purpose

Knowledge Engine v3 upgrades the human-facing layer from Markdown-shaped RepoWiki pages to an interactive React/HTML decision interface. The Agent-facing layer remains Knowledge Cards. The human-facing layer becomes a structured UI for reading, reviewing, and approving generated knowledge.

The local v3A-D scope has been implemented. Future work should extend this document or split new Ready Goals for richer LLM rewrite, enterprise review workflows, and team/shared review-state semantics.

## 2. Baseline

Current implemented behavior:

* Knowledge Cards are stored under `data/knowledge/cards/*.yaml`.
* RepoWiki pages are generated under `data/knowledge/repowiki/*.md`.
* Frontend Knowledge mode has Cards and read-only RepoWiki subviews.
* `/wiki/*` is unsupported and returns 404.
* `/knowledge` chat commands can list/show/add/update/pin Cards.
* `/api/knowledge/view*` exposes a ViewModel, structured pages, review queue, review actions, and relation graph.
* Frontend Knowledge mode renders Overview, Reader, Review, Relation Canvas, and Cards subviews.
* `data/knowledge/review-state.json` stores generated human review metadata.

## 3. Desired v3 Behavior

* Implemented: Frontend renders human knowledge as structured React/HTML views, not raw Markdown blocks.
* Implemented: Backend exposes a `KnowledgeViewModel` API aggregating Cards, RepoWiki pages, source evidence, maintenance status, review items, and relation graph summaries.
* Knowledge mode includes:
  * Implemented: Overview
  * Implemented: Reader
  * Implemented: Review
  * Implemented: Cards
* Implemented: Humans can inspect source evidence and Card provenance from the HTML view.
* Implemented: Review actions are explicit and auditable through review-state.
* Implemented: Human actions write to Card metadata or `data/knowledge/review-state.json`, not original Markdown sources.

## 4. Non-Goals

* Do not restore old `/wiki/*`.
* Do not restore old `src/wiki/*`.
* Do not make generated HTML a new source truth.
* Do not introduce a new frontend framework or UI component library.
* Do not implement enterprise team permissions or remote sync in v3 Core.
* Do not auto-apply rewrite or merge suggestions without human confirmation.

## 5. Proposed API

All endpoints live under `/api/knowledge`:

* Implemented: `GET /api/knowledge/view`
* Implemented: `GET /api/knowledge/view/pages`
* Implemented: `GET /api/knowledge/view/pages/{slug}`
* Implemented: `GET /api/knowledge/view/review`
* Implemented: `POST /api/knowledge/view/review/{item_id}/confirm`
* Implemented: `POST /api/knowledge/view/review/{item_id}/hide`
* Implemented: `POST /api/knowledge/view/review/{item_id}/rewrite`
* Implemented: `POST /api/knowledge/view/review/{item_id}/apply`
* Implemented: `POST /api/knowledge/view/cards/{slug}/pin`

## 6. Proposed Data Files

Generated review state:

* Implemented: `data/knowledge/review-state.json`

Existing truth and generated layers remain:

* `data/knowledge/cards/*.yaml`
* `data/knowledge/index.json`
* `data/knowledge/repowiki/*.md`

## 7. Frontend Requirements

Use the existing React + TypeScript frontend:

* `app/src/api.ts`
* `app/src/types.ts`
* `app/src/App.tsx`
* `app/src/styles.css`

Implemented v3 UI uses focused components under `app/src/knowledge/`.

Design references:

* Current Knowledge mode from v2 Core.
* Old Wiki graph workspace from commit `e461a33 feat: add wiki graph workspace UI`, only for interaction ideas such as typed lists, relation canvas, and side detail panels.

## 8. Acceptance Criteria

Before any v3 goal is marked Implemented:

* Implemented: API tests cover the new view endpoints and review action endpoints.
* Implemented: Unit tests cover deterministic ViewModel generation and isolated review state persistence.
* Implemented: Frontend build passes.
* Implemented: Browser/runtime checks verify API/frontend availability and `/wiki/*` 404.
* Implemented: `/wiki/*` remains 404.
* Implemented: `uv run python scripts/verify.py --mode quick` passes.

## 9. Suggested Goal Split

### v3A: HTML Reader

Implemented: ViewModel APIs and structured Reader UI.

### v3B: Review Queue

Implemented: review item state and confirm/hide/pin actions.

### v3C: Relationship Canvas

Implemented: secondary relationship graph for topic exploration.

### v3D: Rewrite Loop

Implemented locally: deterministic rewrite suggestions and human-confirmed application to Cards. Rich LLM rewrite remains future work.
