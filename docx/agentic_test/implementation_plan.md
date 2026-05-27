# Agentic Testing First Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first executable DeepMemo regression-testing loop, including a browser-level smoke path.

**Architecture:** Move tests into a top-level `tests/` package, use pytest fixtures to isolate `data/` and SQLite state, add critical API contract and E2E scenario tests, expose one verify command for agents, and add a small Playwright browser smoke layer. Keep L2 unit tests thin and preserve AI refactor freedom.

**Tech Stack:** Python 3.11, pytest, FastAPI TestClient, SQLite, Vite/TypeScript build.

---

## Execution Status

Completed on 2026-05-27 as the first pass. Verification evidence:

- `uv run pytest tests -q --tb=short`: 33 passed.
- `npm run build`: passed.
- `uv run python scripts/verify.py --mode quick`: 31 passed, 2 deselected, frontend build passed.
- `uv run python scripts/verify.py --mode full`: 33 passed, frontend build passed.
- `npm run test:browser`: passed with the first browser smoke flow.
- `uv run python scripts/verify.py --mode full`: now also runs browser Playwright tests.

---

### Task 1: Pytest Configuration

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] Add `pytest`, `pytest-asyncio`, and `httpx` to the dev dependency group.
- [ ] Configure pytest to collect from `tests/`, not from `src/`.
- [ ] Register the `e2e` marker.
- [ ] Run `uv run pytest --co -q`.

### Task 2: Shared Test Fixtures

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] Create a temporary data directory fixture.
- [ ] Create a temporary SQLite database fixture.
- [ ] Patch `src.app.database`, `src.app.core.fs_manager`, `src.routers.fs`, `src.app.main`, and wiki path constants to use test paths.
- [ ] Initialize the schema with `init_db()`.
- [ ] Provide a `client` fixture using the real FastAPI app.
- [ ] Provide DB helper functions for inserting sessions and messages.

### Task 3: Migrate Existing Tests

**Files:**
- Move: `src/app/core/test_asset_manager.py` to `tests/unit/test_asset_manager.py`
- Move: `src/app/core/test_fs_manager.py` to `tests/unit/test_fs_manager.py`
- Move: `src/wiki/test_reconstruction.py` to `tests/unit/test_wiki_pipeline.py`
- Move: `src/app/test_static_assets.py` to `tests/api/test_app.py`
- Move: `src/routers/test_fs_assets.py` to `tests/api/test_fs.py`
- Move: `src/wiki/test_ingest.py` to `scripts/cli_ingest.py`

- [ ] Keep stable pure-function tests as unit tests.
- [ ] Keep static mount and asset upload tests as API tests.
- [ ] Stop collecting CLI ingest as a test file.

### Task 4: First Critical API Contract Tests

**Files:**
- Modify: `tests/api/test_app.py`
- Modify: `tests/api/test_fs.py`
- Create: `tests/api/test_sessions.py`
- Create: `tests/api/test_chat_references.py`
- Create: `tests/api/test_citations.py`

- [ ] Test root health response.
- [ ] Test file create/read/write/move/tree lifecycle.
- [ ] Test fs path traversal is rejected.
- [ ] Test session create/list/get/delete and delete cascade.
- [ ] Test `/api/chat/file-references` normalizes relative, `data/`, and absolute paths.
- [ ] Test `/api/chat/citations` returns stored citation evidence.

### Task 5: Filesystem Path Guard

**Files:**
- Modify: `src/app/core/fs_manager.py`
- Modify: `src/routers/fs.py`

- [ ] Use the new path traversal test as the failing RED test.
- [ ] Add a small data-root resolver to `fs_manager`.
- [ ] Route `ValueError` to HTTP 400 for unsafe paths.
- [ ] Re-run the fs tests and confirm they pass.

### Task 6: E2E Scenario Seed

**Files:**
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/scenarios.yaml`
- Create: `tests/e2e/test_scenarios.py`

- [ ] Record the first critical natural-language scenarios.
- [ ] Implement executable tests for filesystem lifecycle and chat citation traceability.

### Task 7: Verification Command and Agent Rules

**Files:**
- Create: `scripts/verify.py`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

- [ ] Add `quick` and `full` modes to `scripts/verify.py`.
- [ ] Run backend pytest and frontend build from the verifier.
- [ ] Document mandatory agent testing rules in both agent instruction files.

### Task 8: Final Verification

**Files:**
- No additional files.

- [ ] Run `uv run pytest tests -q --tb=short`.
- [ ] Run `npm run build` from `app/`.
- [ ] Run `uv run python scripts/verify.py --mode quick`.
- [ ] Report any remaining failures with exact commands and causes.
