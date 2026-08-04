from pathlib import Path

from src.ai.local_search_agent import LocalSearchAgent
from src.ai.local_tools import KnowledgeBaseTools
from src.knowledge.card_store import CardStore
from src.knowledge.models import EvidenceSource, KnowledgeCard
from src.knowledge.retriever import KnowledgeRetriever


class TopicEmbeddingProvider:
    model_id = "topic-test-v1"

    def __init__(self):
        self.document_batches = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        if len(texts) > 1:
            self.document_batches += 1
        vectors = []
        for text in texts:
            lowered = text.lower()
            vectors.append(
                [
                    1.0 if any(term in lowered for term in ("cat", "feline", "kitten")) else 0.0,
                    1.0 if any(term in lowered for term in ("database", "sql")) else 0.0,
                ]
            )
        return vectors


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
    assert result.searched_paths == ["knowledge/wiki"]
    assert result.evidence[0].path == "knowledge/wiki/concepts/knowledge-engine.md"
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


def test_retriever_uses_optional_embeddings_and_caches_page_vectors(tmp_path: Path):
    data_dir = tmp_path / "data"
    store = CardStore(data_dir=data_dir)
    store.save(
        KnowledgeCard(
            slug="feline-behavior",
            title="Feline Behavior",
            type="concept",
            definition="Cats communicate with posture.",
        )
    )
    store.save(
        KnowledgeCard(
            slug="database-index",
            title="Database Index",
            type="concept",
            definition="SQL indexes accelerate lookups.",
        )
    )
    provider = TopicEmbeddingProvider()
    retriever = KnowledgeRetriever(
        data_dir=data_dir,
        embedding_provider=provider,
    )

    first = retriever.search("kitten", limit=2)
    second = retriever.search("kitten", limit=2)

    assert first[0]["slug"] == "feline-behavior"
    assert first[0]["retrieval"] == "vector"
    assert second[0]["slug"] == "feline-behavior"
    assert provider.document_batches == 1
    assert retriever.last_warnings == []
