from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.wiki.constants import DATA_DIR, SYNC_STATUSES
from src.wiki.path_utils import normalize_rel_path


@dataclass(slots=True)
class TreeNode:
    name: str
    path: str
    type: str
    sync_status: str
    modified: str
    children: list["TreeNode"] = field(default_factory=list)


def _modified_iso(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    except OSError:
        return ""


def _node_type(path: Path) -> str:
    return "directory" if path.is_dir() else "file"


def _node_status(path: Path) -> str:
    return "synced"


def build_tree(base_path: str = "") -> list[dict]:
    scan_path = DATA_DIR / normalize_rel_path(base_path) if base_path else DATA_DIR
    if not scan_path.exists():
        return []

    def walk(directory: Path) -> list[dict]:
        nodes: list[dict] = []
        for item in sorted(directory.iterdir(), key=lambda path: (path.is_file(), path.name.lower())):
            rel_path = normalize_rel_path(str(item.relative_to(DATA_DIR)))
            if item.is_dir():
                nodes.append(
                    {
                        "name": item.name,
                        "path": rel_path,
                        "type": _node_type(item),
                        "sync_status": _node_status(item),
                        "modified": _modified_iso(item),
                        "children": walk(item),
                    }
                )
            else:
                nodes.append(
                    {
                        "name": item.name,
                        "path": rel_path,
                        "type": _node_type(item),
                        "sync_status": _node_status(item),
                        "modified": _modified_iso(item),
                    }
                )
        return nodes

    return walk(scan_path)


def list_markdown_files(base_path: str = "") -> list[Path]:
    scan_path = DATA_DIR / normalize_rel_path(base_path) if base_path else DATA_DIR
    if not scan_path.exists():
        return []
    return [path for path in scan_path.rglob("*.md") if path.is_file()]


def sync_status_is_known(value: str) -> bool:
    return value in SYNC_STATUSES

