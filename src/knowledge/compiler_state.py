from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from src.knowledge.atomic_io import atomic_write_json, load_json
from src.knowledge.models import ExtractedKnowledge, KnowledgeCard, SourceSnapshot


_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class CompileStateStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.root = self.data_dir / "knowledge" / ".deepmemo"
        self.state_path = self.root / "compile-state.json"
        self.extractions_dir = self.root / "extractions"

    def load(self) -> dict:
        state = load_json(
            self.state_path,
            {"version": 2, "sources": {}, "updated_at": None},
        )
        if not isinstance(state, dict) or state.get("version") != 2:
            raise ValueError("unsupported knowledge compile state")
        state.setdefault("sources", {})
        return state

    def save(self, state: dict) -> None:
        state["version"] = 2
        state["updated_at"] = _now()
        atomic_write_json(self.state_path, state)

    def save_extractions(
        self,
        snapshot: SourceSnapshot,
        items: list[ExtractedKnowledge],
        *,
        model_id: str,
        prompt_version: str,
    ) -> None:
        atomic_write_json(
            self.extractions_dir / f"{snapshot.source_id}.json",
            {
                "version": 1,
                "snapshot": snapshot.to_dict(),
                "model_id": model_id,
                "prompt_version": prompt_version,
                "items": [item.to_dict() for item in items],
            },
        )

    def load_extractions(self, source_id: str) -> list[ExtractedKnowledge]:
        _validate_id(source_id)
        path = self.extractions_dir / f"{source_id}.json"
        data = load_json(path, None)
        if data is None:
            return []
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError(f"unsupported extraction cache: {source_id}")
        return [ExtractedKnowledge.from_dict(item) for item in data.get("items") or []]

    def iter_extractions(self) -> Iterator[tuple[SourceSnapshot, list[ExtractedKnowledge]]]:
        if not self.extractions_dir.exists():
            return
        for path in sorted(self.extractions_dir.glob("src-*.json")):
            data = load_json(path, None)
            if not isinstance(data, dict) or data.get("version") != 1:
                continue
            yield (
                SourceSnapshot.from_dict(data["snapshot"]),
                [ExtractedKnowledge.from_dict(item) for item in data.get("items") or []],
            )

    def delete_extractions(self, source_id: str) -> None:
        _validate_id(source_id)
        (self.extractions_dir / f"{source_id}.json").unlink(missing_ok=True)


class CandidateStore:
    def __init__(self, data_dir: str | Path):
        self.root = Path(data_dir) / "knowledge" / ".deepmemo"
        self.pending_dir = self.root / "candidates"
        self.archive_dir = self.pending_dir / "archive"

    def write(
        self,
        card: KnowledgeCard,
        *,
        reasons: list[str],
        source_hashes: dict[str, str],
    ) -> str:
        payload = json.dumps(card.to_dict(), ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
        candidate_id = f"{card.slug}-{digest}"
        _validate_id(candidate_id)
        atomic_write_json(
            self.pending_dir / f"{candidate_id}.json",
            {
                "version": 1,
                "id": candidate_id,
                "slug": card.slug,
                "card": card.to_dict(),
                "reasons": sorted(set(reasons)),
                "source_hashes": dict(sorted(source_hashes.items())),
                "status": "pending",
                "created_at": _now(),
            },
        )
        return candidate_id

    def list(self) -> list[dict]:
        if not self.pending_dir.exists():
            return []
        candidates: list[dict] = []
        for path in sorted(self.pending_dir.glob("*.json")):
            data = load_json(path, None)
            if isinstance(data, dict) and data.get("version") == 1:
                candidates.append(data)
        return candidates

    def load(self, candidate_id: str) -> dict:
        _validate_id(candidate_id)
        data = load_json(self.pending_dir / f"{candidate_id}.json", None)
        if not isinstance(data, dict) or data.get("version") != 1:
            raise FileNotFoundError(candidate_id)
        return data

    def archive(self, candidate_id: str, *, status: str) -> dict:
        if status not in {"approved", "rejected"}:
            raise ValueError(f"unsupported candidate status: {status}")
        data = self.load(candidate_id)
        data["status"] = status
        data["resolved_at"] = _now()
        target = self.archive_dir / f"{candidate_id}.json"
        atomic_write_json(target, data)
        (self.pending_dir / f"{candidate_id}.json").unlink(missing_ok=True)
        return data


class CompileLock:
    def __init__(self, data_dir: str | Path):
        self.path = Path(data_dir) / "knowledge" / ".deepmemo" / "compile.lock"
        self._descriptor: int | None = None

    def __enter__(self) -> "CompileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(descriptor)
            raise RuntimeError("knowledge compile is already running") from exc
        self._descriptor = descriptor
        return self

    def __exit__(self, *_: object) -> None:
        if self._descriptor is not None:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            os.close(self._descriptor)
            self._descriptor = None


def _validate_id(value: str) -> None:
    if not _SAFE_ID_RE.match(value):
        raise ValueError(f"unsafe knowledge identifier: {value}")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
