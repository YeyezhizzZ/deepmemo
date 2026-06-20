# Knowledge Engine v2 Roadmap

> **Status**: Proposed / Not Ready for Implementation
> **Supersedes Gaps From**: `docs/specs/current/knowledge-engine.md`
> **Rule**: This document is a roadmap. Before coding any item, split it into a Ready Goal under `docs/specs/goals/`.

## 1. Purpose

DeepMemo Knowledge Engine v1 implements the local Knowledge Card truth layer, Card-first RAG, conversation extraction, watcher-triggered compile, maintenance reports, and frontend Card management.

It does **not** yet implement the full software-engineering knowledge engine described by Qoder-style Knowledge Engine 2.0: two-step Card -> RepoWiki condensation, commit-driven growth, team sharing, enterprise version arbitration, `/knowledge` human-in-the-loop command flows, vector retrieval, or AI-native semantic maintenance.

This roadmap records what remains, how to implement it, and how each capability should be accepted.

## 2. Current Baseline

Implemented in v1:

* Markdown under `data/diary/` and `data/raw/` compiles into YAML Cards under `data/knowledge/cards/`.
* `data/knowledge/index.json` indexes Cards by slug, tag, type, key terms, stats, and timestamps.
* Chat sessions periodically generate conversation Cards under `raw/conversations/`.
* Local RAG checks Knowledge Cards before falling back to ripgrep search.
* Watcher events on diary/raw Markdown debounce and compile affected Cards.
* `/api/knowledge/*` exposes Card CRUD, compile, search, stats, health, and maintenance.
* Frontend `Knowledge` mode lists, searches, edits, compiles, and maintains Cards.
* Human-edited Card fields are protected from compiler overwrite.
* Old `/wiki/*`, Wiki frontend mode, `src/wiki/*`, and old Wiki scripts are removed.

## 3. Missing Capabilities

| Area | Missing Capability | Why It Matters |
| --- | --- | --- |
| Human narrative layer | RepoWiki generated from Cards | Humans need coherent project explanations, not only dense Card records |
| Code-side flywheel | Commit/diff-triggered Card update | File watcher sees content changes, but not the developer intent encoded in commits |
| Conversation-side flywheel | Rich plan/spec/review extraction | Current extraction is heuristic and only catches simple conversation signals |
| Human-in-loop command | `/knowledge` command in chat | Users need to create, rewrite, merge, or pin knowledge without leaving the chat flow |
| Retrieval stack | Vector/embedding retrieval | Keyword search is brittle for semantic architecture and convention questions |
| Semantic maintenance | LLM adjudication for conflicts/merges/staleness | Current maintenance is keyword-based and cannot reliably judge contradictions |
| Team sharing | Shared Card namespace and provenance | Teams need personal vs team knowledge separation and promotion workflows |
| Enterprise versioning | Repo + branch + commit arbitration | Concurrent contributors must not overwrite newer knowledge with older compile results |
| CLI/CI integration | Knowledge CLI for batch compile and validation | Enterprise usage needs non-IDE workflows and CI gates |
| Governance | Policy, permissions, audit logs | Team knowledge needs reviewability and admin control |

## 4. Implementation Plan

### Phase 2A: RepoWiki From Cards

Implement a new `src/knowledge/repowiki/` module. It should read Cards as the only structured input, group them by software-engineering topic, and write narrative Markdown under a new path such as `data/knowledge/repowiki/`.

Do not restore old `src/wiki/*` or `/wiki/*`. RepoWiki is a Knowledge Engine output, not the previous Wiki product.

Required APIs:

* `POST /api/knowledge/repowiki/rebuild`
* `GET /api/knowledge/repowiki/pages`
* `GET /api/knowledge/repowiki/pages/{slug}`

Acceptance:

* Given Cards for architecture, decisions, and lessons, rebuild produces deterministic Markdown pages with sources back to Card slugs and original evidence.
* RepoWiki generation never mutates Cards.
* `/wiki/*` remains 404.
* Frontend shows RepoWiki as a read-only Knowledge subview, not as restored Wiki mode.

### Phase 2B: Commit-Diff Flywheel

Add a git-aware compiler that consumes commit metadata and diffs:

* changed files
* commit message
* branch name
* commit hash
* surrounding Card hits

It should update affected Cards or create decision/lesson/pattern Cards when commit messages contain design intent.

Possible entry points:

* CLI: `uv run python -m src.knowledge.cli compile-commit <commit>`
* API: `POST /api/knowledge/compile/commit`
* Optional git hook template under `scripts/`

Acceptance:

