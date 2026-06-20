from __future__ import annotations

from types import SimpleNamespace

import src.routers.chat as chat_router_module
from src.knowledge.card_store import CardStore


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


def test_chat_extracts_conversation_memory_after_four_messages(client, insert_session, test_data_dir):
    class FakeKnowledgeQAService:
        def answer(self, question, history=None, tool=None):
            return SimpleNamespace(
                content="同意，这个决策应该沉淀。",
                local_result=SimpleNamespace(evidence=[]),
            )

    session_id = insert_session("Knowledge Session")
    original_service = chat_router_module.knowledge_qa_service
    chat_router_module.knowledge_qa_service = FakeKnowledgeQAService()
    try:
        for message in [
            "我们应该用 Louvain 做社区发现。",
            "对，就按这个决策沉淀。",
        ]:
            response = client.post("/chat", json={"session_id": session_id, "user_message": message})
            assert response.status_code == 200
    finally:
        chat_router_module.knowledge_qa_service = original_service

    cards = CardStore(data_dir=test_data_dir).list_cards(card_type="decision")
    assert cards
    assert cards[0].sources[0].path.startswith("raw/conversations/")


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


def test_chat_knowledge_commands_add_show_update_pin_and_list(client, insert_session, test_data_dir):
    class FailingKnowledgeQAService:
        def answer(self, question, history=None, tool=None):
            raise AssertionError("/knowledge commands must not call normal QA")

    session_id = insert_session("Knowledge Commands")
    original_service = chat_router_module.knowledge_qa_service
    chat_router_module.knowledge_qa_service = FailingKnowledgeQAService()
    try:
        add_response = client.post(
            "/chat",
            json={
                "session_id": session_id,
                "user_message": "/knowledge add Card First Search :: Local search should query Cards before Markdown.",
            },
        )
        assert add_response.status_code == 200
        assert "card-first-search" in add_response.json()["content"]

        show_response = client.post(
            "/chat",
            json={"session_id": session_id, "user_message": "/knowledge show card-first-search"},
        )
        assert show_response.status_code == 200
        assert "Local search should query Cards" in show_response.json()["content"]

        update_response = client.post(
            "/chat",
            json={
                "session_id": session_id,
                "user_message": "/knowledge update card-first-search :: Human reviewed command update.",
            },
        )
        assert update_response.status_code == 200
        assert "已更新" in update_response.json()["content"]

        pin_response = client.post(
            "/chat",
            json={"session_id": session_id, "user_message": "/knowledge pin card-first-search definition"},
        )
        assert pin_response.status_code == 200
        assert "已固定" in pin_response.json()["content"]

        list_response = client.post(
            "/chat",
            json={"session_id": session_id, "user_message": "/knowledge list"},
        )
        assert list_response.status_code == 200
        assert "Card First Search" in list_response.json()["content"]
    finally:
        chat_router_module.knowledge_qa_service = original_service

    card = CardStore(data_dir=test_data_dir).load("card-first-search")
    assert card is not None
    assert card.definition == "Human reviewed command update."
    assert card.human_edited is True
    assert "definition" in card.human_edited_fields


def test_chat_knowledge_command_returns_readable_error(client, insert_session):
    session_id = insert_session("Invalid Knowledge Command")

    response = client.post(
        "/chat",
        json={"session_id": session_id, "user_message": "/knowledge merge a b"},
    )

    assert response.status_code == 200
    assert "不支持" in response.json()["content"]


def test_chat_stream_rejects_missing_session(client):
    response = client.post(
        "/chat/stream",
        json={
            "session_id": "missing-session",
            "user_message": "hello",
        },
    )

    assert response.status_code == 404
