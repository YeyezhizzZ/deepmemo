from pathlib import Path

import pytest

from src.knowledge.card_store import CardStore
from src.knowledge.models import EvidenceSource, KnowledgeCard


def _card(slug: str = "agentic-testing", *, tag: str = "testing") -> KnowledgeCard:
    return KnowledgeCard(
        slug=slug,
        title="Agentic Testing",
        type="concept",
        definition="A regression strategy for agentic code changes.",
        key_facts=["Uses API contract tests first."],
        sources=[EvidenceSource(path="diary/0620.md", evidence="Agentic testing note", confidence=0.9)],
        tags=[tag],
    )


def test_store_saves_loads_lists_filters_and_indexes_cards(tmp_path: Path):
    store = CardStore(data_dir=tmp_path / "data")
    store.save(_card("agentic-testing", tag="testing"))
    store.save(_card("graph-rag", tag="graph"))

    loaded = store.load("agentic-testing")
    assert loaded.title == "Agentic Testing"
    assert (
        tmp_path
        / "data"
        / "knowledge"
        / "wiki"
        / "concepts"
        / "agentic-testing.md"
    ).exists()

    assert [card.slug for card in store.list_cards(card_type="concept", tag="testing")] == ["agentic-testing"]

    index = store.load_index()
    assert index.stats["total_cards"] == 2
    assert index.tag_index["testing"] == ["agentic-testing"]
    assert index.type_index["concept"] == ["agentic-testing", "graph-rag"]
    assert index.cards["agentic-testing"].source_count == 1


def test_store_delete_rebuilds_index(tmp_path: Path):
    store = CardStore(data_dir=tmp_path / "data")
    store.save(_card("agentic-testing"))
    assert store.delete("agentic-testing") is True
    assert store.load("agentic-testing") is None
    assert store.delete("agentic-testing") is False
    assert store.load_index().stats["total_cards"] == 0


def test_store_rejects_path_traversal_for_source_files(tmp_path: Path):
    store = CardStore(data_dir=tmp_path / "data")
    safe = store.resolve_source_path("diary/0620.md", must_exist=False)
    assert safe == tmp_path / "data" / "diary" / "0620.md"

    with pytest.raises(ValueError, match="escapes data directory"):
        store.resolve_source_path("../secrets.md", must_exist=False)
