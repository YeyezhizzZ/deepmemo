from __future__ import annotations

import threading
from dataclasses import dataclass

from src.deepme.identity import VisitorIdentityService
from src.deepme.jobs import JobQueue
from src.deepme.public_knowledge import PublicKnowledgePublisher
from src.deepme.qa import ScopedQAServiceFactory
from src.deepme.rate_limit import InMemoryRateLimiter
from src.deepme.scopes import (
    ResolvedScope,
    ScopeNotFoundError,
    ScopeNotReadyError,
    ScopeRegistry,
)
from src.deepme.settings import DeepMeSettings
from src.deepme.workspaces import WorkspaceService


@dataclass
class DeepMeRuntime:
    settings: DeepMeSettings
    registry: ScopeRegistry
    publisher: PublicKnowledgePublisher
    identity: VisitorIdentityService
    qa_factory: ScopedQAServiceFactory
    jobs: JobQueue
    workspaces: WorkspaceService
    rate_limiter: InMemoryRateLimiter

    @classmethod
    def create(cls, settings: DeepMeSettings | None = None) -> "DeepMeRuntime":
        resolved_settings = settings or DeepMeSettings.from_env()
        registry = ScopeRegistry(resolved_settings)
        jobs = JobQueue()
        workspaces = WorkspaceService(resolved_settings, registry, jobs)
        return cls(
            settings=resolved_settings,
            registry=registry,
            publisher=PublicKnowledgePublisher(resolved_settings, registry),
            identity=VisitorIdentityService(resolved_settings),
            qa_factory=ScopedQAServiceFactory(resolved_settings),
            jobs=jobs,
            workspaces=workspaces,
            rate_limiter=InMemoryRateLimiter(),
        )

    def ensure_public_ready(self) -> ResolvedScope:
        try:
            return self.registry.resolve(ScopeRegistry.PUBLIC_SCOPE_ID)
        except (ScopeNotFoundError, ScopeNotReadyError):
            return self.publisher.publish()


_runtime: DeepMeRuntime | None = None
_runtime_lock = threading.Lock()


def get_runtime() -> DeepMeRuntime:
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = DeepMeRuntime.create()
        return _runtime


def reset_runtime() -> None:
    global _runtime
    with _runtime_lock:
        if _runtime is not None:
            _runtime.qa_factory.clear()
            _runtime.rate_limiter.clear()
        _runtime = None
