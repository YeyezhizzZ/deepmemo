from pathlib import Path

from src.knowledge.card_store import CardStore
from src.knowledge.models import EvidenceSource, KnowledgeCard
from src.knowledge.repowiki import RepoWikiBuilder
from src.knowledge.view_model import KnowledgeViewService


def seed_cards(data_dir: Path) -> CardStore:
    source = data_dir / "diary" / "0620.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Retrieval\n\nCards before rg.\n", encoding="utf-8")
    raw_source = data_dir / "raw" / "lesson.md"
    raw_source.parent.mkdir(parents=True)
    raw_source.write_text("# Lesson\n\nNever overwrite human edits.\n", encoding="utf-8")

    store = CardStore(data_dir)
    store.save(
        KnowledgeCard(
            slug="card-first-rag",
            title="Card-first RAG",
            type="decision",
            definition="Local search queries Cards before Markdown.",
            key_facts=["Card evidence keeps context dense.", "ripgrep remains fallback."],
            sources=[EvidenceSource(path="diary/0620.md", evidence="Cards before rg", confidence=0.9)],
            related_cards=["human-edit-protection"],
            tags=["retrieval", "architecture"],
        )
    )
    store.save(
        KnowledgeCard(
            slug="human-edit-protection",
            title="Human Edit Protection",
            type="pattern",
            definition="Compiler merges preserve fields marked by humans.",
            key_facts=["human_edited_fields is the merge boundary."],
            sources=[EvidenceSource(path="raw/lesson.md", evidence="Never overwrite human edits", confidence=0.8)],
            related_cards=["card-first-rag"],
            tags=["architecture", "maintenance"],
        )
    )
    RepoWikiBuilder(data_dir).rebuild()
    return store


def test_view_model_returns_structured_pages_review_queue_and_graph(test_data_dir: Path):
    seed_cards(test_data_dir)

    view = KnowledgeViewService(test_data_dir).build_view()

    assert view["stats"]["total_cards"] == 2
    assert [page["slug"] for page in view["pages"]] == ["decisions", "patterns"]
    assert view["pages"][0]["sections"][0]["card_slug"] == "card-first-rag"
    assert view["pages"][0]["sections"][0]["sources"][0]["path"] == "diary/0620.md"
    assert {item["id"] for item in view["review_queue"]} >= {
        "new-card-card-first-rag",
        "new-card-human-edit-protection",
        "repowiki-section-decisions-card-first-rag",
    }
    assert {node["id"] for node in view["graph"]["nodes"]} == {"card-first-rag", "human-edit-protection"}
    assert view["graph"]["edges"][0]["reason"] in {"related_card", "shared_tag"}


def test_review_state_confirm_hide_rewrite_apply_and_pin_are_persisted(test_data_dir: Path):
    store = seed_cards(test_data_dir)
    service = KnowledgeViewService(test_data_dir)

    confirmed = service.confirm_review_item("new-card-card-first-rag")
    hidden = service.hide_review_item("new-card-human-edit-protection")
    rewritten = service.request_rewrite(
        "new-card-card-first-rag",
        instruction="Make the definition concise.",
    )
    applied = service.apply_review_item("new-card-card-first-rag")
    pinned = service.pin_card_field("card-first-rag", "definition")

    assert confirmed["status"] == "confirmed"
    assert hidden["status"] == "hidden"
    assert rewritten["rewrite"]["proposed_definition"].startswith("Concise rewrite:")
    assert applied["status"] == "rewritten"
    assert pinned["human_edited"] is True
    assert "definition" in pinned["human_edited_fields"]

    reloaded = KnowledgeViewService(test_data_dir).build_view()
    state_path = test_data_dir / "knowledge" / "review-state.json"
    assert state_path.exists()
    assert next(item for item in reloaded["review_queue"] if item["id"] == "new-card-card-first-rag")["status"] == "rewritten"
    assert store.load("card-first-rag").definition.startswith("Concise rewrite:")


def test_view_model_rejects_unsafe_ids_and_fields(test_data_dir: Path):
    seed_cards(test_data_dir)
    service = KnowledgeViewService(test_data_dir)

    for action in (
        lambda: service.confirm_review_item("../bad"),
        lambda: service.hide_review_item("../bad"),
        lambda: service.request_rewrite("../bad", instruction="rewrite"),
        lambda: service.apply_review_item("../bad"),
        lambda: service.pin_card_field("card-first-rag", "../bad"),
    ):
        try:
            action()
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe value should be rejected")


def test_view_model_recovers_from_corrupt_index(test_data_dir: Path):
    seed_cards(test_data_dir)
    index_path = test_data_dir / "knowledge" / "index.json"
    index_path.write_text("", encoding="utf-8")

    view = KnowledgeViewService(test_data_dir).build_view()

    assert view["stats"]["total_cards"] == 2
