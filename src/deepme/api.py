from __future__ import annotations

import json
import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from src.app.database import connection_scope
from src.deepme.public_knowledge import PublicKnowledgeBuildError
from src.deepme.rate_limit import RateLimitExceeded
from src.deepme.runtime import get_runtime
from src.deepme.scopes import (
    ScopeExpiredError,
    ScopeNotFoundError,
    ScopeNotReadyError,
)


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
    display_name: str | None = None
    source_type: str = "markdown"
    start_line: int
    end_line: int
    page_start: int | None = None
    page_end: int | None = None
    content_hash: str | None = None
    content: str


class MessageCitationsResponse(BaseModel):
    message_id: str
    citations: list[CitationResponse]


class WorkspaceFileResponse(BaseModel):
    file_id: str
    original_name: str
    content_type: str
    byte_size: int
    sha256: str
    status: str
    error_code: str | None = None


class WorkspaceResponse(BaseModel):
    workspace_id: str
    scope_id: str
    status: str
    knowledge_version: str | None = None
    expires_at: str
    files: list[WorkspaceFileResponse] = Field(default_factory=list)


class UploadResponse(BaseModel):
    workspace_id: str
    status: str
    file_ids: list[str]


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


@router.post("/workspaces", response_model=WorkspaceResponse)
def create_workspace(request: Request, response: Response):
    runtime = get_runtime()
    if not runtime.settings.upload_enabled:
        raise HTTPException(status_code=404, detail={"code": "upload_disabled"})
    owner = runtime.identity.resolve(request, response)
    scope = runtime.workspaces.create(owner.owner_key)
    return _workspace_response(scope, [])


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(workspace_id: str, request: Request):
    owner_key = _require_owner(request)
    runtime = get_runtime()
    try:
        scope = runtime.registry.require_access(workspace_id, owner_key)
    except ScopeExpiredError as exc:
        raise HTTPException(status_code=410, detail={"code": "scope_expired"}) from exc
    except ScopeNotFoundError as exc:
        raise _scope_not_found() from exc
    return _workspace_response(
        scope,
        runtime.workspaces.list_files(workspace_id),
    )


@router.post(
    "/workspaces/{workspace_id}/files",
    response_model=UploadResponse,
    status_code=202,
)
async def upload_workspace_files(
    workspace_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
):
    owner_key = _require_owner(request)
    runtime = get_runtime()
    _check_rate_limit(
        "upload",
        owner_key,
        limit=runtime.settings.upload_rate_limit_per_hour,
        window_seconds=3600,
    )
    try:
        scope = runtime.registry.require_access(workspace_id, owner_key)
    except ScopeExpiredError as exc:
        raise HTTPException(status_code=410, detail={"code": "scope_expired"}) from exc
    except ScopeNotFoundError as exc:
        raise _scope_not_found() from exc
    if scope.scope_type != "temporary" or scope.status in {"deleting", "deleted"}:
        raise _scope_not_found()
    if not files:
        raise HTTPException(status_code=422, detail={"code": "no_files"})

    existing = runtime.workspaces.list_files(workspace_id)
    if len(existing) + len(files) > runtime.settings.upload_max_files:
        raise HTTPException(
            status_code=413,
            detail={"code": "upload_limit_exceeded"},
        )
    existing_bytes = sum(int(item["byte_size"]) for item in existing)
    staged: list[dict] = []
    created_paths: list[Path] = []
    upload_dir = runtime.workspaces.workspace_root(workspace_id) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        running_total = existing_bytes
        for upload in files:
            original_name = Path(upload.filename or "upload").name
            extension = Path(original_name).suffix.lower()
            if extension not in {".md", ".txt", ".pdf"}:
                raise HTTPException(
                    status_code=415,
                    detail={"code": "unsupported_file", "file": original_name},
                )
            stored_name = f"{uuid.uuid4().hex}.upload"
            path = upload_dir / stored_name
            created_paths.append(path)
            digest = hashlib.sha256()
            byte_size = 0
            prefix = b""
            with path.open("wb") as handle:
                while chunk := await upload.read(64 * 1024):
                    if not prefix:
                        prefix = chunk[:8]
                    byte_size += len(chunk)
                    running_total += len(chunk)
                    if (
                        byte_size > runtime.settings.upload_max_file_bytes
                        or running_total > runtime.settings.upload_max_bytes
                    ):
                        raise HTTPException(
                            status_code=413,
                            detail={"code": "upload_limit_exceeded"},
                        )
                    digest.update(chunk)
                    handle.write(chunk)
            if extension == ".pdf" and not prefix.startswith(b"%PDF-"):
                raise HTTPException(
                    status_code=415,
                    detail={"code": "unsupported_file", "file": original_name},
                )
            staged.append(
                {
                    "path": path,
                    "stored_name": stored_name,
                    "original_name": original_name,
                    "content_type": upload.content_type or "application/octet-stream",
                    "byte_size": byte_size,
                    "sha256": digest.hexdigest(),
                }
            )
    except Exception:
        for path in created_paths:
            path.unlink(missing_ok=True)
        raise
    finally:
        for upload in files:
            await upload.close()

    file_ids = [
        runtime.workspaces.register_upload(
            scope_id=workspace_id,
            original_name=item["original_name"],
            content_type=item["content_type"],
            byte_size=item["byte_size"],
            sha256=item["sha256"],
            stored_name=item["stored_name"],
        )
        for item in staged
    ]
    return UploadResponse(
        workspace_id=workspace_id,
        status="processing",
        file_ids=file_ids,
    )


