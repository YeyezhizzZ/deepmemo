from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from src.wiki.frontmatter import parse_markdown_frontmatter
from src.wiki.text_utils import normalize_lookup as _normalize_lookup


WIKILINK_RE = re.compile(r"\[\[([^\]]{1,120})\]\]")
SKIP_META_FILES = {"index.md", "overview.md", "log.md"}


def _page_type_from_path(path: Path, wiki_dir: Path, frontmatter: dict[str, Any]) -> str:
    page_type = str(frontmatter.get("type") or "").strip().lower()
    if page_type:
        return page_type
    try:
        parent = path.relative_to(wiki_dir).parts[0]
    except ValueError:
        return "source"
    return {
        "sources": "source",
        "entities": "entity",
        "concepts": "concept",
        "syntheses": "synthesis",
        "queries": "query",
    }.get(parent, "source")


def _read_page(path: Path, wiki_dir: Path) -> dict[str, Any] | None:
    if not path.is_file() or path.suffix != ".md":
        return None
    raw = path.read_text(encoding="utf-8")
    frontmatter, body = parse_markdown_frontmatter(raw)
    title = str(frontmatter.get("title") or path.stem).strip()
    rel_path = path.relative_to(wiki_dir).as_posix()
    return {
        "path": rel_path,
        "title": title,
        "slug": path.stem,
        "type": _page_type_from_path(path, wiki_dir, frontmatter),
        "aliases": [str(item).strip() for item in frontmatter.get("aliases") or [] if str(item).strip()],
        "sources": [str(item).strip() for item in frontmatter.get("sources") or [] if str(item).strip()],
        "body": body if frontmatter else raw,
    }


