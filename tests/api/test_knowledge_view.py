from pathlib import Path

from src.knowledge.card_store import CardStore
from src.knowledge.models import EvidenceSource, KnowledgeCard
from src.knowledge.repowiki import RepoWikiBuilder


def seed_view_data(data_dir: Path) -> None:
    source = data_dir / "diary" / "0620.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Retrieval\n\nCards before rg.\n", encoding="utf-8")
    store = CardStore(data_dir)
    store.save(
        KnowledgeCard(
            slug="card-first-rag",
            title="Card-first RAG",
            type="decision",
            definition="Local search queries Cards before Markdown.",
            key_facts=["Card evidence keeps context dense."],
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
            sources=[EvidenceSource(path="diary/0620.md", evidence="Do not overwrite", confidence=0.8)],
            related_cards=["card-first-rag"],
            tags=["architecture"],
        )
    )
    RepoWikiBuilder(data_dir).rebuild()


def test_knowledge_view_api_returns_view_pages_review_and_graph(client, test_data_dir: Path):
    seed_view_data(test_data_dir)

    view_response = client.get("/api/knowledge/view")
    assert view_response.status_code == 200
    view = view_response.json()
    assert view["stats"]["total_cards"] == 2
    assert view["pages"][0]["sections"][0]["card_slug"] == "card-first-rag"
    assert view["review_queue"][0]["id"]
    assert {node["id"] for node in view["graph"]["nodes"]} == {"card-first-rag", "human-edit-protection"}

    pages_response = client.get("/api/knowledge/view/pages")
    assert pages_response.status_code == 200
    assert pages_response.json()["pages"][0]["slug"] == "decisions"

    page_response = client.get("/api/knowledge/view/pages/decisions")
    assert page_response.status_code == 200
    assert page_response.json()["slug"] == "decisions"

    review_response = client.get("/api/knowledge/view/review")
    assert review_response.status_code == 200
    assert any(item["id"] == "new-card-card-first-rag" for item in review_response.json()["items"])

    assert client.get("/wiki/graph").status_code == 404


def test_knowledge_view_review_actions_and_pin(client, test_data_dir: Path):
    seed_view_data(test_data_dir)

    confirm_response = client.post("/api/knowledge/view/review/new-card-card-first-rag/confirm")
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "confirmed"

    hide_response = client.post("/api/knowledge/view/review/new-card-human-edit-protection/hide")
    assert hide_response.status_code == 200
    assert hide_response.json()["status"] == "hidden"

    rewrite_response = client.post(
        "/api/knowledge/view/review/new-card-card-first-rag/rewrite",
        json={"instruction": "Make this concise."},
    )
    assert rewrite_response.status_code == 200
    assert rewrite_response.json()["rewrite"]["proposed_definition"].startswith("Concise rewrite:")

    apply_response = client.post("/api/knowledge/view/review/new-card-card-first-rag/apply")
    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "rewritten"

    pin_response = client.post(
        "/api/knowledge/view/cards/card-first-rag/pin",
        json={"field": "definition"},
    )
    assert pin_response.status_code == 200
    assert "definition" in pin_response.json()["human_edited_fields"]


def test_knowledge_view_rejects_unsafe_page_item_and_field(client, test_data_dir: Path):
    seed_view_data(test_data_dir)

    assert client.get("/api/knowledge/view/pages/../cards").status_code in {400, 404}
    assert client.post("/api/knowledge/view/review/../bad/confirm").status_code in {400, 404}
    response = client.post(
        "/api/knowledge/view/cards/card-first-rag/pin",
        json={"field": "../bad"},
    )
    assert response.status_code == 400
