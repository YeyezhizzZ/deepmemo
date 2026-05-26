from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.wiki.ingest import DEFAULT_RAW_SEED_DIR, DEFAULT_WIKI_DIR, WikiIngestConfig, run_mock_wiki_ingest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate mock wiki pages from mock diary entries.")
    parser.add_argument("--seed-dir", default=str(DEFAULT_RAW_SEED_DIR), help="Input mock diary directory.")
    parser.add_argument("--wiki-dir", default=str(DEFAULT_WIKI_DIR), help="Output wiki directory.")
    parser.add_argument("--no-clean", action="store_true", help="Keep existing output files instead of recreating them.")
    args = parser.parse_args()

    result = run_mock_wiki_ingest(
        WikiIngestConfig(seed_dir=Path(args.seed_dir), wiki_dir=Path(args.wiki_dir), clean=not args.no_clean)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

