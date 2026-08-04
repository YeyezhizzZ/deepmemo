from __future__ import annotations

import re

from src.knowledge.models import (
    EvidenceSource,
    ExtractedKnowledge,
    KnowledgeCard,
    SourceSnapshot,
)
from src.knowledge.source_store import SourceStore


class FakeKnowledgeProvider:
    def __init__(self, *, confidence: float = 0.9, provenance_state: str = "extracted"):
        self.confidence = confidence
        self.provenance_state = provenance_state
        self.extract_calls = 0
        self.generate_calls = 0

    @property
    def model_id(self) -> str:
        return "fake-knowledge-model"

    def extract(
        self,
        snapshot: SourceSnapshot,
        numbered_content: str,
        existing_index: str,
        source_store: SourceStore,
    ) -> list[ExtractedKnowledge]:
        del existing_index
        self.extract_calls += 1
        numbered_lines = []
        for raw in numbered_content.splitlines():
            match = re.match(r"\s*(\d+)\s+\|\s?(.*)", raw)
            if match:
                numbered_lines.append((int(match.group(1)), match.group(2)))
        title_line = next(
            ((number, text[2:].strip()) for number, text in numbered_lines if text.startswith("# ")),
            None,
        )
        title = title_line[1] if title_line else "Knowledge Item"
        content_lines = [
            (number, text.strip())
            for number, text in numbered_lines
            if text.strip()
            and not text.startswith("#")
            and not text.lower().startswith("tags:")
        ]
        if not content_lines:
            return []
        start_line = content_lines[0][0]
        end_line = content_lines[-1][0]
        evidence = source_store.excerpt(snapshot, start_line, end_line)
        tags = []
        for _, text in numbered_lines:
            if text.lower().startswith("tags:"):
                tags.extend(value.strip() for value in text.split(":", 1)[1].split(","))
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "knowledge-item"
        facts = [text.lstrip("-* ").strip() for _, text in content_lines[:5]]
        return [
            ExtractedKnowledge(
                slug=slug,
                title=title,
                type="concept",
                summary=facts[0],
                key_facts=facts,
                citations=[
                    EvidenceSource(
                        path=snapshot.origin_path,
                        evidence=evidence,
                        confidence=1.0,
                        source_id=snapshot.source_id,
                        source_hash=snapshot.source_hash,
                        start_line=start_line,
                        end_line=end_line,
                    )
                ],
                tags=tags,
                confidence=self.confidence,
                provenance_state=self.provenance_state,
            )
        ]

    def generate(
        self,
        slug: str,
        items: list[ExtractedKnowledge],
        existing: KnowledgeCard | None,
    ) -> KnowledgeCard:
        del existing
        self.generate_calls += 1
        first = items[0]
        sources = []
        seen = set()
        for item in items:
            for source in item.citations:
                key = (
                    source.source_id,
                    source.source_hash,
                    source.start_line,
                    source.end_line,
                )
                if key not in seen:
                    sources.append(source)
                    seen.add(key)
        return KnowledgeCard(
            slug=slug,
            title=first.title,
            type=first.type,
            definition=first.summary,
            key_facts=list(dict.fromkeys(fact for item in items for fact in item.key_facts)),
            sources=sources,
            tags=sorted({tag for item in items for tag in item.tags}),
            aliases=list(dict.fromkeys(alias for item in items for alias in item.aliases)),
            related_cards=list(
                dict.fromkeys(related for item in items for related in item.related_cards)
            ),
            confidence=min(item.confidence for item in items),
            provenance_state="merged" if len(items) > 1 else first.provenance_state,
            contradicted_by=list(
                dict.fromkeys(
                    contradiction
                    for item in items
                    for contradiction in item.contradicted_by
                )
            ),
            model_id=self.model_id,
            prompt_version="knowledge-v2",
        )
