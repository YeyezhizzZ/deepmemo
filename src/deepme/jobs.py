from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.app.database import connection_scope


@dataclass(frozen=True)
class Job:
    job_id: str
    job_type: str
    scope_id: str | None
    payload: dict
    attempts: int


class JobQueue:
    def enqueue(
        self,
        job_type: str,
        *,
        scope_id: str | None,
        payload: dict | None = None,
        deduplicate: bool = False,
    ) -> str:
        now = _now()
        with connection_scope() as conn:
            if deduplicate:
                existing = conn.execute(
                    """
                    SELECT job_id FROM job
                    WHERE job_type = ?
                      AND scope_id IS ?
                      AND status IN ('queued', 'running')
                    ORDER BY created_at
                    LIMIT 1
                    """,
                    (job_type, scope_id),
                ).fetchone()
                if existing:
                    return str(existing["job_id"])
            job_id = f"job_{uuid.uuid4().hex}"
            conn.execute(
                """
                INSERT INTO job (
                    job_id, job_type, scope_id, payload_json, status,
                    attempts, available_at, locked_at, last_error,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'queued', 0, ?, NULL, NULL, ?, ?)
                """,
                (
                    job_id,
                    job_type,
                    scope_id,
                    json.dumps(payload or {}, ensure_ascii=False),
                    now,
                    now,
                    now,
                ),
            )
        return job_id

    def recover_stale(self, *, stale_after_seconds: int = 300) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
        ).replace(microsecond=0).isoformat()
        with connection_scope() as conn:
            cursor = conn.execute(
                """
                UPDATE job
                SET status = 'queued', locked_at = NULL, updated_at = ?
                WHERE status = 'running' AND locked_at < ?
                """,
                (_now(), cutoff),
            )
            return int(cursor.rowcount)

    def claim_next(self) -> Job | None:
        now = _now()
        with connection_scope() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM job
                WHERE status = 'queued' AND available_at <= ?
                ORDER BY created_at, job_id
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                return None
            updated = conn.execute(
                """
                UPDATE job
                SET status = 'running', attempts = attempts + 1,
                    locked_at = ?, updated_at = ?
                WHERE job_id = ? AND status = 'queued'
                """,
                (now, now, row["job_id"]),
            )
            if updated.rowcount != 1:
                return None
            return Job(
                job_id=row["job_id"],
                job_type=row["job_type"],
                scope_id=row["scope_id"],
                payload=json.loads(row["payload_json"] or "{}"),
                attempts=int(row["attempts"]) + 1,
            )

    def succeed(self, job_id: str) -> None:
        with connection_scope() as conn:
            conn.execute(
                """
                UPDATE job
                SET status = 'succeeded', locked_at = NULL,
                    last_error = NULL, updated_at = ?
                WHERE job_id = ?
                """,
                (_now(), job_id),
            )

    def fail(
        self,
        job: Job,
        error: Exception,
        *,
        max_attempts: int = 3,
    ) -> None:
        message = f"{type(error).__name__}: {error}"[:1000]
        if job.attempts >= max_attempts:
            status = "failed"
            available_at = _now()
        else:
            status = "queued"
            delay = min(60, 2 ** job.attempts)
            available_at = (
                datetime.now(timezone.utc) + timedelta(seconds=delay)
            ).replace(microsecond=0).isoformat()
        with connection_scope() as conn:
            conn.execute(
                """
                UPDATE job
                SET status = ?, available_at = ?, locked_at = NULL,
                    last_error = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status, available_at, message, _now(), job.job_id),
            )

    def get(self, job_id: str):
        with connection_scope() as conn:
            return conn.execute(
                "SELECT * FROM job WHERE job_id = ?",
                (job_id,),
            ).fetchone()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
