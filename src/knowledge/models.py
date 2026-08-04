from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


CARD_TYPES = {
    "source",
    "entity",
    "concept",
    "decision",
    "pattern",
    "lesson",
    "synthesis",
    "query",
}
CARD_DENSITIES = {"high", "medium", "low"}
PROVENANCE_STATES = {"extracted", "merged", "inferred", "ambiguous", "human"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class EvidenceSource:
    path: str
    evidence: str
    confidence: float = 0.5
    source_id: str = ""
    source_hash: str = ""
    start_line: int = 0
    end_line: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("EvidenceSource confidence must be between 0.0 and 1.0")
        if self.start_line < 0 or self.end_line < 0:
            raise ValueError("EvidenceSource line numbers cannot be negative")
        if self.start_line and self.end_line < self.start_line:
            raise ValueError("EvidenceSource end_line cannot precede start_line")

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "source_id": self.source_id,
            "source_hash": self.source_hash,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceSource":
        return cls(
            path=str(data.get("path", "")),
            evidence=str(data.get("evidence", "")),
            confidence=float(data.get("confidence", 0.5)),
            source_id=str(data.get("source_id") or ""),
            source_hash=str(data.get("source_hash") or ""),
            start_line=int(data.get("start_line") or 0),
            end_line=int(data.get("end_line") or 0),
        )


@dataclass(frozen=True)
class SourceSnapshot:
    source_id: str
    origin_path: str
    source_hash: str
    snapshot_path: str
    captured_at: str
    line_count: int
    source_type: str = "file"
    truncated: bool = False
    original_chars: int = 0

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "origin_path": self.origin_path,
            "source_hash": self.source_hash,
            "snapshot_path": self.snapshot_path,
            "captured_at": self.captured_at,
            "line_count": self.line_count,
            "source_type": self.source_type,
            "truncated": self.truncated,
            "original_chars": self.original_chars,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SourceSnapshot":
        return cls(
            source_id=str(data["source_id"]),
            origin_path=str(data["origin_path"]),
            source_hash=str(data["source_hash"]),
            snapshot_path=str(data["snapshot_path"]),
            captured_at=str(data["captured_at"]),
            line_count=int(data["line_count"]),
            source_type=str(data.get("source_type") or "file"),
            truncated=bool(data.get("truncated") or False),
            original_chars=int(data.get("original_chars") or 0),
        )


@dataclass
class ExtractedKnowledge:
    slug: str
    title: str
    type: str
    summary: str
    key_facts: list[str]
    citations: list[EvidenceSource]
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    related_cards: list[str] = field(default_factory=list)
    confidence: float = 0.5
    provenance_state: str = "extracted"
    contradicted_by: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.type not in CARD_TYPES:
            raise ValueError(f"Unsupported extracted knowledge type: {self.type}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Extracted knowledge confidence must be between 0.0 and 1.0")
        if self.provenance_state not in PROVENANCE_STATES:
            raise ValueError(f"Unsupported provenance state: {self.provenance_state}")
        self.key_facts = _dedupe_strings(self.key_facts)
        self.tags = sorted(_dedupe_strings(self.tags))
        self.aliases = _dedupe_strings(self.aliases)
        self.related_cards = _dedupe_strings(self.related_cards)
        self.contradicted_by = _dedupe_strings(self.contradicted_by)

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "type": self.type,
            "summary": self.summary,
            "key_facts": list(self.key_facts),
            "citations": [citation.to_dict() for citation in self.citations],
            "tags": list(self.tags),
            "aliases": list(self.aliases),
            "related_cards": list(self.related_cards),
            "confidence": self.confidence,
            "provenance_state": self.provenance_state,
            "contradicted_by": list(self.contradicted_by),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExtractedKnowledge":
        return cls(
            slug=str(data.get("slug") or ""),
            title=str(data.get("title") or ""),
            type=str(data.get("type") or "concept"),
            summary=str(data.get("summary") or ""),
            key_facts=list(data.get("key_facts") or []),
            citations=[
                EvidenceSource.from_dict(item) for item in data.get("citations") or []
            ],
            tags=list(data.get("tags") or []),
            aliases=list(data.get("aliases") or []),
            related_cards=list(data.get("related_cards") or []),
            confidence=float(data.get("confidence", 0.5)),
            provenance_state=str(data.get("provenance_state") or "extracted"),
            contradicted_by=list(data.get("contradicted_by") or []),
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
    confidence: float = 0.5
    provenance_state: str = "extracted"
    contradicted_by: list[str] = field(default_factory=list)
    orphaned: bool = False
    model_id: str = ""
    prompt_version: str = ""

    def __post_init__(self) -> None:
        if self.type not in CARD_TYPES:
            raise ValueError(f"Unsupported card type: {self.type}")
        if self.density not in CARD_DENSITIES:
            raise ValueError(f"Unsupported density: {self.density}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("KnowledgeCard confidence must be between 0.0 and 1.0")
        if self.provenance_state not in PROVENANCE_STATES:
            raise ValueError(f"Unsupported provenance state: {self.provenance_state}")
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
        self.contradicted_by = _dedupe_strings(self.contradicted_by)

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
            "confidence": self.confidence,
            "provenance_state": self.provenance_state,
            "contradicted_by": list(self.contradicted_by),
            "orphaned": self.orphaned,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
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
            confidence=float(data.get("confidence", 0.5)),
            provenance_state=str(data.get("provenance_state") or "extracted"),
            contradicted_by=list(data.get("contradicted_by") or []),
            orphaned=bool(data.get("orphaned") or False),
            model_id=str(data.get("model_id") or ""),
            prompt_version=str(data.get("prompt_version") or ""),
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
    deleted_files: list[str] = field(default_factory=list)
    candidate_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    prompt_version: str = ""

    def to_dict(self) -> dict:
        return {
            "compiled_files": list(self.compiled_files),
            "card_slugs": list(self.card_slugs),
            "skipped_files": list(self.skipped_files),
            "deleted_files": list(self.deleted_files),
            "candidate_ids": list(self.candidate_ids),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "prompt_version": self.prompt_version,
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
