from __future__ import annotations

from pathlib import Path


def test_auto_draft_returns_latest_raw_markdown(client, test_data_dir):
    raw_dir = test_data_dir / "raw"
    raw_dir.mkdir(parents=True)

    older = raw_dir / "older.md"
    newer = raw_dir / "nested" / "newer.md"
    newer.parent.mkdir(parents=True)
    older.write_text("older draft", encoding="utf-8")
    newer.write_text("newer draft", encoding="utf-8")

    older_time = 1_700_000_000
    newer_time = 1_700_000_100
    Path(older).touch()
    Path(newer).touch()
    import os

    os.utime(older, (older_time, older_time))
    os.utime(newer, (newer_time, newer_time))

    response = client.post("/api/diary/auto-draft", json={"raw_dir": "raw", "output_dir": "diary"})

    assert response.status_code == 200
    body = response.json()
    assert body["source_file"] == "newer.md"
    assert body["draft"] == "newer draft"
    assert "placeholder" in body["message"].lower()


def test_auto_draft_returns_404_when_raw_dir_missing(client):
    response = client.post("/api/diary/auto-draft", json={"raw_dir": "missing", "output_dir": "diary"})

    assert response.status_code == 404
