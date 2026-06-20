# Knowledge Engine

* **Status**: Current / Implemented
* **Implemented From**: `docs/specs/goals/knowledge-engine-v1.goal.md`, `docs/specs/goals/knowledge-engine-v2-core.goal.md`

## 1. Scope
Knowledge Engine provides the structured Knowledge Card layer and the local v2 Core loop for DeepMemo. It covers YAML Card files, JSON index maintenance, Markdown and conversation compilation, Card-first retrieval, maintenance, watcher-triggered growth, scheduled health updates, backend/frontend Card management, Card-derived RepoWiki pages, commit-diff compilation, `/knowledge` chat commands, and local CLI validation/rebuild workflows.

## 2. Preserved Behaviors
* **Local Markdown remains source truth**: Knowledge Cards are compiled artifacts under `data/knowledge/`; they do not replace `data/diary/`, `data/raw/`, or user-authored Markdown.
* **YAML Card storage**: Cards are stored at `data/knowledge/cards/{slug}.yaml` with stable fields for identity, content, source evidence, relations, tags, timestamps, staleness, and human edit metadata.
* **Index maintenance**: `data/knowledge/index.json` is rebuilt after Card save/delete and contains `cards`, `tag_index`, `type_index`, `stats`, and `updated_at`.
* **Manual and automatic compile**: `POST /api/knowledge/compile`, `POST /api/knowledge/compile/file`, watcher-triggered diary/raw compilation, and chat conversation extraction all write Cards.
* **LLM extraction is optional**: heuristic extraction is the default safe path; `DEEPMEMO_KNOWLEDGE_USE_LLM=1` enables LLM extraction with heuristic fallback.
* **Human edit protection**: `PUT /api/knowledge/cards/{slug}` marks edited fields in `human_edited_fields`; future compiler merges do not overwrite those protected fields.
* **Card-first search**: `/api/knowledge/search` searches Cards directly, and `LocalSearchAgent` checks Card evidence before falling back to ripgrep Markdown search.
* **Maintenance**: `POST /api/knowledge/maintain` and the startup scheduler update staleness, report orphan Cards, detect simple conflicts, and suggest merges.
* **Knowledge-only product surface**: The frontend exposes `Knowledge` Card management and does not expose the old `Wiki` graph/page workspace. The main FastAPI app exposes `/api/knowledge/*` as the supported knowledge API surface and does not mount `/wiki/*`.
* **RepoWiki from Cards**: RepoWiki pages are generated from Cards only, written under `data/knowledge/repowiki/`, and exposed as a read-only Knowledge subview. RepoWiki generation never mutates Cards and must not restore old `/wiki/*`.
* **Commit-diff flywheel entry point**: `POST /api/knowledge/compile/commit` and `src.knowledge.cli compile-commit` read git commit metadata, changed paths, and commit intent, then create/update commit Cards with `git:{short_hash}` sources while preserving human-edited fields.
* **Chat knowledge command**: `/knowledge` messages are intercepted before normal QA and can list, show, add, update, or pin Knowledge Cards through the same CardStore path as API/frontend edits.
* **CLI/CI workflow**: `uv run python -m src.knowledge.cli` supports compile, compile-file, compile-commit, maintain, validate, and repowiki rebuild. `validate` fails on invalid Card YAML, missing source files, or index drift.

## 3. Evidence
* `src/knowledge/models.py`
* `src/knowledge/card_store.py`
* `src/knowledge/card_compiler.py`
* `src/knowledge/conversation_memory.py`
* `src/knowledge/maintenance.py`
* `src/knowledge/retriever.py`
* `src/knowledge/scheduler.py`
* `src/knowledge/repowiki.py`
* `src/knowledge/commit_compiler.py`
* `src/knowledge/chat_commands.py`
* `src/knowledge/cli.py`
* `src/routers/knowledge.py`
* `src/ai/local_search_agent.py`
* `src/routers/chat.py`
* `src/app/core/watcher.py`
* `app/src/App.tsx`
* `tests/unit/test_knowledge_models.py`
* `tests/unit/test_knowledge_store.py`
* `tests/unit/test_knowledge_compiler.py`
* `tests/api/test_knowledge.py`

## 4. Current Flow
Markdown compile request or watcher event -> resolve safe Markdown path under `DEEPMEMO_DATA_DIR` -> extract Card drafts using optional LLM or heuristic fallback -> merge with existing Cards while preserving human-edited fields -> write YAML Cards -> rebuild JSON index. Chat flows periodically extract decision/lesson/pattern/concept Cards into `raw/conversations/`, and explicit `/knowledge` commands mutate Cards directly. RepoWiki rebuild reads Cards, groups them by engineering type, and writes deterministic read-only Markdown pages. Commit compile reads git metadata/diff summaries from the repository and writes commit Cards without copying full source files.

