from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from src.knowledge.atomic_io import atomic_write_json, atomic_write_text, load_json
from src.knowledge.models import SourceSnapshot


class SourceStore:
    """Content-addressed snapshots for mutable DeepMemo source files."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.knowledge_dir = self.data_dir / "knowledge"
        self.sources_dir = self.knowledge_dir / "sources"
        self.state_dir = self.knowledge_dir / ".deepmemo"
        self.manifest_path = self.state_dir / "source-manifest.json"

    def ingest_path(self, value: str | Path, *, source_type: str = "file") -> SourceSnapshot:
        source_path = self.resolve_origin_path(value)
        content = source_path.read_text(encoding="utf-8")
        origin_path = source_path.relative_to(self.data_dir.resolve()).as_posix()
        source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        source_id = self._source_id(origin_path)
        snapshot_path = self.sources_dir / source_id / f"{source_hash}.md"
        if not snapshot_path.exists():
            atomic_write_text(snapshot_path, content)

        snapshot = SourceSnapshot(
            source_id=source_id,
            origin_path=origin_path,
            source_hash=source_hash,
            snapshot_path=snapshot_path.relative_to(self.data_dir).as_posix(),
            captured_at=self._now(),
            line_count=len(content.splitlines()),
            source_type=source_type,
            original_chars=len(content),
        )
        self._record_snapshot(snapshot)
        return snapshot

    def resolve_origin_path(self, value: str | Path, *, must_exist: bool = True) -> Path:
        raw = Path(value)
        if raw.is_absolute():
            candidate = raw.resolve()
        else:
            normalized = str(value).strip().replace("\\", "/")
            while normalized.startswith("./"):
                normalized = normalized[2:]
            if normalized.startswith("data/"):
                normalized = normalized[len("data/") :]
            candidate = (self.data_dir / normalized).resolve()

        try:
            candidate.relative_to(self.data_dir.resolve())
        except ValueError as exc:
            raise ValueError("source path escapes data directory") from exc
        if candidate.suffix.lower() != ".md":
            raise ValueError("knowledge compiler currently accepts Markdown sources only")
        if must_exist and not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate

    def discover_origins(self) -> list[str]:
        origins: list[str] = []
        for dirname in ("diary", "raw"):
            root = self.data_dir / dirname
            if root.exists():
                origins.extend(
                    path.relative_to(self.data_dir).as_posix()
                    for path in sorted(root.rglob("*.md"))
                )
        return sorted(origins)

    def current_snapshot(self, origin_path: str) -> SourceSnapshot | None:
        entry = self._manifest().get("origins", {}).get(origin_path)
        if not entry:
            return None
        return SourceSnapshot.from_dict(entry["current"])

    def list_current(self) -> list[SourceSnapshot]:
        entries = self._manifest().get("origins", {})
        return [
            SourceSnapshot.from_dict(entries[origin]["current"])
            for origin in sorted(entries)
        ]

    def remove_origin(self, origin_path: str) -> SourceSnapshot | None:
        manifest = self._manifest()
        entry = manifest.get("origins", {}).pop(origin_path, None)
        if entry is None:
            return None
        manifest["updated_at"] = self._now()
        atomic_write_json(self.manifest_path, manifest)
        return SourceSnapshot.from_dict(entry["current"])

    def read_snapshot(self, snapshot: SourceSnapshot) -> str:
        path = (self.data_dir / snapshot.snapshot_path).resolve()
        try:
            path.relative_to(self.sources_dir.resolve())
        except ValueError as exc:
            raise ValueError("snapshot path escapes source store") from exc
        content = path.read_text(encoding="utf-8")
        actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if actual_hash != snapshot.source_hash:
            raise ValueError(f"source snapshot hash mismatch: {snapshot.source_id}")
        return content

    def numbered_chunks(
        self,
        snapshot: SourceSnapshot,
        *,
        max_chars: int = 60_000,
    ) -> list[str]:
        lines = self.read_snapshot(snapshot).splitlines()
        chunks: list[str] = []
        current: list[str] = []
        current_chars = 0
        for line_number, line in enumerate(lines, start=1):
            numbered = f"{line_number:>6} | {line}"
            if current and current_chars + len(numbered) + 1 > max_chars:
                chunks.append("\n".join(current))
                current = []
                current_chars = 0
            current.append(numbered)
            current_chars += len(numbered) + 1
        if current or not chunks:
            chunks.append("\n".join(current))
        return chunks

    def excerpt(self, snapshot: SourceSnapshot, start_line: int, end_line: int) -> str:
        if start_line < 1 or end_line < start_line:
            raise ValueError("invalid citation line range")
        lines = self.read_snapshot(snapshot).splitlines()
        if end_line > len(lines):
            raise ValueError(
                f"citation line range {start_line}-{end_line} exceeds {len(lines)} lines"
            )
        return "\n".join(lines[start_line - 1 : end_line])

    def _record_snapshot(self, snapshot: SourceSnapshot) -> None:
        manifest = self._manifest()
        origins = manifest.setdefault("origins", {})
        entry = origins.setdefault(snapshot.origin_path, {"history": []})
        history = entry.setdefault("history", [])
        if snapshot.source_hash not in history:
            history.append(snapshot.source_hash)
        entry["current"] = snapshot.to_dict()
        manifest["updated_at"] = self._now()
        atomic_write_json(self.manifest_path, manifest)

    def _manifest(self) -> dict:
        data = load_json(
            self.manifest_path,
            {"version": 1, "origins": {}, "updated_at": None},
        )
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("unsupported source manifest")
        data.setdefault("origins", {})
        return data

    def _source_id(self, origin_path: str) -> str:
        digest = hashlib.sha256(origin_path.encode("utf-8")).hexdigest()[:12]
        return f"src-{digest}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
