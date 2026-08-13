from __future__ import annotations

import io
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from src.ai.types import Evidence
from src.app.main import app
from src.deepme.runtime import get_runtime
from src.deepme.worker import DeepMeWorker


def pdf_with_text(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = StreamObject()
    stream.set_data(
        f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


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


class FakeNoEvidenceQAFactory:
    def create(self, scope):
        del scope

        class Service:
            def answer_stream(self, question, history=None):
                del question, history
                return SimpleNamespace(
                    chunks=iter(["当前公开知识库没有找到足够证据回答这个问题。"]),
                    local_result=SimpleNamespace(evidence=[]),
                )

        return Service()

    def clear(self):
        return None


def test_site_creates_visitor_and_exposes_public_version(client):
    response = client.get("/api/v1/site")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "DeepMe"
    assert body["public_scope_id"] == "public"
    assert body["knowledge_version"].startswith("v2_")
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


def test_no_evidence_question_returns_explicit_status(client):
    client.get("/api/v1/site")
    session = client.post(
        "/api/v1/sessions",
        json={"mode": "system"},
    ).json()
    get_runtime().qa_factory = FakeNoEvidenceQAFactory()

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "session_id": session["session_id"],
            "user_message": "知识库没有记录的问题",
        },
    )

    assert response.status_code == 200
    assert '"answer_status": "insufficient_evidence"' in response.text
    messages = client.get(
        f"/api/v1/sessions/{session['session_id']}/messages"
    ).json()
    assert messages[-1]["answer_status"] == "insufficient_evidence"
    citations = client.get(
        f"/api/v1/messages/{messages[-1]['message_id']}/citations"
    ).json()["citations"]
    assert citations == []


def test_workspace_rejects_unsupported_file_and_other_owner(client):
    client.get("/api/v1/site")
    workspace = client.post("/api/v1/workspaces").json()

    unsupported = client.post(
        f"/api/v1/workspaces/{workspace['workspace_id']}/files",
        files={"files": ("archive.zip", b"not-a-zip", "application/zip")},
    )
    assert unsupported.status_code == 415

    other_client = TestClient(app)
    other_client.get("/api/v1/site")
    forbidden = other_client.get(
        f"/api/v1/workspaces/{workspace['workspace_id']}"
    )
    assert forbidden.status_code == 404


def test_temporary_workspace_upload_build_session_and_delete(client):
    client.get("/api/v1/site")
    workspace_response = client.post("/api/v1/workspaces")
    assert workspace_response.status_code == 200
    workspace = workspace_response.json()
    assert workspace["status"] == "empty"

    early_session = client.post(
        "/api/v1/sessions",
        json={"mode": "temporary", "workspace_id": workspace["workspace_id"]},
    )
    assert early_session.status_code == 409

    upload_response = client.post(
        f"/api/v1/workspaces/{workspace['workspace_id']}/files",
        files={
            "files": (
                "notes.md",
                b"# Notes\n\nworkspace-needle belongs to this upload.\n",
                "text/markdown",
            )
        },
    )
    assert upload_response.status_code == 202
    assert upload_response.json()["status"] == "processing"

    worker = DeepMeWorker(get_runtime())
    while worker.run_once():
        pass

    ready_response = client.get(
        f"/api/v1/workspaces/{workspace['workspace_id']}"
    )
    assert ready_response.status_code == 200
    ready = ready_response.json()
    assert ready["status"] == "ready"
    assert ready["knowledge_version"].startswith("v1_")
    assert ready["files"][0]["status"] == "ready"

    session_response = client.post(
        "/api/v1/sessions",
        json={"mode": "temporary", "workspace_id": workspace["workspace_id"]},
    )
    assert session_response.status_code == 200
    session = session_response.json()
    assert session["scope_id"] == workspace["workspace_id"]

    runtime = get_runtime()
    scope_record = runtime.registry.get_scope(workspace["workspace_id"])
    service = runtime.qa_factory.create(
        runtime.registry.resolve(workspace["workspace_id"], scope_record.owner_key)
    )
    result = service.local_search_agent.search("workspace-needle")
    assert result.evidence

    stream_response = client.post(
        "/api/v1/chat/stream",
        json={
            "session_id": session["session_id"],
            "user_message": "workspace-needle",
        },
    )
    assert stream_response.status_code == 200
    assert '"answer_status": "grounded"' in stream_response.text
    messages = client.get(
        f"/api/v1/sessions/{session['session_id']}/messages"
    ).json()
    assert "[1]" in messages[-1]["content"]
    citations = client.get(
        f"/api/v1/messages/{messages[-1]['message_id']}/citations"
    ).json()["citations"]
    assert citations
    assert citations[0]["scope_id"] == workspace["workspace_id"]
    assert citations[0]["display_name"] == "notes.md"

    delete_response = client.delete(
        f"/api/v1/workspaces/{workspace['workspace_id']}"
    )
    assert delete_response.status_code == 202
    inaccessible = client.get(
        f"/api/v1/sessions/{session['session_id']}/messages"
    )
    assert inaccessible.status_code == 404
    inaccessible_citations = client.get(
        f"/api/v1/messages/{messages[-1]['message_id']}/citations"
    )
    assert inaccessible_citations.status_code == 404

    while worker.run_once():
        pass
    deletion = client.get(
        f"/api/v1/workspaces/{workspace['workspace_id']}/deletion"
    )
    assert deletion.status_code == 200
    assert deletion.json()["status"] == "deleted"


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
    assert all(item.path != "private.md" for item in private_result.evidence)
    assert all("private-needle" not in item.excerpt for item in private_result.evidence)


