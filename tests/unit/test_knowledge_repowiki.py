from pathlib import Path

import pytest

from src.knowledge.card_store import CardStore
from src.knowledge.models import EvidenceSource, KnowledgeCard
from src.knowledge.repowiki import RepoWikiBuilder


def test_repowiki_rebuild_writes_deterministic_pages_from_cards(test_data_dir: Path):
    store = CardStore(test_data_dir)
    store.save(
        KnowledgeCard(
            slug="card-first-rag",
            title="Card-first RAG",
            type="decision",
            definition="Local search must query Knowledge Cards before Markdown fallback.",
            key_facts=["Card evidence keeps agent context dense.", "ripgrep remains the fallback path."],
            sources=[EvidenceSource(path="diary/0620.md", evidence="Cards before rg", confidence=0.9)],
            tags=["retrieval", "architecture"],
        )
    )
    store.save(
        KnowledgeCard(
            slug="human-edit-protection",
            title="Human Edit Protection",
            type="pattern",
            definition="Compiler merges must preserve fields marked by users.",
            key_facts=["human_edited_fields is the merge boundary."],
            sources=[EvidenceSource(path="raw/spec.md", evidence="Do not overwrite reviewed fields", confidence=0.8)],
            tags=["maintenance"],
        )
    )

    result = RepoWikiBuilder(data_dir=test_data_dir).rebuild()

    assert result["pages"] == ["decisions", "patterns"]
    decisions_page = test_data_dir / "knowledge" / "repowiki" / "decisions.md"
    assert decisions_page.exists()
    content = decisions_page.read_text(encoding="utf-8")
    assert "# Decisions" in content
    assert "## Card-first RAG" in content
    assert "`card-first-rag`" in content
    assert "diary/0620.md" in content
    assert store.load("card-first-rag").definition == "Local search must query Knowledge Cards before Markdown fallback."


def test_repowiki_rejects_unsafe_page_slug(test_data_dir: Path):
    with pytest.raises(ValueError):
        RepoWikiBuilder(data_dir=test_data_dir).load_page("../cards")
