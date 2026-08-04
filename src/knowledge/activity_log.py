from __future__ import annotations

import fcntl
import os
from datetime import datetime, timezone
from pathlib import Path

from src.knowledge.atomic_io import atomic_write_text


def append_activity(
    data_dir: str | Path,
    operation: str,
    description: str,
    details: list[str] | None = None,
) -> None:
    log_path = Path(data_dir) / "knowledge" / "log.md"
    lock_path = Path(data_dir) / "knowledge" / ".deepmemo" / "activity.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        existing = (
            log_path.read_text(encoding="utf-8").rstrip()
            if log_path.exists()
            else ""
        )
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        entry = [f"## [{timestamp}] {operation} | {description}"]
        entry.extend(f"- {detail}" for detail in details or [])
        content = "\n\n".join(
            part for part in (existing, "\n".join(entry)) if part
        )
        atomic_write_text(log_path, content.rstrip() + "\n")
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
