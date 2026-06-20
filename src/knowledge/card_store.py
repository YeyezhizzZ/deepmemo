from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.knowledge.models import CardIndex, CardIndexEntry, KnowledgeCard


DATA_DIR = Path(os.getenv("DEEPMEMO_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class CardStore:
    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.knowledge_dir = self.data_dir / "knowledge"
        self.cards_dir = self.knowledge_dir / "cards"
        self.index_path = self.knowledge_dir / "index.json"

    def save(self, card: KnowledgeCard, *, rebuild_index: bool = True) -> KnowledgeCard:
        self._validate_slug(card.slug)
        self.cards_dir.mkdir(parents=True, exist_ok=True)
        path = self.card_path(card.slug)
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(card.to_dict(), handle, allow_unicode=True, sort_keys=False)
        if rebuild_index:
            self.rebuild_index()
        return card

    def load(self, slug: str) -> KnowledgeCard | None:
        self._validate_slug(slug)
        path = self.card_path(slug)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return KnowledgeCard.from_dict(data)

    def list_cards(self, *, card_type: str | None = None, tag: str | None = None) -> list[KnowledgeCard]:
        if not self.cards_dir.exists():
            return []
        cards: list[KnowledgeCard] = []
        for path in sorted(self.cards_dir.glob("*.yaml")):
            card = self.load(path.stem)
            if card is None:
                continue
            if card_type and card.type != card_type:
                continue
            if tag and tag not in card.tags:
                continue
            cards.append(card)
        return cards

    def delete(self, slug: str) -> bool:
        self._validate_slug(slug)
        path = self.card_path(slug)
        if not path.exists():
            return False
        path.unlink()
        self.rebuild_index()
        return True

    def card_path(self, slug: str) -> Path:
        self._validate_slug(slug)
        return self.cards_dir / f"{slug}.yaml"

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
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("w", encoding="utf-8") as handle:
            json.dump(index.to_dict(), handle, ensure_ascii=False, indent=2)
        return index

    def resolve_source_path(self, value: str | Path, *, must_exist: bool = True) -> Path:
        raw = Path(value)
        if raw.is_absolute():
            candidate = raw.resolve()
        else:
            normalized = str(value).strip().replace("\\", "/")
            while normalized.startswith("./"):
                normalized = normalized[2:]
            if normalized.startswith("data/"):
                normalized = normalized[len("data/") :]
            candidate = (self.data_dir / normalized).resolve()

        data_root = self.data_dir.resolve()
        try:
            candidate.relative_to(data_root)
        except ValueError as exc:
            raise ValueError("source path escapes data directory") from exc
        if candidate.suffix.lower() != ".md":
            raise ValueError("knowledge compiler only accepts Markdown files")
        if must_exist and not candidate.exists():
            raise FileNotFoundError(candidate)
        return candidate

    def relative_path(self, path: str | Path) -> str:
        return Path(path).resolve().relative_to(self.data_dir.resolve()).as_posix()

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