@router.delete("/workspaces/{workspace_id}", status_code=202)
def delete_workspace(workspace_id: str, request: Request):
    owner_key = _require_owner(request)
    runtime = get_runtime()
    try:
        runtime.registry.mark_deleting(workspace_id, owner_key)
    except ScopeExpiredError:
        with connection_scope() as conn:
            row = conn.execute(
                """
                SELECT scope_id FROM knowledge_scope
                WHERE scope_id = ? AND owner_key = ?
                """,
                (workspace_id, owner_key),
            ).fetchone()
            if not row:
                raise _scope_not_found()
            conn.execute(
                "UPDATE knowledge_scope SET status = 'deleting' WHERE scope_id = ?",
                (workspace_id,),
            )
    except ScopeNotFoundError as exc:
        raise _scope_not_found() from exc
    runtime.jobs.enqueue(
        "delete_scope",
        scope_id=workspace_id,
        deduplicate=True,
    )
    return {"workspace_id": workspace_id, "status": "deleting"}


@router.get("/workspaces/{workspace_id}/deletion")
def get_workspace_deletion(workspace_id: str, request: Request):
    owner_key = _require_owner(request)
    with connection_scope() as conn:
        row = conn.execute(
            """
            SELECT status, deleted_at FROM knowledge_scope
            WHERE scope_id = ? AND owner_key = ?
            """,
            (workspace_id, owner_key),
        ).fetchone()
    if not row:
        raise _scope_not_found()
    return {
        "workspace_id": workspace_id,
        "status": row["status"],
        "deleted_at": row["deleted_at"],
    }


