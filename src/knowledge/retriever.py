from __future__ import annotations

from pathlib import Path

from src.knowledge.card_store import CardStore
from src.knowledge.models import KnowledgeCard
from src.ai.types import Evidence


class KnowledgeRetriever:
    def __init__(self, data_dir: str | Path | None = None, store: CardStore | None = None):
        self.store = store or CardStore(data_dir)

    def search(self, query: str, *, limit: int = 8) -> list[dict]:
        needle = query.strip().lower()
        if not needle:
            return []
        scored: list[tuple[float, KnowledgeCard]] = []
        for card in self.store.list_cards():
            score = self._score(card, needle)
            if score > 0:
                scored.append((score, card))
        scored.sort(key=lambda item: (-item[0], item[1].slug))
        return [
            {
                "slug": card.slug,
                "title": card.title,
                "type": card.type,
                "definition": card.definition,
                "tags": card.tags,
                "score": score,
            }
            for score, card in scored[:limit]
        ]

    def search_evidence(self, query: str, *, limit: int = 8) -> list[Evidence]:
        results = self.search(query, limit=limit)
        evidence: list[Evidence] = []
        for result in results:
            card = self.store.load(result["slug"])
            if card is None:
                continue
            excerpt_lines = [
                f"# {card.title}",
                "",
                card.definition,
            ]
            if card.key_facts:
                excerpt_lines.extend(["", "Key facts:"])
                excerpt_lines.extend(f"- {fact}" for fact in card.key_facts)
            if card.sources:
                excerpt_lines.extend(["", "Sources:"])
                excerpt_lines.extend(f"- {source.path}: {source.evidence}" for source in card.sources[:3])
            evidence.append(
                Evidence(
                    path=f"knowledge/cards/{card.slug}.yaml",
                    start_line=1,
                    end_line=max(1, len(excerpt_lines)),
                    excerpt="\n".join(excerpt_lines),
                    score=float(result["score"]),
                    query=query,
                )
            )
        return evidence

    def _score(self, card: KnowledgeCard, query: str) -> float:
        exact_fields = [card.slug, card.title, *card.tags, *card.aliases]
        if any(query == value.lower() for value in exact_fields):
            return 1.0
        haystack = "\n".join(
            [card.slug, card.title, card.definition, *card.tags, *card.aliases, *card.key_facts]
        ).lower()
        if query in haystack:
            return 0.75
        parts = [part for part in query.split() if part]
        if parts and any(part in haystack for part in parts):
            return 0.45
        return 0.0
