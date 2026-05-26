from __future__ import annotations

import hashlib
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from src.wiki.constants import DATA_DIR, SYNC_STATUSES
from src.wiki.path_utils import normalize_rel_path, resolve_data_path


def compute_file_hash(file_path: Path) -> str:
    if not file_path.exists() or not file_path.is_file():
        return ""
    return hashlib.md5(file_path.read_bytes()).hexdigest()


def read_text(relative_path: str) -> str:
    full_path = resolve_data_path(relative_path)
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")
    return full_path.read_text(encoding="utf-8")


def write_text(relative_path: str, content: str) -> dict[str, str]:
    full_path = resolve_data_path(relative_path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return {
        "file_path": normalize_rel_path(relative_path),
        "file_hash": compute_file_hash(full_path),
        "sync_status": "synced",
        "last_modified": datetime.now().isoformat(),
    }


def create_directory(relative_path: str) -> dict[str, str]:
    full_path = resolve_data_path(relative_path)
    if full_path.exists():
        raise FileExistsError(f"Directory already exists: {relative_path}")
    full_path.mkdir(parents=True, exist_ok=True)
    return {"dir_path": normalize_rel_path(relative_path), "sync_status": "synced"}


def move_path(old_path: str, new_path: str) -> dict[str, str]:
    old_full = resolve_data_path(old_path)
    new_full = resolve_data_path(new_path)
    if not old_full.exists():
        raise FileNotFoundError(f"Source file not found: {old_path}")
    if new_full.exists():
        raise FileExistsError(f"Destination already exists: {new_path}")
    new_full.parent.mkdir(parents=True, exist_ok=True)
    old_full.rename(new_full)
    return {
        "old_path": normalize_rel_path(old_path),
        "new_path": normalize_rel_path(new_path),
        "file_hash": compute_file_hash(new_full),
        "sync_status": "synced",
    }


def create_file(relative_path: str, content: str = "") -> dict[str, str]:
    full_path = resolve_data_path(relative_path)
    if full_path.exists():
        raise FileExistsError(f"File already exists: {relative_path}")
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return {
        "file_path": normalize_rel_path(relative_path),
        "file_hash": compute_file_hash(full_path),
        "sync_status": "synced",
    }


def collect_sync_status(path: Path) -> str:
    if path.is_dir():
        return "synced"
    return "synced"


def is_supported_sync_status(value: str) -> bool:
    return value in SYNC_STATUSES


def make_file_meta(path: Path, sync_status: str = "synced") -> dict[str, str]:
    return {
        "id": str(uuid.uuid4()),
        "file_path": normalize_rel_path(path),
        "file_hash": compute_file_hash(path),
        "sync_status": sync_status if is_supported_sync_status(sync_status) else "synced",
        "last_modified": datetime.now().isoformat(),
        "created_at": datetime.now().isoformat(),
    }


def data_dir() -> Path:
    return DATA_DIR


def delete_path(relative_path: str) -> dict[str, str | bool]:
    full_path = resolve_data_path(relative_path)
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")
    if full_path == DATA_DIR:
        raise ValueError("Refusing to delete data root")
    if full_path.is_dir():
        shutil.rmtree(full_path)
    else:
        full_path.unlink()
    return {
        "path": normalize_rel_path(relative_path),
        "deleted": True,
    }
