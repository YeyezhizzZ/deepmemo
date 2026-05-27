import json
import sqlite3


def test_session_lifecycle_and_delete_cascade(client, db_path):
    create_response = client.post("/sessions", json={"session_name": "Regression Session"})
    assert create_response.status_code == 200
    session = create_response.json()
    session_id = session["session_id"]
    assert session["session_name"] == "Regression Session"
    assert session["message_ids"] == []

    list_response = client.get("/sessions")
    assert list_response.status_code == 200
    assert any(item["session_id"] == session_id for item in list_response.json())

    get_response = client.get(f"/sessions/{session_id}")
    assert get_response.status_code == 200
    assert get_response.json()["session_id"] == session_id

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO message (message_id, session_id, role, content, citations, created_at)
            VALUES ('msg-user', ?, 'user', 'hello', '[]', CURRENT_TIMESTAMP)
            """,
            (session_id,),
        )
        conn.execute(
            """
            UPDATE session SET message_ids = ? WHERE session_id = ?
            """,
            (json.dumps(["msg-user"]), session_id),
        )

    delete_response = client.delete(f"/sessions/{session_id}")
    assert delete_response.status_code == 200

    missing_response = client.get(f"/sessions/{session_id}")
    assert missing_response.status_code == 404
    with sqlite3.connect(db_path) as conn:
        remaining_messages = conn.execute(
            "SELECT COUNT(*) FROM message WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
    assert remaining_messages == 0
