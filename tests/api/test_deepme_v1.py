from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.ai.types import Evidence
from src.app.main import app
from src.deepme.runtime import get_runtime


class FakeScopedQAService:
    def answer_stream(self, question, history=None):
        del question, history
        evidence = [
            Evidence(
                path="profile.md",
                start_line=1,
                end_line=3,
                excerpt="1: # Public Profile\n2:\n3: DeepMe public fixture knowledge.",
                score=0.9,
                query="public fixture",
            )
        ]
        return SimpleNamespace(
            chunks=iter(["公开", "回答[1]"]),
            local_result=SimpleNamespace(evidence=evidence),
        )


class FakeScopedQAFactory:
    def create(self, scope):
        assert scope.scope_id == "public"
        return FakeScopedQAService()

    def clear(self):
        return None


def test_site_creates_visitor_and_exposes_public_version(client):
    response = client.get("/api/v1/site")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "DeepMe"
    assert body["public_scope_id"] == "public"
    assert body["knowledge_version"].startswith("v1_")
    assert response.cookies.get("deepme_visitor")


def test_public_session_stream_and_citations_keep_scope_lineage(client):
    site_response = client.get("/api/v1/site")
    version = site_response.json()["knowledge_version"]
    session_response = client.post("/api/v1/sessions", json={"mode": "system"})
    assert session_response.status_code == 200
    session = session_response.json()
    assert session["scope_id"] == "public"
    assert session["knowledge_version"] == version

    runtime = get_runtime()
    runtime.qa_factory = FakeScopedQAFactory()
    stream_response = client.post(
        "/api/v1/chat/stream",
        json={
            "session_id": session["session_id"],
            "user_message": "介绍一下作者",
        },
    )

    assert stream_response.status_code == 200
    assert "event: meta" in stream_response.text
    assert f'"knowledge_version": "{version}"' in stream_response.text
    assert "event: token" in stream_response.text
    assert "event: done" in stream_response.text
    assert '"answer_status": "grounded"' in stream_response.text

    messages_response = client.get(
        f"/api/v1/sessions/{session['session_id']}/messages"
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert [message["role"] for message in messages] == ["user", "ai"]
    assert messages[1]["knowledge_scope_id"] == "public"
    assert messages[1]["knowledge_version"] == version
    assert messages[1]["answer_status"] == "grounded"

    citations_response = client.get(
        f"/api/v1/messages/{messages[1]['message_id']}/citations"
    )
    assert citations_response.status_code == 200
    citation = citations_response.json()["citations"][0]
    assert citation["scope_id"] == "public"
    assert citation["knowledge_version"] == version
    assert citation["file_path"] == "profile.md"
    assert citation["start_line"] == 1
    assert citation["end_line"] == 3


def test_anonymous_visitors_cannot_read_each_others_sessions(client):
    client.get("/api/v1/site")
    session = client.post(
        "/api/v1/sessions",
        json={"mode": "system"},
    ).json()

    other_client = TestClient(app)
    response = other_client.get(
        f"/api/v1/sessions/{session['session_id']}/messages"
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "scope_not_found"


def test_chat_rejects_client_supplied_scope_id(client):
    client.get("/api/v1/site")
    session = client.post(
        "/api/v1/sessions",
        json={"mode": "system"},
    ).json()

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "session_id": session["session_id"],
            "user_message": "hello",
            "scope_id": "legacy",
        },
    )

    assert response.status_code == 422


def test_temporary_mode_is_not_enabled_before_workspace_phase(client):
    client.get("/api/v1/site")

    response = client.post(
        "/api/v1/sessions",
        json={"mode": "temporary", "workspace_id": "ws_missing"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "temporary_workspace_not_implemented"


def test_scoped_qa_searches_public_snapshot_only(isolated_app_state):
    private_note = isolated_app_state.data_dir / "private.md"
    private_note.write_text("private-needle", encoding="utf-8")
    public_note = isolated_app_state.public_source_dir / "project.md"
    public_note.write_text("# Project\n\npublic-needle\n", encoding="utf-8")

    runtime = get_runtime()
    scope = runtime.ensure_public_ready()
    service = runtime.qa_factory.create(scope)

    public_result = service.local_search_agent.search("public-needle")
    private_result = service.local_search_agent.search("private-needle")

    assert public_result.evidence
    assert all(item.path != "private.md" for item in public_result.evidence)
    assert private_result.evidence == []
