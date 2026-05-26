#!/usr/bin/env python3
"""
批量ingest所有diary文件 — 调用全量 Rebuild 入口
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.wiki.ingest import DiaryWikiIngestConfig, run_diary_wiki_ingest


def batch_ingest():
    # 禁用输出缓冲
    os.environ['PYTHONUNBUFFERED'] = '1'

    clean = "--clean" in sys.argv

    config = DiaryWikiIngestConfig(clean=clean)
    print(f"[batch_ingest] 开始全量 Rebuild (clean={clean})", flush=True)
    print(f"[batch_ingest] diary_dir={config.diary_dir}, wiki_dir={config.wiki_dir}", flush=True)

    try:
        result = run_diary_wiki_ingest(config)
        print("\n" + "=" * 60)
        print("全量 Rebuild 完成!")
        print(f"  sources:    {result.get('sources', 0)}")
        print(f"  entities:   {result.get('entities', 0)}")
        print(f"  concepts:   {result.get('concepts', 0)}")
        print(f"  syntheses:  {result.get('syntheses', 0)}")
        print(f"  total:      {result.get('total_pages', 0)}")
        print(f"  changed:    {result.get('changed_sources', 0)}")
        print(f"  cached:     {result.get('reused_sources', 0)}")
        print("=" * 60, flush=True)
    except Exception as e:
        print(f"\n✗ Rebuild failed: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    batch_ingest()
