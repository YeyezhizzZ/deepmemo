from __future__ import annotations

import json
import sqlite3

import pytest

from src.app.database import init_db
from src.deepme.public_knowledge import PublicKnowledgeBuildError
from src.deepme.runtime import get_runtime
from src.deepme.scopes import ScopeNotReadyError


def test_public_snapshot_is_immutable_and_uses_only_public_source(
    isolated_app_state,
):
    private_note = isolated_app_state.data_dir / "private.md"
    private_note.write_text("private-only-secret", encoding="utf-8")

    runtime = get_runtime()
    first = runtime.ensure_public_ready()
    second = runtime.ensure_public_ready()

    assert first.knowledge_version == second.knowledge_version
    assert first.documents_root != isolated_app_state.data_dir
    assert (first.documents_root / "profile.md").is_file()
    assert not (first.documents_root / "private.md").exists()
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["content_hash"] == first.content_hash
    assert manifest["files"][0]["path"] == "profile.md"


def test_public_snapshot_rejects_symlink(isolated_app_state):
    outside = isolated_app_state.runtime_dir / "outside.md"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("outside", encoding="utf-8")
    (isolated_app_state.public_source_dir / "linked.md").symlink_to(outside)

    with pytest.raises(PublicKnowledgeBuildError, match="symlink"):
        get_runtime().publisher.publish()


def test_public_snapshot_rejects_non_utf8_markdown(isolated_app_state):
    (isolated_app_state.public_source_dir / "invalid.md").write_bytes(b"\xff\xfe")

    with pytest.raises(PublicKnowledgeBuildError, match="UTF-8"):
        get_runtime().publisher.publish()


def test_scope_resolver_rejects_runtime_escape(isolated_app_state):
    runtime = get_runtime()
    scope = runtime.ensure_public_ready()

    with sqlite3.connect(isolated_app_state.db_path) as conn:
        conn.execute(
            """
            UPDATE knowledge_version
            SET documents_path = '../outside'
            WHERE scope_id = ? AND version = ?
            """,
            (scope.scope_id, scope.knowledge_version),
        )

    with pytest.raises(ScopeNotReadyError, match="escapes runtime"):
        runtime.registry.resolve(scope.scope_id)


def test_deepme_migration_is_idempotent(db_path):
    init_db()
    init_db()

    with sqlite3.connect(db_path) as conn:
        applied = conn.execute(
            "SELECT version FROM schema_migration ORDER BY version"
        ).fetchall()
        session_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(session)").fetchall()
        }

    assert applied == [("001_deepme_scope_foundation.sql",)]
    assert {"owner_key", "scope_id", "expires_at"} <= session_columns
