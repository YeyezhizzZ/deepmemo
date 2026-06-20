def test_legacy_wiki_routes_are_not_mounted(client):
    assert client.get("/wiki/graph").status_code == 404
    assert client.get("/wiki/pages").status_code == 404
    assert client.get("/wiki/page", params={"path": "wiki/index.md"}).status_code == 404
    assert client.post("/wiki/rebuild", json={"clean": False}).status_code == 404
    assert client.post("/wiki/ingest", json={"source_path": "raw/source.md"}).status_code == 404


def test_knowledge_routes_remain_the_supported_surface(client):
    response = client.get("/api/knowledge/cards")
    assert response.status_code == 200
    assert response.json()["cards"] == []