## 5. Interfaces / Related Files
* `GET /api/knowledge/cards`
* `GET /api/knowledge/cards/{slug}`
* `PUT /api/knowledge/cards/{slug}`
* `DELETE /api/knowledge/cards/{slug}`
* `POST /api/knowledge/compile`
* `POST /api/knowledge/compile/file`
* `POST /api/knowledge/compile/commit`
* `POST /api/knowledge/search`
* `GET /api/knowledge/stats`
* `GET /api/knowledge/health`
* `POST /api/knowledge/maintain`
* `POST /api/knowledge/repowiki/rebuild`
* `GET /api/knowledge/repowiki/pages`
* `GET /api/knowledge/repowiki/pages/{slug}`
* `uv run python -m src.knowledge.cli compile`
* `uv run python -m src.knowledge.cli compile-file <path>`
* `uv run python -m src.knowledge.cli compile-commit <commit>`
* `uv run python -m src.knowledge.cli maintain`
* `uv run python -m src.knowledge.cli validate`
* `uv run python -m src.knowledge.cli repowiki rebuild`
* Frontend `Knowledge` mode lists, edits, compiles, and maintains Cards, and exposes a read-only RepoWiki subview.
* `/wiki/*` is not a supported public application route.

## 6. Known Gaps
* LLM extraction is opt-in by environment variable to keep default local/test runs deterministic.
* Conflict detection is keyword-based in v1, not semantic LLM adjudication.
* Watcher compile uses a configurable debounce timer; startup full reconciliation is not yet implemented.
* DeepMemo v2 Core is still not a full Qoder-style enterprise knowledge engine. It does not yet provide branch/version conflict arbitration, team knowledge sharing, remote promotion workflows, mandatory vector retrieval, semantic LLM maintenance adjudication, or enterprise governance.
* Commit-diff compilation is an explicit API/CLI entry point; automatic git hook installation is not enabled by default.
* RepoWiki is read-only generated Markdown from Cards; human edits should happen on Cards.
* Future work is tracked in `docs/specs/proposed/knowledge-engine-v2-roadmap.md`.

## 7. Regression Risks
* Changing path resolution could allow writes outside the configured data directory.
* Changing index rebuild semantics could desynchronize YAML Cards from `index.json`.
* Changing merge behavior could overwrite human-reviewed Card fields.

## 8. Implementation Status Against Engineering Knowledge Engine Vision

The implemented v1 is a local, single-repo Knowledge Card engine for DeepMemo. It intentionally focuses on the Card truth layer and removes the old Wiki product surface.

| Capability | Status | Current Evidence |
| --- | --- | --- |
| Raw Markdown to Knowledge Card compile | Implemented | `POST /api/knowledge/compile`, `POST /api/knowledge/compile/file`, `src/knowledge/card_compiler.py` |
| YAML Card truth layer and index | Implemented | `data/knowledge/cards/*.yaml`, `data/knowledge/index.json`, `src/knowledge/card_store.py` |
| Human editable Card fields with merge protection | Implemented | `PUT /api/knowledge/cards/{slug}`, `human_edited_fields` |
| Card-first RAG | Implemented | `src/ai/local_search_agent.py` searches Card evidence before `rg` fallback |
| Conversation memory extraction | Partially implemented | Chat message thresholds call `compile_conversation`; extraction is heuristic and session-local |
| Watcher-triggered growth | Partially implemented | File watcher debounces diary/raw Markdown changes and compiles affected files |
| Maintenance flywheel | Partially implemented | `POST /api/knowledge/maintain` reports staleness, orphan Cards, keyword conflicts, and merge hints |
| Frontend knowledge management | Implemented | `Knowledge` mode lists, searches, edits, compiles, and maintains Cards |
| Legacy Wiki public surface removal | Implemented | `/wiki/*` is unmounted and covered by regression tests |
| RepoWiki human narrative layer | Implemented locally | `src/knowledge/repowiki.py`, `/api/knowledge/repowiki/*`, frontend read-only RepoWiki subview |
| Commit-diff based Card updates | Partially implemented | Explicit API/CLI compile from git commit metadata; no automatic git hook yet |
| Team/shared knowledge mode | Not implemented | No remote Card sync, permissions, or team namespace exists |
| Enterprise version arbitration | Not implemented | No repo+branch upload lock or commit-version裁决 exists |
| `/knowledge` chat command | Implemented locally | Chat intercepts list/show/add/update/pin commands before QA |
| Vector/embedding retrieval | Not implemented | v1 explicitly keeps keyword/BM25-lite retrieval |
| Full AI-native semantic maintenance | Not implemented | Default extraction and maintenance are deterministic heuristics; LLM extraction is opt-in |
| CLI/CI knowledge workflow | Implemented locally | `src/knowledge/cli.py` supports compile, compile-file, compile-commit, maintain, validate, repowiki rebuild |

## 9. Current Acceptance Evidence

Current v1 acceptance is defined by:

* `tests/api/test_knowledge.py`
* `tests/api/test_wiki.py`
* `tests/unit/test_knowledge_models.py`
* `tests/unit/test_knowledge_store.py`
* `tests/unit/test_knowledge_compiler.py`
* `tests/unit/test_knowledge_conversation_maintenance.py`
* `tests/unit/test_knowledge_retriever_integration.py`
* `tests/unit/test_knowledge_repowiki.py`
* `tests/unit/test_knowledge_commit_compiler.py`
* `tests/unit/test_knowledge_cli.py`
* `uv run python scripts/verify.py --mode quick`

Expected runtime contract:

* `/api/knowledge/*` is the supported knowledge API surface.
* `/wiki/*` returns 404 from the main app.
* Frontend build contains `Knowledge` mode with Cards and RepoWiki subviews and no old Wiki mode/API client.
