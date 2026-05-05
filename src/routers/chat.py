import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from src.ai.chat_tools import ChatTool, UnknownChatToolError, get_chat_tool, list_chat_tools
from src.ai.service import knowledge_qa_service
from src.app.database import get_db_connection
from src.models.schemas import ChatRequest, ChatToolResponse, MessageResponse

router = APIRouter(prefix="/chat", tags=["chat"])


def get_session_row(session_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM session WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return dict(row)


def save_message(message_id: str, session_id: str, role: str, content: str, citations: list[dict] | None = None) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO message (message_id, session_id, role, content, citations, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, session_id, role, content, json.dumps(citations or [], ensure_ascii=False), now),
    )
    conn.commit()
    conn.close()
    return {"message_id": message_id, "session_id": session_id, "role": role, "content": content, "created_at": now}


def build_message_citations(answer) -> list[dict]:
    return [
        {
            "local_id": index,
            "evidence_id": item.source_id,
            "file_path": item.path,
            "content": item.excerpt,
        }
        for index, item in enumerate(answer.local_result.evidence, start=1)
    ]


def format_sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def update_session_message_ids(session_id: str, message_ids: list[str]):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        "UPDATE session SET message_ids = ?, updated_at = ? WHERE session_id = ?",
        (json.dumps(message_ids), now, session_id),
    )
    conn.commit()
    conn.close()


def build_llm_messages(session_id: str) -> list[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    message_ids = json.loads(cursor.execute("SELECT message_ids FROM session WHERE session_id = ?", (session_id,)).fetchone()["message_ids"])
    messages = []
    for mid in message_ids:
        row = cursor.execute("SELECT * FROM message WHERE message_id = ?", (mid,)).fetchone()
        if row:
            role = "assistant" if row["role"] == "ai" else row["role"]
            messages.append({"role": role, "content": row["content"]})
    conn.close()
    return messages


def resolve_chat_tool(request: ChatRequest) -> ChatTool | None:
    if not request.tool:
        return None
    if request.tool.scope != "next_message":
        raise HTTPException(status_code=400, detail="当前仅支持 next_message 工具作用域")
    try:
        return get_chat_tool(request.tool.tool_id)
    except UnknownChatToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tools", response_model=list[ChatToolResponse])
def get_tools():
    return [
        ChatToolResponse(
            id=tool.id,
            name=tool.name,
            description=tool.description,
            execution_type=tool.execution_type,
        )
        for tool in list_chat_tools()
    ]


@router.post("/", response_model=MessageResponse)
def chat(request: ChatRequest):
    selected_tool = resolve_chat_tool(request)
    session = get_session_row(request.session_id)
    message_ids = json.loads(session["message_ids"])
    llm_messages = build_llm_messages(request.session_id)

    user_msg_id = str(uuid.uuid4())
    save_message(user_msg_id, request.session_id, "user", request.user_message)
    message_ids.append(user_msg_id)

    answer = knowledge_qa_service.answer(request.user_message, history=llm_messages, tool=selected_tool)
    ai_content = answer.content
    citations = build_message_citations(answer)

    ai_msg_id = str(uuid.uuid4())
    save_message(ai_msg_id, request.session_id, "ai", ai_content, citations)
    message_ids.append(ai_msg_id)

    update_session_message_ids(request.session_id, message_ids)

    return MessageResponse(
        message_id=ai_msg_id,
        session_id=request.session_id,
        role="ai",
        content=ai_content,
        created_at=datetime.now(),
    )


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """SSE 流式聊天端点"""
    selected_tool = resolve_chat_tool(request)
    session = get_session_row(request.session_id)
    message_ids = json.loads(session["message_ids"])
    llm_messages = build_llm_messages(request.session_id)

    user_msg_id = str(uuid.uuid4())
    save_message(user_msg_id, request.session_id, "user", request.user_message)
    message_ids.append(user_msg_id)
    update_session_message_ids(request.session_id, message_ids)

    async def event_generator():
        full_content = ""
        try:
            answer = knowledge_qa_service.answer_stream(
                request.user_message,
                history=llm_messages,
                tool=selected_tool,
            )
            for chunk in answer.chunks:
                full_content += chunk
                yield format_sse_event({"type": "token", "content": chunk})

            ai_msg_id = str(uuid.uuid4())
            saved_message = save_message(
                ai_msg_id,
                request.session_id,
                "ai",
                full_content,
                build_message_citations(answer),
            )
            message_ids.append(ai_msg_id)
            update_session_message_ids(request.session_id, message_ids)
            yield format_sse_event({"type": "done", "message": saved_message})
        except Exception as exc:
            if full_content:
                ai_msg_id = str(uuid.uuid4())
                saved_message = save_message(ai_msg_id, request.session_id, "ai", full_content)
                message_ids.append(ai_msg_id)
                update_session_message_ids(request.session_id, message_ids)
                yield format_sse_event({"type": "done", "message": saved_message})
            yield format_sse_event({"type": "error", "content": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
def get_messages(session_id: str):
    get_session_row(session_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM message WHERE session_id = ? ORDER BY created_at", (session_id,)).fetchall()
    conn.close()
    return [
        MessageResponse(
            message_id=row["message_id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in rows
    ]


class FileReferenceResponse(BaseModel):
    session_id: str
    session_name: str
    message_id: str
    role: str
    content: str
    created_at: datetime


@router.get("/file-references", response_model=list[FileReferenceResponse])
def get_file_references(path: str):
    """获取引用了指定文件的所有消息"""
    conn = get_db_connection()
    cursor = conn.cursor()

    rows = cursor.execute("""
        SELECT m.message_id, m.session_id, m.role, m.content, m.created_at,
               s.session_name
        FROM message m
        JOIN session s ON m.session_id = s.session_id
        WHERE m.citations != '[]' AND m.citations IS NOT NULL
    """).fetchall()

    conn.close()

    references = []
    for row in rows:
        try:
            citations = json.loads(row["citations"] or "[]")
            if any(c.get("file_path") == path for c in citations):
                references.append(FileReferenceResponse(
                    session_id=row["session_id"],
                    session_name=row["session_name"],
                    message_id=row["message_id"],
                    role=row["role"],
                    content=row["content"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                ))
        except json.JSONDecodeError:
            continue

    return references
