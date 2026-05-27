def test_get_citations_returns_stored_evidence(client, insert_session, insert_message):
    session_id = insert_session()
    message_id = insert_message(
        session_id=session_id,
        citations=[
            {
                "local_id": 1,
                "evidence_id": "local-1",
                "file_path": "diary/0527.md",
                "content": "source excerpt",
            }
        ],
    )

    response = client.get("/api/chat/citations", params={"message_id": message_id})

    assert response.status_code == 200
    assert response.json() == {
        "message_id": message_id,
        "citations": [
            {
                "local_id": 1,
                "evidence_id": "local-1",
                "file_path": "diary/0527.md",
                "content": "source excerpt",
            }
        ],
    }


def test_get_citations_returns_404_for_missing_message(client):
    response = client.get("/api/chat/citations", params={"message_id": "missing"})

    assert response.status_code == 404
