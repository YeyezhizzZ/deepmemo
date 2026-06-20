from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


CARD_TYPES = {"entity", "concept", "decision", "pattern", "lesson"}
CARD_DENSITIES = {"high", "medium", "low"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class EvidenceSource:
    path: str
    evidence: str
    confidence: float = 0.5

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("EvidenceSource confidence must be between 0.0 and 1.0")

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceSource":
        return cls(
            path=str(data.get("path", "")),
            evidence=str(data.get("evidence", "")),
            confidence=float(data.get("confidence", 0.5)),
        )


@dataclass
class KnowledgeCard:
    slug: str
    title: str
    type: str
    definition: str
    id: str = ""
    density: str = "medium"
    key_facts: list[str] = field(default_factory=list)
    sources: list[EvidenceSource] = field(default_factory=list)
    related_cards: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    update_count: int = 0
    staleness_score: float = 0.0
    human_edited: bool = False
    human_edited_fields: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.type not in CARD_TYPES:
            raise ValueError(f"Unsupported card type: {self.type}")
        if self.density not in CARD_DENSITIES:
            raise ValueError(f"Unsupported density: {self.density}")
        if not self.id:
            self.id = f"kc-{uuid4().hex[:8]}"
        now = _now_iso()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = self.created_at
        self.key_facts = _dedupe_strings(self.key_facts)
        self.related_cards = _dedupe_strings(self.related_cards)
        self.tags = sorted(_dedupe_strings(self.tags))
        self.aliases = _dedupe_strings(self.aliases)
        self.human_edited_fields = _dedupe_strings(self.human_edited_fields)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "type": self.type,
            "density": self.density,
            "definition": self.definition,
            "key_facts": list(self.key_facts),
            "sources": [source.to_dict() for source in self.sources],
            "related_cards": list(self.related_cards),
            "tags": list(self.tags),
            "aliases": list(self.aliases),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "update_count": self.update_count,
            "staleness_score": self.staleness_score,
            "human_edited": self.human_edited,
            "human_edited_fields": list(self.human_edited_fields),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeCard":
        return cls(
            id=str(data.get("id") or ""),
            slug=str(data.get("slug") or ""),
            title=str(data.get("title") or ""),
            type=str(data.get("type") or "concept"),
            density=str(data.get("density") or "medium"),
            definition=str(data.get("definition") or ""),
            key_facts=list(data.get("key_facts") or []),
            sources=[EvidenceSource.from_dict(item) for item in data.get("sources") or []],
            related_cards=list(data.get("related_cards") or []),
            tags=list(data.get("tags") or []),
            aliases=list(data.get("aliases") or []),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            update_count=int(data.get("update_count") or 0),
            staleness_score=float(data.get("staleness_score") or 0.0),
            human_edited=bool(data.get("human_edited") or False),
            human_edited_fields=list(data.get("human_edited_fields") or []),
        )


@dataclass
class CardIndexEntry:
    title: str
    type: str
    tags: list[str] = field(default_factory=list)
    key_terms: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    staleness: float = 0.0
    source_count: int = 0
    human_edited: bool = False

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "type": self.type,
            "tags": list(self.tags),
            "key_terms": list(self.key_terms),
            "related": list(self.related),
            "staleness": self.staleness,
            "source_count": self.source_count,
            "human_edited": self.human_edited,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CardIndexEntry":
        return cls(
            title=str(data.get("title") or ""),
            type=str(data.get("type") or "concept"),
            tags=list(data.get("tags") or []),
            key_terms=list(data.get("key_terms") or []),
            related=list(data.get("related") or []),
            staleness=float(data.get("staleness") or 0.0),
            source_count=int(data.get("source_count") or 0),
            human_edited=bool(data.get("human_edited") or False),
        )


@dataclass
class CardIndex:
    version: int = 1
    cards: dict[str, CardIndexEntry] = field(default_factory=dict)
    tag_index: dict[str, list[str]] = field(default_factory=dict)
    type_index: dict[str, list[str]] = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "cards": {slug: entry.to_dict() for slug, entry in self.cards.items()},
            "tag_index": self.tag_index,
            "type_index": self.type_index,
            "stats": self.stats,
            "updated_at": self.updated_at or _now_iso(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CardIndex":
        return cls(
            version=int(data.get("version") or 1),
            cards={slug: CardIndexEntry.from_dict(entry) for slug, entry in (data.get("cards") or {}).items()},
            tag_index={tag: list(slugs) for tag, slugs in (data.get("tag_index") or {}).items()},
            type_index={card_type: list(slugs) for card_type, slugs in (data.get("type_index") or {}).items()},
            stats=dict(data.get("stats") or {}),
            updated_at=str(data.get("updated_at") or ""),
        )


@dataclass
class CompileResult:
    compiled_files: list[str] = field(default_factory=list)
    card_slugs: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "compiled_files": list(self.compiled_files),
            "card_slugs": list(self.card_slugs),
            "skipped_files": list(self.skipped_files),
            "warnings": list(self.warnings),
        }


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result
