# Knowledge Engine v3 HTML Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Knowledge Engine v3A-D: ViewModel HTML Reader, Review Queue actions, Relation Canvas, and Rewrite Loop.

**Architecture:** Backend adds `src/knowledge/view_model.py` as the aggregation/action boundary over Cards, RepoWiki, Maintenance, review-state, and rewrite suggestions. Frontend adds focused React/TypeScript Knowledge components under `app/src/knowledge/`, while `App.tsx` keeps app-level orchestration and current Cards editing behavior.

**Tech Stack:** FastAPI, pytest, YAML/JSON file persistence, React, TypeScript, Vite, lucide-react, existing CSS.

---

### Task 1: Backend ViewModel Tests And Core

**Files:**
- Create: `tests/unit/test_knowledge_view_model.py`
- Create: `src/knowledge/view_model.py`
- Modify: `tests/conftest.py`

- [ ] Write failing tests for ViewModel stats, pages, graph, review queue, review-state isolation, and rewrite/apply behavior.
- [ ] Run `uv run pytest tests/unit/test_knowledge_view_model.py -q --tb=short`; expect missing module failure.
- [ ] Implement dataclass-free JSON-friendly service functions in `src/knowledge/view_model.py`.
- [ ] Add module DATA_DIR monkeypatching to `tests/conftest.py`.
- [ ] Re-run unit tests; expect pass.

### Task 2: Backend API Tests And Router

**Files:**
- Create: `tests/api/test_knowledge_view.py`
- Modify: `src/routers/knowledge.py`

- [ ] Write failing API tests for `/api/knowledge/view`, pages, review, confirm, hide, rewrite, apply, pin, unsafe IDs, and old `/wiki/*` 404.
- [ ] Run targeted API tests; expect route failures.
- [ ] Add Pydantic request models and router endpoints delegating to `KnowledgeViewService`.
- [ ] Re-run API tests; expect pass.

### Task 3: Frontend Types/API And Components

**Files:**
- Modify: `app/src/types.ts`
- Modify: `app/src/api.ts`
- Create: `app/src/knowledge/KnowledgeWorkspace.tsx`
- Create: `app/src/knowledge/KnowledgeOverview.tsx`
- Create: `app/src/knowledge/KnowledgeReader.tsx`
- Create: `app/src/knowledge/KnowledgeReviewQueue.tsx`
- Create: `app/src/knowledge/KnowledgeRelationCanvas.tsx`
- Modify: `app/src/App.tsx`
- Modify: `app/src/styles.css`

- [ ] Add TypeScript types and API functions for ViewModel, pages, review actions, pin, rewrite, apply.
- [ ] Extract Knowledge UI into focused components while preserving current Card editor behavior.
- [ ] Implement Overview, Reader, Review, Relation Canvas, and Cards subviews.
- [ ] Run `npm run build`; fix type/style regressions until pass.

### Task 4: Verification, Runtime Check, Docs Sync

**Files:**
- Modify: `docs/specs/current/knowledge-engine.md`
- Modify: `docs/specs/proposed/knowledge-engine-v3-html-layer.md`
- Modify: `docs/specs/goals/knowledge-engine-v3-html-layer.goal.md`

- [ ] Run targeted unit/API tests.
- [ ] Run `uv run pytest tests -q --tb=short -m 'not e2e'`.
- [ ] Run `npm run build` in `app/`.
- [ ] Run `uv run python scripts/verify.py --mode quick`.
- [ ] Start backend/frontend dev servers and runtime-check frontend 200, ViewModel JSON, review JSON, and `/wiki/graph` 404.
- [ ] Mark Goal `Implemented` and update current/proposed specs.
- [ ] Commit with `feat: implement knowledge engine v3 html layer`.
- [ ] Push `feature_v2`.

## Self-Review

Coverage: The plan maps v3A to Task 1/2/3 Reader, v3B to review-state/actions, v3C to graph model/canvas, and v3D to rewrite/apply. It preserves non-goals by keeping `/wiki/*` out and writing only generated review metadata plus Cards through CardStore. No placeholders remain.
