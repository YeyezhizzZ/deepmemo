from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from src.wiki.constants import WIKI_PAGE_STATUSES, WIKI_PAGE_TYPES


@dataclass(slots=True)
class FrontmatterPage:
    title: str
    type: str
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    last_updated: str | None = None
    status: str = "draft"
    aliases: list[str] = field(default_factory=list)
    owner: str | None = None
    confidence: float | None = None
    related: list[str] = field(default_factory=list)


def parse_markdown_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    text = content.lstrip("\ufeff")
    if not text.startswith("---\n"):
        return {}, content

    end_marker = "\n---\n"
    end_index = text.find(end_marker, 4)
    if end_index == -1:
        return {}, content

    header = text[4:end_index]
    rest = text[end_index + len(end_marker) :]
    try:
        data = yaml.safe_load(header) or {}
        if not isinstance(data, dict):
            return {}, content
        return data, rest
    except yaml.YAMLError:
        return {}, content


def serialize_frontmatter(data: dict[str, Any]) -> str:
    return "---\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip() + "\n---\n"


def split_markdown(content: str) -> tuple[dict[str, Any], str]:
    return parse_markdown_frontmatter(content)


def read_markdown_page(path: Path) -> tuple[FrontmatterPage | None, str]:
    if not path.is_file():
        return None, ""

    raw = path.read_text(encoding="utf-8")
    frontmatter, body = parse_markdown_frontmatter(raw)
    title = str(frontmatter.get("title") or path.stem).strip()
    page_type = str(frontmatter.get("type") or "source").strip()
    if page_type not in WIKI_PAGE_TYPES:
        page_type = "source"
    status = str(frontmatter.get("status") or "draft").strip()
    if status not in WIKI_PAGE_STATUSES:
        status = "draft"

    page = FrontmatterPage(
        title=title,
        type=page_type,
        tags=[str(tag) for tag in frontmatter.get("tags") or []],
        sources=[str(src) for src in frontmatter.get("sources") or []],
        last_updated=str(frontmatter.get("last_updated") or ""),
        status=status,
        aliases=[str(alias) for alias in frontmatter.get("aliases") or []],
        owner=str(frontmatter.get("owner") or "") or None,
        confidence=frontmatter.get("confidence"),
        related=[str(item) for item in frontmatter.get("related") or []],
    )
    return page, body


def build_default_frontmatter(
    *,
    title: str,
    page_type: str,
    status: str = "draft",
    tags: list[str] | None = None,
    sources: list[str] | None = None,
    related: list[str] | None = None,
) -> dict[str, Any]:
    updated = date.today().isoformat()
    return {
        "title": title,
        "type": page_type if page_type in WIKI_PAGE_TYPES else "source",
        "tags": tags or [],
        "sources": sources or [],
        "last_updated": updated,
        "status": status if status in WIKI_PAGE_STATUSES else "draft",
        "related": related or [],
    }


def render_markdown_page(frontmatter: dict[str, Any], body: str) -> str:
    body = body.rstrip()
    if body:
        return f"{serialize_frontmatter(frontmatter)}\n{body}\n"
    return f"{serialize_frontmatter(frontmatter)}\n"