def test_two_temporary_workspaces_use_separate_indexes(client):
    client.get("/api/v1/site")
    first = client.post("/api/v1/workspaces").json()
    second = client.post("/api/v1/workspaces").json()
    client.post(
        f"/api/v1/workspaces/{first['workspace_id']}/files",
        files={"files": ("first.md", "苹果火箭甲".encode(), "text/markdown")},
    )
    client.post(
        f"/api/v1/workspaces/{second['workspace_id']}/files",
        files={"files": ("second.md", "海盐星球乙".encode(), "text/markdown")},
    )
    worker = DeepMeWorker(get_runtime())
    while worker.run_once():
        pass

    runtime = get_runtime()
    first_scope = runtime.registry.get_scope(first["workspace_id"])
    second_scope = runtime.registry.get_scope(second["workspace_id"])
    first_service = runtime.qa_factory.create(
        runtime.registry.resolve(first["workspace_id"], first_scope.owner_key)
    )
    second_service = runtime.qa_factory.create(
        runtime.registry.resolve(second["workspace_id"], second_scope.owner_key)
    )

    first_result = first_service.local_search_agent.search("苹果火箭甲")
    second_result = second_service.local_search_agent.search("海盐星球乙")

    assert first_result.evidence
    assert second_result.evidence
    assert all("海盐星球乙" not in item.excerpt for item in first_result.evidence)
    assert all("苹果火箭甲" not in item.excerpt for item in second_result.evidence)


def test_pdf_upload_preserves_page_citation(client):
    client.get("/api/v1/site")
    workspace = client.post("/api/v1/workspaces").json()
    response = client.post(
        f"/api/v1/workspaces/{workspace['workspace_id']}/files",
        files={
            "files": (
                "evidence.pdf",
                pdf_with_text("pdf-needle evidence"),
                "application/pdf",
            )
        },
    )
    assert response.status_code == 202
    worker = DeepMeWorker(get_runtime())
    while worker.run_once():
        pass

    runtime = get_runtime()
    scope = runtime.registry.get_scope(workspace["workspace_id"])
    service = runtime.qa_factory.create(
        runtime.registry.resolve(workspace["workspace_id"], scope.owner_key)
    )
    result = service.local_search_agent.search("pdf-needle")

    assert result.evidence
    assert result.evidence[0].display_name == "evidence.pdf"
    assert result.evidence[0].source_type == "pdf"
    assert result.evidence[0].page_start == 1
    assert result.evidence[0].page_end == 1
