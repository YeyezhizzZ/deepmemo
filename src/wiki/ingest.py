from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.wiki.frontmatter import parse_markdown_frontmatter
from src.wiki.ingest_analyzer import (
    DEFAULT_RAW_SEED_DIR,
    MockDiaryEntry,
    WikiDraft,
    analyze_entry,
    load_mock_diary_entries,
    merge_draft,
    normalize_draft,
    _slugify,
    _load_llm_service,
)
from src.wiki.ingest_writer import resolve_related_paths, write_generated_wiki
from src.wiki.merger import merge_candidate_drafts
from src.wiki.link_resolver import resolve_draft_links
from src.wiki.evidence import build_drafts_from_evidence, extract_evidence_cards
from src.wiki.path_utils import normalize_rel_path, rel_path
from src.wiki.storage import compute_file_hash, resolve_data_path
from src.wiki import graph as wiki_graph
import time
from src.wiki.health import build_wiki_health_report


DEFAULT_WIKI_DIR = Path("data/wiki")
DEFAULT_DIARY_DIR = Path("data/diary")
DEFAULT_INGEST_CACHE = Path("data/wiki/.wiki-ingest-cache.json")


@dataclass(slots=True)
class WikiIngestConfig:
    seed_dir: Path = DEFAULT_RAW_SEED_DIR
    wiki_dir: Path = DEFAULT_WIKI_DIR
    clean: bool = True


@dataclass(slots=True)
class DiaryWikiIngestConfig:
    diary_dir: Path = DEFAULT_DIARY_DIR
    wiki_dir: Path = DEFAULT_WIKI_DIR
    cache_file: Path = DEFAULT_INGEST_CACHE
    clean: bool = False


def _load_existing_titles(entries: list[MockDiaryEntry]) -> list[str]:
    titles: list[str] = []
    for entry in entries:
        titles.append(entry.title)
    return titles


def _load_markdown_title(content: str, fallback: str) -> str:
    frontmatter, body = parse_markdown_frontmatter(content)
    title = str(frontmatter.get("title") or "").strip()
    if title:
        return title

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or fallback
        if stripped:
            break

    body_lines = [line.strip() for line in body.splitlines() if line.strip()]
    for line in body_lines:
        if not line.startswith("#"):
            return line[:80] or fallback
    return fallback


def _load_diary_entries(seed_dir: Path = DEFAULT_DIARY_DIR) -> list[MockDiaryEntry]:
    if not seed_dir.exists():
        return []

    entries: list[MockDiaryEntry] = []
    for path in sorted(seed_dir.rglob("*.md"), key=lambda item: item.relative_to(seed_dir).as_posix()):
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        title = _load_markdown_title(content, path.stem)
        entries.append(
            MockDiaryEntry(
                path=normalize_rel_path(str(path)),
                title=title,
                content=content,
            )
        )
    return entries


def _normalize_source_draft(source_draft: WikiDraft, entry: MockDiaryEntry) -> WikiDraft:
    source_draft.slug = Path(entry.path).stem
    source_draft.title = f"{source_draft.slug} · {source_draft.title}" if source_draft.title else source_draft.slug
    source_draft.sources = [entry.path]
    return source_draft


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


NOISY_PAGE_LABELS = {
    "data",
    "raw",
    "mock",
    "diary",
    "wiki",
    "reference",
    "docs",
    "docx",
    "src",
    "app",
    "frontend",
    "backend",
    "index",
    "overview",
    "log",
    "agents",
    "readme",
}


def _is_noisy_page_label(value: str) -> bool:
    token = value.strip().lower()
    if not token:
        return True
    if token in NOISY_PAGE_LABELS:
        return True
    if token.endswith(".md") or token.endswith(".py") or token.endswith(".json"):
        return True
    if "/" in token or "\\" in token:
        return True
    return False


def _iter_analysis_items(analysis: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw_items = analysis.get(key) if isinstance(analysis, dict) else None
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, dict):
            items.append(item)
    return items


