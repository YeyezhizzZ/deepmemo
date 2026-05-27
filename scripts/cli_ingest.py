#!/usr/bin/env python3
"""
手动运行 ingest pipeline
用法: uv run python scripts/cli_ingest.py <source_file>
"""
import sys
from pathlib import Path

# 添加项目根目录到path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.wiki.ingest_pipeline import auto_ingest


def main():
    if len(sys.argv) < 2:
        print("用法: uv run python scripts/cli_ingest.py <source_file>")
        print("示例: uv run python scripts/cli_ingest.py data/diary/2026/425.md")
        sys.exit(1)

    source_path = sys.argv[1]
    source_file = Path(source_path)

    if not source_file.exists():
        print(f"错误: 源文件不存在: {source_path}")
        sys.exit(1)

    print(f"开始ingest: {source_path}")
    print("=" * 60)

    # 读取现有的index和overview
    wiki_dir = Path("data/wiki")
    index_path = wiki_dir / "index.md"
    overview_path = wiki_dir / "overview.md"

    index_content = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    overview_content = overview_path.read_text(encoding="utf-8") if overview_path.exists() else ""

    try:
        result = auto_ingest(
            source_path=source_path,
            wiki_dir=wiki_dir,
            index=index_content,
            overview=overview_content,
        )

        print("\n" + "=" * 60)
        print("Ingest完成!")
        print(f"\n写入的文件 ({len(result.written_paths)}):")
        for path in result.written_paths:
            print(f"  - {path}")

        if result.warnings:
            print(f"\n警告 ({len(result.warnings)}):")
            for warning in result.warnings:
                print(f"  - {warning}")

        print("\n" + "=" * 60)
        print("分析结果预览 (前500字符):")
        print("-" * 60)
        print(result.analysis[:500] + "..." if len(result.analysis) > 500 else result.analysis)

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
