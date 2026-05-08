from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal


GrepMode = Literal["files_with_matches", "content", "count"]


@dataclass
class LineRef:
    path: str
    line_number: int
    text: str


@dataclass
class FileSearchResult:
    files: list[str]
    truncated: bool = False
    message: str | None = None


@dataclass
class GrepHit:
    path: str
    line_number: int
    text: str
    context_before: list[LineRef] = field(default_factory=list)
    context_after: list[LineRef] = field(default_factory=list)


@dataclass
class CountMatch:
    path: str
    count: int


@dataclass
class GrepContentResult:
    query: str
    mode: GrepMode
    hits: list[GrepHit] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    counts: list[CountMatch] = field(default_factory=list)
    truncated: bool = False
    message: str | None = None


@dataclass
class ReadLinesResult:
    path: str
    start: int
    end: int
    lines: list[LineRef]
    truncated: bool = False
    message: str | None = None


@dataclass
class Evidence:
    path: str
    start_line: int
    end_line: int
    excerpt: str
    score: float
    query: str

    @property
    def source_id(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}"


@dataclass
class LocalSearchResult:
    question: str
    evidence: list[Evidence]
    searched_queries: list[str]
    searched_paths: list[str]
    truncated: bool = False
    message: str | None = None

    @property
    def has_evidence(self) -> bool:
        return bool(self.evidence)

    @property
    def high_confidence(self) -> bool:
        return any(item.score >= 0.5 for item in self.evidence)


@dataclass
class RouteDecision:
    use_local_search: bool
    needs_web: bool
    path_hints: list[str]
    query_hints: list[str]
    reason: str


@dataclass
class WebSearchResult:
    enabled: bool
    used: bool = False
    snippets: list[str] = field(default_factory=list)
    message: str | None = None


@dataclass
class WebExtractResult:
    enabled: bool
    used: bool = False
    results: list[dict] = field(default_factory=list)  # [{"url": ..., "raw_content": ...}]
    failed_results: list[dict] = field(default_factory=list)
    message: str | None = None


@dataclass
class WebCrawlResult:
    enabled: bool
    used: bool = False
    base_url: str = ""
    results: list[dict] = field(default_factory=list)  # [{"url": ..., "raw_content": ...}]
    message: str | None = None


@dataclass
class WebMapResult:
    enabled: bool
    used: bool = False
    base_url: str = ""
    results: list[str] = field(default_factory=list)  # URL list
    message: str | None = None


@dataclass
class QueryRewriteResult:
    original_question: str
    rewritten_query: str
    changed: bool = False
    reason: str | None = None


@dataclass
class KnowledgeAnswer:
    content: str
    route: RouteDecision
    local_result: LocalSearchResult
    retrieval_query: str | None = None
    rewrite_changed: bool = False
    web_result: WebSearchResult | None = None


@dataclass
class KnowledgeAnswerStream:
    chunks: Iterator[str]
    route: RouteDecision
    local_result: LocalSearchResult
    retrieval_query: str | None = None
    rewrite_changed: bool = False
    web_result: WebSearchResult | None = None
