import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from src.app.database import get_db_connection
from src.models.schemas import SessionCreate, SessionResponse

router = APIRouter(prefix="/sessions", tags=["session"])


@router.post("/", response_model=SessionResponse)
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


@router.get("/", response_model=list[SessionResponse])
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


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM session WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(
        session_id=row["session_id"],
        session_name=row["session_name"],
        message_ids=json.loads(row["message_ids"]),
        session_topic=row["session_topic"] or "",
        session_summary=row["session_summary"] or "",
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


@router.delete("/{session_id}")
def delete_session(session_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM message WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM session WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return {"message": "Session deleted"}
