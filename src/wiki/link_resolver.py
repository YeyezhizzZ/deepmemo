from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.wiki.frontmatter import read_markdown_page
from src.wiki.ingest_analyzer import WikiDraft, _slugify
from src.wiki.text_utils import normalize_lookup as _normalize_lookup


WIKILINK_RE = re.compile(r"\[\[([^\]]{1,120})\]\]")


class LinkResolutionIndex:
    def __init__(self):
        # Maps normalized string to canonical (title, slug)
        self.lookup: dict[str, tuple[str, str]] = {}
        # Maps slug to canonical (title, slug)
        self.slug_lookup: dict[str, tuple[str, str]] = {}

    def add_page(self, title: str, slug: str, aliases: list[str] = None):
        t_canonical = title.strip()
        s_canonical = slug.strip()
        
        # Add primary title and slug
        self.lookup[_normalize_lookup(t_canonical)] = (t_canonical, s_canonical)
        self.lookup[_normalize_lookup(s_canonical)] = (t_canonical, s_canonical)
        self.slug_lookup[s_canonical] = (t_canonical, s_canonical)
        
        # Add aliases
        if aliases:
            for alias in aliases:
                self.lookup[_normalize_lookup(alias)] = (t_canonical, s_canonical)

    def resolve(self, raw_target: str) -> tuple[str, str] | None:
        """
        Attempts to resolve raw_target to a canonical (title, slug).
        """
        # Split pipe if exists
        target = raw_target.split("|")[0].strip()
        
        lookup_str = _normalize_lookup(target)
        if not lookup_str:
            return None
            
        # 1. Direct match
        if lookup_str in self.lookup:
            return self.lookup[lookup_str]
            
        # 2. Check if slug match
        slugified = _slugify(target, "")
        if slugified and slugified in self.slug_lookup:
            return self.slug_lookup[slugified]
            
        # 3. Fuzzy match: check substring matches with ratio constraint
        # Only match if lookup_str is significant (>= 8 chars) and length ratio >= 0.5
        if len(lookup_str) >= 8:
            best_match = None
            best_ratio = 0.0
            for key, val in self.lookup.items():
                if lookup_str in key or key in lookup_str:
                    ratio = min(len(lookup_str), len(key)) / max(len(lookup_str), len(key))
                    if ratio >= 0.5 and ratio > best_ratio:
                        best_match = val
                        best_ratio = ratio
            if best_match:
                return best_match
                    
        return None


def scan_existing_wiki_pages(wiki_dir: Path, exclude_slugs: set[str]) -> list[tuple[str, str, list[str]]]:
    """
    Scans existing wiki/ directory to extract metadata for building resolution index.
    """
    pages_meta: list[tuple[str, str, list[str]]] = []
    if not wiki_dir.exists():
        return pages_meta
        
    for path in wiki_dir.rglob("*.md"):
        if not path.is_file():
            continue
        # Skip index, overview, log
        if path.name in ("index.md", "overview.md", "log.md"):
            continue
            
        slug = path.stem
        if slug in exclude_slugs:
            continue
            
        try:
            page, _ = read_markdown_page(path)
            if page:
                pages_meta.append((page.title, slug, page.aliases))
        except Exception:
            pass
            
    return pages_meta


def resolve_text_links(text: str, index: LinkResolutionIndex) -> tuple[str, int, int]:
    """
    Replaces all [[wikilinks]] in text based on index.
    Unresolved links are preserved as-is (not downgraded to plain text).
    Returns (resolved_text, resolved_count, unresolved_count).
    """
    resolved_count = 0
    unresolved_count = 0

    def replace_match(match: re.Match) -> str:
        nonlocal resolved_count, unresolved_count
        raw_content = match.group(1)
        
        # Parse potential pipe format [[Target|Display]]
        parts = raw_content.split("|", 1)
        target = parts[0].strip()
        display = parts[1].strip() if len(parts) > 1 else target
        
        resolved = index.resolve(target)
        if resolved:
            resolved_count += 1
            canonical_title, canonical_slug = resolved
            if len(parts) > 1:
                return f"[[{canonical_title}|{display}]]"
            else:
                return f"[[{canonical_title}]]"
        else:
            # Preserve unresolved link as-is — health report will flag it
            unresolved_count += 1
            return match.group(0)

    result = WIKILINK_RE.sub(replace_match, text)
    return result, resolved_count, unresolved_count


def resolve_draft_links(drafts: list[WikiDraft], wiki_dir: Path) -> list[WikiDraft]:
    """
    Resolves and rewrites wikilinks and related links for a list of WikiDrafts.
    """
    import time
    t0 = time.time()

    # 1. Build global index
    index = LinkResolutionIndex()
    
    # Add drafts in the current batch
    draft_slugs = {d.slug for d in drafts}
    for d in drafts:
        index.add_page(d.title, d.slug, d.aliases)
        
    # Add existing pages on disk that are not being overwritten
    existing_meta = scan_existing_wiki_pages(wiki_dir, exclude_slugs=draft_slugs)
    for title, slug, aliases in existing_meta:
        index.add_page(title, slug, aliases)

    total_resolved = 0
    total_unresolved = 0
        
    # 2. Rewrite drafts
    for d in drafts:
        # Rewrite summary
        if d.summary:
            d.summary, r, u = resolve_text_links(d.summary, index)
            total_resolved += r
            total_unresolved += u
            
        # Rewrite sections
        for section in d.sections:
            if section.callout:
                section.callout, r, u = resolve_text_links(section.callout, index)
                total_resolved += r
                total_unresolved += u
            new_bullets: list[str] = []
            for bullet in section.bullets:
                resolved_bullet, r, u = resolve_text_links(bullet, index)
                new_bullets.append(resolved_bullet)
                total_resolved += r
                total_unresolved += u
            section.bullets = new_bullets
            
        # Rewrite related slugs
        new_related: list[str] = []
        for ref in d.related:
            resolved = index.resolve(ref)
            if resolved:
                _, canonical_slug = resolved
                if canonical_slug != d.slug and canonical_slug not in new_related:
                    new_related.append(canonical_slug)
        d.related = new_related

    elapsed = time.time() - t0
    total_links = total_resolved + total_unresolved
    print(f"  [link_resolver] {total_links} wikilinks: {total_resolved} resolved, {total_unresolved} unresolved (index: {len(index.lookup)} entries) [{elapsed:.1f}s]", flush=True)
        
    return drafts
