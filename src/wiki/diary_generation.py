from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.wiki.ingest import DEFAULT_DIARY_DIR, DEFAULT_INGEST_CACHE, DEFAULT_WIKI_DIR, DiaryWikiIngestConfig, run_diary_wiki_ingest


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile diary markdown files into wiki pages.")
    parser.add_argument("--diary-dir", default=str(DEFAULT_DIARY_DIR), help="Input diary directory.")
    parser.add_argument("--wiki-dir", default=str(DEFAULT_WIKI_DIR), help="Output wiki directory.")
    parser.add_argument("--cache-file", default=str(DEFAULT_INGEST_CACHE), help="Ingest cache manifest path.")
    parser.add_argument("--clean", action="store_true", help="Rebuild wiki directory from scratch.")
    args = parser.parse_args()

    result = run_diary_wiki_ingest(
        DiaryWikiIngestConfig(
            diary_dir=Path(args.diary_dir),
            wiki_dir=Path(args.wiki_dir),
            cache_file=Path(args.cache_file),
            clean=args.clean,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
