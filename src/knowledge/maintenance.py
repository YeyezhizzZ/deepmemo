from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.knowledge.card_store import CardStore, DATA_DIR


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
        now = datetime.now(timezone.utc)
        for card in self.store.list_cards():
            try:
                updated = datetime.fromisoformat(card.updated_at)
            except ValueError:
                updated = now
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            days = max(0, (now - updated).days)
            card.staleness_score = min(1.0, round(days / 30, 4))
            self.store.save(card, rebuild_index=False)
        self.store.rebuild_index()

    def detect_orphans(self) -> list[str]:
        orphans: list[str] = []
        for card in self.store.list_cards():
            if card.sources and all(not (self.store.data_dir / source.path).exists() for source in card.sources):
                orphans.append(card.slug)
        return sorted(orphans)

    def detect_conflicts(self) -> list[tuple[str, str]]:
        cards = self.store.list_cards()
        pairs: set[tuple[str, str]] = set()
        negative_terms = ("不是", "不再", "不能", "not ", "never")
        for index, card in enumerate(cards):
            facts = " ".join(card.key_facts).lower()
            if not any(term in facts for term in negative_terms):
                continue
            for other in cards[index + 1 :]:
                if set(card.tags) & set(other.tags):
                    pairs.add(tuple(sorted((card.slug, other.slug))))
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
