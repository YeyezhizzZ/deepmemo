from __future__ import annotations

from datetime import date
from pathlib import Path
from subprocess import CompletedProcess

import src.routers.pulse as pulse_router_module


def test_today_pulse_reports_commits_and_raw_materials(client, test_data_dir, monkeypatch):
    raw_dir = test_data_dir / "raw"
    raw_dir.mkdir(parents=True)

    note_a = raw_dir / "note-a.md"
    note_b = raw_dir / "note-b.md"
    note_a.write_text("a", encoding="utf-8")
    note_b.write_text("b", encoding="utf-8")
    older_time = 1_700_000_000
    newer_time = 1_700_000_100
    Path(note_a).touch()
    Path(note_b).touch()
    import os

    os.utime(note_a, (older_time, older_time))
    os.utime(note_b, (newer_time, newer_time))

    fake_log = CompletedProcess(
        args=["git", "log"],
        returncode=0,
        stdout="abc123|Add testing plan|DeepMemo|2026-05-27 10:00:00 +0800\n",
        stderr="",
    )
    monkeypatch.setattr(pulse_router_module.subprocess, "run", lambda *args, **kwargs: fake_log)

    response = client.get("/api/pulse/today")

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == date.today().isoformat()
    assert body["git_commits"][0]["hash"] == "abc123"
    assert body["git_commits"][0]["subject"] == "Add testing plan"
    assert [item["name"] for item in body["raw_materials"]] == ["note-b.md", "note-a.md"]
