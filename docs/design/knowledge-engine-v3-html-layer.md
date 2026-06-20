# DeepMemo Knowledge Engine v3: Human HTML Layer

> **Status**: Design Draft / Not Implemented
> **Created**: 2026-06-20
> **Builds On**: Knowledge Engine v1 Cards + v2 Core RepoWiki
> **Frontend Stack**: React + TypeScript + existing CSS/lucide UI system

---

## 1. Thesis

Knowledge Engine v1 solved the Agent layer: high-density Knowledge Cards give AI a structured, searchable memory. v2 Core added a human-readable RepoWiki, but it is still primarily Markdown-shaped: linear, static, and optimized for reading text.

v3 upgrades the human layer from **Markdown pages** to an **interactive HTML decision surface**. The goal is not to export `.html` files. The goal is to keep humans in the loop with higher bandwidth: dense scanning, visual structure, review queues, source drill-down, relationship navigation, and explicit accept/reject/pin actions.

The system should keep the existing two-audience split:

* **Agent-facing truth**: `data/knowledge/cards/*.yaml`
* **Human-facing view**: React-rendered Knowledge HTML views backed by structured API view models

Local Markdown remains the user's durable source truth. Cards and HTML views are generated knowledge assets, not replacements for diary/raw Markdown.

## 2. Why HTML, Not More Markdown

Markdown is excellent for linear, lightweight, AI-editable artifacts. It is weak when humans need to make decisions across many pieces of generated knowledge:

* A long Markdown RepoWiki hides conflict, freshness, evidence, and confidence behind scrolling.
* Human review requires actions, not only reading: confirm, pin, reject, merge, rewrite, drill into evidence.
* Knowledge status is multidimensional: source, recency, type, confidence, related Cards, affected commits, review state.
* The human needs to inspect the shape of the knowledge base, not only the prose.

HTML/React gives DeepMemo a richer information channel:

* persistent navigation
* filters and facets
* expandable evidence
* graph/community views
* review queues
* side-by-side Card/page/source panels
* explicit human decisions that write back to Cards

## 3. Scope

v3 should implement the first production-grade human review layer for Knowledge Engine.

### In Scope

* Replace the current read-only Markdown-style RepoWiki display with a structured React/HTML Knowledge View.
* Add backend `KnowledgeViewModel` APIs that aggregate Cards, RepoWiki pages, sources, relations, maintenance status, and review state.
* Add a human review queue for generated knowledge changes.
* Add actions: confirm, pin, hide suggestion, request rewrite, open source, open Card.
* Preserve the current Knowledge Card editor.
* Keep `/wiki/*` deleted and unsupported.
* Reuse existing frontend style: quiet operational UI, three-pane app shell, lucide icons, CSS modules-by-convention in `styles.css`.
* Use old Wiki commit `e461a33 feat: add wiki graph workspace UI` only as interaction reference: typed side list, central relationship canvas, source/detail panel.

### Non-Goals

* Do not restore old `src/wiki/*` or `/wiki/*`.
* Do not make Markdown RepoWiki the primary human UX.
* Do not introduce a new frontend framework or design system.
* Do not add enterprise team permissions, remote sync, or version-lock arbitration in this goal.
* Do not make vector retrieval mandatory.
* Do not edit original diary/raw Markdown from the HTML view.
* Do not auto-apply merge or rewrite suggestions without human action.

## 4. Design Alternatives

### Option A: Static HTML Export

Generate HTML files under `data/knowledge/html/` from RepoWiki Markdown.

Pros:
* Simple mental model.
* Works without a running frontend app.
* Easy to archive.

Cons:
* Still mostly static and document-shaped.
* Hard to support interactive review actions.
* Duplicates the React frontend.
* Risks creating another generated artifact that can drift.

Decision: Do not choose for v3 Core. Static export can be a later CLI feature.

### Option B: React Knowledge ViewModel

Add backend APIs that expose structured view models. The React app renders those models as an interactive human layer.

Pros:
* Best fit for human-in-the-loop review.
* Reuses current React + TypeScript frontend.
* Keeps Cards as truth while letting humans inspect and act.
* Avoids resurrecting old Wiki routes.
* Testable through API contracts and frontend build/browser checks.

Cons:
* Requires new backend view-model aggregation.
* More UI state than simple Markdown display.

Decision: Recommended.

### Option C: Graph-First Knowledge Console

Make the old Wiki graph-style canvas the primary entry point, with nodes as Cards/pages and side panels for details.

Pros:
* Strong visual overview.
* Reuses a proven interaction pattern from commit `e461a33`.
* Good for relationship-heavy exploration.

Cons:
* Graphs become noisy as the knowledge base grows.
* Review workflows still need list/queue structure.
* Layout algorithms can distract from the core human decision loop.

Decision: Use as a secondary view inside Option B, not the default v3 entry point.

## 5. Recommended Product Model

