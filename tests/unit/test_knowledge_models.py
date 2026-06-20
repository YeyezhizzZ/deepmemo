import pytest

from src.knowledge.models import EvidenceSource, KnowledgeCard


def test_card_defaults_and_round_trip_serialization():
    card = KnowledgeCard(
        slug="agentic-testing",
        title="Agentic Testing",
        type="concept",
        definition="A regression strategy for agentic code changes.",
        key_facts=["Uses API contract tests first."],
        tags=["testing", "agentic"],
    )

    assert card.id.startswith("kc-")
    assert card.density == "medium"
    assert card.sources == []
    assert card.update_count == 0
    assert card.human_edited is False
    assert card.human_edited_fields == []

    restored = KnowledgeCard.from_dict(card.to_dict())

    assert restored == card


def test_card_rejects_invalid_type_and_density():
    with pytest.raises(ValueError, match="Unsupported card type"):
        KnowledgeCard(slug="bad", title="Bad", type="note", definition="Bad")

    with pytest.raises(ValueError, match="Unsupported density"):
        KnowledgeCard(slug="bad", title="Bad", type="concept", density="dense", definition="Bad")


def test_evidence_source_rejects_invalid_confidence():
    with pytest.raises(ValueError, match="confidence"):
        EvidenceSource(path="diary/0620.md", evidence="example", confidence=1.2)