def _normalize_page_candidate(
    page_type: str,
    item: dict[str, Any],
    *,
    default_source: str,
    default_summary: str,
) -> WikiDraft | None:
    title = str(item.get("title") or "").strip()
    if not title or _is_noisy_page_label(title):
        return None

    payload = dict(item)
    payload.setdefault("title", title)
    payload.setdefault("summary", default_summary)
    payload.setdefault("sources", [default_source])
    payload.setdefault("related", [])
    payload.setdefault("sections", [])
    draft = normalize_draft(page_type, payload, default_source)
    draft.sources = _dedupe_preserve_order(draft.sources + [default_source])
    if not draft.sections:
        draft.sections = [
            {
                "heading": "Evidence",
                "bullets": [default_summary] if default_summary else [],
            }
        ]
    return draft


def _merge_candidate(
    collection: dict[str, WikiDraft],
    draft: WikiDraft | None,
) -> None:
    if draft is None:
        return
    existing = collection.get(draft.slug)
    collection[draft.slug] = merge_draft(existing, draft) if existing else draft


def _build_knowledge_pages_from_analyses(
    entries: list[MockDiaryEntry],
    analyses: dict[str, dict[str, Any]],
    *,
    diary_dir: Path | None = None,
    wiki_dir: Path = DEFAULT_WIKI_DIR,
) -> tuple[
    dict[str, WikiDraft],
    dict[str, WikiDraft],
    dict[str, WikiDraft],
    dict[str, WikiDraft],
]:
    entity_candidates: list[WikiDraft] = []
    concept_candidates: list[WikiDraft] = []
    synthesis_candidates: list[WikiDraft] = []
    source_pages: dict[str, WikiDraft] = {}

    t_extract = time.time()
    for entry in entries:
        analysis = analyses.get(entry.path) or {}
        default_summary = entry.content.strip().splitlines()[0].strip() if entry.content.strip() else entry.title
        
        # Extract source page draft
        source_data = analysis.get("source")
        if isinstance(source_data, dict):
            draft = normalize_draft("source", source_data, entry.path)
            draft = _normalize_source_draft(draft, entry)
            source_pages[draft.slug] = draft

        # Extract knowledge candidate pages
        for key, page_type, target_list in [
            ("entities", "entity", entity_candidates),
            ("concepts", "concept", concept_candidates),
            ("syntheses", "synthesis", synthesis_candidates),
        ]:
            for item in _iter_analysis_items(analysis, key):
                draft = _normalize_page_candidate(
                    page_type,
                    item,
                    default_source=entry.path,
                    default_summary=default_summary,
                )
                if draft is not None:
                    target_list.append(draft)

    print(f"  [ingest] Candidate extraction took {time.time() - t_extract:.2f}s (explicit: {len(entity_candidates)} entities, {len(concept_candidates)} concepts, {len(synthesis_candidates)} syntheses)", flush=True)

    t_ev = time.time()
    evidence_cards = extract_evidence_cards(entries)
    evidence_entity_pages, evidence_concept_pages = build_drafts_from_evidence(evidence_cards)
    entity_candidates.extend(evidence_entity_pages.values())
    concept_candidates.extend(evidence_concept_pages.values())

    print(f"  [ingest] Evidence extraction took {time.time() - t_ev:.2f}s: {len(evidence_cards)} cards → {len(evidence_entity_pages)} entity + {len(evidence_concept_pages)} concept drafts", flush=True)

    # Perform global merge and deduplication
    t_merge = time.time()
    has_llm = _load_llm_service() is not None
    print(f"  [ingest] Merging candidates (llm={'on' if has_llm else 'off'}) ...", flush=True)
    merged_entities = merge_candidate_drafts(entity_candidates, use_llm=has_llm)
    merged_concepts = merge_candidate_drafts(concept_candidates, use_llm=has_llm)
    merged_syntheses = merge_candidate_drafts(synthesis_candidates, use_llm=has_llm)
    print(f"  [ingest] Global merge took {time.time() - t_merge:.2f}s (merged to: {len(merged_entities)} entities, {len(merged_concepts)} concepts, {len(merged_syntheses)} syntheses)", flush=True)

    total_explicit = len(merged_entities) + len(merged_concepts) + len(merged_syntheses)
    has_evidence_candidates = bool(evidence_entity_pages or evidence_concept_pages)
    should_fallback = not has_evidence_candidates and (total_explicit < 12 or len(merged_concepts) < 6)

    if should_fallback:
        t_fallback = time.time()
        print(f"  [ingest] Fallback: only {total_explicit} explicit pages, using term extraction ...", flush=True)
        term_entries = wiki_graph._load_diary_entries(diary_dir or DEFAULT_DIARY_DIR) if diary_dir else []  # type: ignore[attr-defined]
        if not term_entries:
            term_entries = wiki_graph._load_diary_entries(DEFAULT_DIARY_DIR)  # type: ignore[attr-defined]
        term_data = wiki_graph._select_terms(term_entries)  # type: ignore[attr-defined]

        for term, data in term_data.items():
            page_type = wiki_graph._term_type(term, data)  # type: ignore[attr-defined]
            if _is_noisy_page_label(term):
                continue
            slug = _slugify(term, f"{page_type}-term")
            page_item = {
                "slug": slug,
                "title": term,
                "summary": f"出现在 {data['doc_freq']} 篇日记中。",
                "tags": [page_type, f"df:{data['doc_freq']}"],
                "sources": list(data["sources"]),
                "related": [],
                "sections": [
                    {
                        "heading": "Evidence",
                        "bullets": [str(example) for example in data.get("examples", [])[:5]],
                    },
                ],
            }
            draft = normalize_draft(page_type, page_item, data["sources"][0] if data["sources"] else "diary")
            draft.sources = list(data["sources"])
            draft.related = []
            
            if page_type == "entity":
                entity_candidates.append(draft)
            elif page_type == "concept":
                concept_candidates.append(draft)
            elif page_type == "synthesis":
                synthesis_candidates.append(draft)

        # Run merge again after fallback terms are added
        merged_entities = merge_candidate_drafts(entity_candidates, use_llm=has_llm)
        merged_concepts = merge_candidate_drafts(concept_candidates, use_llm=has_llm)
        merged_syntheses = merge_candidate_drafts(synthesis_candidates, use_llm=has_llm)
        print(f"  [ingest] Fallback merging took {time.time() - t_fallback:.2f}s (final: {len(merged_entities)} entities, {len(merged_concepts)} concepts, {len(merged_syntheses)} syntheses)", flush=True)

    # Reconstruct final mappings
    entity_pages = {d.slug: d for d in merged_entities}
    concept_pages = {d.slug: d for d in merged_concepts}
    synthesis_pages = {d.slug: d for d in merged_syntheses}

    # Calculate related links based on source overlaps
    t_rel = time.time()
    all_pages = list(entity_pages.values()) + list(concept_pages.values()) + list(synthesis_pages.values())
    page_lookup = {page.slug: page for page in all_pages}
    slugs = list(page_lookup.keys())
    related_count = 0
    for slug in slugs:
        page = page_lookup[slug]
        source_set = set(page.sources)
        scored: list[tuple[float, str]] = []
        for other_slug in slugs:
            if other_slug == slug:
                continue
            other = page_lookup[other_slug]
            other_source_set = set(other.sources)
            shared = len(source_set & other_source_set)
            if shared <= 0:
                continue
            score = shared / max(1, len(source_set | other_source_set))
            if score < 0.15:
                continue
            scored.append((score, other_slug))
        page.related = [other_slug for _score, other_slug in sorted(scored, key=lambda item: (-item[0], item[1]))[:3]]
        if page.related:
            related_count += 1
    print(f"  [ingest] Related links calculation took {time.time() - t_rel:.2f}s (Jaccard >= 0.15, {related_count}/{len(slugs)} pages linked)", flush=True)

    # Run global link resolver to finalize and rewrite wikilinks (downgrading dead links)
    t_link = time.time()
    resolve_draft_links(all_pages, wiki_dir)
    resolve_draft_links(list(source_pages.values()), wiki_dir)
    print(f"  [ingest] Link resolution took {time.time() - t_link:.2f}s", flush=True)

    return source_pages, entity_pages, concept_pages, synthesis_pages