v3 should expose three human-facing subviews inside the existing `Knowledge` workspace:

1. **Overview**
   * Shows health, freshness, review backlog, high-impact changes, and topic clusters.
   * Optimized for "what changed and what needs my attention?"

2. **Reader**
   * Replaces MarkdownLite RepoWiki rendering with structured HTML sections.
   * Shows narrative, source Cards, evidence snippets, related knowledge, and freshness inline.
   * Optimized for "do I understand this part of the project?"

3. **Review**
   * Lists generated or changed knowledge items needing human judgment.
   * Supports confirm, pin, reject/hide, request rewrite, open Card, open source.
   * Optimized for "what should be accepted into durable knowledge?"

Graph/community exploration should be available from Overview or Reader as a local panel, not a new top-level mode.

## 6. Information Architecture

The existing app shell remains:

```
Left Sidebar        Main Workspace                 Right Source Panel
-------------       ------------------------       ------------------------
Knowledge list      Overview / Reader / Review     Selected Card details
Cards filter        HTML sections                  Evidence and sources
RepoWiki pages      Review actions                 Backlinks and related
Review queue        Relationship canvas            Source file jumps
```

### Left Sidebar

Reuse the current Knowledge sidebar, but split navigation into stable groups:

* Cards
* Human Views
  * Overview
  * Reader
  * Review
* Types
  * Decisions
  * Patterns
  * Lessons
  * Concepts
  * Entities

The sidebar should remain dense and utilitarian. It should not become a marketing-style page or decorative dashboard.

### Main Workspace

Use tabs or segmented controls:

* `Overview`
* `Reader`
* `Review`
* `Cards`

Cards remains the editing view from v2. Reader and Review are new.

### Right Source Panel

Extend the existing SourcePanel. In Knowledge mode it should show:

* selected Card metadata
* evidence snippets
* source files
* related Cards
* generated review item details
* action history

This mirrors the old Wiki node detail pattern without restoring old Wiki APIs.

## 7. Backend Architecture

### New Module

```
src/knowledge/view_model.py
```

Responsibilities:

* Load Cards from `CardStore`.
* Load RepoWiki pages from `RepoWikiBuilder`.
* Load maintenance report from `KnowledgeMaintainer`.
* Build topic groups and relationship summaries.
* Build review items from:
  * new Cards
  * changed Cards
  * high staleness Cards
  * conflict pairs
  * merge suggestions
  * generated RepoWiki sections
* Return frontend-ready JSON.

It should not mutate Cards unless called through an explicit action endpoint.

### New Models

Conceptual TypeScript/Python shape:

```ts
type KnowledgeViewModel = {
  generatedAt: string;
  stats: KnowledgeViewStats;
  overview: KnowledgeOverviewSection[];
  pages: KnowledgeHtmlPageSummary[];
  cards: KnowledgeCardSummary[];
  reviewQueue: KnowledgeReviewItem[];
  graph: KnowledgeRelationGraph;
};

type KnowledgeReviewItem = {
  id: string;
  kind: 'new_card' | 'changed_card' | 'stale_card' | 'conflict' | 'merge_suggestion' | 'repowiki_section';
  severity: 'high' | 'medium' | 'low';
  title: string;
  summary: string;
  cardSlugs: string[];
  sourcePaths: string[];
  suggestedAction: 'confirm' | 'pin' | 'rewrite' | 'merge' | 'hide';
  status: 'open' | 'confirmed' | 'hidden' | 'rewritten';
};
```

### API Surface

Add under `/api/knowledge`, not `/wiki`:

* `GET /api/knowledge/view`
* `GET /api/knowledge/view/pages`
* `GET /api/knowledge/view/pages/{slug}`
* `GET /api/knowledge/view/review`
* `POST /api/knowledge/view/review/{item_id}/confirm`
* `POST /api/knowledge/view/review/{item_id}/hide`
* `POST /api/knowledge/view/review/{item_id}/rewrite`
* `POST /api/knowledge/view/cards/{slug}/pin`

The first implementation can store review state under:

```
data/knowledge/review-state.json
```

This state is generated metadata. It must not replace Card YAML or user Markdown.

## 8. Frontend Architecture

### Existing Stack

Keep:

* React
* TypeScript
* Vite
* lucide-react
* existing `app/src/api.ts`
* existing `app/src/types.ts`
* existing `app/src/App.tsx`
* existing `app/src/styles.css`

Do not add a new UI framework for v3 Core.

### Suggested Components

As the current `App.tsx` is already large, v3 should split Knowledge UI into focused files:

```
app/src/knowledge/
  KnowledgeWorkspace.tsx
  KnowledgeOverview.tsx
  KnowledgeReader.tsx
  KnowledgeReviewQueue.tsx
  KnowledgeRelationCanvas.tsx
  KnowledgeSourcePanel.tsx
  knowledgeViewModel.ts
```

