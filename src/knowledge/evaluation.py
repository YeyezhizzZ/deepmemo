from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.knowledge.atomic_io import atomic_write_text
from src.knowledge.card_store import CardStore
from src.knowledge.compiler_state import CandidateStore
from src.knowledge.embedding_index import EmbeddingIndex
from src.knowledge.models import EvidenceSource, KnowledgeCard
from src.knowledge.source_store import SourceStore


class KnowledgeEvaluator:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.store = CardStore(self.data_dir)
        self.source_store = SourceStore(self.data_dir)
        self.candidate_store = CandidateStore(self.data_dir)
        self.embedding_index = EmbeddingIndex(self.data_dir)
        self.history_path = (
            self.data_dir / "knowledge" / ".deepmemo" / "eval" / "history.jsonl"
        )

    def evaluate(
        self,
        *,
        min_health: float = 0.0,
        min_citation_coverage: float = 0.0,
        min_citation_precision: float = 0.0,
        record: bool = True,
    ) -> dict:
        cards = self.store.list_cards()
        citation = self._citation_metrics(cards)
        graph = self._graph_metrics(cards)
        pending = len(self.candidate_store.list())
        current_hashes = {
            snapshot.source_id: snapshot.source_hash
            for snapshot in self.source_store.list_current()
        }
        stale = sorted(
            card.slug
            for card in cards
            if card.staleness_score > 0
            or any(
                source.source_id
                and current_hashes.get(source.source_id) != source.source_hash
                for source in card.sources
            )
        )
        orphaned = sorted(
            card.slug
            for card in cards
            if card.orphaned
            or (
                any(source.source_id for source in card.sources)
                and all(
                    source.source_id not in current_hashes
                    for source in card.sources
                    if source.source_id
                )
            )
        )
        health = max(
            0.0,
            100.0
            - len(orphaned) * 10.0
            - len(stale) * 3.0
            - citation["invalid_citations"] * 5.0,
        )
        report = {
            "suite": "fast",
            "timestamp": self._now(),
            "health": {
                "score": round(health, 2),
                "max_score": 100,
                "stale_pages": stale,
                "orphaned_pages": orphaned,
                "pending_reviews": pending,
            },
            "citations": citation,
            "graph": graph,
            "stats": {
                "source_count": len(self.source_store.list_current()),
                "page_count": len(cards),
                "embedding_count": self.embedding_index.count(),
                "total_wiki_chars": sum(
                    len(
                        self.store.wiki_store.find_page_path(card.slug).read_text(
                            encoding="utf-8"
                        )
                    )
                    for card in cards
                    if self.store.wiki_store.find_page_path(card.slug) is not None
                ),
            },
            "threshold_violations": [],
        }
        violations = report["threshold_violations"]
        if health < min_health:
            violations.append(f"health {health:.2f} < {min_health:.2f}")
        if citation["coverage_percent"] < min_citation_coverage:
            violations.append(
                f"citation coverage {citation['coverage_percent']:.2f} "
                f"< {min_citation_coverage:.2f}"
            )
        if citation["precision_percent"] < min_citation_precision:
            violations.append(
                f"citation precision {citation['precision_percent']:.2f} "
                f"< {min_citation_precision:.2f}"
            )
        if record:
            self._append_history(report)
        return report

    def _citation_metrics(self, cards: list[KnowledgeCard]) -> dict:
        total_claims = sum(1 + len(card.key_facts) for card in cards)
        cited_claims = sum(
            1 + len(card.key_facts)
            for card in cards
            if any(self._is_precise(source) for source in card.sources)
        )
        citations = [source for card in cards for source in card.sources]
        valid = sum(self._citation_valid(source) for source in citations)
        total_sources = self.source_store.list_current()
        current_hashes = {
            snapshot.source_id: snapshot.source_hash for snapshot in total_sources
        }
        cited_source_ids = {
            source.source_id
            for source in citations
            if source.source_id
            and current_hashes.get(source.source_id) == source.source_hash
            and self._citation_valid(source)
        }
        return {
            "total_claims": total_claims,
            "cited_claims": cited_claims,
            "coverage_percent": self._percent(cited_claims, total_claims),
            "total_citations": len(citations),
            "valid_citations": valid,
            "invalid_citations": len(citations) - valid,
            "precision_percent": self._percent(valid, len(citations)),
            "precise_citations": sum(self._is_precise(source) for source in citations),
            "source_utilization_percent": self._percent(
                len(cited_source_ids),
                len(total_sources),
            ),
        }

    def _graph_metrics(self, cards: list[KnowledgeCard]) -> dict:
        known = {card.slug for card in cards}
        incoming = {slug: 0 for slug in known}
        edge_count = 0
        dangling: set[str] = set()
        for card in cards:
            for related in card.related_cards:
                if related in known:
                    incoming[related] += 1
                    edge_count += 1
                else:
                    dangling.add(related)
        return {
            "page_count": len(cards),
            "edge_count": edge_count,
            "unreferenced_pages": sorted(
                slug
                for slug, count in incoming.items()
                if count == 0
                and not next(card for card in cards if card.slug == slug).related_cards
            ),
            "dangling_targets": sorted(dangling),
        }

    def _citation_valid(self, source: EvidenceSource) -> bool:
        if not self._is_precise(source):
            return False
        path = (
            self.source_store.sources_dir
            / source.source_id
            / f"{source.source_hash}.md"
        )
        if not path.is_file():
            return False
        lines = path.read_text(encoding="utf-8").splitlines()
        if source.end_line > len(lines):
            return False
        excerpt = "\n".join(lines[source.start_line - 1 : source.end_line])
        return excerpt.strip() == source.evidence.strip()

    def _is_precise(self, source: EvidenceSource) -> bool:
        return bool(
            source.source_id
            and source.source_hash
            and source.start_line > 0
            and source.end_line >= source.start_line
        )

    def _append_history(self, report: dict) -> None:
        existing = (
            self.history_path.read_text(encoding="utf-8")
            if self.history_path.exists()
            else ""
        )
        line = json.dumps(report, ensure_ascii=False, sort_keys=True)
        atomic_write_text(self.history_path, existing + line + "\n")

    def _percent(self, numerator: int, denominator: int) -> float:
        if denominator == 0:
            return 100.0
        return round(numerator / denominator * 100.0, 2)

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
