import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DEEPMEMO_DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
WIKI_DIR = DATA_DIR / "wiki"
POLICY_DIR = DATA_DIR / "policy"

WIKI_PAGE_TYPES = ("source", "entity", "concept", "synthesis", "query", "policy")
WIKI_PAGE_STATUSES = ("draft", "active", "archived")
SYNC_STATUSES = ("synced", "dirty", "draft", "processing", "error")
