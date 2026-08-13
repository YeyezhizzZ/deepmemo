from __future__ import annotations

import signal
import time
from dataclasses import dataclass

from src.app.database import connection_scope, init_db
from src.deepme.jobs import Job, JobQueue
from src.deepme.runtime import DeepMeRuntime, get_runtime


@dataclass
class WorkerState:
    stopping: bool = False


class DeepMeWorker:
    def __init__(self, runtime: DeepMeRuntime):
        self.runtime = runtime
        self.jobs: JobQueue = runtime.jobs
        self.state = WorkerState()
        self._last_public_sync = 0.0
        self._last_expiry_scan = 0.0

    def run_once(self) -> bool:
        job = self.jobs.claim_next()
        if job is None:
            return False
        try:
            self._execute(job)
        except Exception as exc:
            self.jobs.fail(job, exc)
            if job.scope_id and job.attempts >= 3:
                try:
                    scope = self.runtime.registry.get_scope(job.scope_id)
                    if not scope.current_version and scope.status not in {
                        "deleting",
                        "deleted",
                    }:
                        self.runtime.registry.set_status(job.scope_id, "error")
                except Exception:
                    pass
            return True
        self.jobs.succeed(job.job_id)
        return True

    def run_forever(self) -> None:
        self.jobs.recover_stale()
        while not self.state.stopping:
            self.run_periodic_tasks()
            if not self.run_once():
                time.sleep(self.runtime.settings.worker_poll_seconds)

    def run_periodic_tasks(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_public_sync >= self.runtime.settings.public_sync_seconds:
            try:
                self.runtime.publisher.publish()
            except Exception as exc:
                print(
                    f"[deepme-worker] public publish skipped: {type(exc).__name__}: {exc}",
                    flush=True,
                )
            self._last_public_sync = now
        if force or now - self._last_expiry_scan >= 60:
            try:
                self._enqueue_expired_scopes()
            except Exception as exc:
                print(
                    f"[deepme-worker] expiry scan failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )
            self._last_expiry_scan = now

    def stop(self) -> None:
        self.state.stopping = True

    def _execute(self, job: Job) -> None:
        if job.job_type == "ingest_file":
            self.runtime.workspaces.normalize_file(str(job.payload["file_id"]))
            return
        if job.job_type == "build_scope":
            if not job.scope_id:
                raise ValueError("build_scope job requires scope_id")
            self.runtime.workspaces.build_scope(job.scope_id)
            return
        if job.job_type == "delete_scope":
            if not job.scope_id:
                raise ValueError("delete_scope job requires scope_id")
            self.runtime.workspaces.delete_scope(job.scope_id)
            return
        if job.job_type == "publish_public":
            self.runtime.publisher.publish()
            return
        raise ValueError(f"unsupported job type: {job.job_type}")

    def _enqueue_expired_scopes(self) -> None:
        for scope_id in self.runtime.registry.expired_temporary_scope_ids():
            with connection_scope() as conn:
                conn.execute(
                    """
                    UPDATE knowledge_scope
                    SET status = 'deleting'
                    WHERE scope_id = ?
                      AND status NOT IN ('deleting', 'deleted')
                    """,
                    (scope_id,),
                )
            self.jobs.enqueue(
                "delete_scope",
                scope_id=scope_id,
                deduplicate=True,
            )


def main() -> int:
    init_db()
    worker = DeepMeWorker(get_runtime())

    def handle_signal(*_):
        worker.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    worker.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
