from pathlib import Path


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
