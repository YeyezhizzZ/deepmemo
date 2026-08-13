from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.app.database import connection_scope
from src.deepme.settings import DeepMeSettings


class ScopeNotFoundError(LookupError):
    pass


class ScopeNotReadyError(RuntimeError):
    pass


class ScopeExpiredError(RuntimeError):
    pass


@dataclass(frozen=True)
class KnowledgeScope:
    scope_id: str
    scope_type: str
    owner_key: str | None
    status: str
    current_version: str | None
    created_at: str
    expires_at: str | None


@dataclass(frozen=True)
class ResolvedScope:
    scope_id: str
    scope_type: str
    knowledge_version: str
    documents_root: Path
    manifest_path: Path
    index_path: Path | None
    content_hash: str


class ScopeRegistry:
    PUBLIC_SCOPE_ID = "public"

    def __init__(self, settings: DeepMeSettings):
        self.settings = settings

    def ensure_public_scope(self) -> KnowledgeScope:
        now = _now()
        with connection_scope() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO knowledge_scope (
                    scope_id, scope_type, owner_key, status, current_version,
                    created_at, expires_at, deleted_at
                )
                VALUES (?, 'system', NULL, 'empty', NULL, ?, NULL, NULL)
                """,
                (self.PUBLIC_SCOPE_ID, now),
            )
        return self.get_scope(self.PUBLIC_SCOPE_ID)

    def get_scope(self, scope_id: str) -> KnowledgeScope:
        with connection_scope() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_scope WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()
        if not row or row["status"] == "deleted":
            raise ScopeNotFoundError(scope_id)
        return _scope_from_row(row)

    def require_access(self, scope_id: str, owner_key: str | None) -> KnowledgeScope:
        scope = self.get_scope(scope_id)
        if scope.status == "deleting":
            raise ScopeNotFoundError(scope_id)
        if scope.scope_type == "temporary" and scope.owner_key != owner_key:
            raise ScopeNotFoundError(scope_id)
        if (
            scope.scope_type == "temporary"
            and scope.expires_at
            and scope.expires_at <= _now()
        ):
            raise ScopeExpiredError(scope_id)
        return scope

    def create_temporary_scope(self, owner_key: str) -> KnowledgeScope:
        scope_id = f"ws_{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc).replace(microsecond=0)
        expires_at = now + timedelta(hours=self.settings.upload_ttl_hours)
        with connection_scope() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_scope (
                    scope_id, scope_type, owner_key, status, current_version,
                    created_at, expires_at, deleted_at
                )
                VALUES (?, 'temporary', ?, 'empty', NULL, ?, ?, NULL)
                """,
                (
                    scope_id,
                    owner_key,
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
        return self.get_scope(scope_id)

    def set_status(self, scope_id: str, status: str) -> None:
        with connection_scope() as conn:
            conn.execute(
                "UPDATE knowledge_scope SET status = ? WHERE scope_id = ?",
                (status, scope_id),
            )

    def mark_deleting(self, scope_id: str, owner_key: str) -> KnowledgeScope:
        scope = self.require_access(scope_id, owner_key)
        if scope.scope_type != "temporary":
            raise ScopeNotFoundError(scope_id)
        with connection_scope() as conn:
            conn.execute(
                """
                UPDATE knowledge_scope
                SET status = 'deleting'
                WHERE scope_id = ? AND owner_key = ?
                """,
                (scope_id, owner_key),
            )
        return self.get_scope(scope_id)

    def mark_deleted(self, scope_id: str) -> None:
        with connection_scope() as conn:
            conn.execute(
                """
                UPDATE knowledge_scope
                SET status = 'deleted', current_version = NULL, deleted_at = ?
                WHERE scope_id = ?
                """,
                (_now(), scope_id),
            )

    def expired_temporary_scope_ids(self) -> list[str]:
        with connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT scope_id FROM knowledge_scope
                WHERE scope_type = 'temporary'
                  AND status NOT IN ('deleting', 'deleted')
                  AND expires_at IS NOT NULL
                  AND expires_at <= ?
                """,
                (_now(),),
            ).fetchall()
        return [row["scope_id"] for row in rows]

    def register_public_version(
        self,
        *,
        version: str,
        content_hash: str,
        documents_path: str,
        manifest_path: str,
        index_path: str | None = None,
        source_revision: str | None = None,
    ) -> ResolvedScope:
        self.ensure_public_scope()
        return self.register_version(
            scope_id=self.PUBLIC_SCOPE_ID,
            version=version,
            content_hash=content_hash,
            documents_path=documents_path,
            manifest_path=manifest_path,
            index_path=index_path,
            source_revision=source_revision,
        )

    def register_version(
        self,
        *,
        scope_id: str,
        version: str,
        content_hash: str,
        documents_path: str,
        manifest_path: str,
        index_path: str | None = None,
        source_revision: str | None = None,
    ) -> ResolvedScope:
        now = _now()
        scope = self.get_scope(scope_id)
        with connection_scope() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO knowledge_version (
                    scope_id, version, content_hash, documents_path, manifest_path,
                    index_path, status, source_revision, built_at, published_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'ready', ?, ?, ?)
                """,
                (
                    scope_id,
                    version,
                    content_hash,
                    documents_path,
                    manifest_path,
                    index_path,
                    source_revision,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE knowledge_scope
                SET status = 'ready', current_version = ?, deleted_at = NULL
                WHERE scope_id = ?
                """,
                (version, scope_id),
            )
        return self.resolve(scope_id, scope.owner_key)

    def resolve(self, scope_id: str, owner_key: str | None = None) -> ResolvedScope:
        scope = self.require_access(scope_id, owner_key)
        if scope.status != "ready" or not scope.current_version:
            raise ScopeNotReadyError(scope_id)

        with connection_scope() as conn:
            row = conn.execute(
                """
                SELECT * FROM knowledge_version
                WHERE scope_id = ? AND version = ? AND status = 'ready'
                """,
                (scope.scope_id, scope.current_version),
            ).fetchone()
        if not row:
            raise ScopeNotReadyError(scope_id)

        documents_root = self._runtime_path(row["documents_path"], expect_directory=True)
        manifest_path = self._runtime_path(row["manifest_path"], expect_directory=False)
        index_path = (
            self._runtime_path(row["index_path"], expect_directory=False, must_exist=False)
            if row["index_path"]
            else None
        )
        return ResolvedScope(
            scope_id=scope.scope_id,
            scope_type=scope.scope_type,
            knowledge_version=row["version"],
            documents_root=documents_root,
            manifest_path=manifest_path,
            index_path=index_path,
            content_hash=row["content_hash"],
        )

    def _runtime_path(
        self,
        relative: str,
        *,
        expect_directory: bool,
        must_exist: bool = True,
    ) -> Path:
        root = self.settings.runtime_dir.resolve()
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ScopeNotReadyError("scope path escapes runtime directory") from exc
        if must_exist and not path.exists():
            raise ScopeNotReadyError(f"scope path is missing: {relative}")
        if must_exist and expect_directory != path.is_dir():
            raise ScopeNotReadyError(f"scope path has an invalid type: {relative}")
        return path


def _scope_from_row(row) -> KnowledgeScope:
    return KnowledgeScope(
        scope_id=row["scope_id"],
        scope_type=row["scope_type"],
        owner_key=row["owner_key"],
        status=row["status"],
        current_version=row["current_version"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
