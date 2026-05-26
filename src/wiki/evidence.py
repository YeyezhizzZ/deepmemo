from __future__ import annotations

import hashlib
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from src.wiki.ingest_analyzer import MockDiaryEntry, WikiDraft, WikiSection, _slugify


MARKDOWN_LINK_RE = re.compile(r"\[([^\]]{2,160})\]\(([^)]+)\)")
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
EN_TERM_RE = re.compile(
    r"(?:[A-Z]{2,}[A-Za-z0-9+._-]*|[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+|[A-Z][A-Za-z0-9+._-]{1,})(?:\s+[A-Z][A-Za-z0-9+._-]{1,}){0,3}"
)
ZH_TITLE_SPLIT_RE = re.compile(r"[-–—_:：|｜/]")

ABSTRACT_HINTS = {
    "agent",
    "agents",
    "memory",
    "rag",
    "retrieval",
    "query",
    "rewrite",
    "rewriting",
    "workflow",
    "skill",
    "skills",
    "context",
    "compression",
    "graph",
    "wiki",
    "prompt",
    "search",
    "operator",
    "operators",
}

STOP_TERMS = {
    "ai",
    "api",
    "cli",
    "json",
    "yaml",
    "markdown",
    "readme",
    "deepmemo",
    "diary",
    "wiki",
    "source",
    "sources",
    "agent",
    "agents",
    "memory",
    "tools",
    "workflow",
}


@dataclass(slots=True)
class EvidenceCard:
    id: str
    source_path: str
    source_date: str
    section: str
    statement: str
    raw_excerpt: str
    terms: list[str] = field(default_factory=list)
    importance: str = "normal"


def _source_date(source_path: str) -> str:
    stem = Path(source_path).stem
    return stem if re.fullmatch(r"\d{4}", stem) else ""


def _clean_line(line: str) -> str:
    stripped = line.strip()
    stripped = re.sub(r"^[-*]\s+", "", stripped)
    stripped = re.sub(r"^\d+[.)]\s+", "", stripped)
    return stripped.strip()


def _stable_card_id(source_path: str, section: str, statement: str) -> str:
    digest = hashlib.sha1(f"{source_path}\n{section}\n{statement}".encode("utf-8")).hexdigest()[:10]
    return f"{Path(source_path).stem}-{digest}"


def _normalize_title(value: str) -> str:
    value = value.strip().strip("`'\"“”‘’()[]{}<>《》")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _candidate_terms_from_label(label: str) -> list[str]:
    terms: list[str] = []
    for part in ZH_TITLE_SPLIT_RE.split(label):
        candidate = _normalize_title(part)
        if candidate:
            terms.append(candidate)
    terms.append(_normalize_title(label))
    return terms


def _candidate_terms(text: str) -> list[str]:
    terms: list[str] = []
    for label, _url in MARKDOWN_LINK_RE.findall(text):
        terms.extend(_candidate_terms_from_label(label))
    terms.extend(match.group(0) for match in EN_TERM_RE.finditer(text))

    clean_terms: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = _normalize_title(term)
        if not normalized:
            continue
        slug = _slugify(normalized, "")
        if not slug or slug in STOP_TERMS:
            continue
        if len(slug) <= 2:
            continue
        if slug in seen:
            continue
        seen.add(slug)
        clean_terms.append(normalized)
    return clean_terms


