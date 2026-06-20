from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.knowledge.card_store import CardStore, DATA_DIR
from src.knowledge.models import KnowledgeCard


_PAGE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_TYPE_PAGES = {
    "decision": ("decisions", "Decisions"),
    "pattern": ("patterns", "Patterns"),
    "lesson": ("lessons", "Lessons"),
    "concept": ("concepts", "Concepts"),
    "entity": ("entities", "Entities"),
}


@dataclass
class RepoWikiPage:
    slug: str
    title: str
    content: str
    card_slugs: list[str]
    path: str

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "content": self.content,
            "card_slugs": list(self.card_slugs),
            "path": self.path,
        }


class RepoWikiBuilder:
    def __init__(self, data_dir: str | Path | None = None, store: CardStore | None = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.store = store or CardStore(self.data_dir)
        self.repowiki_dir = self.data_dir / "knowledge" / "repowiki"

    def rebuild(self) -> dict:
        pages = self._build_pages(self.store.list_cards())
        self.repowiki_dir.mkdir(parents=True, exist_ok=True)

        existing = {path.stem for path in self.repowiki_dir.glob("*.md")}
        next_slugs = {page.slug for page in pages}
        for stale_slug in existing - next_slugs:
            (self.repowiki_dir / f"{stale_slug}.md").unlink(missing_ok=True)

        for page in pages:
            (self.repowiki_dir / f"{page.slug}.md").write_text(page.content, encoding="utf-8")
        return {"pages": [page.slug for page in pages], "page_count": len(pages)}

    def list_pages(self) -> list[RepoWikiPage]:
        if not self.repowiki_dir.exists():
            return []
        pages = []
        for path in sorted(self.repowiki_dir.glob("*.md")):
            page = self.load_page(path.stem)
            pages.append(page)
        return pages

    def load_page(self, slug: str) -> RepoWikiPage:
        self._validate_slug(slug)
        path = self.repowiki_dir / f"{slug}.md"
        if not path.exists():
            raise FileNotFoundError(path)
        content = path.read_text(encoding="utf-8")
        title = self._extract_title(content) or slug.replace("-", " ").title()
        card_slugs = re.findall(r"Card:\s+`([^`]+)`", content)
        return RepoWikiPage(
            slug=slug,
            title=title,
            content=content,
            card_slugs=card_slugs,
            path=f"knowledge/repowiki/{slug}.md",
        )

    def _build_pages(self, cards: list[KnowledgeCard]) -> list[RepoWikiPage]:
        grouped: dict[str, list[KnowledgeCard]] = {}
        for card in cards:
            page_slug, _ = _TYPE_PAGES.get(card.type, ("concepts", "Concepts"))
            grouped.setdefault(page_slug, []).append(card)

        pages: list[RepoWikiPage] = []
        for page_slug in [value[0] for value in _TYPE_PAGES.values()]:
            cards_for_page = sorted(grouped.get(page_slug, []), key=lambda card: (card.title.lower(), card.slug))
            if not cards_for_page:
                continue
            title = next(title for slug, title in _TYPE_PAGES.values() if slug == page_slug)
            content = self._render_page(title, cards_for_page)
            pages.append(
                RepoWikiPage(
                    slug=page_slug,
                    title=title,
                    content=content,
                    card_slugs=[card.slug for card in cards_for_page],
                    path=f"knowledge/repowiki/{page_slug}.md",
                )
            )
        return pages

    def _render_page(self, title: str, cards: list[KnowledgeCard]) -> str:
        lines = [
            f"# {title}",
            "",
            "Generated from Knowledge Cards. Edit Cards, not this page.",
            "",
        ]
        for card in cards:
            lines.extend(
                [
                    f"## {card.title}",
                    "",
                    f"Card: `{card.slug}`",
                    "",
                    card.definition,
                    "",
                ]
            )
            if card.key_facts:
                lines.append("Key facts:")
                for fact in card.key_facts:
                    lines.append(f"- {fact}")
                lines.append("")
            if card.sources:
                lines.append("Sources:")
                for source in card.sources:
                    lines.append(f"- `{source.path}`: {source.evidence}")
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _extract_title(self, content: str) -> str | None:
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return None

    def _validate_slug(self, slug: str) -> None:
        if not _PAGE_SLUG_RE.match(slug):
            raise ValueError(f"Invalid RepoWiki page slug: {slug}")
