from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.knowledge.atomic_io import atomic_write_json, atomic_write_text
from src.knowledge.models import CardIndex, CardIndexEntry, KnowledgeCard
from src.knowledge.relation_store import RelationStore
from src.knowledge.source_store import SourceStore
from src.knowledge.wiki_store import WikiStore


DATA_DIR = Path(os.getenv("DEEPMEMO_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class CardStore:
    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.knowledge_dir = self.data_dir / "knowledge"
        self.wiki_store = WikiStore(self.data_dir)
        self.source_store = SourceStore(self.data_dir)
        self.relation_store = RelationStore(self.data_dir)
        # Compatibility alias for callers that only need the storage root.
        self.cards_dir = self.wiki_store.wiki_dir
        self.index_path = self.knowledge_dir / "index.json"
        self.markdown_index_path = self.knowledge_dir / "index.md"

    def save(self, card: KnowledgeCard, *, rebuild_index: bool = True) -> KnowledgeCard:
        self._validate_slug(card.slug)
        self.wiki_store.save_card(card)
        if rebuild_index:
            self.rebuild_index()
        return card

    def load(self, slug: str) -> KnowledgeCard | None:
        self._validate_slug(slug)
        return self.wiki_store.load_card(slug)

    def list_cards(self, *, card_type: str | None = None, tag: str | None = None) -> list[KnowledgeCard]:
        cards: list[KnowledgeCard] = []
        for card in self.wiki_store.list_cards():
            if card_type and card.type != card_type:
                continue
            if tag and tag not in card.tags:
                continue
            cards.append(card)
        return cards

    def delete(self, slug: str) -> bool:
        self._validate_slug(slug)
        if not self.wiki_store.delete_card(slug):
            return False
        self.rebuild_index()
        return True

    def card_path(self, slug: str) -> Path:
        self._validate_slug(slug)
        return self.wiki_store.find_page_path(slug) or self.wiki_store.page_path(slug, "concept")

    def load_index(self) -> CardIndex:
        if not self.index_path.exists():
            return self.rebuild_index()
        import json

        with self.index_path.open("r", encoding="utf-8") as handle:
            return CardIndex.from_dict(json.load(handle))

    def rebuild_index(self) -> CardIndex:
        import json

        cards = self.list_cards()
        entries: dict[str, CardIndexEntry] = {}
        tag_index: dict[str, list[str]] = defaultdict(list)
        type_index: dict[str, list[str]] = defaultdict(list)
        by_type: dict[str, int] = defaultdict(int)
        staleness_total = 0.0

        for card in cards:
            key_terms = self._key_terms(card)
            entries[card.slug] = CardIndexEntry(
                title=card.title,
                type=card.type,
                tags=list(card.tags),
                key_terms=key_terms,
                related=list(card.related_cards),
                staleness=card.staleness_score,
                source_count=len(card.sources),
                human_edited=card.human_edited,
            )
            type_index[card.type].append(card.slug)
            by_type[card.type] += 1
            staleness_total += card.staleness_score
            for tag in card.tags:
                tag_index[tag].append(card.slug)

        stats = {
            "total_cards": len(cards),
            "by_type": dict(sorted(by_type.items())),
            "avg_staleness": round(staleness_total / len(cards), 4) if cards else 0.0,
            "last_compile": None,
        }
        index = CardIndex(
            cards=dict(sorted(entries.items())),
            tag_index={tag: sorted(slugs) for tag, slugs in sorted(tag_index.items())},
            type_index={card_type: sorted(slugs) for card_type, slugs in sorted(type_index.items())},
            stats=stats,
            updated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )
        atomic_write_json(self.index_path, index.to_dict())
        atomic_write_text(self.markdown_index_path, self._render_markdown_index(cards))
        self.relation_store.rebuild(cards)
        return index

    def resolve_source_path(self, value: str | Path, *, must_exist: bool = True) -> Path:
        return self.source_store.resolve_origin_path(value, must_exist=must_exist)

    def relative_path(self, path: str | Path) -> str:
        return Path(path).resolve().relative_to(self.data_dir.resolve()).as_posix()

    def migrate_legacy_cards(self) -> dict[str, list[str]]:
        legacy_dir = self.knowledge_dir / "cards"
        migrated: list[str] = []
        skipped: list[str] = []
        if not legacy_dir.exists():
            return {"migrated": migrated, "skipped": skipped}
        for path in sorted(legacy_dir.glob("*.yaml")):
            with path.open(encoding="utf-8") as handle:
                card = KnowledgeCard.from_dict(yaml.safe_load(handle) or {})
            if self.load(card.slug) is not None:
                skipped.append(card.slug)
                continue
            self.wiki_store.save_card(card)
            migrated.append(card.slug)
        self.rebuild_index()
        return {"migrated": migrated, "skipped": skipped}

    def _key_terms(self, card: KnowledgeCard) -> list[str]:
        values = [card.slug, card.title, *card.tags, *card.aliases, *card.key_facts]
        terms: list[str] = []
        seen: set[str] = set()
        for value in values:
            for term in re.findall(r"[\w\u4e00-\u9fff-]+", value.lower()):
                term = term.strip("-_")
                if len(term) >= 2 and term not in seen:
                    terms.append(term)
                    seen.add(term)
        return terms

    def _validate_slug(self, slug: str) -> None:
        if not _SLUG_RE.match(slug):
            raise ValueError(f"Invalid card slug: {slug}")

    def _render_markdown_index(self, cards: list[KnowledgeCard]) -> str:
        lines = [
            "# Knowledge Index",
            "",
            "Generated from reviewed Wiki pages. Edit pages, not this index.",
            "",
        ]
        grouped: dict[str, list[KnowledgeCard]] = defaultdict(list)
        for card in cards:
            grouped[card.type].append(card)
        for card_type in sorted(grouped):
            lines.extend([f"## {card_type.title()}s", ""])
            for card in sorted(grouped[card_type], key=lambda item: item.title.lower()):
                path = self.wiki_store.relative_page_path(card.slug)
                relative = Path(path).relative_to("knowledge").with_suffix("").as_posix()
                lines.append(f"- [[{relative}|{card.title}]] — {card.definition}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
