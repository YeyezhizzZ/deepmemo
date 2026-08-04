from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Protocol

from src.knowledge.models import KnowledgeCard
from src.services.llm_service import LLMService, llm_service


class EmbeddingProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingProvider:
    def __init__(self, service: LLMService | None = None):
        self.service = service or llm_service

    @property
    def model_id(self) -> str:
        return self.service.embedding_model()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.service.embed(texts)


class EmbeddingIndex:
    def __init__(self, data_dir: str | Path):
        self.path = Path(data_dir) / "knowledge" / ".deepmemo" / "embeddings.sqlite3"

    def search(
        self,
        cards: list[KnowledgeCard],
        query: str,
        provider: EmbeddingProvider,
        *,
        limit: int,
    ) -> list[tuple[str, float]]:
        self.sync(cards, provider)
        query_vectors = provider.embed([query])
        if len(query_vectors) != 1:
            raise ValueError("embedding provider returned an invalid query batch")
        query_vector = query_vectors[0]
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT slug, vector FROM page_embeddings WHERE model_id = ?",
                (provider.model_id,),
            ).fetchall()
        ranked = [
            (str(slug), self._cosine(query_vector, json.loads(vector)))
            for slug, vector in rows
        ]
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked[:limit]

    def sync(
        self,
        cards: list[KnowledgeCard],
        provider: EmbeddingProvider,
    ) -> None:
        model_id = provider.model_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            existing = {
                slug: (content_hash, stored_model)
                for slug, content_hash, stored_model in connection.execute(
                    "SELECT slug, content_hash, model_id FROM page_embeddings"
                )
            }
            live = {card.slug for card in cards}
            for slug in set(existing) - live:
                connection.execute(
                    "DELETE FROM page_embeddings WHERE slug = ?",
                    (slug,),
                )

            changed: list[tuple[KnowledgeCard, str, str]] = []
            for card in cards:
                text = self._embedding_text(card)
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if existing.get(card.slug) != (content_hash, model_id):
                    changed.append((card, text, content_hash))

            if changed:
                vectors = provider.embed([text for _, text, _ in changed])
                if len(vectors) != len(changed):
                    raise ValueError("embedding provider returned an invalid batch size")
                for (card, _, content_hash), vector in zip(changed, vectors, strict=True):
                    if not vector or not all(math.isfinite(float(value)) for value in vector):
                        raise ValueError(f"invalid embedding vector for {card.slug}")
                    connection.execute(
                        """
                        INSERT INTO page_embeddings (slug, content_hash, model_id, vector)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(slug) DO UPDATE SET
                            content_hash = excluded.content_hash,
                            model_id = excluded.model_id,
                            vector = excluded.vector
                        """,
                        (
                            card.slug,
                            content_hash,
                            model_id,
                            json.dumps([float(value) for value in vector]),
                        ),
                    )
            connection.commit()

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM page_embeddings").fetchone()
        return int(row[0])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS page_embeddings (
                slug TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                model_id TEXT NOT NULL,
                vector TEXT NOT NULL
            )
            """
        )
        return connection

    def _embedding_text(self, card: KnowledgeCard) -> str:
        return "\n".join(
            [
                card.title,
                card.definition,
                *card.key_facts,
                " ".join(card.tags),
                " ".join(card.aliases),
            ]
        )

    def _cosine(self, left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
        right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return dot / (left_norm * right_norm)
