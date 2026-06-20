from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from src.knowledge.card_store import DATA_DIR
from src.knowledge.maintenance import KnowledgeMaintainer


_scheduler_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _seconds_until_next_run(hour: int = 3) -> float:
    from datetime import datetime, timedelta

    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def _loop(data_dir: Path) -> None:
    while not _stop_event.wait(_seconds_until_next_run()):
        try:
            KnowledgeMaintainer(data_dir=data_dir).run_maintenance()
        except Exception as exc:
            print(f"[knowledge] scheduled maintenance failed: {exc}", flush=True)
        time.sleep(1)


def start_knowledge_scheduler(data_dir: str | Path | None = None) -> None:
    global _scheduler_thread
    if os.getenv("DEEPMEMO_DISABLE_KNOWLEDGE_SCHEDULER", "").lower() in {"1", "true", "yes"}:
        return
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _stop_event.clear()
    root = Path(data_dir) if data_dir else DATA_DIR
    _scheduler_thread = threading.Thread(target=_loop, args=(root,), daemon=True)
    _scheduler_thread.start()


def stop_knowledge_scheduler() -> None:
    _stop_event.set()