def _build_knowledge_pages_from_terms(
    diary_dir: Path,
) -> tuple[
    dict[str, WikiDraft],
    dict[str, WikiDraft],
    dict[str, WikiDraft],
    dict[str, WikiDraft],
]:
    diary_entries = wiki_graph._load_diary_entries(diary_dir)  # type: ignore[attr-defined]
    return _build_knowledge_pages_from_analyses(diary_entries, {}, diary_dir=diary_dir)


def build_mock_wiki_drafts(entries: list[MockDiaryEntry]) -> tuple[
    dict[str, WikiDraft],
    dict[str, WikiDraft],
    dict[str, WikiDraft],
    dict[str, WikiDraft],
]:
    existing_titles = _load_existing_titles(entries)
    analyses = {
        entry.path: analyze_entry(entry, existing_titles)
        for entry in entries
    }
    return _build_knowledge_pages_from_analyses(entries, analyses, diary_dir=DEFAULT_RAW_SEED_DIR)


def _manifest_path(cache_file: Path, wiki_dir: Path) -> Path:
    if cache_file.is_absolute():
        return cache_file
    return wiki_dir / cache_file.name


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "entries": {}, "generated_paths": [], "summary": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("version", 1)
            data.setdefault("entries", {})
            data.setdefault("generated_paths", [])
            data.setdefault("summary", {})
            return data
    except Exception:
        pass
    return {"version": 1, "entries": {}, "generated_paths": [], "summary": {}}


