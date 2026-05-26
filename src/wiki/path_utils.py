from __future__ import annotations

from pathlib import Path

from src.wiki.constants import DATA_DIR, POLICY_DIR, RAW_DIR, WIKI_DIR


def normalize_rel_path(value: str | None) -> str:
    if not value:
        return ""

    normalized = str(value).strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    if normalized.startswith("data/"):
        normalized = normalized[len("data/"):]
    return normalized


def is_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_under_root(relative_path: str, root: Path) -> Path:
    rel = normalize_rel_path(relative_path)
    candidate = (root / rel).resolve()
    if not is_within_root(candidate, root):
        raise ValueError(f"Path escapes root: {relative_path}")
    return candidate


def resolve_data_path(relative_path: str) -> Path:
    return resolve_under_root(relative_path, DATA_DIR)


def resolve_raw_path(relative_path: str) -> Path:
    return resolve_under_root(relative_path, RAW_DIR)


def resolve_wiki_path(relative_path: str) -> Path:
    return resolve_under_root(relative_path, WIKI_DIR)


def resolve_policy_path(relative_path: str) -> Path:
    return resolve_under_root(relative_path, POLICY_DIR)


def rel_path(path: Path, root: Path = DATA_DIR) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()

