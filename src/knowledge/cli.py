from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.knowledge.card_compiler import KnowledgeCardCompiler
from src.knowledge.card_store import CardStore, DATA_DIR
from src.knowledge.commit_compiler import CommitKnowledgeCompiler
from src.knowledge.evaluation import KnowledgeEvaluator
from src.knowledge.maintenance import KnowledgeMaintainer
from src.knowledge.repowiki import RepoWikiBuilder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.knowledge.cli")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", default=str(DATA_DIR))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("compile", parents=[common])

    compile_file = subparsers.add_parser("compile-file", parents=[common])
    compile_file.add_argument("path")

    compile_commit = subparsers.add_parser("compile-commit", parents=[common])
    compile_commit.add_argument("commit")
    compile_commit.add_argument("--repo-dir", default=str(Path(__file__).resolve().parents[2]))

    subparsers.add_parser("maintain", parents=[common])
    subparsers.add_parser("validate", parents=[common])
    subparsers.add_parser("migrate-v2", parents=[common])
    evaluate = subparsers.add_parser("eval", parents=[common])
    evaluate.add_argument("--min-health", type=float, default=0.0)
    evaluate.add_argument("--min-citation-coverage", type=float, default=0.0)
    evaluate.add_argument("--min-citation-precision", type=float, default=0.0)
    evaluate.add_argument("--no-record", action="store_true")

    repowiki = subparsers.add_parser("repowiki", parents=[common])
    repowiki_subparsers = repowiki.add_subparsers(dest="repowiki_command", required=True)
    repowiki_subparsers.add_parser("rebuild", parents=[common])

    args = parser.parse_args(argv)
    data_dir = Path(args.data_dir)
    try:
        if args.command == "compile":
            result = KnowledgeCardCompiler(data_dir).compile_all()
            print(json.dumps(result.to_dict(), ensure_ascii=False))
            return 1 if result.errors else 0
        if args.command == "compile-file":
            result = KnowledgeCardCompiler(data_dir).compile_file(args.path)
            print(json.dumps(result.to_dict(), ensure_ascii=False))
            return 1 if result.errors else 0
        if args.command == "compile-commit":
            print(
                json.dumps(
                    CommitKnowledgeCompiler(data_dir=data_dir, repo_dir=args.repo_dir).compile_commit(args.commit).to_dict(),
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "maintain":
            print(json.dumps(KnowledgeMaintainer(data_dir).run_maintenance().to_dict(), ensure_ascii=False))
            return 0
        if args.command == "migrate-v2":
            print(
                json.dumps(
                    CardStore(data_dir).migrate_legacy_cards(),
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "validate":
            errors = validate(data_dir)
            if errors:
                for error in errors:
                    print(f"ERROR: {error}")
                return 1
            print("Knowledge validation passed")
            return 0
        if args.command == "eval":
            report = KnowledgeEvaluator(data_dir).evaluate(
                min_health=args.min_health,
                min_citation_coverage=args.min_citation_coverage,
                min_citation_precision=args.min_citation_precision,
                record=not args.no_record,
            )
            print(json.dumps(report, ensure_ascii=False))
            return 1 if report["threshold_violations"] else 0
        if args.command == "repowiki" and args.repowiki_command == "rebuild":
            print(json.dumps(RepoWikiBuilder(data_dir=data_dir).rebuild(), ensure_ascii=False))
            return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    return 1


def validate(data_dir: str | Path) -> list[str]:
    data_root = Path(data_dir)
    store = CardStore(data_root)
    errors: list[str] = []
    card_slugs: list[str] = []

    if store.wiki_store.wiki_dir.exists():
        for path in sorted(store.wiki_store.wiki_dir.glob("*/*.md")):
            try:
                card = store.wiki_store.parse_card(path.read_text(encoding="utf-8"))
                card_slugs.append(card.slug)
            except Exception as exc:
                errors.append(f"{path.name}: invalid wiki page ({exc})")
                continue
            if card.slug != path.stem:
                errors.append(f"{path.name}: slug does not match filename")
            for source in card.sources:
                if source.path.startswith("git:"):
                    continue
                if source.source_id and source.source_hash:
                    snapshot_path = (
                        data_root
                        / "knowledge"
                        / "sources"
                        / source.source_id
                        / f"{source.source_hash}.md"
                    )
                    if not snapshot_path.is_file():
                        errors.append(
                            f"{path.name}: missing source snapshot "
                            f"{source.source_id}@{source.source_hash}"
                        )
                        continue
                    lines = snapshot_path.read_text(encoding="utf-8").splitlines()
                    if (
                        source.start_line < 1
                        or source.end_line < source.start_line
                        or source.end_line > len(lines)
                    ):
                        errors.append(f"{path.name}: invalid citation line range")
                        continue
                    excerpt = "\n".join(
                        lines[source.start_line - 1 : source.end_line]
                    )
                    if excerpt.strip() != source.evidence.strip():
                        errors.append(f"{path.name}: citation evidence mismatch")
                elif not (data_root / source.path).exists():
                    errors.append(f"{path.name}: broken source path {source.path}")

    if store.index_path.exists():
        try:
            with store.index_path.open("r", encoding="utf-8") as handle:
                index = json.load(handle)
            indexed_slugs = sorted((index.get("cards") or {}).keys())
            if indexed_slugs != sorted(card_slugs):
                errors.append("index drift: index card slugs do not match card files")
        except Exception as exc:
            errors.append(f"index.json: invalid index ({exc})")
    elif card_slugs:
        errors.append("index drift: index.json is missing")

    return errors


if __name__ == "__main__":
    raise SystemExit(main())