def _save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    summary = manifest.get("summary")
    return summary if isinstance(summary, dict) else {}


def _load_diary_analyses(
    entries: list[MockDiaryEntry],
    manifest: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], int]:
    cached_entries = manifest.get("entries") or {}
    analyses: dict[str, dict[str, Any]] = {}
    changed = 0
    existing_titles = _load_existing_titles(entries)
    total = len(entries)

    for idx, entry in enumerate(entries, 1):
        entry_hash = compute_file_hash(resolve_data_path(entry.path))
        cached = cached_entries.get(entry.path) if isinstance(cached_entries, dict) else None
        if isinstance(cached, dict) and cached.get("hash") == entry_hash and isinstance(cached.get("analysis"), dict):
            analyses[entry.path] = cached["analysis"]
            continue
        print(f"  [{idx}/{total}] analyzing {entry.path} ...", flush=True)
        analyses[entry.path] = analyze_entry(entry, existing_titles)
        changed += 1

    return analyses, changed


def _collect_generated_paths(
    source_pages: dict[str, WikiDraft],
    entity_pages: dict[str, WikiDraft],
    concept_pages: dict[str, WikiDraft],
    synthesis_pages: dict[str, WikiDraft],
) -> list[str]:
    paths: list[str] = []
    for draft in list(source_pages.values()) + list(entity_pages.values()) + list(concept_pages.values()) + list(synthesis_pages.values()):
        folder = {
            "source": "sources",
            "entity": "entities",
            "concept": "concepts",
            "synthesis": "syntheses",
            "query": "queries",
        }.get(draft.page_type, "misc")
        paths.append(f"wiki/{folder}/{draft.slug}.md")
    paths.extend(["wiki/index.md", "wiki/overview.md", "wiki/log.md"])
    return list(dict.fromkeys(paths))


def _build_result_summary(
    source_pages: dict[str, WikiDraft],
    entity_pages: dict[str, WikiDraft],
    concept_pages: dict[str, WikiDraft],
    synthesis_pages: dict[str, WikiDraft],
) -> dict[str, int]:
    all_pages: list[WikiDraft] = []
    for collection in [source_pages, entity_pages, concept_pages, synthesis_pages]:
        all_pages.extend(collection.values())
    return {
        "sources": len(source_pages),
        "entities": len(entity_pages),
        "concepts": len(concept_pages),
        "syntheses": len(synthesis_pages),
        "total_pages": len(all_pages),
    }


