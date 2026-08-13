from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class DeepMeSettings:
    repo_root: Path
    runtime_dir: Path
    public_source_dir: Path
    site_name: str
    site_bio: str
    site_avatar: str
    cookie_secret: str
    cookie_secure: bool
    visitor_ttl_hours: int
    session_ttl_hours: int
    upload_enabled: bool
    upload_ttl_hours: int
    upload_max_files: int
    upload_max_bytes: int
    upload_max_file_bytes: int
    pdf_max_pages: int
    parse_timeout_seconds: int
    normalized_max_chars: int
    worker_poll_seconds: int
    public_sync_seconds: int
    retrieval_mode: str
    rerank_enabled: bool
    chat_rate_limit_per_minute: int
    upload_rate_limit_per_hour: int

    @classmethod
    def from_env(cls) -> "DeepMeSettings":
        repo_root = Path(__file__).resolve().parents[2]
        runtime_dir = Path(os.getenv("DEEPME_RUNTIME_DIR", repo_root / "runtime")).expanduser().resolve()
        public_source_dir = Path(
            os.getenv("DEEPME_PUBLIC_SOURCE_DIR", repo_root / "data" / "mock")
        ).expanduser().resolve()
        environment = os.getenv("DEEPME_ENV", "development").strip().lower()
        cookie_secret = os.getenv("DEEPME_COOKIE_SECRET", "").strip()
        if not cookie_secret:
            if environment == "production":
                raise ValueError("DEEPME_COOKIE_SECRET is required in production")
            cookie_secret = "deepme-development-cookie-secret"
        retrieval_mode = os.getenv("DEEPME_RETRIEVAL_MODE", "hybrid").strip().lower()
        if retrieval_mode not in {"ngram", "hybrid"}:
            raise ValueError("DEEPME_RETRIEVAL_MODE must be ngram or hybrid")

        return cls(
            repo_root=repo_root,
            runtime_dir=runtime_dir,
            public_source_dir=public_source_dir,
            site_name=os.getenv("DEEPME_SITE_NAME", "DeepMe").strip() or "DeepMe",
            site_bio=os.getenv(
                "DEEPME_SITE_BIO",
                "基于作者公开知识库的可追溯问答。",
            ).strip(),
            site_avatar=os.getenv("DEEPME_SITE_AVATAR", "").strip(),
            cookie_secret=cookie_secret,
            cookie_secure=_env_bool("DEEPME_COOKIE_SECURE", environment == "production"),
            visitor_ttl_hours=_env_int("DEEPME_VISITOR_TTL_HOURS", 24),
            session_ttl_hours=_env_int("DEEPME_SESSION_TTL_HOURS", 24),
            upload_enabled=_env_bool("DEEPME_UPLOAD_ENABLED", True),
            upload_ttl_hours=_env_int("DEEPME_UPLOAD_TTL_HOURS", 24),
            upload_max_files=_env_int("DEEPME_UPLOAD_MAX_FILES", 20),
            upload_max_bytes=_env_int("DEEPME_UPLOAD_MAX_BYTES", 50 * 1024 * 1024),
            upload_max_file_bytes=_env_int(
                "DEEPME_UPLOAD_MAX_FILE_BYTES",
                20 * 1024 * 1024,
            ),
            pdf_max_pages=_env_int("DEEPME_PDF_MAX_PAGES", 200),
            parse_timeout_seconds=_env_int("DEEPME_PARSE_TIMEOUT_SECONDS", 60),
            normalized_max_chars=_env_int(
                "DEEPME_NORMALIZED_MAX_CHARS",
                2_000_000,
            ),
            worker_poll_seconds=_env_int("DEEPME_WORKER_POLL_SECONDS", 2),
            public_sync_seconds=_env_int("DEEPME_PUBLIC_SYNC_SECONDS", 24 * 3600),
            retrieval_mode=retrieval_mode,
            rerank_enabled=_env_bool("DEEPME_RERANK_ENABLED", True),
            chat_rate_limit_per_minute=_env_int(
                "DEEPME_CHAT_RATE_LIMIT_PER_MINUTE",
                30,
            ),
            upload_rate_limit_per_hour=_env_int(
                "DEEPME_UPLOAD_RATE_LIMIT_PER_HOUR",
                20,
            ),
        )

    @property
    def public_releases_dir(self) -> Path:
        return self.runtime_dir / "public" / "releases"

    @property
    def public_staging_dir(self) -> Path:
        return self.runtime_dir / "public" / "staging"

    @property
    def temporary_dir(self) -> Path:
        return self.runtime_dir / "temporary"