def _build_lookup(pages: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for page in pages:
        for value in [
            page["title"],
            page["slug"],
            page["path"],
            page["path"].removesuffix(".md"),
            *page["aliases"],
        ]:
            key = _normalize_lookup(str(value))
            if key:
                lookup.setdefault(key, page["path"])
    return lookup


def _missing_links(pages: list[dict[str, Any]], lookup: dict[str, str]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for page in pages:
        for raw_target in WIKILINK_RE.findall(page["body"]):
            target = raw_target.split("|", 1)[0].strip()
            if not target:
                continue
            if _normalize_lookup(target) not in lookup:
                missing.append({"path": page["path"], "target": target})
    return missing


def _token_set(title: str) -> set[str]:
    normalized = re.sub(r"[^a-zA-Z0-9\s]+", " ", title.lower()).strip()
    return {token for token in normalized.split() if token}


def _duplicate_candidates(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    semantic_pages = [page for page in pages if page["type"] in {"entity", "concept", "synthesis"}]
    candidates: list[dict[str, Any]] = []
    for index, left in enumerate(semantic_pages):
        left_tokens = _token_set(left["title"])
        if not left_tokens:
            continue
        for right in semantic_pages[index + 1 :]:
            if left["type"] != right["type"]:
                continue
            right_tokens = _token_set(right["title"])
            if not right_tokens:
                continue
            overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
            sequence_score = SequenceMatcher(None, left["title"].lower(), right["title"].lower()).ratio()
            if overlap >= 0.75 or sequence_score >= 0.65:
                candidates.append(
                    {
                        "left": left["path"],
                        "right": right["path"],
                        "left_title": left["title"],
                        "right_title": right["title"],
                        "score": round(max(overlap, sequence_score), 3),
                    }
                )
    return sorted(candidates, key=lambda item: (-item["score"], item["left"], item["right"]))


def build_wiki_health_report(wiki_dir: Path = Path("data/wiki")) -> dict[str, Any]:
    pages = []
    if wiki_dir.exists():
        for path in sorted(wiki_dir.rglob("*.md"), key=lambda item: item.relative_to(wiki_dir).as_posix()):
            if path.name in SKIP_META_FILES:
                continue
            page = _read_page(path, wiki_dir)
            if page is not None:
                pages.append(page)

    lookup = _build_lookup(pages)
    dangling = _missing_links(pages, lookup)
    duplicate_candidates_raw = _duplicate_candidates(pages)
    alias_count = sum(len(page["aliases"]) for page in pages)
    source_backed_count = sum(1 for page in pages if page["sources"])

    # Build grouped dangling links
    dangling_by_target = {}
    for item in dangling:
        t = item["target"]
        ref = item["path"]
        if t not in dangling_by_target:
            best_match_slug = None
            best_ratio = 0.0
            norm_target = _normalize_lookup(t)
            for page in pages:
                for val in [page["title"], page["slug"], *page["aliases"]]:
                    ratio = SequenceMatcher(None, norm_target, _normalize_lookup(val)).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match_slug = page["slug"]
            possible_match = best_match_slug if best_ratio >= 0.65 else None
            dangling_by_target[t] = {
                "target": t,
                "referenced_by": [],
                "possible_match": possible_match
            }
        if ref not in dangling_by_target[t]["referenced_by"]:
            dangling_by_target[t]["referenced_by"].append(ref)

    dangling_links = list(dangling_by_target.values())

    # Build design.md style duplicate candidates
    duplicate_candidates = [
        {
            "pair": [Path(c["left"]).stem, Path(c["right"]).stem],
            "similarity": c["score"]
        }
        for c in duplicate_candidates_raw
    ]

    # Calculate orphan pages (pages other than index/overview/log/sources with 0 incoming links)
    incoming_counts = {p["path"]: 0 for p in pages}
    for page in pages:
        for raw_target in WIKILINK_RE.findall(page["body"]):
            target = raw_target.split("|", 1)[0].strip()
            if not target:
                continue
            norm = _normalize_lookup(target)
            if norm in lookup:
                target_path = lookup[norm]
                if target_path in incoming_counts:
                    incoming_counts[target_path] += 1

    orphan_pages = []
    for p in pages:
        if p["type"] != "source" and Path(p["path"]).name not in SKIP_META_FILES:
            if incoming_counts.get(p["path"], 0) == 0:
                orphan_pages.append(p["slug"])

    # Calculate stub pages (non-source pages with minimal content)
    stub_pages = []
    for p in pages:
        if p["type"] == "source" or Path(p["path"]).name in SKIP_META_FILES:
            continue
        body_stripped = p["body"].strip()
        lines = [line.strip() for line in body_stripped.splitlines() if line.strip()]
        non_header_lines = [line for line in lines if not line.startswith("#") and not line.startswith("---")]
        if len(non_header_lines) <= 1 or len(body_stripped) < 60:
            stub_pages.append(p["slug"])

    # Calculate wikilinks stats
    total_wikilinks = 0
    dangling_wikilinks = 0
    for page in pages:
        for raw_target in WIKILINK_RE.findall(page["body"]):
            target = raw_target.split("|", 1)[0].strip()
            if not target:
                continue
            total_wikilinks += 1
            if _normalize_lookup(target) not in lookup:
                dangling_wikilinks += 1

    resolved_wikilinks = total_wikilinks - dangling_wikilinks
    multi_source_pages = sum(1 for p in pages if len(p["sources"]) > 1)

    return {
        # Original format keys for backward compatibility
        "pages": {
            "total": len(pages),
            "by_type": {
                page_type: sum(1 for page in pages if page["type"] == page_type)
                for page_type in sorted({page["type"] for page in pages})
            },
            "with_sources": source_backed_count,
            "alias_count": alias_count,
        },
        "links": {
            "dangling_count": len(dangling),
            "dangling": dangling[:100],
        },
        "duplicates": {
            "candidate_count": len(duplicate_candidates_raw),
            "candidates": duplicate_candidates_raw[:100],
        },
        # Upgraded format keys for design.md spec
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "stats": {
            "total_pages": len(pages),
            "source_backed_pages": source_backed_count,
            "multi_source_pages": multi_source_pages,
            "total_wikilinks": total_wikilinks,
            "resolved_wikilinks": resolved_wikilinks,
            "dangling_wikilinks": dangling_wikilinks,
        },
        "dangling_links": dangling_links,
        "duplicate_candidates": duplicate_candidates,
        "orphan_pages": orphan_pages,
        "stub_pages": stub_pages,
    }
