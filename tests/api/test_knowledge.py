from pathlib import Path

import src.routers.knowledge as knowledge_router
from src.knowledge.card_compiler import KnowledgeCardCompiler
from src.knowledge.card_store import CardStore
from src.knowledge.knowledge_llm import OpenAIKnowledgeProvider
from src.knowledge.models import EvidenceSource, KnowledgeCard
from src.services.llm_service import LLMService
from tests.fake_knowledge_provider import FakeKnowledgeProvider


def test_knowledge_compile_file_crud_search_stats_and_health(client, test_data_dir: Path):
    source = test_data_dir / "diary" / "0620.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# Knowledge Engine\n\nTags: deepmemo, architecture\n\n- Compiles local markdown into cards.\n",
        encoding="utf-8",
    )

    compile_response = client.post("/api/knowledge/compile/file", json={"path": "diary/0620.md"})
    assert compile_response.status_code == 200
    assert compile_response.json()["card_slugs"] == ["knowledge-engine"]

    list_response = client.get("/api/knowledge/cards", params={"type": "concept", "tag": "deepmemo"})
    assert list_response.status_code == 200
    assert [card["slug"] for card in list_response.json()["cards"]] == ["knowledge-engine"]

    detail_response = client.get("/api/knowledge/cards/knowledge-engine")
    assert detail_response.status_code == 200
    assert detail_response.json()["title"] == "Knowledge Engine"

    update_response = client.put(
        "/api/knowledge/cards/knowledge-engine",
        json={"definition": "Human reviewed Knowledge Engine definition."},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["human_edited"] is True
    assert "definition" in updated["human_edited_fields"]
    protected_update = client.put(
        "/api/knowledge/cards/knowledge-engine",
        json={"source_hash": "tampered"},
    )
    assert protected_update.status_code == 400

    search_response = client.post("/api/knowledge/search", json={"query": "architecture"})
    assert search_response.status_code == 200
    assert search_response.json()["results"][0]["slug"] == "knowledge-engine"

    stats_response = client.get("/api/knowledge/stats")
    assert stats_response.status_code == 200
    assert stats_response.json()["total_cards"] == 1

    health_response = client.get("/api/knowledge/health")
    assert health_response.status_code == 200
    assert health_response.json()["stats"]["total_cards"] == 1
    assert health_response.json()["orphan_cards"] == []

    maintain_response = client.post("/api/knowledge/maintain")
    assert maintain_response.status_code == 200
    assert maintain_response.json()["stats"]["total_cards"] == 1

    delete_response = client.delete("/api/knowledge/cards/knowledge-engine")
    assert delete_response.status_code == 200
    assert delete_response.json()["slug"] == "knowledge-engine"
    assert client.get("/api/knowledge/cards/knowledge-engine").status_code == 404


def test_knowledge_compile_file_rejects_path_traversal(client):
    response = client.post("/api/knowledge/compile/file", json={"path": "../secret.md"})
    assert response.status_code == 400


def test_repowiki_api_rebuild_list_and_get_page(client, test_data_dir: Path):
    CardStore(test_data_dir).save(
        KnowledgeCard(
            slug="architecture-decision",
            title="Architecture Decision",
            type="decision",
            definition="Knowledge Cards are the structured truth layer.",
            key_facts=["RepoWiki is generated from Cards only."],
            sources=[EvidenceSource(path="diary/0620.md", evidence="Cards first", confidence=0.9)],
            tags=["architecture"],
        )
    )
    source = test_data_dir / "diary" / "0620.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Source\n", encoding="utf-8")

    rebuild_response = client.post("/api/knowledge/repowiki/rebuild")
    assert rebuild_response.status_code == 200
    assert rebuild_response.json()["pages"] == ["decisions"]

    list_response = client.get("/api/knowledge/repowiki/pages")
    assert list_response.status_code == 200
    assert list_response.json()["pages"][0]["slug"] == "decisions"
    assert list_response.json()["pages"][0]["title"] == "Decisions"

    detail_response = client.get("/api/knowledge/repowiki/pages/decisions")
    assert detail_response.status_code == 200
    assert detail_response.json()["slug"] == "decisions"
    assert "Architecture Decision" in detail_response.json()["content"]
    assert client.get("/wiki/graph").status_code == 404


def test_repowiki_api_rejects_unsafe_slug(client):
    response = client.get("/api/knowledge/repowiki/pages/../cards")
    assert response.status_code in {400, 404}


def test_compile_commit_api_creates_commit_card(client):
    response = client.post("/api/knowledge/compile/commit", json={"commit": "HEAD"})

    assert response.status_code == 200
    body = response.json()
    assert body["card_slugs"]
    detail = client.get(f"/api/knowledge/cards/{body['card_slugs'][0]}")
    assert detail.status_code == 200
    card = detail.json()
    assert card["sources"][0]["path"].startswith("git:")
    assert card["sources"][0]["source_hash"]


def test_compile_candidate_api_requires_review_before_page_is_live(
    client,
    test_data_dir: Path,
    monkeypatch,
):
    source = test_data_dir / "diary" / "review.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Review Gate\n\nLow confidence evidence.\n", encoding="utf-8")
    provider = FakeKnowledgeProvider(confidence=0.4)
    monkeypatch.setattr(
        knowledge_router,
        "_compiler",
        lambda: KnowledgeCardCompiler(test_data_dir, provider=provider),
    )

    compiled = client.post(
        "/api/knowledge/compile/file",
        json={"path": "diary/review.md"},
    )
    candidate_id = compiled.json()["candidate_ids"][0]

    assert client.get("/api/knowledge/cards/review-gate").status_code == 404
    candidates = client.get("/api/knowledge/candidates")
    assert candidates.status_code == 200
    assert candidates.json()["candidates"][0]["id"] == candidate_id

    approved = client.post(f"/api/knowledge/candidates/{candidate_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["slug"] == "review-gate"
    assert client.get("/api/knowledge/cards/review-gate").status_code == 200


def test_compile_api_returns_503_when_llm_is_not_configured(
    client,
    test_data_dir: Path,
    monkeypatch,
    tmp_path: Path,
):
    source = test_data_dir / "diary" / "missing-config.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Missing Config\n\nCompilation needs a provider.\n", encoding="utf-8")
    provider = OpenAIKnowledgeProvider(LLMService(tmp_path / "missing.yaml"))
    monkeypatch.setattr(
        knowledge_router,
        "_compiler",
        lambda: KnowledgeCardCompiler(test_data_dir, provider=provider),
    )

    response = client.post(
        "/api/knowledge/compile/file",
        json={"path": "diary/missing-config.md"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["message"] == "Knowledge compilation failed"
