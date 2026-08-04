from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from src.knowledge.card_store import CardStore
from src.knowledge.embedding_index import (
    EmbeddingIndex,
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from src.knowledge.models import KnowledgeCard

if TYPE_CHECKING:
    from src.ai.types import Evidence


class KnowledgeRetriever:
    def __init__(
        self,
        data_dir: str | Path | None = None,
        store: CardStore | None = None,
        *,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.store = store or CardStore(data_dir)
        self.index_path = self.store.knowledge_dir / ".deepmemo" / "search.sqlite3"
        embeddings_enabled = os.getenv(
            "DEEPMEMO_KNOWLEDGE_EMBEDDINGS",
            "",
        ).lower() in {"1", "true", "yes"}
        self.embedding_provider = (
            embedding_provider
            if embedding_provider is not None
            else OpenAIEmbeddingProvider() if embeddings_enabled else None
        )
        self.embedding_index = EmbeddingIndex(self.store.data_dir)
        self.last_warnings: list[dict[str, str]] = []

    def search(self, query: str, *, limit: int = 8) -> list[dict]:
        normalized = query.strip()
        self.last_warnings = []
        if not normalized:
            return []
        cards = self.store.list_cards()
        if not cards:
            return []
        try:
            ranked = self._fts_search(cards, normalized, limit)
        except sqlite3.OperationalError:
            ranked = self._lexical_search(cards, normalized, limit)
            self.last_warnings.append(
                {
                    "code": "fts5-unavailable",
                    "message": "SQLite FTS5 is unavailable; lexical fallback was used.",
                }
            )
        if self.embedding_provider is not None:
            try:
                semantic = self.embedding_index.search(
                    cards,
                    normalized,
                    self.embedding_provider,
                    limit=max(limit, 15),
                )
                ranked = self._fuse(ranked, semantic, cards, limit)
            except Exception:
                self.last_warnings.append(
                    {
                        "code": "embedding-unavailable",
                        "message": "Embedding retrieval failed; FTS5 and graph retrieval remain active.",
                    }
                )
        return self._expand_graph(ranked, cards, limit)

    def search_evidence(self, query: str, *, limit: int = 8) -> list["Evidence"]:
        from src.ai.types import Evidence

        results = self.search(query, limit=limit)
        evidence: list[Evidence] = []
        for result in results:
            card = self.store.load(result["slug"])
            if card is None:
                continue
            page_path = self.store.wiki_store.find_page_path(card.slug)
            if page_path is None:
                continue
            content = page_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            evidence.append(
                Evidence(
                    path=page_path.relative_to(self.store.data_dir).as_posix(),
                    start_line=1,
                    end_line=max(1, len(lines)),
                    excerpt=content,
                    score=float(result["score"]),
                    query=query,
                )
            )
        return evidence

    def _fts_search(
        self,
        cards: list[KnowledgeCard],
        query: str,
        limit: int,
    ) -> list[dict]:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.index_path) as connection:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_pages USING fts5(
                    slug UNINDEXED,
                    title,
                    definition,
                    key_facts,
                    tags,
                    aliases,
                    tokenize = 'unicode61'
                )
                """
            )
            connection.execute("DELETE FROM knowledge_pages")
            connection.executemany(
                """
                INSERT INTO knowledge_pages
                    (slug, title, definition, key_facts, tags, aliases)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        card.slug,
                        card.title,
                        card.definition,
                        "\n".join(card.key_facts),
                        " ".join(card.tags),
                        " ".join(card.aliases),
                    )
                    for card in cards
                ],
            )
            tokens = re.findall(r"[\w\u4e00-\u9fff-]+", query.lower())
            if not tokens:
                return []
            expression = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens)
            rows = connection.execute(
                """
                SELECT slug, bm25(knowledge_pages, 0.0, 4.0, 2.0, 1.5, 2.0, 1.5)
                FROM knowledge_pages
                WHERE knowledge_pages MATCH ?
                ORDER BY bm25(knowledge_pages)
                LIMIT ?
                """,
                (expression, limit),
            ).fetchall()
        card_map = {card.slug: card for card in cards}
        results: list[dict] = []
        for slug, rank in rows:
            card = card_map.get(slug)
            if card is None:
                continue
            score = 1.0 / (1.0 + abs(float(rank)))
            results.append(self._result(card, score, "fts5"))
        return results

    def _lexical_search(
        self,
        cards: list[KnowledgeCard],
        query: str,
        limit: int,
    ) -> list[dict]:
        tokens = re.findall(r"[\w\u4e00-\u9fff-]+", query.lower())
        scored: list[tuple[float, KnowledgeCard]] = []
        for card in cards:
            title = f"{card.slug} {card.title} {' '.join(card.aliases)}".lower()
            body = (
                f"{card.definition} {' '.join(card.key_facts)} {' '.join(card.tags)}"
            ).lower()
            score = sum(2.0 for token in tokens if token in title)
            score += sum(1.0 for token in tokens if token in body)
            if score:
                scored.append((score, card))
        scored.sort(key=lambda item: (-item[0], item[1].slug))
        ceiling = scored[0][0] if scored else 1.0
        return [
            self._result(card, score / ceiling, "lexical")
            for score, card in scored[:limit]
        ]

    def _expand_graph(
        self,
        ranked: list[dict],
        cards: list[KnowledgeCard],
        limit: int,
    ) -> list[dict]:
        card_map = {card.slug: card for card in cards}
        adjacency: dict[str, set[str]] = {slug: set() for slug in card_map}
        for relation in self.store.relation_store.list():
            left = str(relation.get("from") or "")
            right = str(relation.get("to") or "")
            if left in adjacency and right in adjacency:
                adjacency[left].add(right)
                adjacency[right].add(left)
        results = list(ranked)
        seen = {result["slug"] for result in results}
        for result in list(ranked):
            card = card_map.get(result["slug"])
            if card is None:
                continue
            for related in sorted(adjacency.get(card.slug, set())):
                if related in seen or related not in card_map:
                    continue
                results.append(
                    self._result(
                        card_map[related],
                        max(0.15, float(result["score"]) * 0.5),
                        "graph",
                    )
                )
                seen.add(related)
                if len(results) >= limit:
                    return results
        return results[:limit]

    def _fuse(
        self,
        lexical: list[dict],
        semantic: list[tuple[str, float]],
        cards: list[KnowledgeCard],
        limit: int,
    ) -> list[dict]:
        if not semantic:
            return lexical
        card_map = {card.slug: card for card in cards}
        scores: dict[str, float] = {}
        for rank, result in enumerate(lexical, start=1):
            scores[result["slug"]] = scores.get(result["slug"], 0.0) + 1.0 / (
                60 + rank
            )
        for rank, (slug, _) in enumerate(semantic, start=1):
            scores[slug] = scores.get(slug, 0.0) + 1.0 / (60 + rank)
        ordered = sorted(scores, key=lambda slug: (-scores[slug], slug))[:limit]
        maximum = max((scores[slug] for slug in ordered), default=1.0)
        return [
            self._result(
                card_map[slug],
                scores[slug] / maximum,
                "hybrid" if any(item["slug"] == slug for item in lexical) else "vector",
            )
            for slug in ordered
            if slug in card_map
        ]

    def _result(self, card: KnowledgeCard, score: float, retrieval: str) -> dict:
        path = self.store.wiki_store.find_page_path(card.slug)
        return {
            "slug": card.slug,
            "title": card.title,
            "type": card.type,
            "definition": card.definition,
            "tags": card.tags,
            "score": round(score, 6),
            "retrieval": retrieval,
            "path": path.relative_to(self.store.data_dir).as_posix() if path else "",
            "sources": json.loads(
                json.dumps(
                    [source.to_dict() for source in card.sources],
                    ensure_ascii=False,
                )
            ),
        }
