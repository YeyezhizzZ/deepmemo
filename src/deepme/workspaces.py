from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.app.database import connection_scope
from src.deepme.documents import DocumentNormalizer
from src.deepme.jobs import JobQueue
from src.deepme.retrieval import VersionIndexBuilder
from src.deepme.scopes import KnowledgeScope, ScopeRegistry
from src.deepme.settings import DeepMeSettings


class WorkspaceError(RuntimeError):
    pass


class WorkspaceService:
    def __init__(
        self,
        settings: DeepMeSettings,
        registry: ScopeRegistry,
        jobs: JobQueue,
    ):
        self.settings = settings
        self.registry = registry
        self.jobs = jobs
        self.normalizer = DocumentNormalizer(settings)
        self.index_builder = VersionIndexBuilder(settings)

    def create(self, owner_key: str) -> KnowledgeScope:
        scope = self.registry.create_temporary_scope(owner_key)
        self.workspace_root(scope.scope_id).mkdir(parents=True, exist_ok=True)
        return scope

    def workspace_root(self, scope_id: str) -> Path:
        root = self.settings.temporary_dir.resolve()
        path = (root / scope_id).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise WorkspaceError("workspace path escapes temporary root") from exc
        return path

    def register_upload(
        self,
        *,
        scope_id: str,
        original_name: str,
        content_type: str,
        byte_size: int,
        sha256: str,
        stored_name: str,
    ) -> str:
        file_id = f"file_{uuid.uuid4().hex}"
        now = _now()
        with connection_scope() as conn:
            conn.execute(
                """
                INSERT INTO upload_file (
                    file_id, scope_id, original_name, stored_name,
                    content_type, byte_size, sha256, parse_status,
                    error_code, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', NULL, ?)
                """,
                (
                    file_id,
                    scope_id,
                    original_name,
                    stored_name,
                    content_type,
                    byte_size,
                    sha256,
                    now,
                ),
            )
        self.registry.set_status(scope_id, "processing")
        self.jobs.enqueue(
            "ingest_file",
            scope_id=scope_id,
            payload={"file_id": file_id},
        )
        return file_id

    def list_files(self, scope_id: str) -> list[dict]:
        with connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT * FROM upload_file
                WHERE scope_id = ? AND parse_status != 'deleted'
                ORDER BY created_at, file_id
                """,
                (scope_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def normalize_file(self, file_id: str) -> None:
        with connection_scope() as conn:
            row = conn.execute(
                "SELECT * FROM upload_file WHERE file_id = ?",
                (file_id,),
            ).fetchone()
            if not row:
                raise WorkspaceError(f"upload file not found: {file_id}")
            conn.execute(
                """
                UPDATE upload_file
                SET parse_status = 'parsing', error_code = NULL
                WHERE file_id = ?
                """,
                (file_id,),
            )
        item = dict(row)
        workspace_root = self.workspace_root(item["scope_id"])
        upload_path = workspace_root / "uploads" / item["stored_name"]
        markdown_path = workspace_root / "normalized" / f"{file_id}.md"
        source_map_path = workspace_root / "source-maps" / f"{file_id}.json"
        try:
            document = self.normalizer.normalize_with_timeout(
                upload_path,
                item["original_name"],
            )
            self.normalizer.write(
                document,
                markdown_path=markdown_path,
                source_map_path=source_map_path,
            )
        except Exception as exc:
            with connection_scope() as conn:
                conn.execute(
                    """
                    UPDATE upload_file
                    SET parse_status = 'error', error_code = ?
                    WHERE file_id = ?
                    """,
                    (f"{type(exc).__name__}: {exc}"[:500], file_id),
                )
            raise

        with connection_scope() as conn:
            conn.execute(
                """
                UPDATE upload_file
                SET parse_status = 'ready', error_code = NULL
                WHERE file_id = ?
                """,
                (file_id,),
            )
        self.jobs.enqueue(
            "build_scope",
            scope_id=item["scope_id"],
            deduplicate=True,
        )

    def build_scope(self, scope_id: str) -> None:
        scope = self.registry.get_scope(scope_id)
        if scope.scope_type != "temporary" or scope.status in {"deleting", "deleted"}:
            return
        ready_files = [
            item for item in self.list_files(scope_id) if item["parse_status"] == "ready"
        ]
        if not ready_files:
            self.registry.set_status(scope_id, "error")
            raise WorkspaceError("workspace has no ready files")

        root = self.workspace_root(scope_id)
        content_hash = self._scope_content_hash(root, ready_files)
        version = f"v1_{content_hash[:16]}"
        release_dir = root / "versions" / version
        if not release_dir.exists():
            self._build_release(
                root=root,
                release_dir=release_dir,
                scope_id=scope_id,
                version=version,
                content_hash=content_hash,
                ready_files=ready_files,
            )
        runtime_root = self.settings.runtime_dir.resolve()
        self.registry.register_version(
            scope_id=scope_id,
            version=version,
            content_hash=content_hash,
            documents_path=(release_dir / "documents")
            .relative_to(runtime_root)
            .as_posix(),
            manifest_path=(release_dir / "manifest.json")
            .relative_to(runtime_root)
            .as_posix(),
            index_path=(release_dir / "index" / "search.sqlite3")
            .relative_to(runtime_root)
            .as_posix(),
        )

    def _scope_content_hash(self, root: Path, ready_files: list[dict]) -> str:
        digest = hashlib.sha256()
        for item in sorted(ready_files, key=lambda value: value["file_id"]):
            path = root / "normalized" / f"{item['file_id']}.md"
            content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            digest.update(item["file_id"].encode("utf-8"))
            digest.update(b"\0")
            digest.update(content_hash.encode("ascii"))
            digest.update(b"\0")
        return digest.hexdigest()

    def _build_release(
        self,
        *,
        root: Path,
        release_dir: Path,
        scope_id: str,
        version: str,
        content_hash: str,
        ready_files: list[dict],
    ) -> None:
        staging_dir = root / "staging" / f"{version}-{uuid.uuid4().hex}"
        documents_dir = staging_dir / "documents"
        source_maps_dir = staging_dir / "source-maps"
        documents_dir.mkdir(parents=True)
        source_maps_dir.mkdir(parents=True)
        manifest_files: list[dict] = []
        try:
            for item in sorted(ready_files, key=lambda value: value["file_id"]):
                file_id = item["file_id"]
                normalized_path = root / "normalized" / f"{file_id}.md"
                source_map_path = root / "source-maps" / f"{file_id}.json"
                destination_name = f"{file_id}.md"
                source_map_name = f"{file_id}.json"
                shutil.copyfile(normalized_path, documents_dir / destination_name)
                shutil.copyfile(source_map_path, source_maps_dir / source_map_name)
                source_map = json.loads(source_map_path.read_text(encoding="utf-8"))
                normalized_sha = hashlib.sha256(normalized_path.read_bytes()).hexdigest()
                manifest_files.append(
                    {
                        "path": destination_name,
                        "display_name": item["original_name"],
                        "source_type": source_map["source_type"],
                        "source_map_file": source_map_name,
                        "page_count": source_map.get("page_count"),
                        "sha256": normalized_sha,
                        "byte_size": normalized_path.stat().st_size,
                        "original_sha256": item["sha256"],
                    }
                )
            manifest = {
                "schema_version": 1,
                "scope_id": scope_id,
                "version": version,
                "content_hash": content_hash,
                "built_at": _now(),
                "files": manifest_files,
            }
            manifest["index"] = self.index_builder.build(
                documents_root=documents_dir,
                source_maps_root=source_maps_dir,
                manifest=manifest,
                index_path=staging_dir / "index" / "search.sqlite3",
            )
            (staging_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            release_dir.parent.mkdir(parents=True, exist_ok=True)
            if release_dir.exists():
                return
            os.replace(staging_dir, release_dir)
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)

    def delete_scope(self, scope_id: str) -> None:
        root = self.workspace_root(scope_id)
        if root.exists():
            shutil.rmtree(root)
        with connection_scope() as conn:
            session_ids = [
                row["session_id"]
                for row in conn.execute(
                    "SELECT session_id FROM session WHERE scope_id = ?",
                    (scope_id,),
                ).fetchall()
            ]
            for session_id in session_ids:
                conn.execute(
                    "DELETE FROM message WHERE session_id = ?",
                    (session_id,),
                )
            conn.execute("DELETE FROM session WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM upload_file WHERE scope_id = ?", (scope_id,))
            conn.execute("DELETE FROM knowledge_version WHERE scope_id = ?", (scope_id,))
        self.registry.mark_deleted(scope_id)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