@router.post("/sessions", response_model=SessionResponse)
def create_session(data: SessionCreateRequest, request: Request, response: Response):
    runtime = get_runtime()
    owner = runtime.identity.resolve(request, response)
    if data.mode == "system":
        if data.workspace_id is not None:
            raise HTTPException(status_code=422, detail={"code": "invalid_workspace"})
        scope = _ensure_public_scope()
    else:
        if not data.workspace_id:
            raise HTTPException(status_code=422, detail={"code": "workspace_required"})
        try:
            temporary = runtime.registry.require_access(
                data.workspace_id,
                owner.owner_key,
            )
        except ScopeExpiredError as exc:
            raise HTTPException(
                status_code=410,
                detail={"code": "scope_expired"},
            ) from exc
        except ScopeNotFoundError as exc:
            raise _scope_not_found() from exc
        if temporary.scope_type != "temporary":
            raise _scope_not_found()
        if temporary.status != "ready" or not temporary.current_version:
            raise HTTPException(status_code=409, detail={"code": "scope_not_ready"})
        scope = runtime.registry.resolve(temporary.scope_id, owner.owner_key)
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
            SELECT s.*, ks.scope_type, ks.current_version,
                   ks.status AS scope_status, ks.expires_at AS scope_expires_at
            FROM session s
            JOIN knowledge_scope ks ON ks.scope_id = s.scope_id
            WHERE s.owner_key = ?
              AND (s.expires_at IS NULL OR s.expires_at > ?)
              AND ks.status NOT IN ('deleting', 'deleted')
              AND (ks.expires_at IS NULL OR ks.expires_at > ?)
            ORDER BY s.updated_at DESC
            """,
            (owner.owner_key, now, now),
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
    runtime = get_runtime()
    _check_rate_limit(
        "chat",
        owner_key,
        limit=runtime.settings.chat_rate_limit_per_minute,
        window_seconds=60,
    )
    session = _require_session(data.session_id, owner_key)
    try:
        scope = runtime.registry.resolve(session["scope_id"], owner_key)
    except ScopeNotFoundError as exc:
        raise _scope_not_found() from exc
    except ScopeExpiredError as exc:
        raise HTTPException(status_code=410, detail={"code": "scope_expired"}) from exc
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

    async def event_generator():
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
                if await request.is_disconnected():
                    return
                if not chunk:
                    continue
                full_content += chunk
                yield _sse("token", {"content": chunk})

            if answer.local_result.evidence and not _has_valid_citation(
                full_content,
                len(answer.local_result.evidence),
            ):
                citation_suffix = "\n\n参考 [1]"
                full_content += citation_suffix
                yield _sse("token", {"content": citation_suffix})

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
            JOIN knowledge_scope ks ON ks.scope_id = s.scope_id
            WHERE m.message_id = ?
              AND s.owner_key = ?
              AND ks.status NOT IN ('deleting', 'deleted')
              AND (ks.expires_at IS NULL OR ks.expires_at > ?)
            """,
            (message_id, owner_key, _now()),
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
            SELECT s.*, ks.scope_type, ks.current_version,
                   ks.status AS scope_status, ks.expires_at AS scope_expires_at
            FROM session s
            JOIN knowledge_scope ks ON ks.scope_id = s.scope_id
            WHERE s.session_id = ? AND s.owner_key = ?
            """,
            (session_id, owner_key),
        ).fetchone()
    if not row:
        raise _scope_not_found()
    if row["scope_status"] in {"deleting", "deleted"}:
        raise _scope_not_found()
    if row["scope_expires_at"] and row["scope_expires_at"] <= _now():
        raise HTTPException(status_code=410, detail={"code": "scope_expired"})
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
            "display_name": item.display_name,
            "source_type": item.source_type,
            "start_line": item.start_line,
            "end_line": item.end_line,
            "page_start": item.page_start,
            "page_end": item.page_end,
            "content_hash": item.content_hash,
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


def _workspace_response(scope, files: list[dict]) -> WorkspaceResponse:
    return WorkspaceResponse(
        workspace_id=scope.scope_id,
        scope_id=scope.scope_id,
        status=scope.status,
        knowledge_version=scope.current_version,
        expires_at=scope.expires_at,
        files=[
            WorkspaceFileResponse(
                file_id=item["file_id"],
                original_name=item["original_name"],
                content_type=item["content_type"],
                byte_size=int(item["byte_size"]),
                sha256=item["sha256"],
                status=item["parse_status"],
                error_code=item["error_code"],
            )
            for item in files
        ],
    )


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _has_valid_citation(content: str, evidence_count: int) -> bool:
    return any(
        1 <= int(value) <= evidence_count
        for value in re.findall(r"\[(\d+)\]", content)
    )


def _scope_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "scope_not_found"})


def _check_rate_limit(
    bucket: str,
    owner_key: str,
    *,
    limit: int,
    window_seconds: int,
) -> None:
    try:
        get_runtime().rate_limiter.check(
            bucket,
            owner_key,
            limit=limit,
            window_seconds=window_seconds,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited"},
        ) from exc


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
