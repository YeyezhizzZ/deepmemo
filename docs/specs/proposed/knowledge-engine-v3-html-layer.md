# Knowledge Engine v3 HTML Layer

> **Status**: Proposed / Not Ready for Implementation
> **Design**: `docs/design/knowledge-engine-v3-html-layer.md`
> **Rule**: Split into a Ready Goal under `docs/specs/goals/` before coding.

## 1. Purpose

Knowledge Engine v3 upgrades the human-facing layer from Markdown-shaped RepoWiki pages to an interactive React/HTML decision interface. The Agent-facing layer remains Knowledge Cards. The human-facing layer becomes a structured UI for reading, reviewing, and approving generated knowledge.

## 2. Baseline

Current implemented behavior:

* Knowledge Cards are stored under `data/knowledge/cards/*.yaml`.
* RepoWiki pages are generated under `data/knowledge/repowiki/*.md`.
* Frontend Knowledge mode has Cards and read-only RepoWiki subviews.
* `/wiki/*` is unsupported and returns 404.
* `/knowledge` chat commands can list/show/add/update/pin Cards.

## 3. Desired v3 Behavior

* Frontend renders human knowledge as structured React/HTML views, not raw Markdown blocks.
* Backend exposes a `KnowledgeViewModel` API aggregating Cards, RepoWiki pages, source evidence, maintenance status, review items, and relation graph summaries.
* Knowledge mode includes:
  * Overview
  * Reader
  * Review
  * Cards
* Humans can inspect source evidence and Card provenance from the HTML view.
* Review actions are explicit and auditable.
* Human actions write to Card metadata or `data/knowledge/review-state.json`, not original Markdown sources.

## 4. Non-Goals

* Do not restore old `/wiki/*`.
* Do not restore old `src/wiki/*`.
* Do not make generated HTML a new source truth.
* Do not introduce a new frontend framework or UI component library.
* Do not implement enterprise team permissions or remote sync in v3 Core.
* Do not auto-apply rewrite or merge suggestions without human confirmation.

## 5. Proposed API

All endpoints live under `/api/knowledge`:

* `GET /api/knowledge/view`
* `GET /api/knowledge/view/pages`
* `GET /api/knowledge/view/pages/{slug}`
* `GET /api/knowledge/view/review`
* `POST /api/knowledge/view/review/{item_id}/confirm`
* `POST /api/knowledge/view/review/{item_id}/hide`
* `POST /api/knowledge/view/review/{item_id}/rewrite`
* `POST /api/knowledge/view/cards/{slug}/pin`

## 6. Proposed Data Files

Generated review state:

* `data/knowledge/review-state.json`

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

v3 implementation should split Knowledge UI into focused components under `app/src/knowledge/` when practical.

Design references:

* Current Knowledge mode from v2 Core.
* Old Wiki graph workspace from commit `e461a33 feat: add wiki graph workspace UI`, only for interaction ideas such as typed lists, relation canvas, and side detail panels.

## 8. Acceptance Criteria

Before any v3 goal is marked Implemented:

* API tests cover the new view endpoints and review action endpoints.
* Unit tests cover deterministic ViewModel generation and isolated review state persistence.
* Frontend build passes.
* Browser/runtime checks verify Overview, Reader, Review, and Cards render without overlap.
* `/wiki/*` remains 404.
* `uv run python scripts/verify.py --mode quick` passes.

## 9. Suggested Goal Split

### v3A: HTML Reader

Implement ViewModel APIs and structured Reader UI. No review mutations.

### v3B: Review Queue

Implement review item state and confirm/hide/pin actions.

### v3C: Relationship Canvas

Implement a secondary relationship graph for topic exploration.

### v3D: Rewrite Loop

Implement mockable rewrite suggestions and human-confirmed application to Cards.