def extract_evidence_cards(entries: list[MockDiaryEntry]) -> list[EvidenceCard]:
    t0 = time.time()
    cards: list[EvidenceCard] = []
    section_counter: Counter[str] = Counter()
    for entry in entries:
        current_section = "其他"
        for raw_line in entry.content.splitlines():
            section_match = SECTION_RE.match(raw_line.strip())
            if section_match:
                current_section = section_match.group(1).strip() or "其他"
                continue

            statement = _clean_line(raw_line)
            if not statement or statement.startswith("#"):
                continue
            if len(statement) < 8:
                continue

            terms = _candidate_terms(statement)
            if not terms:
                continue

            importance = "high" if MARKDOWN_LINK_RE.search(statement) and current_section in {"科研", "工程博客", "开发经验"} else "normal"
            cards.append(
                EvidenceCard(
                    id=_stable_card_id(entry.path, current_section, statement),
                    source_path=entry.path,
                    source_date=_source_date(entry.path),
                    section=current_section,
                    statement=re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", statement),
                    raw_excerpt=statement,
                    terms=terms,
                    importance=importance,
                )
            )
            section_counter[current_section] += 1
    elapsed = time.time() - t0
    high_count = sum(1 for c in cards if c.importance == "high")
    section_str = ", ".join(f"{k}:{v}" for k, v in section_counter.most_common(5))
    print(f"  [evidence] extracted {len(cards)} cards ({high_count} high) from {len(entries)} entries [{elapsed:.1f}s]", flush=True)
    if section_str:
        print(f"  [evidence] section distribution: {section_str}", flush=True)
    return cards


def _canonical_title(term: str) -> str:
    words = re.split(r"[-_\s]+", term.strip())
    if not words:
        return term.strip()
    titled: list[str] = []
    for word in words:
        if word.isupper() or len(word) <= 3 and word.lower() in {"llm", "rag", "api", "cli", "mcp", "ui"}:
            titled.append(word.upper())
        else:
            titled.append(word[:1].upper() + word[1:])
    return " ".join(titled).strip()


def _page_type_for_term(term: str) -> str:
    lowered = _slugify(term, "").replace("-", " ")
    if any(hint in lowered.split() for hint in ABSTRACT_HINTS):
        return "concept"
    return "entity"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def build_drafts_from_evidence(cards: list[EvidenceCard]) -> tuple[dict[str, WikiDraft], dict[str, WikiDraft]]:
    t0 = time.time()
    grouped_sources: dict[str, set[str]] = defaultdict(set)
    grouped_aliases: dict[str, set[str]] = defaultdict(set)
    grouped_cards: dict[str, list[EvidenceCard]] = defaultdict(list)
    grouped_importance: Counter[str] = Counter()

    for card in cards:
        for term in card.terms:
            slug = _slugify(term, "")
            if not slug or slug in STOP_TERMS:
                continue
            grouped_sources[slug].add(card.source_path)
            grouped_aliases[slug].add(term)
            grouped_cards[slug].append(card)
            if card.importance == "high":
                grouped_importance[slug] += 1

    skipped_single_source = 0
    entity_pages: dict[str, WikiDraft] = {}
    concept_pages: dict[str, WikiDraft] = {}
    for slug, sources in sorted(grouped_sources.items()):
        if len(sources) < 2:
            skipped_single_source += 1
            continue

        aliases = sorted(grouped_aliases[slug], key=lambda value: (len(value), value))
        title = _canonical_title(aliases[0] if aliases else slug)
        page_type = _page_type_for_term(title)
        evidence_cards = grouped_cards[slug][:8]
        sections = [
            WikiSection(
                heading="Evidence",
                bullets=_dedupe([f"{card.source_path} · {card.section}：{card.statement}" for card in evidence_cards]),
            )
        ]
        draft = WikiDraft(
            page_type=page_type,
            slug=slug,
            title=title,
            summary=f"由 {len(sources)} 个来源中的 {len(grouped_cards[slug])} 条证据归纳得到。",
            tags=[page_type, "evidence-first"],
            sources=sorted(sources),
            related=[],
            sections=sections,
            aliases=[alias for alias in aliases if alias != title],
        )
        if page_type == "concept":
            concept_pages[slug] = draft
        else:
            entity_pages[slug] = draft

    elapsed = time.time() - t0
    total_terms = len(grouped_sources)
    print(f"  [evidence] {total_terms} unique terms → {len(entity_pages)} entity + {len(concept_pages)} concept pages (skipped {skipped_single_source} single-source terms) [{elapsed:.1f}s]", flush=True)
    return entity_pages, concept_pages
