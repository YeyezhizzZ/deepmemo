from pathlib import Path

from src.knowledge.conversation_memory import ConversationMemoryExtractor
from src.knowledge.maintenance import KnowledgeMaintainer
from src.knowledge.card_store import CardStore
from src.knowledge.models import EvidenceSource, KnowledgeCard


def test_conversation_extractor_creates_decision_card(tmp_path: Path):
    extractor = ConversationMemoryExtractor(data_dir=tmp_path / "data")
    messages = [
        {"role": "user", "content": "我们应该用 Louvain 做社区发现。"},
        {"role": "assistant", "content": "原因是模块度可解释。"},
        {"role": "user", "content": "对，就按这个决策沉淀。"},
        {"role": "assistant", "content": "已记录。"},
    ]

    cards = extractor.extract("sess-1", messages)

    assert len(cards) == 1
    assert cards[0].type == "decision"
    assert cards[0].sources[0].path == "raw/conversations/sess-1.md"


def test_maintainer_reports_orphans_and_merge_suggestions(tmp_path: Path):
    data_dir = tmp_path / "data"
    store = CardStore(data_dir=data_dir)
    store.save(
        KnowledgeCard(
            slug="agent-memory",
            title="Agent Memory",
            type="concept",
            definition="Memory for agents.",
            sources=[EvidenceSource(path="diary/missing.md", evidence="missing", confidence=0.5)],
            aliases=["Agent Memory"],
        )
    )
    store.save(
        KnowledgeCard(
            slug="agent-memory-v2",
            title="Agent Memory",
            type="concept",
            definition="Duplicate memory for agents.",
            sources=[],
            aliases=["Agent Memory"],
        )
    )

    report = KnowledgeMaintainer(data_dir=data_dir).run_maintenance()

    assert "agent-memory" in report.orphan_cards
    assert ("agent-memory", "agent-memory-v2") in report.merge_suggestions
    assert CardStore(data_dir=data_dir).load("agent-memory").staleness_score >= 0.0
