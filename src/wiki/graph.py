from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.wiki.constants import DATA_DIR, WIKI_DIR
from src.wiki.frontmatter import parse_markdown_frontmatter
from src.wiki.path_utils import normalize_rel_path, rel_path
from src.wiki.text_utils import normalize_lookup as _normalize_lookup

DIARY_DIR = DATA_DIR / "diary"
WIKI_GRAPH_EXCLUDED_NAMES = {"index.md", "overview.md", "log.md"}
WIKI_GRAPH_PAGE_TYPES = {"source", "entity", "concept", "synthesis"}

SECTION_WEIGHTS: dict[str, float] = {
    "科研": 1.25,
    "工程博客": 1.1,
    "开发经验": 1.0,
    "自媒体": 0.85,
    "其他": 0.7,
}

DIRECT_LINK_WEIGHT = 3.0
SOURCE_OVERLAP_WEIGHT = 4.0
ADAMIC_ADAR_WEIGHT = 1.5
TYPE_AFFINITY_WEIGHT = 1.0
EDGE_THRESHOLD = 0.12

STOPWORDS = {
    "每日记录",
    "学习记录",
    "科研",
    "工程博客",
    "开发经验",
    "自媒体",
    "其他",
    "我们",
    "这个",
    "那个",
    "一个",
    "一些",
    "可以",
    "如果",
    "因为",
    "所以",
    "通过",
    "以及",
    "但是",
    "还是",
    "就是",
    "很多",
    "非常",
    "需要",
    "模型",
    "系统",
    "技术",
    "方法",
    "问题",
    "能力",
    "流程",
    "数据",
    "内容",
    "实现",
    "工具",
    "知识",
    "项目",
    "文章",
    "版本",
    "输入",
    "输出",
    "处理",
    "进行",
    "使用",
    "整理",
    "理解",
    "总结",
    "学习",
    "研究",
    "日记",
    "记录",
}

ENGLISH_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "can",
    "did",
    "do",
    "does",
    "done",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "me",
    "might",
    "must",
    "my",
    "no",
    "not",
    "of",
    "on",
    "or",
    "our",
    "shall",
    "she",
    "should",
    "so",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "too",
    "up",
    "use",
    "via",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "without",
    "would",
    "you",
    "your",
}

KEEP_SHORT_TOKENS = {
    "ai",
    "api",
    "cli",
    "cv",
    "db",
    "etl",
    "io",
    "kv",
    "llm",
    "llms",
    "mcp",
    "ocr",
    "qa",
    "rag",
    "sql",
    "ui",
    "yaml",
    "yml",
    "json",
}

NOISY_FILELIKE_TOKENS = {
    "agents",
    "agents.md",
    "readme",
    "readme.md",
    "index",
    "overview",
    "log",
    "makefile",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "tsconfig.json",
    "vite.config.ts",
    "vite.config.js",
    "deepmemo",
    "llm_wiki",
    "llm-wiki",
    "llm-wiki-skill",
}

ABSTRACT_HINTS = (
    "agent",
    "llm",
    "mcp",
    "rag",
    "prompt",
    "memory",
    "workflow",
    "wiki",
    "graph",
    "图谱",
    "知识库",
    "上下文",
    "技能",
    "skill",
    "mermaid",
    "ui",
    "card",
    "context",
    "retrieval",
    "memory",
    "agent memory",
    "multi-agent",
)

LINK_RE = re.compile(r"\[([^\]]{1,120})\]\(([^)]+)\)")
WIKILINK_RE = re.compile(r"\[\[([^\]]{1,120})\]\]")
QUOTED_RE = re.compile(r"《([^》]{2,120})》")
EN_TOKEN_RE = re.compile(
    r"(?:[A-Z]{2,}[A-Za-z0-9+._-]*|[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+|[A-Z][A-Za-z0-9+._-]{1,})"
)
ZH_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,8}")
PATH_REF_RE = re.compile(r"(?:data/)?diary/\d{4}\.md")
PUNCT_SPLIT_RE = re.compile(r"[/:：—\-·|,，。；;、\s]+")


def _round_number(value: float, digits: int = 3) -> float:
    factor = 10**digits
    return round(value * factor) / factor


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _sorted_pair_key(a: str, b: str) -> str:
    return f"{a}\t{b}" if a < b else f"{b}\t{a}"


def _slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value.strip().lower()).strip("-")
    return slug or fallback


