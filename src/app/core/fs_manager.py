import hashlib
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional
import sqlite3
import re

REPO_ROOT = Path(__file__).resolve().parents[3]
DATABASE_PATH = REPO_ROOT / "data.db"
DATA_DIR = REPO_ROOT / "data"

def natural_name_key(path: Path):
    """Sort date-like numeric names newest first, with hidden entries after visible entries."""
    name = path.name.lower()
    stem = path.stem
    if name.startswith("."):
        return (2, 0, name)
    if stem.isdigit():
        return (0, -int(stem), name)
    parts = re.split(r"(\d+)", name)
    natural_parts = tuple((0, int(part)) if part.isdigit() else (1, part) for part in parts)
    return (1, 0, natural_parts)


def modified_time(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0


def modified_iso(path: Path) -> str:
    return datetime.fromtimestamp(modified_time(path)).isoformat()


def sort_key_for_directory(path: Path, base_path: str):
    """Sort diary entries like chat sessions: most recently edited first."""
    base_parts = Path(base_path).parts if base_path else ()
    if base_parts and base_parts[0] == "diary":
        hidden_rank = 1 if path.name.startswith(".") else 0
        return (hidden_rank, -modified_time(path), natural_name_key(path))
    return natural_name_key(path)


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def compute_file_hash(file_path: Path) -> str:
    if not file_path.exists():
        return ""
    with open(file_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def get_file_meta(file_path: str) -> Optional[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM file_meta WHERE file_path = ?", (file_path,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def upsert_file_meta(file_path: str, file_hash: str, sync_status: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO file_meta (id, file_path, file_hash, sync_status, last_modified, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_path) DO UPDATE SET
            file_hash = excluded.file_hash,
            sync_status = excluded.sync_status,
            last_modified = excluded.last_modified
    """, (str(uuid.uuid4()), file_path, file_hash, sync_status, now, now))
    conn.commit()
    conn.close()

def update_sync_status(file_path: str, sync_status: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    result = cursor.execute(
        "UPDATE file_meta SET sync_status = ?, last_modified = ? WHERE file_path = ?",
        (sync_status, now, file_path)
    )
    conn.commit()
    conn.close()
    if result.rowcount == 0:
        upsert_file_meta(file_path, compute_file_hash(DATA_DIR / file_path), sync_status)

def read_file_content(file_path: str) -> str:
    full_path = DATA_DIR / file_path
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()

def write_file_content(file_path: str, content: str) -> dict:
    full_path = DATA_DIR / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    # 更新 file_meta
    file_hash = compute_file_hash(full_path)
    upsert_file_meta(file_path, file_hash, "synced")
    return {
        "file_path": file_path,
        "file_hash": file_hash,
        "sync_status": "synced",
        "last_modified": datetime.now().isoformat()
    }

def move_file(old_path: str, new_path: str) -> dict:
    old_full = DATA_DIR / old_path
    new_full = DATA_DIR / new_path
    if not old_full.exists():
        raise FileNotFoundError(f"Source file not found: {old_path}")
    new_full.parent.mkdir(parents=True, exist_ok=True)
    old_full.rename(new_full)
    # 更新 file_meta
    file_hash = compute_file_hash(new_full)
    upsert_file_meta(new_path, file_hash, "synced")
    update_sync_status(old_path, "dirty")  # 标记旧路径为 dirty
    return {
        "old_path": old_path,
        "new_path": new_path,
        "file_hash": file_hash,
        "sync_status": "synced"
    }

def create_file(file_path: str, content: str = "") -> dict:
    """创建新文件"""
    full_path = DATA_DIR / file_path
    if full_path.exists():
        raise FileExistsError(f"File already exists: {file_path}")
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    file_hash = compute_file_hash(full_path)
    upsert_file_meta(file_path, file_hash, "synced")
    return {
        "file_path": file_path,
        "file_hash": file_hash,
        "sync_status": "synced"
    }


def create_directory(dir_path: str) -> dict:
    """创建新目录"""
    full_path = DATA_DIR / dir_path
    if full_path.exists():
        raise FileExistsError(f"Directory already exists: {dir_path}")
    full_path.mkdir(parents=True, exist_ok=True)
    return {
        "dir_path": dir_path,
        "sync_status": "synced"
    }


def scan_directory_tree(base_path: str = "") -> list:
    """递归扫描 data/ 目录，返回嵌套 JSON"""
    scan_path = DATA_DIR / base_path if base_path else DATA_DIR
    result = []
    if not scan_path.exists():
        return result
    for item in sorted(scan_path.iterdir(), key=lambda path: sort_key_for_directory(path, base_path)):
        rel_path = str(item.relative_to(DATA_DIR))
        meta = get_file_meta(rel_path)
        sync_status = meta["sync_status"] if meta else "synced"
        modified = modified_iso(item)
        if item.is_dir():
            result.append({
                "name": item.name,
                "path": rel_path,
                "type": "directory",
                "sync_status": sync_status,
                "modified": modified,
                "children": scan_directory_tree(rel_path)
            })
        else:
            result.append({
                "name": item.name,
                "path": rel_path,
                "type": "file",
                "sync_status": sync_status,
                "modified": modified
            })
    return result
