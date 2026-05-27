from __future__ import annotations

from pathlib import Path

import src.routers.wiki as wiki_router_module


def test_wiki_page_crud_and_listing(client):
    create_response = client.post(
        "/wiki/page",
        json={
            "path": "wiki/concepts/agentic-testing.md",
            "title": "Agentic Testing",
            "type": "concept",
            "body": "Initial body",
            "tags": ["testing", "agentic"],
            "sources": ["data/diary/0527.md"],
            "related": ["wiki/sources/seed.md"],
            "status": "active",
            "aliases": ["Agentic Test"],
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["path"] == "wiki/concepts/agentic-testing.md"

    get_response = client.get("/wiki/page", params={"path": "wiki/concepts/agentic-testing.md"})
    assert get_response.status_code == 200
    page = get_response.json()
    assert page["title"] == "Agentic Testing"
    assert page["type"] == "concept"
    assert page["status"] == "active"
    assert page["body"].strip() == "Initial body"
    assert "Initial body" in page["content"]

    list_response = client.get("/wiki/pages", params={"page_type": "concept"})
    assert list_response.status_code == 200
    pages = list_response.json()["pages"]
    assert len(pages) == 1
    assert pages[0]["path"] == "wiki/concepts/agentic-testing.md"
    assert pages[0]["summary"] == "Initial body"

    update_response = client.put(
        "/wiki/page",
        json={
            "path": "wiki/concepts/agentic-testing.md",
            "content": page["content"].replace("Initial body", "Updated body"),
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["path"] == "wiki/concepts/agentic-testing.md"

    updated_response = client.get("/wiki/page", params={"path": "wiki/concepts/agentic-testing.md"})
    assert updated_response.status_code == 200
    assert updated_response.json()["body"].strip() == "Updated body"

    move_response = client.post(
        "/wiki/move",
        json={
            "old_path": "wiki/concepts/agentic-testing.md",
            "new_path": "wiki/concepts/agentic-testing-v2.md",
        },
    )
    assert move_response.status_code == 200
    assert move_response.json()["new_path"] == "wiki/concepts/agentic-testing-v2.md"

    old_response = client.get("/wiki/page", params={"path": "wiki/concepts/agentic-testing.md"})
    assert old_response.status_code == 404

    moved_response = client.get("/wiki/page", params={"path": "wiki/concepts/agentic-testing-v2.md"})
    assert moved_response.status_code == 200
    assert moved_response.json()["title"] == "Agentic Testing"

    delete_response = client.delete("/wiki/page", params={"path": "wiki/concepts/agentic-testing-v2.md"})
    assert delete_response.status_code == 200
    assert delete_response.json()["path"] == "wiki/concepts/agentic-testing-v2.md"

    deleted_response = client.get("/wiki/page", params={"path": "wiki/concepts/agentic-testing-v2.md"})
    assert deleted_response.status_code == 404


def test_wiki_page_conflict_and_missing_delete(client):
    create_response = client.post(
        "/wiki/page",
        json={
            "path": "wiki/concepts/duplicate.md",
            "title": "Duplicate Page",
            "type": "concept",
            "body": "First body",
            "status": "active",
        },
    )
    assert create_response.status_code == 200

    duplicate_response = client.post(
        "/wiki/page",
        json={
            "path": "wiki/concepts/duplicate.md",
            "title": "Duplicate Page",
            "type": "concept",
            "body": "Second body",
            "status": "active",
        },
    )
    assert duplicate_response.status_code == 409

    missing_delete_response = client.delete("/wiki/page", params={"path": "wiki/concepts/missing.md"})
    assert missing_delete_response.status_code == 404


def test_wiki_move_conflict_and_missing_source(client):
    create_a = client.post(
        "/wiki/page",
        json={
            "path": "wiki/concepts/source-a.md",
            "title": "Source A",
            "type": "concept",
            "body": "A body",
            "status": "active",
        },
    )
    assert create_a.status_code == 200

    create_b = client.post(
        "/wiki/page",
        json={
            "path": "wiki/concepts/source-b.md",
            "title": "Source B",
            "type": "concept",
            "body": "B body",
            "status": "active",
        },
    )
    assert create_b.status_code == 200

    conflict_response = client.post(
        "/wiki/move",
        json={
            "old_path": "wiki/concepts/source-a.md",
            "new_path": "wiki/concepts/source-b.md",
        },
    )
    assert conflict_response.status_code == 409

    missing_source_response = client.post(
        "/wiki/move",
        json={
            "old_path": "wiki/concepts/missing.md",
            "new_path": "wiki/concepts/target.md",
        },
    )
    assert missing_source_response.status_code == 404


def test_wiki_tree_graph_health_policy_and_directory_routes(client, test_data_dir):
    policy_dir = test_data_dir / "policy"
    policy_dir.mkdir(parents=True)
    (policy_dir / "purpose.md").write_text("Policy purpose", encoding="utf-8")
    (policy_dir / "schema.md").write_text("Policy schema", encoding="utf-8")

    directory_response = client.post("/wiki/directory", json={"path": "wiki/notes"})
    assert directory_response.status_code == 200
    assert directory_response.json()["dir_path"] == "wiki/notes"

    source_response = client.post(
        "/wiki/page",
        json={
            "path": "wiki/sources/seed.md",
            "title": "Seed Source",
            "type": "source",
            "body": "Link to [[Agentic Testing]]",
            "status": "active",
        },
    )
    assert source_response.status_code == 200

    target_response = client.post(
        "/wiki/page",
        json={
            "path": "wiki/concepts/agentic-testing.md",
            "title": "Agentic Testing",
            "type": "concept",
            "body": "Concept body",
            "status": "active",
        },
    )
    assert target_response.status_code == 200

    tree_response = client.get("/wiki/tree")
    assert tree_response.status_code == 200
    paths = _flatten_tree_paths(tree_response.json()["tree"])
    assert "wiki/notes" in paths
    assert "wiki/concepts/agentic-testing.md" in paths
    assert "wiki/sources/seed.md" in paths

    graph_response = client.get("/wiki/graph")
    assert graph_response.status_code == 200
    graph = graph_response.json()
    assert graph["meta"]["total_nodes"] >= 2
    assert graph["meta"]["total_edges"] >= 1
    assert graph["edges"]

    health_response = client.get("/wiki/health")
    assert health_response.status_code == 200
    health = health_response.json()
    assert health["stats"]["total_pages"] == 2
    assert health["links"]["dangling_count"] == 0
    assert health["orphan_pages"] == []

    policy_response = client.get("/wiki/policy")
    assert policy_response.status_code == 200
    policy = policy_response.json()
    assert policy["purpose.md"] == "Policy purpose"
    assert policy["schema.md"] == "Policy schema"
    assert set(policy) == {
        "purpose.md",
        "schema.md",
        "ingest-rules.md",
        "citation-rules.md",
        "maintenance-rules.md",
    }


def test_wiki_ingest_uses_monkeypatched_pipeline(client, test_data_dir, monkeypatch):
    source_file = test_data_dir / "raw" / "source.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("# Source", encoding="utf-8")

    class FakeIngestResult:
        written_paths = ["wiki/sources/source.md"]
        warnings = ["minor warning"]

    captured = {}

    def fake_auto_ingest(*, source_path, wiki_dir, index, overview):
        captured["source_path"] = source_path
        captured["wiki_dir"] = wiki_dir
        captured["index"] = index
        captured["overview"] = overview
        return FakeIngestResult()

    monkeypatch.chdir(test_data_dir.parent)
    monkeypatch.setattr(wiki_router_module, "auto_ingest", fake_auto_ingest)

    response = client.post("/wiki/ingest", json={"source_path": str(source_file)})

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Ingest completed successfully"
    assert body["written_paths"] == ["wiki/sources/source.md"]
    assert body["warnings"] == ["minor warning"]
    assert captured["source_path"] == str(source_file)
    assert captured["wiki_dir"] == wiki_router_module.WIKI_DIR
    assert captured["index"] == (wiki_router_module.WIKI_DIR / "index.md").read_text(encoding="utf-8")
    assert captured["overview"] == (wiki_router_module.WIKI_DIR / "overview.md").read_text(encoding="utf-8")


def test_wiki_rebuild_returns_health_snapshot(client, monkeypatch):
    monkeypatch.setattr(
        wiki_router_module,
        "run_diary_wiki_ingest",
        lambda config: {"written_paths": ["wiki/sources/source.md"], "warnings": []},
    )
    monkeypatch.setattr(
        wiki_router_module,
        "build_wiki_health_report",
        lambda: {"pages": {"total": 1}, "links": {"dangling_count": 0}},
    )

    response = client.post("/wiki/rebuild", json={"clean": True})

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Wiki rebuilt successfully"
    assert body["written_paths"] == ["wiki/sources/source.md"]
    assert body["warnings"] == []
    assert body["health"] == {"pages": {"total": 1}, "links": {"dangling_count": 0}}


def _flatten_tree_paths(nodes):
    paths = []
    for node in nodes:
        paths.append(node["path"])
        paths.extend(_flatten_tree_paths(node.get("children", [])))
    return paths
