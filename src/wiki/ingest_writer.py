from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from src.wiki.frontmatter import render_markdown_page
from src.wiki.ingest_analyzer import MockDiaryEntry, WikiDraft


def _today() -> str:
    return date.today().isoformat()


def _page_path(page_type: str, slug: str) -> str:
    folder = {
        "source": "sources",
        "entity": "entities",
        "concept": "concepts",
        "synthesis": "syntheses",
        "query": "queries",
    }.get(page_type, "misc")
    return f"wiki/{folder}/{slug}.md"


def _resolve_related_refs(
    refs: list[str],
    *,
    source_page_path: str,
    entity_pages: dict[str, WikiDraft],
    concept_pages: dict[str, WikiDraft],
    synthesis_pages: dict[str, WikiDraft],
) -> list[str]:
    resolved: list[str] = []
    for ref in refs:
        value = str(ref).strip()
        if not value:
            continue
        if value.startswith("wiki/"):
            resolved.append(value)
            continue
        if value.startswith("data/") or value.startswith("raw/"):
            resolved.append(source_page_path)
            continue
        if value == source_page_path or value == source_page_path.removeprefix("wiki/"):
            resolved.append(source_page_path)
            continue
        if value in entity_pages:
            resolved.append(_page_path("entity", value))
            continue
        if value in concept_pages:
            resolved.append(_page_path("concept", value))
            continue
        if value in synthesis_pages:
            resolved.append(_page_path("synthesis", value))
            continue
        resolved.append(value)
    return _dedupe_preserve_order(resolved)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _render_page(draft: WikiDraft) -> str:
    frontmatter: dict[str, Any] = {
        "title": draft.title,
        "type": draft.page_type,
        "tags": draft.tags,
        "sources": draft.sources,
        "last_updated": _today(),
        "status": "active" if draft.page_type != "query" else "draft",
        "related": draft.related,
    }
    if draft.aliases:
        frontmatter["aliases"] = draft.aliases

    body_lines: list[str] = [f"# {draft.title}", ""]
    if draft.summary:
        body_lines.extend(["## Summary", draft.summary, ""])

    for section in draft.sections:
        body_lines.append(f"## {section.heading}")
        if section.callout:
            body_lines.append(f"> {section.callout}")
        for bullet in section.bullets:
            body_lines.append(f"- {bullet}")
        body_lines.append("")

    if draft.sources:
        body_lines.extend(["## Sources"])
        for source in draft.sources:
            body_lines.append(f"- {source}")
        body_lines.append("")

    if draft.related:
        body_lines.extend(["## Related"])
        for related in draft.related:
            body_lines.append(f"- [[{related}]]")
        body_lines.append("")

    body = "\n".join(body_lines).strip() + "\n"
    return render_markdown_page(frontmatter, body)


def _render_index(sources: list[WikiDraft], entities: list[WikiDraft], concepts: list[WikiDraft], syntheses: list[WikiDraft]) -> str:
    lines = ["# Wiki Index", ""]
    for title, items in [
        ("Sources", sources),
        ("Entities", entities),
        ("Concepts", concepts),
        ("Syntheses", syntheses),
    ]:
        if not items:
            continue
        lines.extend([f"## {title}"])
        for item in items:
            lines.append(f"- [[{item.title}]] — {item.summary}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_overview(all_pages: list[WikiDraft]) -> str:
    lines = ["# Wiki Overview", ""]
    if not all_pages:
        lines.append("No wiki pages generated yet.")
        return "\n".join(lines).strip() + "\n"

    lines.extend(
        [
            "This wiki is compiled from recurring knowledge extracted from the diary corpus.",
            "High-frequency entities, concepts, and syntheses are merged into durable pages with source traceability.",
            "Daily diary records remain raw evidence; the wiki keeps the stable knowledge layer.",
            "",
        ]
    )
    for page in all_pages[:6]:
        lines.append(f"- [[{page.title}]] ({page.page_type})")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_canonical_registry(all_pages: list[WikiDraft]) -> dict[str, Any]:
    return {
        "version": 1,
        "pages": [
            {
                "type": page.page_type,
                "slug": page.slug,
                "title": page.title,
                "aliases": page.aliases,
                "tags": page.tags,
                "sources": page.sources,
            }
            for page in sorted(all_pages, key=lambda item: (item.page_type, item.slug))
        ],
    }


def write_canonical_registry(wiki_dir: Path, all_pages: list[WikiDraft]) -> None:
    wiki_dir.mkdir(parents=True, exist_ok=True)
    registry_path = wiki_dir / "registry.json"
    registry_path.write_text(
        json.dumps(build_canonical_registry(all_pages), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _append_log(existing: str, entries: list[MockDiaryEntry]) -> str:
    lines = [existing.rstrip(), ""] if existing.strip() else []
    for entry in entries:
        marker = f"## [{_today()}] ingest | {entry.path}"
        if marker in existing:
            continue
        lines.extend([marker, f"- Source: `{entry.path}`", "- Status: generated from mock data", ""])
    return "\n".join(lines).strip() + "\n"


def write_generated_wiki(
    *,
    wiki_dir: Path,
    entries: list[MockDiaryEntry],
    source_pages: dict[str, WikiDraft],
    entity_pages: dict[str, WikiDraft],
    concept_pages: dict[str, WikiDraft],
    synthesis_pages: dict[str, WikiDraft],
) -> None:
    all_pages: list[WikiDraft] = []
    for collection in [source_pages, entity_pages, concept_pages, synthesis_pages]:
        all_pages.extend(collection.values())

    wiki_dir.mkdir(parents=True, exist_ok=True)
    for draft in all_pages:
        page_rel = Path(_page_path(draft.page_type, draft.slug)).relative_to(Path("wiki"))
        path = wiki_dir / page_rel
        _write_file(path, _render_page(draft))

    _write_file(wiki_dir / "index.md", _render_index(
        list(source_pages.values()),
        list(entity_pages.values()),
        list(concept_pages.values()),
        list(synthesis_pages.values()),
    ))
    _write_file(wiki_dir / "overview.md", _render_overview(all_pages))
    write_canonical_registry(wiki_dir, all_pages)

    log_path = wiki_dir / "log.md"
    existing_log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    _write_file(log_path, _append_log(existing_log, entries))


def resolve_related_paths(
    *,
    source_page_path: str,
    entity_pages: dict[str, WikiDraft],
    concept_pages: dict[str, WikiDraft],
    synthesis_pages: dict[str, WikiDraft],
    refs: list[str],
) -> list[str]:
    return _resolve_related_refs(
        refs,
        source_page_path=source_page_path,
        entity_pages=entity_pages,
        concept_pages=concept_pages,
        synthesis_pages=synthesis_pages,
    )
