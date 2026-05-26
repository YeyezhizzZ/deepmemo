from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.wiki.constants import POLICY_DIR
from src.wiki.path_utils import resolve_policy_path
from src.wiki.storage import read_text


POLICY_FILES = (
    "purpose.md",
    "schema.md",
    "ingest-rules.md",
    "citation-rules.md",
    "maintenance-rules.md",
)


@lru_cache(maxsize=8)
def load_policy_file(filename: str) -> str:
    path = resolve_policy_path(filename)
    if not path.exists():
        return ""
    return read_text(f"policy/{filename}")


def load_policy_bundle() -> dict[str, str]:
    return {filename: load_policy_file(filename) for filename in POLICY_FILES}


def policy_exists() -> bool:
    return POLICY_DIR.exists()

