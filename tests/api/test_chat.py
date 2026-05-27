from __future__ import annotations

from types import SimpleNamespace

import src.routers.chat as chat_router_module


def test_chat_endpoint_persists_answer_and_citations(client, insert_session):
    class FakeKnowledgeQAService:
        def answer(self, question, history=None, tool=None):
            evidence = [
                SimpleNamespace(
                    source_id="evidence-1",
                    path="diary/0527.md",
                    excerpt="quoted evidence",
                )
            ]
            return SimpleNamespace(
                content="assistant answer",
                local_result=SimpleNamespace(evidence=evidence),
            )

    session_id = insert_session("Chat Session")
    original_service = chat_router_module.knowledge_qa_service
    chat_router_module.knowledge_qa_service = FakeKnowledgeQAService()
    try:
        response = client.post(
            "/chat",
            json={
                "session_id": session_id,
                "user_message": "What should I test?",
            },
        )
    finally:
        chat_router_module.knowledge_qa_service = original_service

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["role"] == "ai"
    assert body["content"] == "assistant answer"

    messages_response = client.get(f"/chat/{session_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 2
    assert [message["role"] for message in messages] == ["user", "ai"]

    citations_response = client.get("/api/chat/citations", params={"message_id": body["message_id"]})
    assert citations_response.status_code == 200
    assert citations_response.json()["citations"][0]["file_path"] == "diary/0527.md"


def test_chat_tools_route_returns_tool_metadata(client):
    response = client.get("/chat/tools")

    assert response.status_code == 200
    tools = response.json()
    assert isinstance(tools, list)
    assert tools
    assert {"id", "name", "description", "execution_type"} <= set(tools[0])


def test_chat_stream_persists_chunks_and_updates_session(client, insert_session):
    class FakeKnowledgeQAService:
        def answer_stream(self, question, history=None, tool=None):
            evidence = [
                SimpleNamespace(
                    source_id="stream-evidence-1",
                    path="diary/0527.md",
                    excerpt="stream excerpt",
                )
            ]
            return SimpleNamespace(
                chunks=["Hel", "lo"],
                local_result=SimpleNamespace(evidence=evidence),
            )

    session_id = insert_session("Stream Session")
    original_service = chat_router_module.knowledge_qa_service
    chat_router_module.knowledge_qa_service = FakeKnowledgeQAService()
    try:
        response = client.post(
            "/chat/stream",
            json={
                "session_id": session_id,
                "user_message": "stream this",
            },
        )
    finally:
        chat_router_module.knowledge_qa_service = original_service

    assert response.status_code == 200
    body = response.text
    assert 'data: {"type": "token", "content": "Hel"}' in body
    assert 'data: {"type": "token", "content": "lo"}' in body
    assert '"type": "done"' in body

    messages_response = client.get(f"/chat/{session_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 2
    assert messages[1]["content"] == "Hello"

    citations_response = client.get("/api/chat/citations", params={"message_id": messages[1]["message_id"]})
    assert citations_response.status_code == 200
    assert citations_response.json()["citations"][0]["file_path"] == "diary/0527.md"


def test_chat_rejects_unknown_tool(client, insert_session):
    session_id = insert_session("Tool Session")

    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "user_message": "Use a tool",
            "tool": {"tool_id": "missing-tool", "scope": "next_message"},
        },
    )

    assert response.status_code == 400
    assert "未知 Chat Tool" in response.json()["detail"]


def test_chat_rejects_invalid_tool_scope(client, insert_session):
    session_id = insert_session("Tool Scope Session")

    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "user_message": "Use a tool",
            "tool": {"tool_id": "hv-analysis", "scope": "session"},
        },
    )

    assert response.status_code == 400
    assert "next_message" in response.json()["detail"]


def test_chat_stream_rejects_missing_session(client):
    response = client.post(
        "/chat/stream",
        json={
            "session_id": "missing-session",
            "user_message": "hello",
        },
    )

    assert response.status_code == 404
