import json
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.ai.service import knowledge_qa_service
from src.app.database import init_db, get_db_connection
from src.app.core.watcher import start_watcher, stop_watcher
from src.routers.fs import router as fs_router
from src.routers.diary import router as diary_router
from src.routers.pulse import router as pulse_router
from src.routers.citations import router as citations_router
from src.routers.chat import router as chat_router


app = FastAPI(title="DeepMemo API", version="0.2.0")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models ---
class SessionCreate(BaseModel):
    session_name: str


class SessionResponse(BaseModel):
    session_id: str
    session_name: str
    message_ids: list[str]
    session_topic: str = ""
    session_summary: str = ""
    created_at: datetime
    updated_at: datetime


class ChatRequest(BaseModel):
    session_id: str
    user_message: str


class MessageResponse(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: datetime


# --- Database Helpers ---
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
    message_ids = json.loads(
        cursor.execute("SELECT message_ids FROM session WHERE session_id = ?", (session_id,)).fetchone()["message_ids"]
    )
    messages = []
    for mid in message_ids:
        row = cursor.execute("SELECT * FROM message WHERE message_id = ?", (mid,)).fetchone()
        if row:
            role = "assistant" if row["role"] == "ai" else row["role"]
            messages.append({"role": role, "content": row["content"]})
    conn.close()
    return messages


# --- Startup / Shutdown ---
@app.on_event("startup")
def startup():
    init_db()
    start_watcher()

@app.on_event("shutdown")
def shutdown():
    stop_watcher()


# --- FS Routers ---
app.include_router(fs_router)
app.include_router(diary_router)
app.include_router(pulse_router)
app.include_router(citations_router)
app.include_router(chat_router)


# --- Session APIs ---
@app.post("/sessions", response_model=SessionResponse)
def create_session(data: SessionCreate):
    conn = get_db_connection()
    cursor = conn.cursor()
    session_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO session (session_id, session_name, message_ids, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, data.session_name, "[]", now, now),
    )
    conn.commit()
    conn.close()
    return SessionResponse(
        session_id=session_id,
        session_name=data.session_name,
        message_ids=[],
        session_topic="",
        session_summary="",
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
    )


@app.get("/sessions", response_model=list[SessionResponse])
def list_sessions():
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM session ORDER BY created_at DESC").fetchall()
    conn.close()
    return [
        SessionResponse(
            session_id=row["session_id"],
            session_name=row["session_name"],
            message_ids=json.loads(row["message_ids"]),
            session_topic=row["session_topic"] or "",
            session_summary=row["session_summary"] or "",
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
        for row in rows
    ]


@app.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str):
    row = get_session_row(session_id)
    return SessionResponse(
        session_id=row["session_id"],
        session_name=row["session_name"],
        message_ids=json.loads(row["message_ids"]),
        session_topic=row["session_topic"] or "",
        session_summary=row["session_summary"] or "",
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM message WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM session WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return {"message": "Session deleted"}


# --- Chat File References ---
class FileReferenceItem(BaseModel):
    session_id: str
    session_name: str
    message_id: str
    role: str
    content: str
    created_at: datetime


def normalize_reference_path(value: str | None) -> str:
    """Normalize stored and requested citation paths to data-relative POSIX paths."""
    if not value:
        return ""

    normalized = str(value).strip().replace("\\", "/")
    try:
        path = Path(normalized).expanduser()
        if path.is_absolute():
            return path.resolve().relative_to(DATA_DIR.resolve()).as_posix()
    except (OSError, ValueError):
        pass

    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    if normalized.startswith("data/"):
        normalized = normalized[len("data/"):]
    return normalized


@app.get("/api/chat/file-references", response_model=list[FileReferenceItem])
def get_file_references(path: str):
    """获取引用了指定文件的所有消息"""
    target_path = normalize_reference_path(path)
    conn = get_db_connection()
    cursor = conn.cursor()

    rows = cursor.execute("""
        SELECT m.message_id, m.session_id, m.role, m.content, m.created_at,
               m.citations, s.session_name
        FROM message m
        JOIN session s ON m.session_id = s.session_id
        WHERE m.citations != '[]' AND m.citations IS NOT NULL
    """).fetchall()

    conn.close()

    references = []
    for row in rows:
        try:
            citations = json.loads(row["citations"] or "[]")
            if any(normalize_reference_path(c.get("file_path")) == target_path for c in citations):
                references.append(FileReferenceItem(
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


# --- Root ---
@app.get("/")
def root():
    return {"message": "DeepMemo API is running"}
