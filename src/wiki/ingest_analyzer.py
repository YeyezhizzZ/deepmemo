from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.wiki.path_utils import normalize_rel_path


DEFAULT_RAW_SEED_DIR = Path("data/raw/mock/diary")


def _slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or fallback


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


def _merge_text(existing: str, incoming: str) -> str:
    existing = existing.strip()
    incoming = incoming.strip()
    if not existing:
        return incoming
    if not incoming:
        return existing
    if incoming in existing:
        return existing
    if existing in incoming:
        return incoming
    return f"{existing}\n\n{incoming}"


def _parse_json_block(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def _load_llm_service():
    try:
        from src.services.llm_service import llm_service
    except Exception:
        return None
    return llm_service


@dataclass(slots=True)
class MockDiaryEntry:
    path: str
    title: str
    content: str


@dataclass(slots=True)
class WikiSection:
    heading: str
    bullets: list[str] = field(default_factory=list)
    callout: str | None = None


@dataclass(slots=True)
class WikiDraft:
    page_type: str
    slug: str
    title: str
    summary: str
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    sections: list[WikiSection] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


def load_mock_diary_entries(seed_dir: Path = DEFAULT_RAW_SEED_DIR) -> list[MockDiaryEntry]:
    if not seed_dir.exists():
        return []

    entries: list[MockDiaryEntry] = []
    for path in sorted(seed_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        title = path.stem
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                break
        entries.append(
            MockDiaryEntry(
                path=normalize_rel_path(str(path)),
                title=title or path.stem,
                content=content,
            )
        )
    return entries


def _heuristic_analysis(entry: MockDiaryEntry) -> dict[str, Any]:
    body_lines = [line.strip() for line in entry.content.splitlines() if line.strip()]
    summary = ""
    for line in body_lines:
        if not line.startswith("#"):
            summary = line
            break

    tags: list[str] = []
    source_slug = _slugify(entry.title, "mock-diary")
    if "LLM Wiki" in entry.content or "wiki" in entry.content.lower():
        tags.extend(["llm-wiki", "knowledge-base"])
    if "context" in entry.content.lower():
        tags.append("context-compression")
    if "model" in entry.content.lower():
        tags.append("llm")

    entities: list[dict[str, Any]] = []
    concepts: list[dict[str, Any]] = []
    syntheses: list[dict[str, Any]] = []

    if "LLM Wiki" in entry.content or "wiki" in entry.content.lower():
        entities.append(
            {
                "slug": "deepmemo",
                "title": "DeepMemo",
                "summary": "The project itself as the knowledge system being compiled.",
                "tags": ["project", "workspace"],
                "related": [entry.path],
                "sections": [{"heading": "Role", "bullets": ["Acts as the host workspace for raw, wiki, and policy layers."]}],
            }
        )
        concepts.append(
            {
                "slug": "knowledge-compilation",
                "title": "Knowledge Compilation",
                "summary": "Turning raw notes into a maintained wiki rather than a one-shot retrieval layer.",
                "tags": ["process", "wiki"],
                "related": [entry.path],
                "sections": [{"heading": "Why it matters", "bullets": ["Compounded maintenance beats repeated rediscovery."]}],
            }
        )

    if "重复" in entry.content or "duplicate" in entry.content.lower() or "same topic" in entry.content.lower():
        concepts.append(
            {
                "slug": "deduplication",
                "title": "Deduplication",
                "summary": "Repeated facts should merge into one durable wiki page with multiple source pointers.",
                "tags": ["maintenance", "merge"],
                "related": [entry.path],
                "sections": [{"heading": "Rule", "bullets": ["Keep provenance, merge the knowledge asset."]}],
            }
        )
        syntheses.append(
            {
                "slug": "duplicate-source-policy",
                "title": "Duplicate Source Policy",
                "summary": "Diary and raw can repeat the same facts; the wiki should merge evidence rather than duplicate pages.",
                "tags": ["policy", "dedup"],
                "related": [entry.path],
                "sections": [{"heading": "Decision", "bullets": ["Preserve all sources, avoid duplicate knowledge nodes."]}],
            }
        )

    if "LLMService" in entry.content or "local model" in entry.content.lower():
        concepts.append(
            {
                "slug": "local-llm-service",
                "title": "Local LLMService",
                "summary": "A single internal entry point for local-model calls, keeping the generation pipeline aligned with the project.",
                "tags": ["implementation", "model"],
                "related": [entry.path],
                "sections": [{"heading": "Pattern", "bullets": ["Use the project service wrapper instead of inventing a new API layer."]}],
            }
        )

    if not summary:
        summary = "Mock diary entry used to validate wiki generation."

    source = {
        "slug": source_slug,
        "title": entry.title,
        "summary": summary,
        "tags": _dedupe_preserve_order(tags or ["mock", "diary"]),
        "related": [item["slug"] for item in entities + concepts + syntheses],
        "sections": [
            {"heading": "Highlights", "bullets": body_lines[:6]},
        ],
    }
    return {
        "source": source,
        "entities": entities,
        "concepts": concepts,
        "syntheses": syntheses,
    }


def _normalize_section(item: dict[str, Any]) -> WikiSection:
    return WikiSection(
        heading=str(item.get("heading") or "Section").strip() or "Section",
        bullets=[str(b).strip() for b in item.get("bullets") or [] if str(b).strip()],
        callout=str(item.get("callout") or "").strip() or None,
    )


def normalize_draft(page_type: str, item: dict[str, Any], source_path: str) -> WikiDraft:
    raw_slug = str(item.get("slug") or item.get("title") or page_type)
    slug = _slugify(raw_slug, f"{page_type}-{source_path.split('/')[-1].replace('.md', '')}")
    return WikiDraft(
        page_type=page_type,
        slug=slug,
        title=str(item.get("title") or raw_slug).strip() or slug,
        summary=str(item.get("summary") or "").strip(),
        tags=[str(v).strip() for v in item.get("tags") or [] if str(v).strip()],
        sources=[str(v).strip() for v in item.get("sources") or [source_path] if str(v).strip()],
        related=[str(v).strip() for v in item.get("related") or [] if str(v).strip()],
        sections=[_normalize_section(section) for section in item.get("sections") or [] if isinstance(section, dict)],
        aliases=[str(v).strip() for v in item.get("aliases") or [] if str(v).strip()],
    )


def _merge_sections(existing: list[WikiSection], incoming: list[WikiSection]) -> list[WikiSection]:
    merged: dict[str, WikiSection] = {
        section.heading: WikiSection(section.heading, list(section.bullets), section.callout) for section in existing
    }
    for section in incoming:
        current = merged.get(section.heading)
        if not current:
            merged[section.heading] = WikiSection(section.heading, list(section.bullets), section.callout)
            continue
        current.bullets = _dedupe_preserve_order(current.bullets + section.bullets)
        if not current.callout and section.callout:
            current.callout = section.callout
    return list(merged.values())


def merge_draft(existing: WikiDraft, incoming: WikiDraft) -> WikiDraft:
    return WikiDraft(
        page_type=existing.page_type,
        slug=existing.slug,
        title=existing.title if len(existing.title) >= len(incoming.title) else incoming.title,
        summary=_merge_text(existing.summary, incoming.summary),
        tags=_dedupe_preserve_order(existing.tags + incoming.tags),
        sources=_dedupe_preserve_order(existing.sources + incoming.sources),
        related=_dedupe_preserve_order(existing.related + incoming.related),
        sections=_merge_sections(existing.sections, incoming.sections),
        aliases=_dedupe_preserve_order(existing.aliases + incoming.aliases + ([incoming.title] if incoming.title != existing.title else [])),
    )


def analyze_entry(entry: MockDiaryEntry, existing_page_titles: list[str]) -> dict[str, Any]:
    llm_service = _load_llm_service()
    if llm_service is None:
        return _heuristic_analysis(entry)

    import yaml
    prompt_config_path = Path("config/wiki_prompts.yaml")
    if prompt_config_path.exists():
        with open(prompt_config_path, "r", encoding="utf-8") as f:
            prompts = yaml.safe_load(f)
            system_prompt = prompts.get("ingest_analyzer", {}).get("system_prompt", "")
    else:
        system_prompt = ""

    if not system_prompt:
        print("Warning: config/wiki_prompts.yaml not found or empty, using empty system prompt", flush=True)

    payload = {
        "source_path": entry.path,
        "source_title": entry.title,
        "existing_page_titles": existing_page_titles,
        "content": entry.content,
    }
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]

    try:
        response = llm_service.chat(messages)
        content = response.choices[0].message.content or ""
        parsed = _parse_json_block(content)
        if parsed:
            return parsed
    except Exception:
        pass

    return _heuristic_analysis(entry)
