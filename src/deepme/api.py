from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from src.app.database import connection_scope
from src.deepme.public_knowledge import PublicKnowledgeBuildError
from src.deepme.runtime import get_runtime
from src.deepme.scopes import ScopeNotFoundError, ScopeNotReadyError


router = APIRouter(prefix="/api/v1", tags=["deepme-v1"])
MAX_HISTORY_MESSAGES = 20


class SiteResponse(BaseModel):
    name: str
    bio: str
    avatar: str
    public_scope_id: str
    knowledge_version: str
    updated_at: str
    suggested_questions: list[str]


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["system", "temporary"] = "system"
    workspace_id: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    scope_id: str
    mode: str
    session_name: str
    session_topic: str = ""
    knowledge_version: str | None = None
    created_at: str
    updated_at: str
    expires_at: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    user_message: str = Field(min_length=1, max_length=20_000)


class MessageResponse(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    answer_status: str
    knowledge_scope_id: str | None = None
    knowledge_version: str | None = None
    created_at: str


class CitationResponse(BaseModel):
    local_id: int
    evidence_id: str
    scope_id: str
    knowledge_version: str
    file_path: str
    start_line: int
    end_line: int
    content: str


class MessageCitationsResponse(BaseModel):
    message_id: str
    citations: list[CitationResponse]


@router.get("/site", response_model=SiteResponse)
def get_site(request: Request, response: Response):
    runtime = get_runtime()
    runtime.identity.resolve(request, response)
    scope = _ensure_public_scope()
    manifest = json.loads(scope.manifest_path.read_text(encoding="utf-8"))
    return SiteResponse(
        name=runtime.settings.site_name,
        bio=runtime.settings.site_bio,
        avatar=runtime.settings.site_avatar,
        public_scope_id=scope.scope_id,
        knowledge_version=scope.knowledge_version,
        updated_at=str(manifest.get("built_at") or ""),
        suggested_questions=[
            "你最近负责的项目是什么？",
            "你在项目中做过哪些技术取舍？",
            "哪次实验结果改变了原来的判断？",
            "你的开源贡献主要集中在哪些方向？",
        ],
    )


@router.get("/health/live")
def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
def readiness():
    scope = _ensure_public_scope()
    return {
        "status": "ready",
        "scope_id": scope.scope_id,
        "knowledge_version": scope.knowledge_version,
    }


@router.post("/sessions", response_model=SessionResponse)
def create_session(data: SessionCreateRequest, request: Request, response: Response):
    if data.mode != "system" or data.workspace_id is not None:
        raise HTTPException(
            status_code=400,
            detail={"code": "temporary_workspace_not_implemented"},
        )

    runtime = get_runtime()
    owner = runtime.identity.resolve(request, response)
    scope = _ensure_public_scope()
    session_id = str(uuid.uuid4())
    now = _now()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=runtime.settings.session_ttl_hours)
    ).replace(microsecond=0).isoformat()
    with connection_scope() as conn:
        conn.execute(
            """
            INSERT INTO session (
                session_id, session_name, message_ids, session_topic,
                session_summary, owner_key, scope_id, expires_at,
                created_at, updated_at
            )
            VALUES (?, ?, '[]', '', '', ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                "新会话",
                owner.owner_key,
                scope.scope_id,
                expires_at,
                now,
                now,
            ),
        )
    return SessionResponse(
        session_id=session_id,
        scope_id=scope.scope_id,
        mode=scope.scope_type,
        session_name="新会话",
        knowledge_version=scope.knowledge_version,
        created_at=now,
        updated_at=now,
        expires_at=expires_at,
    )


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(request: Request, response: Response):
    runtime = get_runtime()
    owner = runtime.identity.resolve(request, response)
    now = _now()
    with connection_scope() as conn:
        rows = conn.execute(
            """
            SELECT s.*, ks.scope_type, ks.current_version
            FROM session s
            JOIN knowledge_scope ks ON ks.scope_id = s.scope_id
            WHERE s.owner_key = ?
              AND (s.expires_at IS NULL OR s.expires_at > ?)
            ORDER BY s.updated_at DESC
            """,
            (owner.owner_key, now),
        ).fetchall()
    return [_session_response(row) for row in rows]


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
def list_messages(session_id: str, request: Request):
    owner_key = _require_owner(request)
    _require_session(session_id, owner_key)
    with connection_scope() as conn:
        rows = conn.execute(
            "SELECT * FROM message WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
    return [_message_response(row) for row in rows]


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request):
    owner_key = _require_owner(request)
    _require_session(session_id, owner_key)
    with connection_scope() as conn:
        conn.execute("DELETE FROM message WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM session WHERE session_id = ?", (session_id,))
    return {"status": "deleted"}


@router.post("/chat/stream")
def chat_stream(data: ChatRequest, request: Request):
    owner_key = _require_owner(request)
    session = _require_session(data.session_id, owner_key)
    runtime = get_runtime()
    try:
        scope = runtime.registry.resolve(session["scope_id"], owner_key)
    except ScopeNotFoundError as exc:
        raise _scope_not_found() from exc
    except ScopeNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "scope_not_ready"},
        ) from exc

    history = _build_history(data.session_id)
    user_message_id = str(uuid.uuid4())
    _save_message(
        message_id=user_message_id,
        session_id=data.session_id,
        role="user",
        content=data.user_message,
        answer_status="pending",
        scope_id=scope.scope_id,
        knowledge_version=scope.knowledge_version,
        citations=[],
    )
    _append_message_id(data.session_id, user_message_id)
    qa_service = runtime.qa_factory.create(scope)

    def event_generator():
        yield _sse(
            "meta",
            {
                "session_id": data.session_id,
                "scope_id": scope.scope_id,
                "knowledge_version": scope.knowledge_version,
            },
        )
        full_content = ""
        try:
            answer = qa_service.answer_stream(data.user_message, history=history)
            for chunk in answer.chunks:
                if not chunk:
                    continue
                full_content += chunk
                yield _sse("token", {"content": chunk})

            answer_status = (
                "grounded" if answer.local_result.evidence else "insufficient_evidence"
            )
            citations = _build_citations(
                answer.local_result.evidence,
                scope_id=scope.scope_id,
                knowledge_version=scope.knowledge_version,
            )
            ai_message_id = str(uuid.uuid4())
            created_at = _save_message(
                message_id=ai_message_id,
                session_id=data.session_id,
                role="ai",
                content=full_content,
                answer_status=answer_status,
                scope_id=scope.scope_id,
                knowledge_version=scope.knowledge_version,
                citations=citations,
            )
            _append_message_id(data.session_id, ai_message_id)
            _update_session_topic(data.session_id, data.user_message)
            yield _sse(
                "done",
                {
                    "message_id": ai_message_id,
                    "answer_status": answer_status,
                    "citation_count": len(citations),
                    "created_at": created_at,
                },
            )
        except Exception:
            yield _sse(
                "error",
                {
                    "code": "answer_failed",
                    "message": "回答生成失败，请稍后重试。",
                },
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/messages/{message_id}/citations",
    response_model=MessageCitationsResponse,
)
def get_message_citations(message_id: str, request: Request):
    owner_key = _require_owner(request)
    with connection_scope() as conn:
        row = conn.execute(
            """
            SELECT m.message_id, m.citations
            FROM message m
            JOIN session s ON s.session_id = m.session_id
            WHERE m.message_id = ? AND s.owner_key = ?
            """,
            (message_id, owner_key),
        ).fetchone()
    if not row:
        raise _scope_not_found()

    try:
        citations = json.loads(row["citations"] or "[]")
    except json.JSONDecodeError:
        citations = []
    return MessageCitationsResponse(
        message_id=message_id,
        citations=[CitationResponse(**citation) for citation in citations],
    )


def _ensure_public_scope():
    try:
        return get_runtime().ensure_public_ready()
    except (
        OSError,
        PublicKnowledgeBuildError,
        ScopeNotFoundError,
        ScopeNotReadyError,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "public_scope_unavailable"},
        ) from exc


def _require_owner(request: Request) -> str:
    owner_key = get_runtime().identity.existing_owner_key(request)
    if owner_key is None:
        raise _scope_not_found()
    return owner_key


def _require_session(session_id: str, owner_key: str):
    with connection_scope() as conn:
        row = conn.execute(
            """
            SELECT s.*, ks.scope_type, ks.current_version
            FROM session s
            JOIN knowledge_scope ks ON ks.scope_id = s.scope_id
            WHERE s.session_id = ? AND s.owner_key = ?
            """,
            (session_id, owner_key),
        ).fetchone()
    if not row:
        raise _scope_not_found()
    if row["expires_at"] and row["expires_at"] <= _now():
        raise HTTPException(status_code=410, detail={"code": "session_expired"})
    return row


def _save_message(
    *,
    message_id: str,
    session_id: str,
    role: str,
    content: str,
    answer_status: str,
    scope_id: str,
    knowledge_version: str,
    citations: list[dict],
) -> str:
    created_at = _now()
    with connection_scope() as conn:
        conn.execute(
            """
            INSERT INTO message (
                message_id, session_id, role, content, citations, answer_status,
                knowledge_scope_id, knowledge_version, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                role,
                content,
                json.dumps(citations, ensure_ascii=False),
                answer_status,
                scope_id,
                knowledge_version,
                created_at,
            ),
        )
    return created_at


