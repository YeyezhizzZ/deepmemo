import sqlite3

import pytest
import yaml


def test_scenario_registry_contains_executable_critical_scenarios():
    with open("tests/e2e/scenarios.yaml", "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    scenario_ids = {item["id"] for item in data["scenarios"]}
    assert {"fs_create_write_read_move", "chat_citation_traceability"} <= scenario_ids


@pytest.mark.e2e
def test_fs_create_write_read_move_scenario(client):
    create_response = client.post(
        "/api/fs/create-file",
        json={"path": "diary/e2e-source.md", "content": "# Draft"},
    )
    assert create_response.status_code == 200

    write_response = client.post(
        "/api/fs/write",
        json={"path": "diary/e2e-source.md", "content": "# E2E\n稳定回归场景"},
    )
    assert write_response.status_code == 200

    read_response = client.get("/api/fs/content", params={"path": "diary/e2e-source.md"})
    assert read_response.status_code == 200
    assert read_response.json()["content"] == "# E2E\n稳定回归场景"

    move_response = client.post(
        "/api/fs/move",
        json={"old_path": "diary/e2e-source.md", "new_path": "ideas/e2e-target.md"},
    )
    assert move_response.status_code == 200

    moved_read_response = client.get("/api/fs/content", params={"path": "ideas/e2e-target.md"})
    assert moved_read_response.status_code == 200
    assert moved_read_response.json()["content"] == "# E2E\n稳定回归场景"


@pytest.mark.e2e
def test_chat_citation_traceability_scenario(client, db_path, test_data_dir):
    source_file = test_data_dir / "diary" / "0527.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("Agentic testing protects regressions.", encoding="utf-8")

    session_response = client.post("/sessions", json={"session_name": "E2E Citation"})
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO message (message_id, session_id, role, content, citations, created_at)
            VALUES (
                'ai-e2e',
                ?,
                'ai',
                '回答包含引用',
                '[{"local_id": 1, "evidence_id": "ev-e2e", "file_path": "diary/0527.md", "content": "Agentic testing protects regressions."}]',
                CURRENT_TIMESTAMP
            )
            """,
            (session_id,),
        )

    citations_response = client.get("/api/chat/citations", params={"message_id": "ai-e2e"})
    assert citations_response.status_code == 200
    assert citations_response.json()["citations"][0]["file_path"] == "diary/0527.md"

    references_response = client.get("/api/chat/file-references", params={"path": str(source_file)})
    assert references_response.status_code == 200
    references = references_response.json()
    assert len(references) == 1
    assert references[0]["session_id"] == session_id
    assert references[0]["message_id"] == "ai-e2e"