Keep shared request mapping in `app/src/api.ts` and shared types in `app/src/types.ts`.

### Visual Style

Use the existing DeepMemo operational style:

* restrained colors
* compact controls
* 6-8px radius for tool surfaces
* lucide icons in buttons
* no decorative blobs or landing-page treatment
* no nested cards
* stable dimensions for lists, counters, graph nodes, and action buttons

Borrow from old Wiki UI:

* typed badges
* community/topic grouping
* node detail side panel
* graph canvas as an exploratory view
* source/backlink lists

Avoid from old Wiki UI:

* restoring `Wiki` as a top-level mode
* old `/wiki/*` API client
* treating generated pages as directly editable files
* overly large graph as the default screen

## 9. Interaction Flows

### Flow A: Review New Knowledge

1. User opens `Knowledge -> Review`.
2. System shows open review items grouped by severity and type.
3. User selects an item.
4. Right panel shows Cards, sources, evidence, and proposed action.
5. User clicks `Confirm`, `Pin`, `Hide`, or `Rewrite`.
6. Backend updates Card metadata or `review-state.json`.
7. View refreshes without changing original Markdown.

### Flow B: Read Project Narrative

1. User opens `Knowledge -> Reader`.
2. User selects a generated human page.
3. Main panel renders sections as HTML blocks:
   * summary
   * decisions
   * patterns
   * lessons
   * related Cards
   * sources
4. User expands evidence or jumps to source files.
5. User can open the underlying Card editor if the narrative is wrong.

### Flow C: Inspect Knowledge Shape

1. User opens `Knowledge -> Overview`.
2. System shows topic clusters and relationship graph.
3. User clicks a cluster or node.
4. Main panel filters Reader/Review to that topic.
5. Right panel shows details and backlinks.

## 10. Data Flow

```
Markdown / Chat / Commit
  -> Knowledge Cards
  -> RepoWiki pages
  -> Maintenance report
  -> KnowledgeViewModel API
  -> React HTML views
  -> Human action
  -> Card metadata or review-state.json
  -> ViewModel refresh
```

Important boundary:

* Cards remain the machine-readable knowledge layer.
* React HTML views are the human decision layer.
* Review actions may mark Card fields human-edited, pin fields, or hide suggestions.
* Review actions do not rewrite original diary/raw Markdown.

## 11. Acceptance Plan

### Backend Tests

Add L1 API tests:

* `GET /api/knowledge/view` returns stats, pages, review queue, graph.
* Review queue includes stale/conflict/merge suggestions from maintenance.
* Confirming an item changes review state.
* Pinning a Card field marks `human_edited_fields`.
* Unsafe slugs/item ids are rejected.
* `/wiki/*` remains 404.

Add L2 unit tests:

* ViewModel groups Cards deterministically.
* Review item IDs are stable.
* HTML page sections preserve Card/source provenance.
* Review state load/save is isolated under `DEEPMEMO_DATA_DIR`.

### Frontend Tests

At minimum:

* `npm run build`.
* Browser check for Knowledge Overview/Reader/Review rendering.
* Verify no old Wiki mode/API strings return.
* Verify action buttons do not overflow at desktop and mobile widths.

### Full Verification

* `uv run pytest tests -q --tb=short -m 'not e2e'`
* `npm run build` in `app/`
* `uv run python scripts/verify.py --mode quick`
* Browser/runtime check for Knowledge v3 flows.

## 12. Implementation Phasing

### v3A: HTML ViewModel + Reader

* Add `KnowledgeViewModel`.
* Add `/api/knowledge/view` and page APIs.
* Replace MarkdownLite RepoWiki display with structured React Reader.
* Keep review actions out of scope.

### v3B: Review Queue

* Add review item generation.
* Add `review-state.json`.
* Add confirm/hide/pin actions.
* Add Review tab in frontend.

### v3C: Relationship Canvas

* Build relation graph from `related_cards`, shared tags, source overlap, and RepoWiki sections.
* Add optional canvas inspired by old Wiki graph UI.
* Keep graph secondary to Overview/Review.

### v3D: Rewrite Loop

* Add request-rewrite action with mockable LLM path.
* Generated rewrite suggestions must be reviewable before applying.
* Accepted rewrites update Cards, not Markdown sources.

## 13. Open Questions

1. Should `review-state.json` be git-shared or personal-only by default?
2. Should Review items expire automatically after related Cards change?
3. Should Reader pages still write Markdown files, or eventually become pure ViewModel output?
4. Should the relationship canvas use plain SVG first or a graph library later?

## 14. Recommended First Goal

Create `docs/specs/goals/knowledge-engine-v3-html-reader.goal.md` with scope:

* ViewModel API
* structured HTML Reader
* source/evidence drill-down
* no review mutations yet
* old `/wiki/*` remains 404

This keeps the first v3 step small, testable, and aligned with the current React + TypeScript frontend.
