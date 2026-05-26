from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from src.wiki.ingest_analyzer import WikiDraft, _load_llm_service, merge_draft


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", " ", title.lower()).strip()


def word_jaccard_similarity(s1: str, s2: str) -> float:
    w1 = set(_normalize_title(s1).split())
    w2 = set(_normalize_title(s2).split())
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


def Levenshtein_distance(s1: str, s2: str) -> int:
    s1 = _normalize_title(s1)
    s2 = _normalize_title(s2)
    if len(s1) < len(s2):
        return Levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def heuristic_clustering(drafts: list[WikiDraft]) -> dict[str, str]:
    """
    Heuristically maps each candidate slug to a target slug.
    Fallback when LLM is unavailable.
    """
    slug_map: dict[str, str] = {}
    sorted_drafts = sorted(drafts, key=lambda d: len(d.title))
    merge_count = 0

    for i, draft in enumerate(sorted_drafts):
        if draft.slug in slug_map:
            continue
        # Set self as canonical initially
        slug_map[draft.slug] = draft.slug

        for j in range(i + 1, len(sorted_drafts)):
            other = sorted_drafts[j]
            if other.slug in slug_map:
                continue
            if other.page_type != draft.page_type:
                continue

            # Exact slug or title match
            if draft.slug == other.slug or _normalize_title(draft.title) == _normalize_title(other.title):
                slug_map[other.slug] = draft.slug
                merge_count += 1
                continue

            # High Levenshtein ratio or word jaccard
            dist = Levenshtein_distance(draft.title, other.title)
            max_len = max(len(draft.title), len(other.title))
            ratio = 1.0 - (dist / max_len) if max_len > 0 else 0.0

            jaccard = word_jaccard_similarity(draft.title, other.title)

            # High confidence threshold for automatic merge
            if ratio >= 0.78 or jaccard >= 0.75:
                slug_map[other.slug] = draft.slug
                merge_count += 1

    if merge_count > 0:
        print(f"    [merger/heuristic] merged {merge_count} pairs by title similarity", flush=True)
    return slug_map


def llm_clustering(drafts: list[WikiDraft]) -> dict[str, str]:
    """
    Sends candidates to LLM to cluster duplicates.
    Returns a mapping of {slug -> canonical_slug}.
    """
    if not drafts:
        return {}

    llm_service = _load_llm_service()
    if llm_service is None:
        print("    [merger/llm] LLM unavailable, falling back to heuristic clustering", flush=True)
        return heuristic_clustering(drafts)

    # Group by page_type to simplify context
    by_type: dict[str, list[WikiDraft]] = {}
    for d in drafts:
        by_type.setdefault(d.page_type, []).append(d)

    slug_map: dict[str, str] = {}

    import yaml
    prompt_config_path = Path("config/wiki_prompts.yaml")
    if prompt_config_path.exists():
        with open(prompt_config_path, "r", encoding="utf-8") as f:
            prompts = yaml.safe_load(f)
            system_prompt = prompts.get("merger", {}).get("system_prompt", "")
    else:
        system_prompt = ""

    if not system_prompt:
        print("Warning: config/wiki_prompts.yaml not found or empty, using empty system prompt", flush=True)

    for page_type, type_drafts in by_type.items():
        if page_type in ("source", "query", "policy"):
            # These page types generally don't get merged
            for d in type_drafts:
                slug_map[d.slug] = d.slug
            continue

        print(f"    [merger/llm] clustering {len(type_drafts)} {page_type} candidates ...", flush=True)
        t0 = time.time()

        # Format input for LLM
        items_payload = [
            {"slug": d.slug, "title": d.title, "summary": d.summary}
            for d in type_drafts
        ]

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Reconcile these {page_type} candidates:\n\n{json.dumps(items_payload, indent=2, ensure_ascii=False)}"
            }
        ]

        try:
            response = llm_service.chat(messages)
            content = (response.choices[0].message.content or "").strip()
            # Clean markdown code fences if present
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            
            groups = json.loads(content)
            merged_count = 0
            if isinstance(groups, list):
                for group in groups:
                    canonical_slug = group.get("canonical_slug")
                    canonical_title = group.get("canonical_title")
                    slugs = group.get("slugs") or []
                    if canonical_slug and slugs:
                        # Map all members of this group to the canonical slug
                        for s in slugs:
                            slug_map[s] = canonical_slug
                        if len(slugs) > 1:
                            merged_count += len(slugs) - 1
            elapsed = time.time() - t0
            print(f"    [merger/llm] {page_type}: {len(type_drafts)} → {len(type_drafts) - merged_count} pages ({merged_count} merged) [{elapsed:.1f}s]", flush=True)
        except Exception as e:
            elapsed = time.time() - t0
            print(f"    [merger/llm] LLM clustering failed for {page_type} [{elapsed:.1f}s]: {e}. Falling back to heuristics.", flush=True)
            fallback_map = heuristic_clustering(type_drafts)
            slug_map.update(fallback_map)

    # Fill in any missing mappings with self-mapping
    for d in drafts:
        if d.slug not in slug_map:
            slug_map[d.slug] = d.slug

    return slug_map


def merge_candidate_drafts(drafts: list[WikiDraft], use_llm: bool = True) -> list[WikiDraft]:
    """
    Main entry point: clusters and merges a list of WikiDrafts.
    """
    if not drafts:
        return []

    print(f"    [merger] input: {len(drafts)} candidates (llm={'on' if use_llm else 'off'})", flush=True)
    t0 = time.time()

    # Get clustering mapping
    if use_llm:
        slug_map = llm_clustering(drafts)
    else:
        slug_map = heuristic_clustering(drafts)

    # To ensure consistent canonical details, we choose the first draft for each canonical target
    # as the baseline, and then merge the others into it.
    canonical_bases: dict[str, WikiDraft] = {}
    slug_to_canonical_title: dict[str, str] = {}

    # Determine canonical details (title and slug)
    for d in drafts:
        canonical_slug = slug_map.get(d.slug, d.slug)
        # Find if we already have a canonical representative or if this is it
        if canonical_slug not in canonical_bases:
            # Create a clean copy of draft as the base
            canonical_bases[canonical_slug] = WikiDraft(
                page_type=d.page_type,
                slug=canonical_slug,
                title=d.title, # will refine to longest title
                summary=d.summary,
                tags=list(d.tags),
                sources=list(d.sources),
                related=list(d.related),
                sections=list(d.sections),
                aliases=list(d.aliases),
            )
            slug_to_canonical_title[canonical_slug] = d.title
        else:
            # Refine title to be the longest/most complete title in the group
            base = canonical_bases[canonical_slug]
            if len(d.title) > len(base.title):
                base.title = d.title
                slug_to_canonical_title[canonical_slug] = d.title

    # Merge all drafts into their canonical bases
    for d in drafts:
        canonical_slug = slug_map.get(d.slug, d.slug)
        base = canonical_bases[canonical_slug]
        
        # If this is not the base itself, merge it in
        if d is not base:
            # If the draft slug is different, its title acts as an alias
            if d.title != base.title and d.title not in base.aliases:
                base.aliases.append(d.title)
            if d.slug != base.slug and d.slug not in base.aliases:
                base.aliases.append(d.slug)
                
            canonical_bases[canonical_slug] = merge_draft(base, d)

    result = list(canonical_bases.values())
    elapsed = time.time() - t0
    print(f"    [merger] output: {len(result)} pages ({len(drafts) - len(result)} merged) [{elapsed:.1f}s]", flush=True)
    return result
