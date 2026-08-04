from __future__ import annotations

import json
from pathlib import Path

from src.knowledge.atomic_io import atomic_write_text
from src.knowledge.models import KnowledgeCard


class RelationStore:
    def __init__(self, data_dir: str | Path):
        self.path = Path(data_dir) / "knowledge" / "graph" / "relations.jsonl"

    def rebuild(self, cards: list[KnowledgeCard]) -> list[dict]:
        known = {card.slug for card in cards}
        relations: dict[tuple[str, str, str], dict] = {}
        for card in cards:
            source_refs = [
                {
                    "source_id": source.source_id,
                    "source_hash": source.source_hash,
                    "start_line": source.start_line,
                    "end_line": source.end_line,
                }
                for source in card.sources
                if source.source_id
            ]
            for target in card.related_cards:
                if target not in known or target == card.slug:
                    continue
                left, right = sorted((card.slug, target))
                key = (left, right, "related")
                relations[key] = {
                    "from": left,
                    "to": right,
                    "type": "related",
                    "confidence": card.confidence,
                    "sources": source_refs,
                }
            for target in card.contradicted_by:
                if target not in known or target == card.slug:
                    continue
                key = (card.slug, target, "contradicts")
                relations[key] = {
                    "from": card.slug,
                    "to": target,
                    "type": "contradicts",
                    "confidence": card.confidence,
                    "sources": source_refs,
                }
        result = [relations[key] for key in sorted(relations)]
        content = "".join(
            json.dumps(relation, ensure_ascii=False, sort_keys=True) + "\n"
            for relation in result
        )
        atomic_write_text(self.path, content)
        return result

    def list(self) -> list[dict]:
        if not self.path.exists():
            return []
        relations: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                relations.append(json.loads(line))
        return relations