* A commit that changes `src/ai/local_search_agent.py` updates Cards related to retrieval, not unrelated Cards.
* Commit hash appears in Card sources.
* Re-running the same commit compile is idempotent.
* Old commits cannot overwrite human-edited fields.

### Phase 2C: Rich Conversation Memory

Replace the lightweight heuristic extractor with a structured extractor that recognizes:

* accepted plans
* explicit corrections
* architecture decisions
* coding standards
* repeated debugging lessons
* user-confirmed preferences

LLM extraction must remain mockable in tests. The fallback path should preserve deterministic behavior when no LLM is configured.

Acceptance:

* Chat tests cover confirmation, correction, decision, convention, and lesson extraction.
* Extracted Cards include source pointers to `raw/conversations/{session_id}.md`.
* Extraction does not run on every message; it uses thresholds and explicit commands to avoid noise.

### Phase 2D: `/knowledge` Command

Add chat command handling for direct knowledge operations:

* `/knowledge list`
* `/knowledge show <slug>`
* `/knowledge add`
* `/knowledge update <slug>`
* `/knowledge merge <a> <b>`
* `/knowledge pin <field>`

The command should update Cards through the same API/store path as the frontend so human edit protection remains consistent.

Acceptance:

* Command tests verify successful update and invalid command errors.
* `/knowledge update` marks edited fields as human-edited.
* Command changes are visible in frontend Knowledge mode.

### Phase 2E: Hybrid Retrieval

Add optional vector retrieval behind a feature flag. Retrieval order should be:

1. exact slug/tag/type filters
2. Card keyword/BM25-lite score
3. vector semantic score
4. ripgrep fallback

Acceptance:

* Vector retrieval can be disabled with an environment variable.
* Tests mock embeddings and verify ranking composition.
* Existing keyword-only tests still pass when vector retrieval is disabled.

### Phase 2F: Semantic Maintenance

Extend maintenance from keyword checks to semantic checks:

* contradiction adjudication
* merge recommendations with reason
* stale Card explanation
* orphan Card remediation suggestions

Acceptance:

* Maintenance report includes machine-readable reasons and confidence.
* LLM path is mockable and has deterministic fallback.
* Suggested merges do not auto-merge without user/API confirmation.

### Phase 2G: Team And Enterprise Mode

Introduce a namespace model:

* personal Cards
* repo Cards
* team Cards
* promoted Cards

Add version fields:

* repo id
* branch
* base commit
* source commit
* compiler version
* last writer

Acceptance:

* Uploading a Card compiled from an older commit cannot overwrite a newer commit version.
* Team Cards record who promoted or edited them.
* Tests cover branch isolation and conflict rejection.

### Phase 2H: CLI And CI

Add `src/knowledge/cli.py` for non-IDE workflows:

* `compile`
* `compile-file`
* `compile-commit`
* `maintain`
* `validate`
* `repowiki rebuild`

Acceptance:

* CLI commands run against a temporary `DEEPMEMO_DATA_DIR` in tests.
* `validate` fails on invalid Card YAML, broken sources, or index drift.
* CI can run `uv run python -m src.knowledge.cli validate`.

## 5. Validation Matrix

| Capability | Test Level | Required Verification |
| --- | --- | --- |
| RepoWiki APIs | L1 API + unit | API response shape, deterministic page generation, source links |
| Commit compiler | Unit + integration | diff classification, idempotency, human field protection |
| Conversation extractor | API + unit | chat thresholds, command triggers, mocked LLM extraction |
| `/knowledge` command | API | successful edits, invalid syntax, human edit metadata |
| Hybrid retrieval | Unit + API | ranking, feature flag behavior, fallback preservation |
| Semantic maintenance | API + unit | report shape, mock LLM path, no unconfirmed auto-merge |
| Team versioning | API + unit | branch isolation, stale commit rejection, audit metadata |
| CLI/CI | subprocess/integration | exit codes, temp data isolation, validate failures |

## 6. Release Acceptance

Before marking a future v2 goal `Implemented`, the following must pass:

* Targeted tests for the goal.
* `uv run pytest tests -q --tb=short -m 'not e2e'`.
* `npm run build` in `app/` if frontend changed.
* `uv run python scripts/verify.py --mode quick`.
* Browser/runtime check when user-visible Knowledge or RepoWiki views change.
* Spec sync in `docs/specs/current/`.

## 7. Non-Goals Until Explicitly Approved

* Restoring old `/wiki/*`.
* Restoring deleted `src/wiki/*`.
* Sending raw proprietary source code to a remote service by default.
* Auto-merging semantic conflict suggestions without human confirmation.
* Making vector retrieval mandatory.