def _modified_iso(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    except OSError:
        return ""


def _normalize_token(value: str) -> str | None:
    token = value.strip().strip("`'\"“”‘’()[]{}<>《》")
    token = re.sub(r"\s+", " ", token).strip()
    if not token or len(token) < 2:
        return None
    if token.startswith("http://") or token.startswith("https://") or "://" in token:
        return None
    if "/" in token or "\\" in token:
        return None
    lowered = token.lower()
    if lowered in NOISY_FILELIKE_TOKENS:
        return None
    if re.fullmatch(r"[a-z0-9._-]+\.(?:md|markdown|txt|json|ya?ml|csv|tsv|py|toml|ini|ipynb)", lowered):
        return None
    if lowered.endswith(".md") and "." in lowered:
        return None

    if token in STOPWORDS:
        return None
    if lowered in STOPWORDS:
        return None
    if lowered in ENGLISH_STOPWORDS:
        return None
    if lowered.isascii() and len(lowered) <= 3 and lowered not in KEEP_SHORT_TOKENS:
        return None
    if lowered in {"data", "raw", "mock", "diary", "wiki", "reference", "docs", "docx", "src", "app", "frontend", "backend"}:
        return None

    if re.fullmatch(r"\d{1,4}([./-]\d{1,4})*", token):
        return None

    if len(token) > 64:
        return None

    return token


def _split_candidate_text(value: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", value.strip())
    if not cleaned:
        return []

    candidates = [cleaned]
    parts = [part.strip() for part in PUNCT_SPLIT_RE.split(cleaned) if part.strip()]
    candidates.extend(parts)

    if ":" in cleaned and len(cleaned) <= 120:
        left, right = cleaned.split(":", 1)
        candidates.extend([left.strip(), right.strip()])
    if "：" in cleaned and len(cleaned) <= 120:
        left, right = cleaned.split("：", 1)
        candidates.extend([left.strip(), right.strip()])

    return [candidate for candidate in candidates if candidate]


def _extract_terms_from_text(text: str) -> list[tuple[str, float]]:
    candidates: list[tuple[str, float]] = []

    for label, _url in LINK_RE.findall(text):
        for candidate in _split_candidate_text(label):
            candidates.append((candidate, 2.0))

    for link in WIKILINK_RE.findall(text):
        for candidate in _split_candidate_text(link):
            candidates.append((candidate, 2.2))

    for quoted in QUOTED_RE.findall(text):
        for candidate in _split_candidate_text(quoted):
            candidates.append((candidate, 1.6))

    for token in EN_TOKEN_RE.findall(text):
        candidates.append((token, 1.1))

    for token in ZH_TOKEN_RE.findall(text):
        candidates.append((token, 0.9))

    normalized: list[tuple[str, float]] = []
    for candidate, weight in candidates:
        token = _normalize_token(candidate)
        if not token:
            continue
        normalized.append((token, weight))
    return normalized


def _extract_source_paths(text: str) -> list[str]:
    refs = []
    for match in PATH_REF_RE.findall(text):
        normalized = normalize_rel_path(match)
        if normalized:
            refs.append(normalized)
    return list(dict.fromkeys(refs))


def _first_meaningful_line(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
        stripped = stripped.strip()
        if stripped:
            return stripped
    return ""


def _parse_sections(content: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current = {"name": stripped[3:].strip() or "其他", "lines": []}
            sections.append(current)
            continue
        if stripped.startswith("# "):
            continue
        if current is None:
            current = {"name": "其他", "lines": []}
            sections.append(current)
        current["lines"].append(line)

    return sections




def _extract_wikilinks(content: str) -> list[str]:
    return [link.strip() for link in WIKILINK_RE.findall(content)]


@dataclass(slots=True)
class DiaryEntry:
    path: str
    title: str
    content: str
    sections: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    dominant_section: str = "其他"
    tags: list[str] = field(default_factory=list)
    mention_scores: Counter[str] = field(default_factory=Counter)
    mention_examples: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    source_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GraphNode:
    path: str
    title: str
    type: str
    status: str
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    last_updated: str = ""
    summary: str = ""
    body: str = ""
    community_id: str = ""
    incoming: int = 0
    outgoing: int = 0
    degree: float = 0.0
    neighbors: list[str] = field(default_factory=list)
    source_paths: list[str] = field(default_factory=list)
    subtype: str = ""


@dataclass(slots=True)
class WikiPageEntry:
    path: str
    title: str
    type: str
    status: str
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    last_updated: str = ""
    summary: str = ""
    body: str = ""
    links: list[str] = field(default_factory=list)


def _load_diary_entries(base_dir: Path = DIARY_DIR) -> list[DiaryEntry]:
    if not base_dir.exists():
        return []

    entries: list[DiaryEntry] = []
    for file_path in sorted(base_dir.rglob("*.md"), key=lambda path: path.name):
        if not file_path.is_file():
            continue

        raw = file_path.read_text(encoding="utf-8")
        frontmatter, body = parse_markdown_frontmatter(raw)
        if frontmatter:
            content = body
        else:
            content = raw

        title = file_path.stem
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip() or title
                break

        sections = _parse_sections(content)
        summary = _first_meaningful_line([line for section in sections for line in section["lines"]])
        tags = [str(section["name"]).strip() for section in sections if str(section["name"]).strip()]
        dominant_section = "其他"
        section_scores: Counter[str] = Counter()
        mention_scores: Counter[str] = Counter()
        mention_examples: dict[str, list[str]] = defaultdict(list)

        source_refs = _extract_source_paths(content)

        for section in sections:
            section_name = str(section["name"]).strip() or "其他"
            section_weight = SECTION_WEIGHTS.get(section_name, 0.7)
            section_scores[section_name] += 1
            for line in section["lines"]:
                excerpt = line.strip()
                if not excerpt:
                    continue
                line_terms = _extract_terms_from_text(excerpt)
                for term, base_weight in line_terms:
                    mention_scores[term] += base_weight * section_weight
                    if len(mention_examples[term]) < 3:
                        mention_examples[term].append(excerpt)
        if section_scores:
            dominant_section = section_scores.most_common(1)[0][0]

        if not summary:
            summary = title

        entries.append(
            DiaryEntry(
                path=rel_path(file_path),
                title=title,
                content=content,
                sections=sections,
                summary=summary,
                dominant_section=dominant_section,
                tags=tags,
                mention_scores=mention_scores,
                mention_examples=mention_examples,
                source_refs=source_refs,
            )
        )

    return entries


def _infer_graph_type(file_path: Path, frontmatter: dict[str, Any], root_dir: Path = WIKI_DIR) -> str:
    page_type = str(frontmatter.get("type") or "").strip().lower()
    if page_type in WIKI_GRAPH_PAGE_TYPES:
        return page_type

    parts = file_path.relative_to(root_dir).parts
    if len(parts) >= 2:
        parent = parts[0].lower()
        if parent in WIKI_GRAPH_PAGE_TYPES:
            return parent
    return "source"


def _load_wiki_pages(base_dir: Path = WIKI_DIR) -> list[WikiPageEntry]:
    if not base_dir.exists():
        return []

    entries: list[WikiPageEntry] = []
    for file_path in sorted(base_dir.rglob("*.md"), key=lambda path: path.relative_to(base_dir).as_posix()):
        if not file_path.is_file():
            continue

        rel_file = f"wiki/{file_path.relative_to(base_dir).as_posix()}"
        if file_path.name in WIKI_GRAPH_EXCLUDED_NAMES:
            continue

        raw = file_path.read_text(encoding="utf-8")
        frontmatter, body = parse_markdown_frontmatter(raw)
        page_type = _infer_graph_type(file_path, frontmatter, base_dir)
        if page_type not in WIKI_GRAPH_PAGE_TYPES:
            continue

        title = str(frontmatter.get("title") or "").strip()
        if not title:
            title = file_path.stem.replace("-", " ").strip()
        if not title:
            for line in raw.splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    title = stripped[2:].strip()
                    break
        if not title:
            title = file_path.stem

        body_text = body if frontmatter else raw
        body_lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        summary = ""
        for line in body_lines:
            if not line.startswith("#"):
                summary = line
                break
        if not summary:
            summary = title

        tags = [str(tag).strip() for tag in frontmatter.get("tags") or [] if str(tag).strip()]
        sources = [str(src).strip() for src in frontmatter.get("sources") or [] if str(src).strip()]
        related = [str(item).strip() for item in frontmatter.get("related") or [] if str(item).strip()]
        last_updated = str(frontmatter.get("last_updated") or "").strip()
        status = str(frontmatter.get("status") or "draft").strip().lower()
        if status not in {"draft", "active", "archived"}:
            status = "draft"

        entries.append(
            WikiPageEntry(
                path=rel_file,
                title=title,
                type=page_type,
                status=status,
                tags=tags,
                sources=sources,
                related=related,
                last_updated=last_updated,
                summary=summary,
                body=body_text.strip(),
                links=_extract_wikilinks(body_text),
            )
        )

    return entries


def _resolve_wiki_target(raw: str, index: dict[str, str], title_index: dict[str, str], slug_index: dict[str, str]) -> str | None:
    candidate = normalize_rel_path(raw)
    if candidate.startswith("wiki/") and not candidate.endswith(".md"):
        candidate = f"{candidate}.md"
    if candidate in index:
        return index[candidate]
    if candidate in title_index:
        return title_index[candidate]

    lookup = _normalize_lookup(raw)
    if lookup in title_index:
        return title_index[lookup]
    if lookup in slug_index:
        return slug_index[lookup]

    return None


def _type_affinity(node_a: GraphNode, node_b: GraphNode) -> float:
    pair = tuple(sorted((node_a.type, node_b.type)))
    if pair == ("concept", "concept"):
        return 0.95
    if pair == ("entity", "entity"):
        return 0.86
    if pair == ("source", "source"):
        return 0.72 if node_a.subtype == node_b.subtype else 0.64
    if pair == ("concept", "entity"):
        return 0.9
    if pair == ("concept", "source"):
        return 0.78
    if pair == ("entity", "source"):
        return 0.74
    if pair == ("synthesis", "concept"):
        return 0.92
    if pair == ("synthesis", "entity"):
        return 0.88
    if pair == ("synthesis", "source"):
        return 0.8
    if pair == ("synthesis", "synthesis"):
        return 0.9
    return 0.65


def _select_terms(entries: list[DiaryEntry]) -> dict[str, dict[str, Any]]:
    term_sources: dict[str, set[str]] = defaultdict(set)
    term_weight: Counter[str] = Counter()
    term_examples: dict[str, list[str]] = defaultdict(list)

    for entry in entries:
        for term, score in entry.mention_scores.items():
            term_sources[term].add(entry.path)
            term_weight[term] += score
            if len(term_examples[term]) < 5:
                term_examples[term].extend(entry.mention_examples.get(term, [])[:2])

    selected: dict[str, dict[str, Any]] = {}
    for term, sources in term_sources.items():
        weight = term_weight[term]
        doc_freq = len(sources)
        if doc_freq < 2 and weight < 8.0 and not any(hint in term.lower() for hint in ABSTRACT_HINTS):
            continue

        score = weight + doc_freq * 1.5
        selected[term] = {
            "sources": sorted(sources),
            "weight": weight,
            "doc_freq": doc_freq,
            "examples": list(dict.fromkeys(term_examples[term]))[:5],
            "score": score,
        }

    ranked = sorted(selected.items(), key=lambda item: (-item[1]["score"], -item[1]["doc_freq"], item[0]))
    trimmed = ranked[:160]
    return {term: data for term, data in trimmed}


def _term_type(term: str, data: dict[str, Any]) -> str:
    lowered = term.lower()
    if any(hint in lowered for hint in ABSTRACT_HINTS):
        return "concept"
    if data["doc_freq"] >= 5 or data["weight"] >= 18:
        return "concept"
    if len(term) <= 4 and data["doc_freq"] >= 3:
        return "concept"
    return "entity"


def _make_node_id(node_type: str, label: str, fallback: str) -> str:
    return f"{node_type}:{_slugify(label, fallback)}"


def _build_nodes(
    entries: list[DiaryEntry],
    term_data: dict[str, dict[str, Any]],
) -> tuple[dict[str, GraphNode], dict[str, set[str]], dict[str, set[str]], dict[str, dict[str, float]], dict[str, float]]:
    nodes: dict[str, GraphNode] = {}
    neighbors: dict[str, set[str]] = defaultdict(set)
    source_sets: dict[str, set[str]] = defaultdict(set)
    direct_weights: dict[str, dict[str, float]] = defaultdict(dict)
    node_strength: dict[str, float] = defaultdict(float)

    entry_by_path = {entry.path: entry for entry in entries}

    for entry in entries:
        source_id = entry.path
        source_sets[source_id].add(source_id)
        node = GraphNode(
            path=source_id,
            title=entry.title,
            type="source",
            status="active",
            tags=list(dict.fromkeys(entry.tags)),
            sources=[source_id],
            related=[],
            last_updated=_modified_iso(DATA_DIR / normalize_rel_path(source_id)),
            summary=entry.summary,
            body=entry.content.strip(),
            source_paths=[source_id],
            subtype=entry.dominant_section,
        )
        nodes[source_id] = node

    for term, data in term_data.items():
        node_type = _term_type(term, data)
        node_id = _make_node_id(node_type, term, "term")
        node = GraphNode(
            path=node_id,
            title=term,
            type=node_type,
            status="active",
            tags=[node_type, f"df:{data['doc_freq']}"],
            sources=list(data["sources"]),
            related=[],
            summary=f"出现在 {data['doc_freq']} 篇日记中。",
            body="",
            source_paths=list(data["sources"]),
            subtype=node_type,
        )
        nodes[node_id] = node
        source_sets[node_id].update(data["sources"])

    term_to_node_id = {
        term: _make_node_id(_term_type(term, data), term, "term")
        for term, data in term_data.items()
    }

    for entry in entries:
        source_id = entry.path
        source_node = nodes[source_id]
        related_terms = sorted(
            (
                (term, score)
                for term, score in entry.mention_scores.items()
                if term in term_to_node_id
            ),
            key=lambda item: (-item[1], item[0]),
        )[:10]
        for term, score in related_terms:
            target_id = term_to_node_id[term]
            direct_weight = _clamp01(0.2 + min(score / 8.0, 0.8))
            direct_weights[source_id][target_id] = max(direct_weights[source_id].get(target_id, 0.0), direct_weight)
            direct_weights[target_id][source_id] = max(direct_weights[target_id].get(source_id, 0.0), direct_weight)
            neighbors[source_id].add(target_id)
            neighbors[target_id].add(source_id)
            node_strength[source_id] += direct_weight
            node_strength[target_id] += direct_weight

            source_node.related.append(target_id)

    for entry in entries:
        source_id = entry.path
        source_node = nodes[source_id]
        for ref in entry.source_refs:
            if ref not in nodes:
                continue
            weight = 0.95
            direct_weights[source_id][ref] = max(direct_weights[source_id].get(ref, 0.0), weight)
            direct_weights[ref][source_id] = max(direct_weights[ref].get(source_id, 0.0), weight)
            neighbors[source_id].add(ref)
            neighbors[ref].add(source_id)
            node_strength[source_id] += weight
            node_strength[ref] += weight
            if ref not in source_node.related:
                source_node.related.append(ref)

    # source/title based helper links for nodes inside the same diary note
    for entry in entries:
        source_id = entry.path
        top_terms = [term_to_node_id[term] for term in list(entry.mention_scores.keys()) if term in term_to_node_id][:6]
        for index, left in enumerate(top_terms):
            for right in top_terms[index + 1 :]:
                neighbors[left].add(right)
                neighbors[right].add(left)

    return nodes, neighbors, source_sets, direct_weights, node_strength


def _source_overlap(
    left: str,
    right: str,
    nodes: dict[str, GraphNode],
    neighbors: dict[str, set[str]],
    support_sets: dict[str, set[str]],
) -> float:
    left_node = nodes[left]
    right_node = nodes[right]

    if left_node.type == right_node.type == "source":
        shared = len(neighbors.get(left, set()) & neighbors.get(right, set()))
        if shared <= 0:
            return 0.0
        denom = max(1, min(len(neighbors.get(left, set())), len(neighbors.get(right, set()))))
        return shared / denom

    if left_node.type in {"entity", "concept"} and right_node.type in {"entity", "concept"}:
        set_a = support_sets.get(left, set())
        set_b = support_sets.get(right, set())
        if not set_a or not set_b:
            return 0.0
        shared = len(set_a & set_b)
        if shared <= 0:
            return 0.0
        return shared / max(1, len(set_a | set_b))

    source_node, target_node = (left_node, right_node)
    source_id, target_id = left, right
    if left_node.type != "source":
        source_node, target_node = right_node, left_node
        source_id, target_id = right, left

    if source_node.type == "source" and target_node.type in {"entity", "concept"}:
        return 1.0 if source_id in support_sets.get(target_id, set()) else 0.0

    return 0.0


def _adamic_adar(a: str, b: str, neighbors: dict[str, set[str]]) -> float:
    common = neighbors.get(a, set()) & neighbors.get(b, set())
    if not common:
        return 0.0
    score = 0.0
    for neighbor in common:
        degree = len(neighbors.get(neighbor, set()))
        if degree <= 1:
            continue
        score += 1.0 / math.log(degree + 1.0)
    return _clamp01(score / 2.5)



def _compute_pair_metrics(
    nodes: dict[str, GraphNode],
    neighbors: dict[str, set[str]],
    support_sets: dict[str, set[str]],
    direct_weights: dict[str, dict[str, float]],
) -> dict[str, dict[str, Any]]:
    node_ids = sorted(nodes.keys())
    pair_metrics: dict[str, dict[str, Any]] = {}

    for index, left in enumerate(node_ids):
        left_node = nodes[left]
        for right in node_ids[index + 1 :]:
            right_node = nodes[right]
            direct = max(direct_weights.get(left, {}).get(right, 0.0), direct_weights.get(right, {}).get(left, 0.0))
            overlap = _source_overlap(left, right, nodes, neighbors, support_sets)
            adamic = _adamic_adar(left, right, neighbors)
            affinity = _type_affinity(left_node, right_node)

            score = (
                DIRECT_LINK_WEIGHT * direct
                + SOURCE_OVERLAP_WEIGHT * overlap
                + ADAMIC_ADAR_WEIGHT * adamic
                + TYPE_AFFINITY_WEIGHT * affinity
            ) / (DIRECT_LINK_WEIGHT + SOURCE_OVERLAP_WEIGHT + ADAMIC_ADAR_WEIGHT + TYPE_AFFINITY_WEIGHT)

            pair_metrics[_sorted_pair_key(left, right)] = {
                "direct_link": _round_number(direct),
                "source_overlap": _round_number(overlap),
                "adamic_adar": _round_number(adamic),
                "type_affinity": _round_number(affinity),
                "weight": _round_number(_clamp01(score)),
            }

    return pair_metrics


def _build_weighted_graph(node_ids: list[str], pair_metrics: dict[str, dict[str, Any]]) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    adjacency: dict[str, dict[str, float]] = {node_id: {} for node_id in node_ids}
    degrees: dict[str, float] = {node_id: 0.0 for node_id in node_ids}

    for pair_key, metrics in pair_metrics.items():
        left, right = pair_key.split("\t")
        if left not in adjacency or right not in adjacency:
            continue
        weight = metrics["weight"]
        if weight < EDGE_THRESHOLD and metrics["direct_link"] <= 0:
            continue
        adjacency[left][right] = weight
        adjacency[right][left] = weight
        degrees[left] += weight
        degrees[right] += weight

    return adjacency, degrees


def _run_local_move(
    adjacency: dict[str, dict[str, float]],
    degrees: dict[str, float],
) -> tuple[dict[str, str], bool]:
    node_ids = sorted(adjacency.keys())
    communities = {node_id: node_id for node_id in node_ids}
    totals = {node_id: degrees.get(node_id, 0.0) for node_id in node_ids}

    if not node_ids:
        return communities, False

    total_weight = sum(degrees.values())
    if total_weight <= 0:
        return communities, False

    changed = False
    for _ in range(50):
        moved_this_pass = False
        for node_id in node_ids:
            degree = degrees.get(node_id, 0.0)
            current_community = communities[node_id]
            neighbor_communities: dict[str, float] = defaultdict(float)
            for neighbor_id, weight in adjacency[node_id].items():
                neighbor_communities[communities[neighbor_id]] += weight

            totals[current_community] -= degree

            best_community = current_community
            best_gain = 0.0
            for community_id in sorted(neighbor_communities.keys()):
                in_weight = neighbor_communities[community_id]
                gain = in_weight - (totals.get(community_id, 0.0) * degree) / (2 * total_weight)
                if gain > best_gain + 1e-9:
                    best_gain = gain
                    best_community = community_id

            communities[node_id] = best_community
            totals[best_community] = totals.get(best_community, 0.0) + degree
            if best_community != current_community:
                moved_this_pass = True
                changed = True

        if not moved_this_pass:
            break

    return communities, changed


def _aggregate_graph(
    adjacency: dict[str, dict[str, float]],
    degrees: dict[str, float],
    communities: dict[str, str],
) -> tuple[dict[str, dict[str, float]], dict[str, float], dict[str, list[str]]]:
    community_ids = sorted(set(communities.values()))
    aggregated_nodes: dict[str, dict[str, float]] = {community_id: {} for community_id in community_ids}
    aggregated_degrees: dict[str, float] = {community_id: 0.0 for community_id in community_ids}
    members: dict[str, list[str]] = {community_id: [] for community_id in community_ids}

    for node_id, community_id in communities.items():
        members[community_id].append(node_id)

    for left, neighbors in adjacency.items():
        source_community = communities[left]
        for right, weight in neighbors.items():
            if left > right:
                continue
            target_community = communities[right]
            aggregated_nodes[source_community][target_community] = (
                aggregated_nodes[source_community].get(target_community, 0.0) + weight
            )
            if source_community != target_community:
                aggregated_nodes[target_community][source_community] = (
                    aggregated_nodes[target_community].get(source_community, 0.0) + weight
                )

    for community_id, neighbors in aggregated_nodes.items():
        degree = 0.0
        for neighbor_id, weight in neighbors.items():
            degree += weight * 2 if neighbor_id == community_id else weight
        aggregated_degrees[community_id] = degree

    return aggregated_nodes, aggregated_degrees, members


def _run_louvain(node_ids: list[str], pair_metrics: dict[str, dict[str, Any]]) -> dict[str, str]:
    adjacency, degrees = _build_weighted_graph(node_ids, pair_metrics)
    graph_nodes = adjacency
    graph_degrees = degrees
    graph_members = {node_id: [node_id] for node_id in node_ids}

    best_members = graph_members

    while True:
        communities, changed = _run_local_move(graph_nodes, graph_degrees)
        next_nodes, next_degrees, next_members = _aggregate_graph(graph_nodes, graph_degrees, communities)
        best_members = next_members

        if not changed or len(next_nodes) == len(graph_nodes):
            break

        graph_nodes = next_nodes
        graph_degrees = next_degrees

    final_communities: dict[str, str] = {}
    for community_id, members in best_members.items():
        for node_id in members:
            final_communities[node_id] = community_id
    return final_communities


def _build_directed_degree(edges: list[dict[str, Any]]) -> dict[str, float]:
    degree: dict[str, float] = defaultdict(float)
    for edge in edges:
        degree[edge["from"]] += edge.get("weight", 1.0)
        degree[edge["to"]] += edge.get("weight", 1.0)
    return degree


def _choose_community_labels(
    node_ids: list[str],
    community_assignments: dict[str, str],
    nodes: dict[str, GraphNode],
    edges: list[dict[str, Any]],
) -> dict[str, str]:
    groups: dict[str, list[str]] = defaultdict(list)
    directed_degree = _build_directed_degree(edges)

    for node_id in node_ids:
        community_id = community_assignments.get(node_id, node_id)
        groups[community_id].append(node_id)

    labeled: dict[str, str] = {}
    for community_id, members in groups.items():
        members.sort()
        if len(members) == 1:
            labeled[members[0]] = members[0]
            continue

        ranked = sorted(
            members,
            key=lambda node_id: (
                -directed_degree.get(node_id, 0.0),
                nodes[node_id].type != "concept",
                nodes[node_id].type != "entity",
                nodes[node_id].title,
            ),
        )
        label = ranked[0]
        for member in members:
            labeled[member] = label

    return labeled


def _build_insights(
    nodes: dict[str, GraphNode],
    edges: list[dict[str, Any]],
    pair_metrics: dict[str, dict[str, Any]],
    community_assignments: dict[str, str],
    *,
    max_nodes: int = 250,
    max_edges: int = 1000,
) -> dict[str, Any]:
    directed_degree = _build_directed_degree(edges)
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    undirected_pairs: dict[str, dict[str, Any]] = {}

    for edge in edges:
        adjacency.setdefault(edge["from"], set()).add(edge["to"])
        adjacency.setdefault(edge["to"], set()).add(edge["from"])
        pair_key = _sorted_pair_key(edge["from"], edge["to"])
        undirected_pairs.setdefault(
            pair_key,
            {
                "from": pair_key.split("\t")[0],
                "to": pair_key.split("\t")[1],
                "weight": pair_metrics.get(pair_key, {}).get("weight", 0.0),
            },
        )

    isolated_nodes = [
        {
            "id": node_id,
            "label": node.title,
            "degree": _round_number(directed_degree.get(node_id, 0.0)),
            "community": community_assignments.get(node_id),
        }
        for node_id, node in sorted(nodes.items(), key=lambda item: item[0])
        if directed_degree.get(node_id, 0.0) <= 0.6
    ]

    bridge_nodes = []
    community_members: dict[str, list[str]] = defaultdict(list)
    for node_id, community_id in community_assignments.items():
        community_members[community_id].append(node_id)

    for node_id in sorted(nodes.keys()):
        own_community = community_assignments.get(node_id)
        connected_communities = sorted(
            {
                community_assignments.get(neighbor_id)
                for neighbor_id in adjacency.get(node_id, set())
                if community_assignments.get(neighbor_id)
                and community_assignments.get(neighbor_id) != own_community
            }
        )
        if len(connected_communities) >= 2:
            bridge_nodes.append(
                {
                    "id": node_id,
                    "label": nodes[node_id].title,
                    "community": own_community,
                    "connected_communities": connected_communities,
                    "community_count": len(connected_communities),
                }
            )

    sparse_communities = []
    for community_id, members in sorted(community_members.items(), key=lambda item: item[0]):
        if len(members) < 3:
            continue
        member_set = set(members)
        internal_edges = 0
        for pair in undirected_pairs.values():
            if pair["from"] in member_set and pair["to"] in member_set:
                internal_edges += 1
        possible_edges = (len(members) * (len(members) - 1)) / 2
        density = internal_edges / possible_edges if possible_edges else 0.0
        if density < 0.15:
            sparse_communities.append(
                {
                    "id": community_id,
                    "label": nodes[community_id].title if community_id in nodes else community_id,
                    "node_count": len(members),
                    "density": _round_number(density),
                    "members": sorted(members),
                    "internal_edges": internal_edges,
                }
            )

    surprising_connections = [
        {
            "from": pair["from"],
            "to": pair["to"],
            "weight": pair["weight"],
            "from_community": community_assignments.get(pair["from"]),
            "to_community": community_assignments.get(pair["to"]),
        }
        for pair in sorted(
            undirected_pairs.values(),
            key=lambda item: (-item["weight"], item["from"], item["to"]),
        )
        if community_assignments.get(pair["from"]) != community_assignments.get(pair["to"]) and pair["weight"] >= 0.7
    ][:8]

    degraded = len(nodes) > max_nodes or len(edges) > max_edges
    if degraded:
        return {
            "surprising_connections": [],
            "isolated_nodes": isolated_nodes,
            "bridge_nodes": [],
            "sparse_communities": [],
            "meta": {
                "degraded": True,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "max_insight_nodes": max_nodes,
                "max_insight_edges": max_edges,
            },
        }

    return {
        "surprising_connections": surprising_connections,
        "isolated_nodes": isolated_nodes,
        "bridge_nodes": bridge_nodes,
        "sparse_communities": sparse_communities,
        "meta": {
            "degraded": False,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "max_insight_nodes": max_nodes,
            "max_insight_edges": max_edges,
        },
    }


def _source_body(entry: DiaryEntry) -> str:
    return entry.content.strip()


def _entity_body(term: str, data: dict[str, Any], nodes: dict[str, GraphNode]) -> str:
    lines = [f"# {term}", "", "## Summary", f"出现在 {data['doc_freq']} 篇日记中。", ""]
    if data["examples"]:
        lines.extend(["## Evidence"])
        for index, example in enumerate(data["examples"][:5], start=1):
            lines.append(f"- [{index}] {example}")
        lines.append("")
    if data["sources"]:
        lines.extend(["## Sources"])
        for source_path in data["sources"][:8]:
            if source_path in nodes:
                lines.append(f"- [[{source_path}]]")
            else:
                lines.append(f"- {source_path}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _safe_source_dir(base_dir: Path) -> str:
    if not base_dir.exists():
        return rel_path(WIKI_DIR)
    try:
        return rel_path(base_dir)
    except ValueError:
        return base_dir.resolve().as_posix()


def _community_summary(node_ids: list[str], nodes: dict[str, GraphNode]) -> tuple[str, str, list[str], str, int]:
    members = [nodes[node_id] for node_id in node_ids if node_id in nodes]
    if not members:
        return "Community", "", [], "", 0

    ranked = sorted(
        members,
        key=lambda node: (
            -node.degree,
            node.type != "synthesis",
            node.type != "concept",
            node.type != "entity",
            node.title,
        ),
    )
    hub = ranked[0]
    anchor = next((node for node in ranked if node.type in {"synthesis", "concept", "entity"}), hub)
    title = anchor.title
    summary = anchor.summary or hub.summary or f"{len(members)} pages connected by wikilinks and shared sources."
    tags = [tag for tag, _count in Counter(tag for node in members for tag in node.tags if tag).most_common(3)]
    updated_at = max((node.last_updated for node in members if node.last_updated), default="")
    return title, summary, tags, updated_at, len(members)


def build_diary_graph(base_dir: Path = WIKI_DIR) -> dict[str, Any]:
    pages = _load_wiki_pages(base_dir if base_dir.exists() else WIKI_DIR)
    if not pages:
        return {
            "meta": {
                "build_date": datetime.now().isoformat(),
                "source_dir": _safe_source_dir(base_dir),
                "total_nodes": 0,
                "total_edges": 0,
                "total_communities": 0,
                "degraded": False,
                "insights_degraded": False,
            },
            "nodes": [],
            "edges": [],
            "communities": [],
            "insights": {
                "surprising_connections": [],
                "isolated_nodes": [],
                "bridge_nodes": [],
                "sparse_communities": [],
                "meta": {
                    "degraded": False,
                    "node_count": 0,
                    "edge_count": 0,
                    "max_insight_nodes": 250,
                    "max_insight_edges": 1000,
                },
            },
        }

    entries = pages
    nodes: dict[str, GraphNode] = {}
    neighbors: dict[str, set[str]] = defaultdict(set)
    source_sets: dict[str, set[str]] = defaultdict(set)
    direct_weights: dict[str, dict[str, float]] = defaultdict(dict)

    path_index: dict[str, str] = {}
    title_index: dict[str, str] = {}
    slug_index: dict[str, str] = {}

    for entry in entries:
        node = GraphNode(
            path=entry.path,
            title=entry.title,
            type=entry.type,
            status=entry.status,
            tags=list(dict.fromkeys(entry.tags)),
            sources=list(dict.fromkeys(entry.sources)),
            related=[],
            last_updated=entry.last_updated,
            summary=entry.summary,
            body=entry.body,
            source_paths=list(dict.fromkeys(entry.sources)),
            subtype=entry.type,
        )
        nodes[entry.path] = node
        source_sets[entry.path].update(entry.sources)
        path_index[normalize_rel_path(entry.path)] = entry.path
        title_index.setdefault(_normalize_lookup(entry.title), entry.path)
        slug_index.setdefault(_normalize_lookup(Path(entry.path).stem), entry.path)
        slug_index.setdefault(_normalize_lookup(Path(entry.path).with_suffix("").name), entry.path)

    for entry in entries:
        resolved_related: list[str] = []
        for ref in entry.related:
            target = _resolve_wiki_target(ref, path_index, title_index, slug_index)
            if target and target != entry.path:
                resolved_related.append(target)
        for link in entry.links:
            target = _resolve_wiki_target(link, path_index, title_index, slug_index)
            if target and target != entry.path:
                resolved_related.append(target)
                direct_weights[entry.path][target] = 1.0
                direct_weights[target][entry.path] = 1.0
                neighbors[entry.path].add(target)
                neighbors[target].add(entry.path)

        nodes[entry.path].related = sorted(dict.fromkeys(resolved_related))

    node_ids = sorted(nodes.keys())
    pair_metrics = _compute_pair_metrics(nodes, neighbors, source_sets, direct_weights)
    pairwise_edges = [
        {
            "from": left,
            "to": right,
            "weight": metrics["weight"],
        }
        for pair_key, metrics in pair_metrics.items()
        for left, right in [pair_key.split("\t")]
        if metrics["weight"] >= EDGE_THRESHOLD or metrics["direct_link"] > 0
    ]

    clustering_node_ids = [nid for nid in node_ids if nodes[nid].type != "source"]

    if clustering_node_ids:
        clustering_pair_metrics = {
            pair_key: metrics
            for pair_key, metrics in pair_metrics.items()
            for left, right in [pair_key.split("\t")]
            if nodes[left].type != "source"
            and nodes[right].type != "source"
            and (metrics["direct_link"] > 0 or metrics["weight"] >= 0.45)
        }
        louvain_assignments = _run_louvain(clustering_node_ids, clustering_pair_metrics)
        if len(louvain_assignments) != len(clustering_node_ids) or len(set(louvain_assignments.values())) >= len(clustering_node_ids):
            # Fallback connection component clustering on clustering_node_ids
            adjacency_by_type: dict[str, set[str]] = defaultdict(set)
            for pair_key, metrics in pair_metrics.items():
                left, right = pair_key.split("\t")
                if nodes[left].type == "source" or nodes[right].type == "source":
                    continue
                if metrics["weight"] < 0.45:
                    continue
                adjacency_by_type[left].add(right)
                adjacency_by_type[right].add(left)

            visited: set[str] = set()
            components: list[list[str]] = []
            for node_id in clustering_node_ids:
                if node_id in visited:
                    continue
                stack = [node_id]
                component: list[str] = []
                visited.add(node_id)
                while stack:
                    current = stack.pop()
                    component.append(current)
                    for neighbor in adjacency_by_type.get(current, set()):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            stack.append(neighbor)
                components.append(component)

            fallback_assignments: dict[str, str] = {}
            for index, component in enumerate(sorted(components, key=lambda item: (-len(item), item[0])), start=1):
                community_id = f"community-{index}"
                for node_id in component:
                    fallback_assignments[node_id] = community_id
            if not fallback_assignments:
                for index, node_id in enumerate(clustering_node_ids, start=1):
                    fallback_assignments[node_id] = f"community-{index}"
            community_assignments = fallback_assignments
        else:
            clustering_edges = [
                edge for edge in pairwise_edges
                if nodes[edge["from"]].type != "source" and nodes[edge["to"]].type != "source"
            ]
            community_assignments = _choose_community_labels(
                clustering_node_ids,
                louvain_assignments,
                nodes,
                clustering_edges,
            )
    else:
        community_assignments = {}

    # Assign source nodes to the community of their strongest connected semantic neighbor
    for node_id in node_ids:
        if nodes[node_id].type == "source":
            best_neighbor = None
            best_weight = -1.0
            for other_id in clustering_node_ids:
                pair_key = "\t".join(sorted((node_id, other_id)))
                metrics = pair_metrics.get(pair_key)
                if metrics and metrics["weight"] > best_weight:
                    best_weight = metrics["weight"]
                    best_neighbor = other_id
            if best_neighbor and best_neighbor in community_assignments:
                community_assignments[node_id] = community_assignments[best_neighbor]
            else:
                community_assignments[node_id] = "community-sources"

    analyzed_edges: list[dict[str, Any]] = []
    for pair_key, metrics in sorted(pair_metrics.items(), key=lambda item: (-item[1]["weight"], item[0])):
        if metrics["weight"] < EDGE_THRESHOLD and metrics["direct_link"] <= 0:
            continue
        left, right = pair_key.split("\t")
        analyzed_edges.append(
            {
                "from": left,
                "to": right,
                "weight": metrics["weight"],
                "direct_link": metrics["direct_link"],
                "source_overlap": metrics["source_overlap"],
                "adamic_adar": metrics["adamic_adar"],
                "type_affinity": metrics["type_affinity"],
            }
        )

    communities_data: list[dict[str, Any]] = []
    community_groups: dict[str, list[str]] = defaultdict(list)
    for node_id, community_id in community_assignments.items():
        community_groups[community_id].append(node_id)

    for index, (community_id, members) in enumerate(
        sorted(community_groups.items(), key=lambda item: (-len(item[1]), item[0])),
        start=1,
    ):
        title, summary, top_tags, updated_at, node_count = _community_summary(members, nodes)
        hub = sorted(
            members,
            key=lambda node_id: (
                -nodes[node_id].degree,
                nodes[node_id].type != "synthesis",
                nodes[node_id].type != "concept",
                nodes[node_id].type != "entity",
                nodes[node_id].title,
            ),
        )[0]
        internal_edge_count = sum(
            1
            for edge in analyzed_edges
            if edge["from"] in members and edge["to"] in members
        )
        communities_data.append(
            {
                "id": f"community-{index}",
                "title": title,
                "summary": summary,
                "node_paths": sorted(members),
                "hub_path": hub,
                "updated_at": updated_at,
                "top_tags": top_tags,
                "node_count": node_count,
                "edge_count": internal_edge_count,
            }
        )
        for member in members:
            nodes[member].community_id = f"community-{index}"

    analyzed_nodes: list[dict[str, Any]] = []
    for node_id in node_ids:
        node = nodes[node_id]
        node.neighbors = sorted(
            {
                neighbor_id
                for edge in analyzed_edges
                for neighbor_id in ([edge["to"]] if edge["from"] == node_id else [edge["from"]] if edge["to"] == node_id else [])
            }
        )
        node.degree = sum(
            edge["weight"]
            for edge in analyzed_edges
            if node_id == edge["from"] or node_id == edge["to"]
        )
        node.incoming = sum(1 for edge in analyzed_edges if edge["to"] == node_id)
        node.outgoing = sum(1 for edge in analyzed_edges if edge["from"] == node_id)
        node.related = sorted(dict.fromkeys(node.related))[:12]
        analyzed_nodes.append(
            {
                "path": node.path,
                "title": node.title,
                "type": node.type,
                "status": node.status,
                "tags": node.tags,
                "sources": node.sources,
                "related": node.related,
                "last_updated": node.last_updated,
                "summary": node.summary,
                "body": node.body,
                "community_id": node.community_id,
                "incoming": node.incoming,
                "outgoing": node.outgoing,
                "degree": _round_number(node.degree),
                "neighbors": node.neighbors,
                "source_paths": node.source_paths,
                "subtype": node.subtype,
            }
        )

    insights = _build_insights(nodes, analyzed_edges, pair_metrics, {node["path"]: node["community_id"] for node in analyzed_nodes})

    return {
        "meta": {
            "build_date": datetime.now().isoformat(),
            "source_dir": _safe_source_dir(base_dir),
            "total_nodes": len(analyzed_nodes),
            "total_edges": len(analyzed_edges),
            "total_communities": len(communities_data),
            "degraded": False,
            "insights_degraded": bool(insights["meta"]["degraded"]),
        },
        "nodes": analyzed_nodes,
        "edges": analyzed_edges,
        "communities": communities_data,
        "insights": insights,
    }
