from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.deepme.scopes import ResolvedScope, ScopeRegistry
from src.deepme.settings import DeepMeSettings


class PublicKnowledgeBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceFile:
    path: Path
    relative_path: str
    sha256: str
    byte_size: int


class PublicKnowledgePublisher:
    def __init__(self, settings: DeepMeSettings, registry: ScopeRegistry):
        self.settings = settings
        self.registry = registry
        self._publish_lock = threading.Lock()

    def publish(self) -> ResolvedScope:
        with self._publish_lock:
            return self._publish_locked()

    def _publish_locked(self) -> ResolvedScope:
        source_files = self._discover_source_files()
        content_hash = self._content_hash(source_files)
        version = f"v1_{content_hash[:16]}"
        release_dir = self.settings.public_releases_dir / version

        if not release_dir.exists():
            self._build_release(release_dir, source_files, content_hash, version)

        runtime_root = self.settings.runtime_dir.resolve()
        documents_path = (release_dir / "documents").relative_to(runtime_root).as_posix()
        manifest_path = (release_dir / "manifest.json").relative_to(runtime_root).as_posix()
        return self.registry.register_public_version(
            version=version,
            content_hash=content_hash,
            documents_path=documents_path,
            manifest_path=manifest_path,
            source_revision=os.getenv("DEEPME_PUBLIC_SOURCE_REVISION") or None,
        )

    def _discover_source_files(self) -> list[SourceFile]:
        source_root = self.settings.public_source_dir
        if not source_root.is_dir():
            raise PublicKnowledgeBuildError(
                f"public knowledge directory does not exist: {source_root}"
            )
        if source_root.is_symlink():
            raise PublicKnowledgeBuildError("public knowledge root cannot be a symlink")

        files: list[SourceFile] = []
        for path in sorted(source_root.rglob("*.md")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_root)
            if any(part.startswith(".") for part in relative.parts):
                raise PublicKnowledgeBuildError(
                    f"hidden public knowledge path is not allowed: {relative.as_posix()}"
                )
            if self._contains_symlink(source_root, path):
                raise PublicKnowledgeBuildError(
                    f"public knowledge symlink is not allowed: {relative.as_posix()}"
                )
            content = path.read_bytes()
            try:
                content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise PublicKnowledgeBuildError(
                    f"public knowledge must be UTF-8: {relative.as_posix()}"
                ) from exc
            files.append(
                SourceFile(
                    path=path,
                    relative_path=relative.as_posix(),
                    sha256=hashlib.sha256(content).hexdigest(),
                    byte_size=len(content),
                )
            )

        if not files:
            raise PublicKnowledgeBuildError("public knowledge directory has no Markdown files")
        return files

    def _contains_symlink(self, source_root: Path, path: Path) -> bool:
        current = path
        while current != source_root:
            if current.is_symlink():
                return True
            current = current.parent
        return False

    def _content_hash(self, files: list[SourceFile]) -> str:
        digest = hashlib.sha256()
        for item in files:
            digest.update(item.relative_path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(item.sha256.encode("ascii"))
            digest.update(b"\0")
        return digest.hexdigest()

    def _build_release(
        self,
        release_dir: Path,
        files: list[SourceFile],
        content_hash: str,
        version: str,
    ) -> None:
        self.settings.public_staging_dir.mkdir(parents=True, exist_ok=True)
        self.settings.public_releases_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = self.settings.public_staging_dir / f"{version}-{uuid.uuid4().hex}"
        documents_dir = staging_dir / "documents"
        documents_dir.mkdir(parents=True)

        try:
            for item in files:
                destination = documents_dir / item.relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item.path, destination)

            manifest = {
                "schema_version": 1,
                "scope_id": ScopeRegistry.PUBLIC_SCOPE_ID,
                "version": version,
                "content_hash": content_hash,
                "built_at": _now(),
                "source_revision": os.getenv("DEEPME_PUBLIC_SOURCE_REVISION") or None,
                "files": [
                    {
                        "path": item.relative_path,
                        "sha256": item.sha256,
                        "byte_size": item.byte_size,
                    }
                    for item in files
                ],
            }
            (staging_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            if release_dir.exists():
                return
            os.replace(staging_dir, release_dir)
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
