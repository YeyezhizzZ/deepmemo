from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pypdf import PdfWriter
import pytest

from src.app.database import connection_scope
from src.deepme.documents import DocumentParseError
from src.deepme.rate_limit import InMemoryRateLimiter, RateLimitExceeded
from src.deepme.runtime import get_runtime
from src.deepme.worker import DeepMeWorker


def test_blank_pdf_is_rejected(isolated_app_state):
    pdf_path = isolated_app_state.runtime_dir / "blank.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    with pytest.raises(DocumentParseError, match="no extractable text"):
        get_runtime().workspaces.normalizer.normalize(pdf_path, "blank.pdf")


def test_worker_deletes_expired_workspace():
    runtime = get_runtime()
    scope = runtime.workspaces.create("owner")
    expired_at = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    ).replace(microsecond=0).isoformat()
    with connection_scope() as conn:
        conn.execute(
            "UPDATE knowledge_scope SET expires_at = ? WHERE scope_id = ?",
            (expired_at, scope.scope_id),
        )

    worker = DeepMeWorker(runtime)
    worker.run_periodic_tasks(force=True)
    while worker.run_once():
        pass

    with connection_scope() as conn:
        row = conn.execute(
            "SELECT status, deleted_at FROM knowledge_scope WHERE scope_id = ?",
            (scope.scope_id,),
        ).fetchone()
    assert row["status"] == "deleted"
    assert row["deleted_at"]
    assert not runtime.workspaces.workspace_root(scope.scope_id).exists()


def test_worker_publishes_changed_public_knowledge(isolated_app_state):
    runtime = get_runtime()
    first = runtime.ensure_public_ready()
    (isolated_app_state.public_source_dir / "new.md").write_text(
        "# New\n\nnew public knowledge\n",
        encoding="utf-8",
    )

    DeepMeWorker(runtime).run_periodic_tasks(force=True)
    second = runtime.registry.resolve("public")

    assert second.knowledge_version != first.knowledge_version
    assert first.documents_root.exists()
    assert (second.documents_root / "new.md").is_file()


def test_rate_limiter_isolated_by_owner():
    limiter = InMemoryRateLimiter()
    limiter.check("chat", "owner-a", limit=1, window_seconds=60)
    limiter.check("chat", "owner-b", limit=1, window_seconds=60)

    with pytest.raises(RateLimitExceeded):
        limiter.check("chat", "owner-a", limit=1, window_seconds=60)
