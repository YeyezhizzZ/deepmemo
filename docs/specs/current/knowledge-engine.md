# Knowledge Engine

* **Status**: Current / Implemented
* **Implemented From**: `docs/specs/goals/knowledge-engine-v1.goal.md`

## 1. Scope
Knowledge Engine v1 provides the structured Knowledge Card layer for DeepMemo. It covers YAML Card files, JSON index maintenance, Markdown and conversation compilation, Card-first retrieval, maintenance, watcher-triggered growth, scheduled health updates, and backend/frontend Card management.

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

## 3. Evidence
* `src/knowledge/models.py`
* `src/knowledge/card_store.py`
* `src/knowledge/card_compiler.py`
* `src/knowledge/conversation_memory.py`
* `src/knowledge/maintenance.py`
* `src/knowledge/retriever.py`
* `src/knowledge/scheduler.py`
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
Markdown compile request or watcher event -> resolve safe Markdown path under `DEEPMEMO_DATA_DIR` -> extract Card drafts using optional LLM or heuristic fallback -> merge with existing Cards while preserving human-edited fields -> write YAML Cards -> rebuild JSON index. Chat flows periodically extract decision/lesson/pattern/concept Cards into `raw/conversations/`. The frontend reads and edits Cards directly through `/api/knowledge/*`.

## 5. Interfaces / Related Files
* `GET /api/knowledge/cards`
* `GET /api/knowledge/cards/{slug}`
* `PUT /api/knowledge/cards/{slug}`
* `DELETE /api/knowledge/cards/{slug}`
* `POST /api/knowledge/compile`
* `POST /api/knowledge/compile/file`
* `POST /api/knowledge/search`
* `GET /api/knowledge/stats`
* `GET /api/knowledge/health`
* `POST /api/knowledge/maintain`
* Frontend `Knowledge` mode lists, edits, compiles, and maintains Cards.
* `/wiki/*` is not a supported public application route.

## 6. Known Gaps
* LLM extraction is opt-in by environment variable to keep default local/test runs deterministic.
* Conflict detection is keyword-based in v1, not semantic LLM adjudication.
* Watcher compile uses a configurable debounce timer; startup full reconciliation is not yet implemented.
* DeepMemo v1 is not a full Qoder-style engineering knowledge engine. It does not yet provide RepoWiki synthesis, commit-diff triggered updates, branch/version conflict arbitration, team knowledge sharing, `/knowledge` chat commands, vector retrieval, or enterprise governance.
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
| RepoWiki human narrative layer | Not implemented | Old Wiki was removed; no replacement RepoWiki exists |
| Commit-diff based Card updates | Not implemented | No git hook, commit watcher, or diff-to-Card compiler exists |
| Team/shared knowledge mode | Not implemented | No remote Card sync, permissions, or team namespace exists |
| Enterprise version arbitration | Not implemented | No repo+branch upload lock or commit-version裁决 exists |
| `/knowledge` chat command | Not implemented | Chat tools do not expose a knowledge-edit command surface |
| Vector/embedding retrieval | Not implemented | v1 explicitly keeps keyword/BM25-lite retrieval |
| Full AI-native semantic maintenance | Not implemented | Default extraction and maintenance are deterministic heuristics; LLM extraction is opt-in |

## 9. Current Acceptance Evidence

Current v1 acceptance is defined by:

* `tests/api/test_knowledge.py`
* `tests/api/test_wiki.py`
* `tests/unit/test_knowledge_models.py`
* `tests/unit/test_knowledge_store.py`
* `tests/unit/test_knowledge_compiler.py`
* `tests/unit/test_knowledge_conversation_maintenance.py`
* `tests/unit/test_knowledge_retriever_integration.py`
* `uv run python scripts/verify.py --mode quick`

Expected runtime contract:

* `/api/knowledge/*` is the supported knowledge API surface.
* `/wiki/*` returns 404 from the main app.
* Frontend build contains `Knowledge` mode and no old Wiki mode/API client.
