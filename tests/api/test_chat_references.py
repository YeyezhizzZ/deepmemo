import sqlite3


def test_api_chat_file_references_normalizes_paths(
    client,
    db_path,
    insert_session,
    insert_message,
    test_data_dir,
):
    source_file = test_data_dir / "diary" / "0527.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("# 0527", encoding="utf-8")

    session_id = insert_session("Citation Session")
    insert_message(
        session_id=session_id,
        role="ai",
        content="answer with citation",
        citations=[
            {
                "local_id": 1,
                "evidence_id": "ev-1",
                "file_path": "diary/0527.md",
                "content": "quoted evidence",
            }
        ],
    )

    with sqlite3.connect(db_path) as conn:
        message_count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
    assert message_count == 1

    for requested_path in [
        "diary/0527.md",
        "data/diary/0527.md",
        str(source_file),
    ]:
        response = client.get("/api/chat/file-references", params={"path": requested_path})
        assert response.status_code == 200
        references = response.json()
        assert len(references) == 1
        assert references[0]["session_id"] == session_id
        assert references[0]["session_name"] == "Citation Session"
        assert references[0]["content"] == "answer with citation"