def _prune_stale_generated_pages(wiki_dir: Path, keep_paths: set[str], previous_paths: list[str]) -> None:
    if previous_paths:
        stale_paths = [path for path in previous_paths if path not in keep_paths]
    else:
        stale_paths = []
        for folder in ("sources", "entities", "concepts", "syntheses", "queries"):
            root = wiki_dir / folder
            if not root.exists():
                continue
            for path in root.rglob("*.md"):
                relative = rel_path(path)
                if relative not in keep_paths:
                    stale_paths.append(relative)

    for relative_path in stale_paths:
        full_path = resolve_data_path(relative_path)
        if not full_path.exists():
            continue
        if full_path.is_dir():
            shutil.rmtree(full_path)
        else:
            full_path.unlink()


def run_diary_wiki_ingest(config: DiaryWikiIngestConfig) -> dict[str, Any]:
    t_start = time.time()
    t0 = time.time()
    entries = _load_diary_entries(config.diary_dir)
    if not entries:
        raise FileNotFoundError(f"No diary entries found in {config.diary_dir}")

    print(f"[ingest] loaded {len(entries)} diary entries from {config.diary_dir} in {time.time() - t0:.2f}s", flush=True)

    cache_path = _manifest_path(config.cache_file, config.wiki_dir)
    manifest = _load_manifest(cache_path)
    t0 = time.time()
    analyses, changed_count = _load_diary_analyses(entries, manifest)

    print(f"[ingest] analysis done in {time.time() - t0:.2f}s: {changed_count} new, {len(entries) - changed_count} cached", flush=True)

    if changed_count == 0 and not config.clean and config.wiki_dir.exists():
        summary = _manifest_summary(manifest)
        if summary:
            # Output health report summary even on cached rebuild
            t0 = time.time()
            report = build_wiki_health_report(config.wiki_dir)
            print(f"[ingest] health report generated in {time.time() - t0:.2f}s", flush=True)
            print("\n" + "=" * 60)
            print("--- Health Report Summary (Cached) ---")
            print(f"  Total Pages:          {report['stats']['total_pages']} (source: {report['pages']['by_type'].get('source', 0)}, entity: {report['pages']['by_type'].get('entity', 0)}, concept: {report['pages']['by_type'].get('concept', 0)}, synthesis: {report['pages']['by_type'].get('synthesis', 0)})")
            print(f"  Source Backed Pages: {report['stats']['source_backed_pages']}")
            print(f"  Multi-source Pages:  {report['stats']['multi_source_pages']}")
            print(f"  Dangling Links:      {report['stats']['dangling_wikilinks']}")
            print(f"  Duplicate Pairs:     {report['duplicates']['candidate_count']}")
            print(f"  Orphan Pages:        {len(report['orphan_pages'])}")
            print(f"  Stub Pages:          {len(report['stub_pages'])}")
            print("=" * 60 + "\n", flush=True)
            return {
                **summary,
                "changed_sources": 0,
                "reused_sources": len(entries),
            }

    if config.clean and config.wiki_dir.exists():
        print(f"[ingest] clean mode: removing {config.wiki_dir}", flush=True)
        shutil.rmtree(config.wiki_dir)

    print("[ingest] building knowledge pages (evidence + merge) ...", flush=True)
    t0 = time.time()
    source_pages, entity_pages, concept_pages, synthesis_pages = _build_knowledge_pages_from_analyses(
        entries,
        analyses,
        diary_dir=config.diary_dir,
        wiki_dir=config.wiki_dir,
    )
    print(f"[ingest] knowledge pages compiled in {time.time() - t0:.2f}s", flush=True)

    t0 = time.time()
    write_generated_wiki(
        wiki_dir=config.wiki_dir,
        entries=entries,
        source_pages=source_pages,
        entity_pages=entity_pages,
        concept_pages=concept_pages,
        synthesis_pages=synthesis_pages,
    )
    total_pages = len(source_pages) + len(entity_pages) + len(concept_pages) + len(synthesis_pages)
    print(f"[ingest] wrote {total_pages} pages in {time.time() - t0:.2f}s: {len(source_pages)} source, {len(entity_pages)} entity, {len(concept_pages)} concept, {len(synthesis_pages)} synthesis", flush=True)
    print(f"[ingest] registry.json + index.md + overview.md written to {config.wiki_dir}", flush=True)

    t0 = time.time()
    generated_paths = _collect_generated_paths(source_pages, entity_pages, concept_pages, synthesis_pages)
    previous_paths = [str(item) for item in manifest.get("generated_paths") or []]
    _prune_stale_generated_pages(config.wiki_dir, set(generated_paths), previous_paths)
    print(f"[ingest] pruned stale pages in {time.time() - t0:.2f}s", flush=True)

    # Output health report summary on rebuild
    t0 = time.time()
    report = build_wiki_health_report(config.wiki_dir)
    print(f"[ingest] health report generated in {time.time() - t0:.2f}s", flush=True)
    print("\n" + "=" * 60)
    print("--- Health Report Summary ---")
    print(f"  Total Pages:          {report['stats']['total_pages']} (source: {report['pages']['by_type'].get('source', 0)}, entity: {report['pages']['by_type'].get('entity', 0)}, concept: {report['pages']['by_type'].get('concept', 0)}, synthesis: {report['pages']['by_type'].get('synthesis', 0)})")
    print(f"  Source Backed Pages: {report['stats']['source_backed_pages']}")
    print(f"  Multi-source Pages:  {report['stats']['multi_source_pages']}")
    print(f"  Dangling Links:      {report['stats']['dangling_wikilinks']}")
    print(f"  Duplicate Pairs:     {report['duplicates']['candidate_count']}")
    print(f"  Orphan Pages:        {len(report['orphan_pages'])}")
    print(f"  Stub Pages:          {len(report['stub_pages'])}")
    print("=" * 60 + "\n", flush=True)

    summary = _build_result_summary(source_pages, entity_pages, concept_pages, synthesis_pages)
    next_manifest = {
        "version": 1,
        "entries": {
            entry.path: {
                "hash": compute_file_hash(resolve_data_path(entry.path)),
                "analysis": analyses.get(entry.path) or {},
            }
            for entry in entries
        },
        "generated_paths": generated_paths,
        "summary": summary,
    }
    _save_manifest(cache_path, next_manifest)
    print(f"[ingest] done in {time.time() - t_start:.2f}s. manifest saved to {cache_path}", flush=True)

    return {
        **summary,
        "changed_sources": changed_count,
        "reused_sources": len(entries) - changed_count,
    }


def run_mock_wiki_ingest(config: WikiIngestConfig) -> dict[str, Any]:
    entries = load_mock_diary_entries(config.seed_dir)
    if not entries:
        raise FileNotFoundError(f"No mock diary entries found in {config.seed_dir}")

    if config.clean and config.wiki_dir.exists():
        shutil.rmtree(config.wiki_dir)

    source_pages, entity_pages, concept_pages, synthesis_pages = build_mock_wiki_drafts(entries)
    write_generated_wiki(
        wiki_dir=config.wiki_dir,
        entries=entries,
        source_pages=source_pages,
        entity_pages=entity_pages,
        concept_pages=concept_pages,
        synthesis_pages=synthesis_pages,
    )

    all_pages: list[WikiDraft] = []
    for collection in [source_pages, entity_pages, concept_pages, synthesis_pages]:
        all_pages.extend(collection.values())

    return {
        "sources": len(source_pages),
        "entities": len(entity_pages),
        "concepts": len(concept_pages),
        "syntheses": len(synthesis_pages),
        "total_pages": len(all_pages),
    }
