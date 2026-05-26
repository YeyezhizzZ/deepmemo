"""
Wiki Ingest Pipeline - 两阶段处理
参考 reference/llm_wiki/llm_wiki 的实现

Step 1: Analysis - LLM分析源文件，提取实体、概念、论点
Step 2: Generation - LLM生成wiki页面（FILE blocks）
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from src.wiki.frontmatter import parse_markdown_frontmatter, read_markdown_page
from src.wiki.path_utils import normalize_rel_path
from src.wiki.ingest_analyzer import WikiDraft, WikiSection, normalize_draft, merge_draft, _slugify, _load_llm_service
from src.wiki.ingest_writer import _render_page
from src.wiki.link_resolver import resolve_draft_links, scan_existing_wiki_pages
from src.wiki.text_utils import normalize_lookup as _normalize_lookup


@dataclass(slots=True)
class ParsedFileBlock:
    """一个FILE block"""
    path: str
    content: str


@dataclass(slots=True)
class ParseResult:
    """解析结果"""
    blocks: list[ParsedFileBlock]
    warnings: list[str]


# FILE block 解析正则
OPENER_LINE = re.compile(r'^---\s*FILE:\s*(.+?)\s*---\s*$', re.IGNORECASE)
CLOSER_LINE = re.compile(r'^---\s*END\s+FILE\s*---\s*$', re.IGNORECASE)
FENCE_LINE = re.compile(r'^\s{0,3}(```+|~~~+)')


def is_safe_ingest_path(p: str) -> bool:
    """
    检查路径是否安全（防止路径遍历攻击）
    只允许 wiki/ 下的路径
    """
    if not isinstance(p, str) or not p.strip():
        return False
    # 拒绝控制字符
    if re.search(r'[\x00-\x1f]', p):
        return False
    # 拒绝绝对路径
    if p.startswith('/') or p.startswith('\\'):
        return False
    # 规范化
    normalized = p.replace('\\', '/')
    # 拒绝 .. 路径
    segments = normalized.split('/')
    if '..' in segments:
        return False
    # 必须在 wiki/ 下
    if not normalized.startswith('wiki/'):
        return False
    return True


def parse_file_blocks(text: str) -> ParseResult:
    """
    解析LLM输出的FILE blocks
    格式: ---FILE: wiki/path/to/page.md--- ... ---END FILE---
    """
    # 规范化换行符
    normalized = text.replace('\r\n', '\n')
    lines = normalized.split('\n')

    blocks: list[ParsedFileBlock] = []
    warnings: list[str] = []

    i = 0
    while i < len(lines):
        opener_match = OPENER_LINE.match(lines[i])
        if not opener_match:
            i += 1
            continue

        path = opener_match.group(1).strip()
        i += 1  # consume opener

        content_lines: list[str] = []
        fence_marker: str | None = None
        fence_len = 0
        closed = False

        while i < len(lines):
            line = lines[i]

            # 检查代码围栏状态
            fence_match = FENCE_LINE.match(line)
            if fence_match:
                run = fence_match.group(1)
                char = run[0]
                length = len(run)
                if fence_marker is None:
                    fence_marker = char
                    fence_len = length
                elif char == fence_marker and length >= fence_len:
                    fence_marker = None
                    fence_len = 0
                content_lines.append(line)
                i += 1
                continue

            # 在代码围栏外才检查结束标记
            if fence_marker is None and CLOSER_LINE.match(line):
                closed = True
                i += 1
                break

            content_lines.append(line)
            i += 1

        if not closed:
            path_label = path or "(unnamed)"
            msg = f'FILE block "{path_label}" was not closed before end of stream — likely truncation. Block dropped.'
            warnings.append(msg)
            continue

        if not path:
            msg = 'FILE block with empty path skipped.'
            warnings.append(msg)
            continue

        if not is_safe_ingest_path(path):
            msg = f'FILE block with unsafe path "{path}" rejected (must be under wiki/).'
            warnings.append(msg)
            continue

        blocks.append(ParsedFileBlock(path=path, content='\n'.join(content_lines)))

    return ParseResult(blocks=blocks, warnings=warnings)


def build_analysis_prompt(
    purpose: str,
    index: str,
    source_content: str = "",
    ingest_rules: str = "",
    citation_rules: str = "",
    maintenance_rules: str = "",
) -> str:
    """
    Step 1 prompt: 分析源文件，提取关键信息
    参考 reference/llm_wiki/llm_wiki/src/lib/ingest.ts 的 buildAnalysisPrompt
    """
    return "\n".join(filter(None, [
        "You are an expert research analyst. Read the source document and produce a structured analysis.",
        "Do not output chain-of-thought, hidden reasoning, or a thinking transcript. Reason internally and write only the concise final analysis.",
        "",
        "Your analysis should cover:",
        "",
        "## Key Entities",
        "List people, organizations, products, datasets, tools mentioned. For each:",
        "- Name and type",
        "- Role in the source (central vs. peripheral)",
        "- Whether it likely already exists in the wiki (check the index)",
        "",
        "## Key Concepts",
        "List theories, methods, techniques, phenomena. For each:",
        "- Name and brief definition",
        "- Why it matters in this source",
        "- Whether it likely already exists in the wiki",
        "",
        "## Main Arguments & Findings",
        "- What are the core claims or results?",
        "- What evidence supports them?",
        "- How strong is the evidence?",
        "",
        "## Connections to Existing Wiki",
        "- What existing pages does this source relate to?",
        "- Does it strengthen, challenge, or extend existing knowledge?",
        "",
        "## Contradictions & Tensions",
        "- Does anything in this source conflict with existing wiki content?",
        "- Are there internal tensions or caveats?",
        "",
        "## Recommendations",
        "- What wiki pages should be created or updated?",
        "- What should be emphasized vs. de-emphasized?",
        "- Any open questions worth flagging for the user?",
        "",
        "Be thorough but concise. Focus on what's genuinely important.",
        "",
        purpose and f"## Wiki Purpose (for context)\n{purpose}",
        ingest_rules and f"## Ingest Rules\n{ingest_rules}",
        citation_rules and f"## Citation Rules\n{citation_rules}",
        maintenance_rules and f"## Maintenance Rules\n{maintenance_rules}",
        index and f"## Current Wiki Index (for checking existing content)\n{index}",
    ]))


def build_generation_prompt(
    schema: str,
    purpose: str,
    index: str,
    source_file_name: str,
    overview: str = "",
    source_content: str = "",
    ingest_rules: str = "",
    citation_rules: str = "",
    maintenance_rules: str = "",
) -> str:
    """
    Step 2 prompt: 生成wiki页面
    参考 reference/llm_wiki/llm_wiki/src/lib/ingest.ts 的 buildGenerationPrompt
    """
    source_base_name = Path(source_file_name).stem

    return "\n".join(filter(None, [
        "You are a wiki maintainer. Based on the analysis provided, generate wiki files.",
        "Do not output chain-of-thought, hidden reasoning, or explanatory preamble. Reason internally and output only the requested FILE blocks.",
        "",
        f"## IMPORTANT: Source File",
        f"The original source file is: **{source_file_name}**",
        "All wiki pages generated from this source MUST include this filename in their frontmatter `sources` field.",
        "",
        "## What to generate",
        "",
        f"1. A source summary page at **wiki/sources/{source_base_name}.md** (MUST use this exact path)",
        "2. Entity pages in wiki/entities/ for key entities identified in the analysis",
        "3. Concept pages in wiki/concepts/ for key concepts identified in the analysis",
        "4. An updated wiki/index.md — add new entries to existing categories, preserve all existing entries",
        "5. A log entry for wiki/log.md (just the new entry to append, format: ## [YYYY-MM-DD] ingest | Title)",
        "6. An updated wiki/overview.md — a high-level summary of what the entire wiki covers",
        "",
        "## Frontmatter Rules (CRITICAL — parser is strict)",
        "",
        "Every page begins with a YAML frontmatter block. Format rules, in order of importance:",
        "",
        '1. The VERY FIRST line of the file MUST be exactly `---` (three hyphens, nothing else).',
        "   Do NOT wrap the file in a ```yaml ... ``` code fence.",
        '2. Each frontmatter line is a `key: value` pair on its own line.',
        '3. The frontmatter ends with another `---` line on its own.',
        '4. The next line after the closing `---` is the start of the page body.',
        '5. Arrays use the standard YAML inline form `[a, b, c]`.',
        "",
        "Required fields and types:",
        "  • type     — one of: source | entity | concept | synthesis | query",
        '  • title    — string (quote it if it contains a colon, e.g. `title: "Foo: Bar"`)',
        "  • created  — date in YYYY-MM-DD form (no quotes)",
        "  • updated  — same as created",
        "  • tags     — array of bare strings: `tags: [microbiology, ai]`",
        "  • related  — array of bare wiki page slugs: `related: [foo, bar-baz]`",
        f'  • sources  — array of source filenames; MUST include "{source_file_name}".',
        "",
        "Concrete example of a complete, parseable page:",
        "",
        "    ---",
        "    type: entity",
        "    title: Example Entity",
        "    created: 2026-04-29",
        "    updated: 2026-04-29",
        "    tags: [example, demo]",
        "    related: [related-slug-1, related-slug-2]",
        f'    sources: ["{source_file_name}"]',
        "    ---",
        "",
        "    # Example Entity",
        "",
        "    Body content goes here. Use [[wikilink]] syntax in the body for cross-references.",
        "",
        "Other rules:",
        "- Use [[wikilink]] syntax in the BODY for cross-references between pages",
        "- Use kebab-case filenames",
        "- Follow the analysis recommendations on what to emphasize",
        "",
        "## Output Format (MUST FOLLOW EXACTLY — this is how the parser reads your response)",
        "",
        "Your ENTIRE response consists of FILE blocks. Nothing else.",
        "",
        "FILE block template:",
        "```",
        "---FILE: wiki/path/to/page.md---",
        "(complete file content with YAML frontmatter)",
        "---END FILE---",
        "```",
        "",
        "## Output Requirements (STRICT — deviations will cause parse failure)",
        "",
        '1. The FIRST character of your response MUST be `-` (the opening of `---FILE:`).',
        '2. DO NOT output any preamble such as "Here are the files:", "Based on the analysis...", or any introductory prose.',
        "3. DO NOT echo or restate the analysis — that was stage 1's job. Your job is to emit FILE blocks.",
        "4. DO NOT output markdown tables, bullet lists, or headings outside of FILE blocks.",
        '5. DO NOT output any trailing commentary after the last `---END FILE---`.',
        "6. Between blocks, use only blank lines — no prose.",
        "",
        'If you start with anything other than `---FILE:`, the entire response will be discarded.',
        "",
        purpose and f"## Wiki Purpose\n{purpose}",
        schema and f"## Wiki Schema\n{schema}",
        ingest_rules and f"## Ingest Rules\n{ingest_rules}",
        citation_rules and f"## Citation Rules\n{citation_rules}",
        maintenance_rules and f"## Maintenance Rules\n{maintenance_rules}",
        index and f"## Current Wiki Index (preserve all existing entries, add new ones)\n{index}",
        overview and f"## Current Overview (update this to reflect the new source)\n{overview}",
    ]))


def run_analysis(
    source_content: str,
    source_file_name: str,
    purpose: str = "",
    index: str = "",
    ingest_rules: str = "",
    citation_rules: str = "",
    maintenance_rules: str = "",
) -> str:
    """
    Step 1: 分析源文件
    返回分析结果文本
    """
    llm_service = _load_llm_service()
    if llm_service is None:
        raise RuntimeError("LLM service is unavailable; install/configure the LLM client before running auto_ingest.")

    prompt = build_analysis_prompt(
        purpose,
        index,
        source_content,
        ingest_rules,
        citation_rules,
        maintenance_rules,
    )

    # 截断过长的内容
    truncated = source_content[:50000] + "\n\n[...truncated...]" if len(source_content) > 50000 else source_content

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Analyze this source document:\n\n**File:** {source_file_name}\n\n---\n\n{truncated}"},
    ]

    response = llm_service.chat(messages)
    return response.choices[0].message.content or ""


def run_generation(
    analysis: str,
    source_content: str,
    source_file_name: str,
    schema: str = "",
    purpose: str = "",
    index: str = "",
    overview: str = "",
    ingest_rules: str = "",
    citation_rules: str = "",
    maintenance_rules: str = "",
) -> str:
    """
    Step 2: 生成wiki页面
    返回包含FILE blocks的文本
    """
    llm_service = _load_llm_service()
    if llm_service is None:
        raise RuntimeError("LLM service is unavailable; install/configure the LLM client before running auto_ingest.")

    prompt = build_generation_prompt(
        schema,
        purpose,
        index,
        source_file_name,
        overview,
        source_content,
        ingest_rules,
        citation_rules,
        maintenance_rules,
    )

    # 截断过长的内容
    truncated = source_content[:50000] + "\n\n[...truncated...]" if len(source_content) > 50000 else source_content

    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": "\n".join([
                f"Source document to process: **{source_file_name}**",
                "",
                "The Stage 1 analysis below is CONTEXT to inform your output. Do NOT echo",
                "its tables, bullet points, or prose. Your output must be FILE",
                "blocks as specified in the system prompt — nothing else.",
                "",
                "## Stage 1 Analysis (context only — do not repeat)",
                "",
                analysis,
                "",
                "## Original Source Content",
                "",
                truncated,
                "",
                "---",
                "",
                f"Now emit the FILE blocks for the wiki files derived from **{source_file_name}**.",
                "Your response MUST begin with `---FILE:` as the very first characters.",
                "No preamble. No analysis prose. Start immediately.",
            ]),
        },
    ]

    response = llm_service.chat(messages)
    return response.choices[0].message.content or ""


@dataclass(slots=True)
class IngestResult:
    """Ingest结果"""
    written_paths: list[str]
    warnings: list[str]
    analysis: str
    generation: str


def _read_policy_file(file_path: Path) -> str:
    """读取policy文件，如果不存在返回空字符串"""
    try:
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""


def parse_markdown_to_draft(content: str, page_path: str) -> WikiDraft:
    """
    Parses a wiki page markdown content (with frontmatter) into a WikiDraft.
    """
    frontmatter, body = parse_markdown_frontmatter(content)
    page_type = str(frontmatter.get("type") or "concept")
    title = str(frontmatter.get("title") or Path(page_path).stem)
    slug = Path(page_path).stem
    tags = list(frontmatter.get("tags") or [])
    sources = list(frontmatter.get("sources") or [])
    related = list(frontmatter.get("related") or [])
    aliases = list(frontmatter.get("aliases") or [])
    
    sections: list[WikiSection] = []
    summary_lines: list[str] = []
    
    current_heading: str | None = None
    current_bullets: list[str] = []
    
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            if current_heading is not None:
                sections.append(WikiSection(heading=current_heading, bullets=list(current_bullets)))
                current_bullets.clear()
            current_heading = stripped[3:].strip()
        elif stripped.startswith("# "):
            continue
        else:
            if current_heading is None:
                if stripped:
                    summary_lines.append(line)
            else:
                if stripped:
                    if stripped.startswith("- "):
                        current_bullets.append(stripped[2:].strip())
                    elif stripped.startswith("* "):
                        current_bullets.append(stripped[2:].strip())
                    else:
                        current_bullets.append(stripped)
                        
    if current_heading is not None:
        sections.append(WikiSection(heading=current_heading, bullets=list(current_bullets)))
        
    summary = ""
    summary_section = None
    for sec in sections:
        if sec.heading.lower() in ("summary", "overview"):
            summary_section = sec
            break
            
    if summary_section:
        summary = "\n".join(summary_section.bullets)
        sections.remove(summary_section)
    else:
        summary = "\n".join(summary_lines).strip()
        
    return WikiDraft(
        page_type=page_type,
        slug=slug,
        title=title,
        summary=summary,
        tags=tags,
        sources=sources,
        related=related,
        sections=sections,
        aliases=aliases,
    )


def auto_ingest(
    source_path: str,
    wiki_dir: Path = Path("data/wiki"),
    purpose: str = "",
    schema: str = "",
    index: str = "",
    overview: str = "",
) -> IngestResult:
    """
    自动ingest流程：读取源文件 → 分析 → 生成 → 合并 → 写入
    """
    t_start = time.time()
    # 读取policy文件（如果未提供）
    policy_dir = Path("data/policy")
    if not purpose:
        purpose = _read_policy_file(policy_dir / "purpose.md")
    if not schema:
        schema = _read_policy_file(policy_dir / "schema.md")
    ingest_rules = _read_policy_file(policy_dir / "ingest-rules.md")
    citation_rules = _read_policy_file(policy_dir / "citation-rules.md")
    maintenance_rules = _read_policy_file(policy_dir / "maintenance-rules.md")

    # 读取源文件
    source_path_obj = Path(source_path)
    if not source_path_obj.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    source_content = source_path_obj.read_text(encoding="utf-8")
    source_file_name = source_path_obj.name

    # Step 1: Analysis
    print(f"[ingest] Step 1/2: Analyzing {source_file_name}...", flush=True)
    t0 = time.time()
    analysis = run_analysis(
        source_content,
        source_file_name,
        purpose,
        index,
        ingest_rules,
        citation_rules,
        maintenance_rules,
    )
    print(f"[ingest] Step 1/2: Analysis completed in {time.time() - t0:.2f}s", flush=True)

    # Step 2: Generation
    print(f"[ingest] Step 2/2: Generating wiki pages...", flush=True)
    t0 = time.time()
    generation = run_generation(
        analysis=analysis,
        source_content=source_content,
        source_file_name=source_file_name,
        schema=schema,
        purpose=purpose,
        index=index,
        overview=overview,
        ingest_rules=ingest_rules,
        citation_rules=citation_rules,
        maintenance_rules=maintenance_rules,
    )
    print(f"[ingest] Step 2/2: Generation completed in {time.time() - t0:.2f}s", flush=True)

    # Step 3: Parse blocks
    print(f"[ingest] Parsing and aligning files...", flush=True)
    parse_result = parse_file_blocks(generation)

    # Scan existing pages to build alignment index
    existing_meta = scan_existing_wiki_pages(wiki_dir, exclude_slugs=set())
    existing_slug_map: dict[str, str] = {}
    for title, slug, aliases in existing_meta:
        existing_slug_map[_normalize_lookup(slug)] = slug
        existing_slug_map[_normalize_lookup(title)] = slug
        for alias in aliases or []:
            existing_slug_map[_normalize_lookup(alias)] = slug

    written_paths: list[str] = []
    processed_drafts: list[WikiDraft] = []
    draft_paths: dict[str, Path] = {}
    merged_count = 0
    created_count = 0

    for block in parse_result.blocks:
        full_path = Path(block.path)
        if not str(full_path).startswith("wiki/"):
            parse_result.warnings.append(f"Skipping block with path outside wiki/: {block.path}")
            continue

        file_path = wiki_dir.parent / block.path
        
        # Log and meta files are written normally
        if block.path.endswith("/log.md") or block.path == "wiki/log.md":
            file_path.parent.mkdir(parents=True, exist_ok=True)
            existing_log = ""
            if file_path.exists():
                existing_log = file_path.read_text(encoding="utf-8")
            content = existing_log.rstrip() + "\n\n" + block.content.strip() if existing_log else block.content
            file_path.write_text(content.strip() + "\n", encoding="utf-8")
            written_paths.append(block.path)
            continue
            
        if block.path.endswith("/index.md") or block.path == "wiki/index.md" or \
           block.path.endswith("/overview.md") or block.path == "wiki/overview.md":
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(block.content, encoding="utf-8")
            written_paths.append(block.path)
            continue

        # Parse generated block as WikiDraft
        new_draft = parse_markdown_to_draft(block.content, block.path)
        
        # Check alignment with existing semantic pages
        aligned_slug = None
        if new_draft.page_type in ("entity", "concept", "synthesis"):
            lookup_slug = _normalize_lookup(new_draft.slug)
            lookup_title = _normalize_lookup(new_draft.title)
            
            if lookup_slug in existing_slug_map:
                aligned_slug = existing_slug_map[lookup_slug]
            elif lookup_title in existing_slug_map:
                aligned_slug = existing_slug_map[lookup_title]

        if aligned_slug:
            folder = {
                "entity": "entities",
                "concept": "concepts",
                "synthesis": "syntheses",
            }.get(new_draft.page_type, "misc")
            
            target_path = wiki_dir / f"{folder}/{aligned_slug}.md"
            
            if target_path.exists():
                try:
                    existing_draft = parse_markdown_to_draft(target_path.read_text(encoding="utf-8"), str(target_path))
                    new_draft.slug = aligned_slug
                    new_draft.title = existing_draft.title
                    
                    merged_draft = merge_draft(existing_draft, new_draft)
                    processed_drafts.append(merged_draft)
                    draft_paths[merged_draft.slug] = target_path
                    merged_count += 1
                    print(f"  Aligned & Merged: {block.path} -> wiki/{folder}/{aligned_slug}.md", flush=True)
                except Exception as e:
                    print(f"  Failed to merge existing page {target_path}: {e}. Overwriting.", flush=True)
                    processed_drafts.append(new_draft)
                    draft_paths[new_draft.slug] = file_path
                    created_count += 1
            else:
                processed_drafts.append(new_draft)
                draft_paths[new_draft.slug] = file_path
                created_count += 1
        else:
            processed_drafts.append(new_draft)
            draft_paths[new_draft.slug] = file_path
            created_count += 1

    # Run link resolver on all processed drafts
    if processed_drafts:
        t0 = time.time()
        resolve_draft_links(processed_drafts, wiki_dir)
        print(f"[ingest] Resolved draft links in {time.time() - t0:.2f}s", flush=True)
        
        for draft in processed_drafts:
            dest_path = draft_paths[draft.slug]
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            rendered_content = _render_page(draft)
            dest_path.write_text(rendered_content, encoding="utf-8")
            
            rel_write_path = "wiki/" + str(dest_path.relative_to(wiki_dir))
            written_paths.append(rel_write_path)
            print(f"  Written: {rel_write_path}", flush=True)

    print(f"[ingest] Incremental ingest completed: {merged_count} merged, {created_count} created in {time.time() - t_start:.2f}s", flush=True)

    return IngestResult(
        written_paths=list(dict.fromkeys(written_paths)),
        warnings=parse_result.warnings,
        analysis=analysis,
        generation=generation,
    )