def _append_message_id(session_id: str, message_id: str) -> None:
    with connection_scope() as conn:
        row = conn.execute(
            "SELECT message_ids FROM session WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        message_ids = json.loads(row["message_ids"] or "[]")
        message_ids.append(message_id)
        conn.execute(
            "UPDATE session SET message_ids = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(message_ids), _now(), session_id),
        )


def _build_history(session_id: str) -> list[dict]:
    with connection_scope() as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM message
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, MAX_HISTORY_MESSAGES),
        ).fetchall()
    history = []
    for row in reversed(rows):
        history.append(
            {
                "role": "assistant" if row["role"] == "ai" else "user",
                "content": row["content"],
            }
        )
    return history


def _build_citations(evidence, *, scope_id: str, knowledge_version: str) -> list[dict]:
    return [
        {
            "local_id": index,
            "evidence_id": item.source_id,
            "scope_id": scope_id,
            "knowledge_version": knowledge_version,
            "file_path": item.path,
            "start_line": item.start_line,
            "end_line": item.end_line,
            "content": item.excerpt,
        }
        for index, item in enumerate(evidence, start=1)
    ]


def _update_session_topic(session_id: str, user_message: str) -> None:
    topic = " ".join(user_message.split())
    if len(topic) > 20:
        topic = f"{topic[:20]}..."
    with connection_scope() as conn:
        conn.execute(
            "UPDATE session SET session_topic = ?, updated_at = ? WHERE session_id = ?",
            (topic, _now(), session_id),
        )


def _session_response(row) -> SessionResponse:
    return SessionResponse(
        session_id=row["session_id"],
        scope_id=row["scope_id"],
        mode=row["scope_type"],
        session_name=row["session_name"],
        session_topic=row["session_topic"] or "",
        knowledge_version=row["current_version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
    )


def _message_response(row) -> MessageResponse:
    return MessageResponse(
        message_id=row["message_id"],
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        answer_status=row["answer_status"],
        knowledge_scope_id=row["knowledge_scope_id"],
        knowledge_version=row["knowledge_version"],
        created_at=row["created_at"],
    )


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _scope_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "scope_not_found"})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
