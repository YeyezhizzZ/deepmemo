import os
import hashlib
import threading
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

DATA_DIR = Path(os.getenv("DEEPMEMO_DATA_DIR", Path(__file__).resolve().parents[2].parent / "data"))

def calculate_hash(file_path: Path) -> str:
    """计算文件的 MD5 hash"""
    if not file_path.exists():
        return ""
    with open(file_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def get_db_connection():
    import sqlite3
    DATABASE_PATH = Path(os.getenv("DEEPMEMO_DB_PATH", Path(__file__).resolve().parents[2].parent / "data.db"))
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

class KnowledgeBaseHandler(FileSystemEventHandler):
    def __init__(self, on_change_callback=None):
        super().__init__()
        self.on_change_callback = on_change_callback

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            self._handle_change(event.src_path, "modified")

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            self._handle_change(event.src_path, "created")

    def on_deleted(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            self._handle_change(event.src_path, "deleted")

    def _handle_change(self, src_path: str, event_type: str):
        full_path = Path(src_path)
        rel_path = str(full_path.relative_to(DATA_DIR))

        # 计算新 hash
        new_hash = calculate_hash(full_path)

        # 查询 DB，如果 Hash 不同，标记为 dirty
        conn = get_db_connection()
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT file_hash, sync_status FROM file_meta WHERE file_path = ?",
            (rel_path,)
        ).fetchone()

        if row:
            if row["file_hash"] != new_hash:
                now = datetime.now().isoformat()
                cursor.execute(
                    "UPDATE file_meta SET file_hash = ?, sync_status = 'dirty', last_modified = ? WHERE file_path = ?",
                    (new_hash, now, rel_path)
                )
                conn.commit()
                print(f"[Watcher] {event_type}: {rel_path} -> dirty (hash changed)")
                if self.on_change_callback:
                    self.on_change_callback(rel_path, "dirty")
        conn.close()

class WatcherService:
    def __init__(self, on_change_callback=None):
        observer_mode = os.getenv("DEEPMEMO_WATCHER_MODE", "").strip().lower()
        self.observer = PollingObserver() if observer_mode == "polling" else Observer()
        self.handler = KnowledgeBaseHandler(on_change_callback)

    def start(self):
        self.observer.schedule(self.handler, str(DATA_DIR), recursive=True)
        self.observer.start()
        print(f"[Watcher] Started watching {DATA_DIR}")

    def stop(self):
        self.observer.stop()
        self.observer.join()
        print("[Watcher] Stopped")

    def is_running(self) -> bool:
        return self.observer.is_alive()

# 单例
_watcher_service = None

def get_watcher_service(on_change_callback=None) -> WatcherService:
    global _watcher_service
    if _watcher_service is None:
        _watcher_service = WatcherService(on_change_callback)
    return _watcher_service

def start_watcher(on_change_callback=None):
    service = get_watcher_service(on_change_callback)
    if not service.is_running():
        service.start()
    return service

def stop_watcher():
    global _watcher_service
    if _watcher_service is not None:
        _watcher_service.stop()
        _watcher_service = None
