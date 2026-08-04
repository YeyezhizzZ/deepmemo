from __future__ import annotations

import re
from pathlib import Path

import yaml

from src.knowledge.atomic_io import atomic_write_text
from src.knowledge.models import CARD_TYPES, EvidenceSource, KnowledgeCard


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_CITATION_RE = re.compile(
    r"\^\[(?P<source_id>src-[a-f0-9]{12})@(?P<source_hash>[a-f0-9]{64}):"
    r"(?P<start>\d+)-(?P<end>\d+)\]"
)
_TYPE_DIRS = {
    "source": "sources",
    "entity": "entities",
    "concept": "concepts",
    "decision": "decisions",
    "pattern": "patterns",
    "lesson": "lessons",
    "synthesis": "syntheses",
    "query": "queries",
}


class WikiStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.knowledge_dir = self.data_dir / "knowledge"
        self.wiki_dir = self.knowledge_dir / "wiki"

    def save_card(self, card: KnowledgeCard) -> KnowledgeCard:
        self._validate_slug(card.slug)
        if card.type not in CARD_TYPES:
            raise ValueError(f"unsupported wiki page type: {card.type}")
        target = self.page_path(card.slug, card.type)
        previous = self.find_page_path(card.slug)
        atomic_write_text(target, self.render_card(card))
        if previous is not None and previous != target:
            previous.unlink(missing_ok=True)
        return card

    def load_card(self, slug: str) -> KnowledgeCard | None:
        self._validate_slug(slug)
        path = self.find_page_path(slug)
        if path is None:
            return None
        return self.parse_card(path.read_text(encoding="utf-8"))

    def list_cards(self) -> list[KnowledgeCard]:
        if not self.wiki_dir.exists():
            return []
        cards: list[KnowledgeCard] = []
        for directory in sorted(set(_TYPE_DIRS.values())):
            root = self.wiki_dir / directory
            if not root.exists():
                continue
            for path in sorted(root.glob("*.md")):
                cards.append(self.parse_card(path.read_text(encoding="utf-8")))
        return sorted(cards, key=lambda card: card.slug)

    def delete_card(self, slug: str) -> bool:
        self._validate_slug(slug)
        path = self.find_page_path(slug)
        if path is None:
            return False
        path.unlink()
        return True

    def page_path(self, slug: str, card_type: str) -> Path:
        self._validate_slug(slug)
        directory = _TYPE_DIRS.get(card_type)
        if directory is None:
            raise ValueError(f"unsupported wiki page type: {card_type}")
        return self.wiki_dir / directory / f"{slug}.md"

    def find_page_path(self, slug: str) -> Path | None:
        self._validate_slug(slug)
        for directory in _TYPE_DIRS.values():
            path = self.wiki_dir / directory / f"{slug}.md"
            if path.is_file():
                return path
        return None

    def relative_page_path(self, slug: str) -> str:
        path = self.find_page_path(slug)
        if path is None:
            raise FileNotFoundError(slug)
        return path.relative_to(self.data_dir).as_posix()

    def render_card(self, card: KnowledgeCard) -> str:
        metadata = {
            "id": card.id,
            "slug": card.slug,
            "title": card.title,
            "type": card.type,
            "density": card.density,
            "sources": [source.to_dict() for source in card.sources],
            "related_cards": list(card.related_cards),
            "tags": list(card.tags),
            "aliases": list(card.aliases),
            "created_at": card.created_at,
            "updated_at": card.updated_at,
            "update_count": card.update_count,
            "staleness_score": card.staleness_score,
            "human_edited": card.human_edited,
            "human_edited_fields": list(card.human_edited_fields),
            "confidence": card.confidence,
            "provenance_state": card.provenance_state,
            "contradicted_by": list(card.contradicted_by),
            "orphaned": card.orphaned,
            "model_id": card.model_id,
            "prompt_version": card.prompt_version,
        }
        frontmatter = yaml.safe_dump(
            metadata,
            allow_unicode=True,
            sort_keys=False,
        ).rstrip()
        citations = self._citation_markers(card.sources)
        definition = card.definition.strip()
        if citations:
            definition = f"{definition} {citations}".strip()

        lines = ["---", frontmatter, "---", "", f"# {card.title}", "", definition, ""]
        if card.key_facts:
            lines.extend(["## Key Facts", ""])
            for fact in card.key_facts:
                suffix = f" {citations}" if citations else ""
                lines.append(f"- {fact}{suffix}")
            lines.append("")
        if card.related_cards:
            lines.extend(["## Related", ""])
            lines.extend(f"- [[{slug}]]" for slug in card.related_cards)
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def parse_card(self, content: str) -> KnowledgeCard:
        metadata, body = self._parse_frontmatter(content)
        definition, key_facts = self._parse_body(body)
        data = {
            **metadata,
            "definition": definition,
            "key_facts": key_facts,
        }
        return KnowledgeCard.from_dict(data)

    def citation_markers(self, content: str) -> list[dict]:
        return [
            {
                "source_id": match.group("source_id"),
                "source_hash": match.group("source_hash"),
                "start_line": int(match.group("start")),
                "end_line": int(match.group("end")),
            }
            for match in _CITATION_RE.finditer(content)
        ]

    def _citation_markers(self, sources: list[EvidenceSource]) -> str:
        markers: list[str] = []
        for source in sources:
            if (
                source.source_id
                and source.source_hash
                and source.start_line > 0
                and source.end_line >= source.start_line
            ):
                markers.append(
                    f"^[{source.source_id}@{source.source_hash}:"
                    f"{source.start_line}-{source.end_line}]"
                )
        return " ".join(dict.fromkeys(markers))

    def _parse_frontmatter(self, content: str) -> tuple[dict, str]:
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError("wiki page is missing YAML frontmatter")
        try:
            closing = lines.index("---", 1)
        except ValueError as exc:
            raise ValueError("wiki page has unclosed YAML frontmatter") from exc
        metadata = yaml.safe_load("\n".join(lines[1:closing])) or {}
        if not isinstance(metadata, dict):
            raise ValueError("wiki page frontmatter must be an object")
        return metadata, "\n".join(lines[closing + 1 :])

    def _parse_body(self, body: str) -> tuple[str, list[str]]:
        lines = body.splitlines()
        definition_lines: list[str] = []
        facts: list[str] = []
        section = "intro"
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                continue
            if stripped == "## Key Facts":
                section = "facts"
                continue
            if stripped.startswith("## "):
                section = "other"
                continue
            if not stripped:
                continue
            clean = _CITATION_RE.sub("", stripped).strip()
            if section == "intro":
                definition_lines.append(clean)
            elif section == "facts" and clean.startswith("- "):
                facts.append(clean[2:].strip())
        return "\n\n".join(definition_lines).strip(), facts

    def _validate_slug(self, slug: str) -> None:
        if not _SLUG_RE.match(slug):
            raise ValueError(f"invalid wiki page slug: {slug}")
