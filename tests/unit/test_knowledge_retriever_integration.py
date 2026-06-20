from pathlib import Path

from src.ai.local_search_agent import LocalSearchAgent
from src.ai.local_tools import KnowledgeBaseTools
from src.knowledge.card_store import CardStore
from src.knowledge.models import EvidenceSource, KnowledgeCard
from src.knowledge.retriever import KnowledgeRetriever


def test_retriever_expands_card_evidence_before_ripgrep(tmp_path: Path):
    data_dir = tmp_path / "data"
    store = CardStore(data_dir=data_dir)
    store.save(
        KnowledgeCard(
            slug="knowledge-engine",
            title="Knowledge Engine",
            type="concept",
            definition="Compiled knowledge cards for DeepMemo.",
            key_facts=["Card retrieval should precede ripgrep fallback."],
            sources=[
                EvidenceSource(
                    path="diary/0620.md",
                    evidence="Card retrieval should precede ripgrep fallback.",
                    confidence=0.9,
                )
            ],
            tags=["architecture"],
        )
    )

    result = LocalSearchAgent(
        tools=KnowledgeBaseTools(root_path=data_dir),
        knowledge_retriever=KnowledgeRetriever(data_dir=data_dir),
    ).search("architecture")

    assert result.evidence
    assert result.searched_paths == ["knowledge/cards"]
    assert result.evidence[0].path == "knowledge/cards/knowledge-engine.yaml"
    assert "Compiled knowledge cards" in result.evidence[0].excerpt


def test_retriever_falls_back_to_ripgrep_when_cards_miss(tmp_path: Path):
    data_dir = tmp_path / "data"
    diary = data_dir / "diary" / "0620.md"
    diary.parent.mkdir(parents=True)
    diary.write_text("plain markdown fallback target", encoding="utf-8")

    result = LocalSearchAgent(
        tools=KnowledgeBaseTools(root_path=data_dir),
        knowledge_retriever=KnowledgeRetriever(data_dir=data_dir),
    ).search("plain markdown")

    assert result.evidence
    assert result.evidence[0].path == "diary/0620.md"
