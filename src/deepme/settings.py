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
        )

    @property
    def public_releases_dir(self) -> Path:
        return self.runtime_dir / "public" / "releases"

    @property
    def public_staging_dir(self) -> Path:
        return self.runtime_dir / "public" / "staging"
