from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.knowledge.card_compiler import KnowledgeCardCompiler
from src.knowledge.card_store import CardStore, DATA_DIR
from src.knowledge.compiler_state import CandidateStore
from src.knowledge.maintenance import KnowledgeMaintainer, MaintenanceReport
from src.knowledge.models import KnowledgeCard
from src.knowledge.repowiki import RepoWikiBuilder


_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_PINNABLE_FIELDS = {
    "title",
    "type",
    "density",
    "definition",
    "key_facts",
    "sources",
    "related_cards",
    "tags",
    "aliases",
}


class KnowledgeViewService:
    def __init__(self, data_dir: str | Path | None = None, store: CardStore | None = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.store = store or CardStore(self.data_dir)
        self.repowiki = RepoWikiBuilder(self.data_dir, store=self.store)
        self.candidate_store = CandidateStore(self.data_dir)
        self.state_path = self.data_dir / "knowledge" / "review-state.json"

    def build_view(self) -> dict[str, Any]:
        cards = self.store.list_cards()
        pages = self._pages(cards)
        review_items = self._review_items(cards, pages)
        graph = self._graph(cards)
        index = self._safe_index_stats()
        return {
            "generated_at": self._now(),
            "stats": {
                **index,
                "review_open": sum(1 for item in review_items if item["status"] == "open"),
                "page_count": len(pages),
                "relation_count": len(graph["edges"]),
            },
            "overview": self._overview(cards, pages, review_items, graph),
            "pages": pages,
            "cards": [self._card_summary(card) for card in cards],
            "review_queue": review_items,
            "graph": graph,
        }

    def list_pages(self) -> list[dict[str, Any]]:
        return self.build_view()["pages"]

    def get_page(self, slug: str) -> dict[str, Any]:
        self._validate_safe_id(slug)
        for page in self.list_pages():
            if page["slug"] == slug:
                return page
        raise FileNotFoundError(slug)

    def review_queue(self) -> list[dict[str, Any]]:
        return self.build_view()["review_queue"]

    def confirm_review_item(self, item_id: str) -> dict[str, Any]:
        candidate = self._load_candidate(item_id)
        if candidate is not None:
            card = KnowledgeCardCompiler(self.data_dir, store=self.store).approve_candidate(
                item_id
            )
            item = self._candidate_item(candidate)
            return {**item, "status": "confirmed", "card_slugs": [card.slug]}
        return self._update_item(item_id, {"status": "confirmed", "updated_at": self._now()})

    def hide_review_item(self, item_id: str) -> dict[str, Any]:
        candidate = self._load_candidate(item_id)
        if candidate is not None:
            KnowledgeCardCompiler(self.data_dir, store=self.store).reject_candidate(item_id)
            return {**self._candidate_item(candidate), "status": "hidden"}
        return self._update_item(item_id, {"status": "hidden", "updated_at": self._now()})

    def request_rewrite(self, item_id: str, *, instruction: str = "") -> dict[str, Any]:
        item = self._find_review_item(item_id)
        card = self._first_card(item)
        proposed = f"Concise rewrite: {card.definition}"
        if instruction.strip():
            proposed = f"{proposed} ({instruction.strip()})"
        return self._update_item(
            item_id,
            {
                "status": "open",
                "updated_at": self._now(),
                "rewrite": {
                    "field": "definition",
                    "instruction": instruction,
                    "proposed_definition": proposed,
                },
            },
        )

    def apply_review_item(self, item_id: str) -> dict[str, Any]:
        item = self._find_review_item(item_id)
        rewrite = item.get("rewrite") or {}
        proposed = str(rewrite.get("proposed_definition") or "").strip()
        if not proposed:
            raise ValueError("review item has no rewrite proposal")
        card = self._first_card(item)
        card.definition = proposed
        card.human_edited = True
        if "definition" not in card.human_edited_fields:
            card.human_edited_fields.append("definition")
        self.store.save(KnowledgeCard.from_dict(card.to_dict()))
        return self._update_item(item_id, {"status": "rewritten", "updated_at": self._now()})

    def pin_card_field(self, slug: str, field: str) -> dict[str, Any]:
        self._validate_safe_id(slug)
        if field not in _PINNABLE_FIELDS:
            raise ValueError(f"cannot pin field: {field}")
        card = self.store.load(slug)
        if card is None:
            raise FileNotFoundError(slug)
        card.human_edited = True
        if field not in card.human_edited_fields:
            card.human_edited_fields.append(field)
        self.store.save(KnowledgeCard.from_dict(card.to_dict()))
        return self.store.load(slug).to_dict()

    def _pages(self, cards: list[KnowledgeCard]) -> list[dict[str, Any]]:
        if not self.repowiki.repowiki_dir.exists():
            self.repowiki.rebuild()
        pages = []
        for page in self.repowiki.list_pages():
            page_cards = [card for card in cards if card.slug in page.card_slugs]
            pages.append(
                {
                    "slug": page.slug,
                    "title": page.title,
                    "path": page.path,
                    "summary": self._page_summary(page_cards),
                    "card_slugs": list(page.card_slugs),
                    "sections": [self._page_section(card) for card in page_cards],
                }
            )
        return pages

    def _review_items(self, cards: list[KnowledgeCard], pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        report = self._safe_maintenance_report()
        state = self._load_state()
        items: list[dict[str, Any]] = []

        for candidate in self.candidate_store.list():
            items.append(self._candidate_item(candidate))

        for card in sorted(cards, key=lambda item: item.slug):
            items.append(
                self._with_state(
                    {
                        "id": f"new-card-{card.slug}",
                        "kind": "new_card",
                        "severity": "medium",
                        "title": f"Review Card: {card.title}",
                        "summary": card.definition,
                        "card_slugs": [card.slug],
                        "source_paths": [source.path for source in card.sources],
                        "suggested_action": "confirm",
                    },
                    state,
                )
            )
            if card.staleness_score >= 0.6:
                items.append(
                    self._with_state(
                        {
                            "id": f"stale-card-{card.slug}",
                            "kind": "stale_card",
                            "severity": "high",
                            "title": f"Stale Card: {card.title}",
                            "summary": f"Staleness score is {card.staleness_score}.",
                            "card_slugs": [card.slug],
                            "source_paths": [source.path for source in card.sources],
                            "suggested_action": "rewrite",
                        },
                        state,
                    )
                )

        for left, right in report.conflict_pairs:
            items.append(
                self._with_state(
                    {
                        "id": f"conflict-{left}-{right}",
                        "kind": "conflict",
                        "severity": "high",
                        "title": f"Conflict: {left} / {right}",
                        "summary": "Cards share tags and contain negative or contradictory language.",
                        "card_slugs": [left, right],
                        "source_paths": [],
                        "suggested_action": "rewrite",
                    },
                    state,
                )
            )

        for left, right in report.merge_suggestions:
            items.append(
                self._with_state(
                    {
                        "id": f"merge-{left}-{right}",
                        "kind": "merge_suggestion",
                        "severity": "medium",
                        "title": f"Merge candidate: {left} / {right}",
                        "summary": "Cards share title or aliases.",
                        "card_slugs": [left, right],
                        "source_paths": [],
                        "suggested_action": "merge",
                    },
                    state,
                )
            )

        for page in pages:
            for section in page["sections"]:
                items.append(
                    self._with_state(
                        {
                            "id": f"repowiki-section-{page['slug']}-{section['card_slug']}",
                            "kind": "repowiki_section",
                            "severity": "low",
                            "title": f"Reader section: {section['title']}",
                            "summary": section["definition"],
                            "card_slugs": [section["card_slug"]],
                            "source_paths": [source["path"] for source in section["sources"]],
                            "suggested_action": "confirm",
                        },
                        state,
                    )
                )
        return sorted(items, key=lambda item: (item["status"] != "open", item["severity"], item["id"]))

    def _candidate_item(self, candidate: dict[str, Any]) -> dict[str, Any]:
        card = KnowledgeCard.from_dict(candidate["card"])
        reasons = [str(reason) for reason in candidate.get("reasons") or []]
        return {
            "id": str(candidate["id"]),
            "kind": "compile_candidate",
            "severity": "high" if "contradicted" in reasons else "medium",
            "title": f"Compile Candidate: {card.title}",
            "summary": card.definition,
            "card_slugs": [card.slug],
            "source_paths": [source.path for source in card.sources],
            "suggested_action": "confirm",
            "status": "open",
            "updated_at": None,
            "rewrite": None,
            "reasons": reasons,
        }

    def _load_candidate(self, item_id: str) -> dict[str, Any] | None:
        self._validate_safe_id(item_id)
        try:
            return self.candidate_store.load(item_id)
        except FileNotFoundError:
            return None

    def _graph(self, cards: list[KnowledgeCard]) -> dict[str, Any]:
        nodes = [self._graph_node(card) for card in sorted(cards, key=lambda item: item.slug)]
        edges = [
            {
                "from": relation["from"],
                "to": relation["to"],
                "reason": (
                    "related_card"
                    if relation["type"] == "related"
                    else relation["type"]
                ),
                "confidence": relation["confidence"],
            }
            for relation in self.store.relation_store.list()
        ]
        return {"nodes": nodes, "edges": edges}

    def _overview(
        self,
        cards: list[KnowledgeCard],
        pages: list[dict[str, Any]],
        review_items: list[dict[str, Any]],
        graph: dict[str, Any],
    ) -> list[dict[str, Any]]:
        open_items = [item for item in review_items if item["status"] == "open"]
        high_items = [item for item in open_items if item["severity"] == "high"]
        return [
            {
                "id": "review",
                "title": "Review Backlog",
                "value": len(open_items),
                "summary": f"{len(high_items)} high severity items need attention.",
            },
            {
                "id": "reader",
                "title": "Human Reader",
                "value": len(pages),
                "summary": f"{len(cards)} Cards are condensed into {len(pages)} pages.",
            },
            {
                "id": "relations",
                "title": "Relations",
                "value": len(graph["edges"]),
                "summary": "Edges are explicit typed relations with provenance.",
            },
        ]

    def _safe_index_stats(self) -> dict[str, Any]:
        try:
            return self.store.load_index().stats
        except Exception:
            return self.store.rebuild_index().stats

    def _safe_maintenance_report(self) -> MaintenanceReport:
        try:
            return KnowledgeMaintainer(self.data_dir, store=self.store).run_maintenance()
        except Exception:
            index = self.store.rebuild_index()
            return MaintenanceReport(
                stats=index.stats,
                orphan_cards=[],
                conflict_pairs=[],
                merge_suggestions=[],
            )

    def _card_summary(self, card: KnowledgeCard) -> dict[str, Any]:
        return {
            "slug": card.slug,
            "title": card.title,
            "type": card.type,
            "definition": card.definition,
            "tags": list(card.tags),
            "source_count": len(card.sources),
            "staleness_score": card.staleness_score,
            "human_edited": card.human_edited,
            "human_edited_fields": list(card.human_edited_fields),
        }

    def _graph_node(self, card: KnowledgeCard) -> dict[str, Any]:
        return {
            "id": card.slug,
            "title": card.title,
            "type": card.type,
            "tags": list(card.tags),
            "source_count": len(card.sources),
            "degree_hint": len(card.related_cards) + len(card.tags),
        }

    def _page_section(self, card: KnowledgeCard) -> dict[str, Any]:
        return {
            "card_slug": card.slug,
            "title": card.title,
            "type": card.type,
            "definition": card.definition,
            "key_facts": list(card.key_facts),
            "sources": [source.to_dict() for source in card.sources],
            "related_cards": list(card.related_cards),
            "tags": list(card.tags),
        }

    def _page_summary(self, cards: list[KnowledgeCard]) -> str:
        if not cards:
            return ""
        titles = ", ".join(card.title for card in cards[:3])
        suffix = "" if len(cards) <= 3 else f" and {len(cards) - 3} more"
        return f"Covers {titles}{suffix}."

    def _find_review_item(self, item_id: str) -> dict[str, Any]:
        self._validate_safe_id(item_id)
        for item in self.review_queue():
            if item["id"] == item_id:
                return item
        raise FileNotFoundError(item_id)

    def _first_card(self, item: dict[str, Any]) -> KnowledgeCard:
        slugs = item.get("card_slugs") or []
        if not slugs:
            raise ValueError("review item has no cards")
        card = self.store.load(str(slugs[0]))
        if card is None:
            raise FileNotFoundError(str(slugs[0]))
        return card

    def _update_item(self, item_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        self._validate_safe_id(item_id)
        item = self._find_review_item(item_id)
        state = self._load_state()
        current = state.setdefault("items", {}).setdefault(item_id, {})
        current.update(updates)
        state["updated_at"] = self._now()
        self._save_state(state)
        next_item = dict(item)
        next_item.update(current)
        return next_item

    def _with_state(self, item: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        stored = (state.get("items") or {}).get(item["id"], {})
        return {
            **item,
            "status": stored.get("status", "open"),
            "updated_at": stored.get("updated_at"),
            "rewrite": stored.get("rewrite"),
        }

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"version": 1, "items": {}, "updated_at": None}
        with self.state_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        data.setdefault("version", 1)
        data.setdefault("items", {})
        return data

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)

    def _validate_safe_id(self, value: str) -> None:
        if not _SAFE_ID_RE.match(value):
            raise ValueError(f"unsafe knowledge view id: {value}")

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
