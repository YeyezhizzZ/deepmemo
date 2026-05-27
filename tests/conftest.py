from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import src.app.core.fs_manager as fs_manager
import src.app.database as database
import src.app.main as main_module
import src.routers.wiki as wiki_router
import src.routers.diary as diary_router
import src.routers.fs as fs_router
import src.routers.pulse as pulse_router
import src.wiki.graph as wiki_graph
import src.wiki.health as wiki_health
import src.wiki.constants as wiki_constants
import src.wiki.path_utils as wiki_path_utils
import src.wiki.policy as wiki_policy
import src.wiki.tree as wiki_tree
import src.wiki.storage as wiki_storage
from src.app.database import init_db


@pytest.fixture(autouse=True)
def isolated_app_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = tmp_path / "data.db"

    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    monkeypatch.setattr(fs_manager, "DATABASE_PATH", db_path)
    monkeypatch.setattr(fs_manager, "DATA_DIR", data_dir)
    monkeypatch.setattr(fs_router, "DATA_DIR", data_dir)
    monkeypatch.setattr(diary_router, "DATA_DIR", data_dir)
    monkeypatch.setattr(pulse_router, "DATA_DIR", data_dir)
    monkeypatch.setattr(main_module, "DATA_DIR", data_dir)

    raw_dir = data_dir / "raw"
    wiki_dir = data_dir / "wiki"
    policy_dir = data_dir / "policy"
    monkeypatch.setattr(wiki_constants, "DATA_DIR", data_dir)
    monkeypatch.setattr(wiki_constants, "RAW_DIR", raw_dir)
    monkeypatch.setattr(wiki_constants, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(wiki_constants, "POLICY_DIR", policy_dir)
    monkeypatch.setattr(wiki_tree, "DATA_DIR", data_dir)
    monkeypatch.setattr(wiki_graph, "DATA_DIR", data_dir)
    monkeypatch.setattr(wiki_graph, "DIARY_DIR", raw_dir)
    monkeypatch.setattr(wiki_graph, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(wiki_policy, "POLICY_DIR", policy_dir)
    monkeypatch.setattr(wiki_path_utils, "DATA_DIR", data_dir)
    monkeypatch.setattr(wiki_path_utils, "RAW_DIR", raw_dir)
    monkeypatch.setattr(wiki_path_utils, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(wiki_path_utils, "POLICY_DIR", policy_dir)
    monkeypatch.setattr(wiki_storage, "DATA_DIR", data_dir)
    def wiki_router_path(*parts, **kwargs):
        raw_path = Path(*parts, **kwargs)
        if not raw_path.is_absolute() and str(raw_path).startswith("data/"):
            return data_dir / raw_path.relative_to("data")
        return raw_path

    monkeypatch.setattr(wiki_router, "Path", wiki_router_path, raising=False)
    monkeypatch.setattr(wiki_router, "rel_path", lambda path, root=None: wiki_path_utils.rel_path(path, root=data_dir))
    monkeypatch.setattr(wiki_router, "build_diary_graph", lambda: wiki_graph.build_diary_graph(wiki_dir))
    monkeypatch.setattr(wiki_router, "build_wiki_health_report", lambda: wiki_health.build_wiki_health_report(wiki_dir))
    wiki_policy.load_policy_file.cache_clear()

    init_db()
    return SimpleNamespace(data_dir=data_dir, db_path=db_path)


@pytest.fixture
def client() -> TestClient:
    return TestClient(main_module.app)


@pytest.fixture
def db_path(isolated_app_state) -> Path:
    return isolated_app_state.db_path


@pytest.fixture
def test_data_dir(isolated_app_state) -> Path:
    return isolated_app_state.data_dir


@pytest.fixture
def insert_session(db_path: Path):
    def _insert_session(session_name: str = "Test Session", message_ids: list[str] | None = None) -> str:
        session_id = str(uuid4())
        now = datetime.now().isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO session (
                    session_id, session_name, message_ids, session_topic,
                    session_summary, created_at, updated_at
                )
                VALUES (?, ?, ?, '', '', ?, ?)
                """,
                (session_id, session_name, json.dumps(message_ids or []), now, now),
            )
        return session_id

    return _insert_session


@pytest.fixture
def insert_message(db_path: Path):
    def _insert_message(
        session_id: str,
        role: str = "ai",
        content: str = "answer",
        citations: list[dict] | None = None,
    ) -> str:
        message_id = str(uuid4())
        now = datetime.now().isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO message (message_id, session_id, role, content, citations, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, content, json.dumps(citations or []), now),
            )
        return message_id

    return _insert_message
