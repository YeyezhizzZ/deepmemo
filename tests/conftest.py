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
import src.deepme.runtime as deepme_runtime
import src.routers.knowledge as knowledge_router
import src.routers.diary as diary_router
import src.routers.fs as fs_router
import src.routers.pulse as pulse_router
import src.knowledge.card_store as knowledge_card_store
import src.knowledge.card_compiler as knowledge_card_compiler
import src.knowledge.chat_commands as knowledge_chat_commands
import src.knowledge.cli as knowledge_cli
import src.knowledge.commit_compiler as knowledge_commit_compiler
import src.knowledge.conversation_memory as knowledge_conversation_memory
import src.knowledge.maintenance as knowledge_maintenance
import src.knowledge.repowiki as knowledge_repowiki
import src.knowledge.view_model as knowledge_view_model
from src.app.database import init_db
from src.knowledge.card_compiler import KnowledgeCardCompiler
from tests.fake_knowledge_provider import FakeKnowledgeProvider


@pytest.fixture(autouse=True)
def isolated_app_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = tmp_path / "data.db"
    runtime_dir = tmp_path / "runtime"
    public_source_dir = tmp_path / "public-knowledge"
    public_source_dir.mkdir()
    (public_source_dir / "profile.md").write_text(
        "# Public Profile\n\nDeepMe public fixture knowledge.\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DEEPME_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.setenv("DEEPME_PUBLIC_SOURCE_DIR", str(public_source_dir))
    monkeypatch.setenv("DEEPME_COOKIE_SECRET", "test-cookie-secret")
    monkeypatch.setenv("DEEPME_COOKIE_SECURE", "false")
    monkeypatch.setenv("DEEPME_RETRIEVAL_MODE", "ngram")
    monkeypatch.setenv("DEEPME_RERANK_ENABLED", "false")
    deepme_runtime.reset_runtime()

    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    monkeypatch.setattr(fs_manager, "DATABASE_PATH", db_path)
    monkeypatch.setattr(fs_manager, "DATA_DIR", data_dir)
    monkeypatch.setattr(fs_router, "DATA_DIR", data_dir)
    monkeypatch.setattr(diary_router, "DATA_DIR", data_dir)
    monkeypatch.setattr(pulse_router, "DATA_DIR", data_dir)
    monkeypatch.setattr(main_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(knowledge_router, "DATA_DIR", data_dir)
    monkeypatch.setattr(knowledge_card_store, "DATA_DIR", data_dir)
    monkeypatch.setattr(knowledge_card_compiler, "DATA_DIR", data_dir)
    monkeypatch.setattr(knowledge_chat_commands, "DATA_DIR", data_dir)
    monkeypatch.setattr(knowledge_cli, "DATA_DIR", data_dir)
    monkeypatch.setattr(knowledge_commit_compiler, "DATA_DIR", data_dir)
    monkeypatch.setattr(knowledge_conversation_memory, "DATA_DIR", data_dir)
    monkeypatch.setattr(knowledge_maintenance, "DATA_DIR", data_dir)
    monkeypatch.setattr(knowledge_repowiki, "DATA_DIR", data_dir)
    monkeypatch.setattr(knowledge_view_model, "DATA_DIR", data_dir)
    provider = FakeKnowledgeProvider()
    monkeypatch.setattr(
        knowledge_router,
        "_compiler",
        lambda: KnowledgeCardCompiler(
            data_dir=knowledge_router.DATA_DIR,
            provider=provider,
        ),
    )

    init_db()
    return SimpleNamespace(
        data_dir=data_dir,
        db_path=db_path,
        provider=provider,
        runtime_dir=runtime_dir,
        public_source_dir=public_source_dir,
    )


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
def fake_knowledge_provider(isolated_app_state) -> FakeKnowledgeProvider:
    return isolated_app_state.provider


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
