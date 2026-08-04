from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.knowledge.card_store import CardStore, DATA_DIR
from src.knowledge.source_store import SourceStore


@dataclass
class MaintenanceReport:
    stats: dict
    orphan_cards: list[str] = field(default_factory=list)
    conflict_pairs: list[tuple[str, str]] = field(default_factory=list)
    merge_suggestions: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "stats": self.stats,
            "orphan_cards": self.orphan_cards,
            "conflict_pairs": [list(pair) for pair in self.conflict_pairs],
            "merge_suggestions": [list(pair) for pair in self.merge_suggestions],
        }


class KnowledgeMaintainer:
    def __init__(self, data_dir: str | Path | None = None, store: CardStore | None = None):
        self.store = store or CardStore(data_dir or DATA_DIR)
        self.source_store = SourceStore(self.store.data_dir)

    def run_maintenance(self) -> MaintenanceReport:
        self.update_staleness_scores()
        report = MaintenanceReport(
            stats=self.store.load_index().stats,
            orphan_cards=self.detect_orphans(),
            conflict_pairs=self.detect_conflicts(),
            merge_suggestions=self.suggest_merges(),
        )
        self.store.rebuild_index()
        report.stats = self.store.load_index().stats
        return report

    def update_staleness_scores(self) -> None:
        current_hashes = {
            snapshot.source_id: snapshot.source_hash
            for snapshot in self.source_store.list_current()
        }
        for card in self.store.list_cards():
            grounded = [
                source
                for source in card.sources
                if source.source_id and source.source_hash
            ]
            if not grounded:
                card.staleness_score = 1.0 if card.orphaned else 0.0
            else:
                stale_count = sum(
                    current_hashes.get(source.source_id) != source.source_hash
                    for source in grounded
                )
                card.staleness_score = round(stale_count / len(grounded), 4)
                card.orphaned = stale_count == len(grounded)
            self.store.save(card, rebuild_index=False)
        self.store.rebuild_index()

    def detect_orphans(self) -> list[str]:
        orphans: list[str] = []
        for card in self.store.list_cards():
            if card.orphaned:
                orphans.append(card.slug)
                continue
            legacy_sources = [
                source
                for source in card.sources
                if not source.source_id and not source.path.startswith("git:")
            ]
            if legacy_sources and all(
                not (self.store.data_dir / source.path).exists()
                for source in legacy_sources
            ):
                orphans.append(card.slug)
        return sorted(orphans)

    def detect_conflicts(self) -> list[tuple[str, str]]:
        cards = self.store.list_cards()
        known = {card.slug for card in cards}
        pairs: set[tuple[str, str]] = set()
        for card in cards:
            for other in card.contradicted_by:
                if other in known and other != card.slug:
                    pairs.add(tuple(sorted((card.slug, other))))
        return sorted(pairs)

    def suggest_merges(self) -> list[tuple[str, str]]:
        cards = self.store.list_cards()
        suggestions: set[tuple[str, str]] = set()
        for index, card in enumerate(cards):
            names = {card.title.lower(), *[alias.lower() for alias in card.aliases]}
            for other in cards[index + 1 :]:
                other_names = {other.title.lower(), *[alias.lower() for alias in other.aliases]}
                if names & other_names:
                    suggestions.add(tuple(sorted((card.slug, other.slug))))
        return sorted(suggestions)
