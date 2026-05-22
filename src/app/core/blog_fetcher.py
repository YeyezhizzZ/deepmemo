from __future__ import annotations

import argparse
import html as html_module
import json
import os
import re
import time
import sys
from dataclasses import dataclass, asdict
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen

import yaml


SHANGHAI_TZ = timezone(timedelta(hours=8))
DEFAULT_CONFIG_PATH = Path("config/blog_sources.yaml")
DEFAULT_DATE_FORMAT = "%m%d"
DEFAULT_SUMMARY_SYSTEM_PROMPT = (
    "你是中文技术日记摘要器。请基于输入材料生成适合写入工程博客日记的条目化摘要和补充思考。"
    "只输出 JSON，格式为 {\"summary\": \"...\", \"thinking\": \"...\"}，不要输出多余文本。"
    "summary 不要写成一整段文章；请写成 1~3 个短点，点与点之间用换行分隔。"
    "每个短点都必须是信息增量，例如核心观点、可复用方法、对我的启发判断。"
    "thinking 只写 1 条简短补充判断，或 1 个短点；不要空泛，不要复述 summary。"
    "summary 和 thinking 都不要复制正文原句，不要出现关联正文或原文如下之类字样。"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _decode_html(text: str) -> str:
    return html_module.unescape(text or "")


def _normalize_spaces(text: str) -> str:
    return "\n".join(
        line.strip()
        for line in (part.strip() for part in text.replace("\r", "\n").split("\n"))
        if line.strip()
    ).strip()


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text or "").strip()


def _markdown_points(text: str) -> list[str]:
    points: list[str] = []
    for raw_line in (text or "").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[\-\*\d\.\、\)]+\s*", "", line)
        line = _collapse_whitespace(line)
        if line:
            points.append(line)
    return points


def _strip_tags(text: str) -> str:
    class _TagStripper(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self.parts.append(data)

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag in {"p", "div", "br", "li", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"}:
                self.parts.append("\n")

        def handle_endtag(self, tag: str) -> None:
            if tag in {"p", "div", "li", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"}:
                self.parts.append("\n")

    stripper = _TagStripper()
    stripper.feed(_decode_html(text))
    return _normalize_spaces("".join(stripper.parts))


def _request_text(url: str, *, referer: str | None = None, timeout: float = 15.0) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def _ensure_absolute_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://mp.weixin.qq.com{url}" if url.startswith("/s?") or url.startswith("/s/") else url


class _ArticleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.capture = False
        self.capture_depth = 0
        self.found_target = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if not self.capture and tag == "div" and attrs_dict.get("id") == "js_content":
            self.capture = True
            self.capture_depth = 1
            self.found_target = True
            return

        if self.capture:
            if tag == "div":
                self.capture_depth += 1
            if tag in {"p", "div", "br", "li", "section", "article"}:
                self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self.capture:
            return
        if tag in {"p", "div", "li", "section", "article"}:
            self.parts.append("\n")
        if tag == "div":
            self.capture_depth -= 1
            if self.capture_depth <= 0:
                self.capture = False

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.parts.append(data)

    def text(self) -> str:
        return _normalize_spaces(_decode_html("".join(self.parts)))


class TavilySearchError(RuntimeError):
    pass


@dataclass(slots=True)
class TavilySearchResult:
    title: str
    url: str
    content: str = ""
    published_at: datetime | None = None
    raw: dict[str, Any] | None = None


class TavilySearchClient:
    api_url = "https://api.tavily.com/search"

    def __init__(self, config_path: Path | None = None) -> None:
        self.repo_root = _repo_root()
        self.config_path = config_path or (self.repo_root / "config/web_search.yaml")
        self.config = _load_yaml(self.config_path)
        tavily_config = self.config.get("tavily") if isinstance(self.config.get("tavily"), dict) else {}
        env_api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        config_api_key = str((tavily_config or {}).get("api_key", "") or "").strip()
        self.api_key = env_api_key or config_api_key
        self.enabled = bool(self.api_key) and bool(self.config.get("enabled", True))
        self.disabled_reason = "Tavily API key 未配置" if not self.api_key else "Tavily 搜索未启用"

    def discover_wechat_articles(self, source_name: str, target_date: datetime) -> tuple[list[TavilySearchResult], list[str]]:
        if not self.enabled:
            return [], [f"微信公众号 URL 发现器不可用：{source_name} - {self.disabled_reason}"]

        target_day = target_date.date()
        day_text = target_day.isoformat()
        next_day_text = (target_date + timedelta(days=1)).date().isoformat()
        query_variants = [
            f'site:mp.weixin.qq.com/s/ "{source_name}"',
            f'site:mp.weixin.qq.com/s/ "{source_name}" 微信公众号',
            f'site:mp.weixin.qq.com/s/ "{source_name}" {day_text}',
        ]

        warnings: list[str] = []
        candidates: list[TavilySearchResult] = []
        seen_urls: set[str] = set()

        for query in query_variants:
            try:
                response = self.search(
                    query,
                    start_date=day_text,
                    end_date=next_day_text,
                    include_domains=["mp.weixin.qq.com"],
                    max_results=10,
                )
            except TavilySearchError as exc:
                warnings.append(f"微信公众号 URL 搜索失败：{source_name} - {query} - {exc}")
                continue

            results = response.get("results", []) if isinstance(response, dict) else []
            for item in results:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", "") or "").strip()
                parsed = urlparse(url)
                if not url or parsed.scheme not in {"http", "https"}:
                    continue
                if parsed.netloc.lower() != "mp.weixin.qq.com" or not parsed.path.startswith("/s"):
                    continue
                if url in seen_urls:
                    continue

                published_at = _tavily_result_published_at(item)
                if published_at and published_at.date() != target_day:
                    continue

                seen_urls.add(url)
                candidates.append(
                    TavilySearchResult(
                        title=_strip_tags(str(item.get("title", "") or "")),
                        url=url,
                        content=_strip_tags(str(item.get("content", "") or "")),
                        published_at=published_at,
                        raw=item,
                    )
                )

        if not candidates:
            warnings.append(f"微信公众号 URL 搜索没有返回可用文章：{source_name}")
        return candidates, warnings

    def search(
        self,
        query: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        include_domains: list[str] | None = None,
        max_results: int = 10,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise TavilySearchError(self.disabled_reason)

        payload: dict[str, Any] = {
            "query": query,
            "search_depth": "advanced",
            "topic": "general",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_usage": False,
        }
        if start_date:
            payload["start_date"] = start_date
        if end_date:
            payload["end_date"] = end_date
        if include_domains:
            payload["include_domains"] = include_domains

        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self.api_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            },
        )

        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="replace")
        except (HTTPError, URLError) as exc:
            raise TavilySearchError(str(exc)) from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TavilySearchError(f"Tavily 返回非 JSON：{exc}") from exc

        if not isinstance(data, dict):
            raise TavilySearchError("Tavily 返回结构异常")
        return data


def _tavily_result_published_at(result: dict[str, Any]) -> datetime | None:
    published = result.get("published_date") or result.get("published_at") or ""
    if not published:
        return None
    return _parse_datetime_value(str(published))


def _parse_datetime_value(value: str) -> datetime | None:
    text = _decode_html(str(value or "")).strip()
    if not text:
        return None
    text = text.replace("/", "-")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except Exception:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(SHANGHAI_TZ)


def _find_meta_content(html_text: str, names: set[str]) -> str:
    for name in names:
        pattern = (
            r'<meta[^>]+(?:name|property)=["\']'
            + re.escape(name)
            + r'["\'][^>]+content=["\']([^"\']+)["\']'
        )
        match = re.search(pattern, html_text, re.S | re.I)
        if match:
            return _decode_html(match.group(1)).strip()
        pattern = (
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']'
            + re.escape(name)
            + r'["\']'
        )
        match = re.search(pattern, html_text, re.S | re.I)
        if match:
            return _decode_html(match.group(1)).strip()
    return ""


def _extract_page_published_at(html_text: str) -> datetime | None:
    candidate_names = {
        "article:published_time",
        "og:published_time",
        "publish_date",
        "pubdate",
        "pubDate",
        "dc.date",
        "dc.date.issued",
        "date",
        "datePublished",
        "dateCreated",
        "parsely-pub-date",
        "sailthru.date",
    }
    time_match = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', html_text, re.S | re.I)
    json_ld_match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html_text, re.S | re.I)
    modified_match = re.search(r'"dateModified"\s*:\s*"([^"]+)"', html_text, re.S | re.I)
    for value in (
        _find_meta_content(html_text, candidate_names),
        time_match.group(1) if time_match else "",
        json_ld_match.group(1) if json_ld_match else "",
        modified_match.group(1) if modified_match else "",
    ):
        published_at = _parse_datetime_value(value)
        if published_at:
            return published_at
    return None


def _extract_page_title(html_text: str) -> str:
    title_match = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
    return _strip_tags(title_match.group(1)) if title_match else ""


def _fetch_page_title_and_text(url: str, *, referer: str | None = None) -> tuple[str, str, str]:
    try:
        html_text = _request_text(url, referer=referer or url)
    except (HTTPError, URLError):
        return "", "", ""

    if "链接已过期" in html_text:
        return "", "", ""

    title = _extract_page_title(html_text)

    extractor = _ArticleTextExtractor()
    extractor.feed(html_text)
    content = extractor.text()
    if not content:
        page_extractor = _PageTextExtractor()
        page_extractor.feed(html_text)
        content = page_extractor.text()

    if not content:
        meta_match = re.search(
            r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
            html_text,
            re.S | re.I,
        )
        if meta_match:
            content = _strip_tags(meta_match.group(1))

    return title, content, html_text


def _fetch_wechat_article_text(url: str) -> tuple[str, str]:
    title, content, _ = _fetch_page_title_and_text(url, referer=url)
    return title, content


def _looks_like_url(text: str) -> bool:
    stripped = text.strip().lower()
    return stripped.startswith("http://") or stripped.startswith("https://")


def _normalize_wechat_account_name(text: str) -> str:
    normalized = _collapse_whitespace(_decode_html(text)).lower()
    normalized = normalized.replace(" - 微信公众平台", "")
    normalized = normalized.replace("- 微信公众平台", "")
    normalized = normalized.replace("微信公众号", "")
    normalized = normalized.replace("微信公众平台", "")
    normalized = normalized.replace("（微信公众平台）", "")
    normalized = normalized.replace("(微信公众平台)", "")
    normalized = re.sub(r"[\s\u3000]+", "", normalized)
    normalized = normalized.strip(" -_：:")
    return normalized


def _extract_wechat_account_candidates(html_text: str) -> list[str]:
    patterns = [
        r'var\s+nickname\s*=\s*["\']([^"\']+)["\']',
        r'var\s+user_name\s*=\s*["\']([^"\']+)["\']',
        r'var\s+appmsg_title\s*=\s*["\']([^"\']+)["\']',
        r'<meta[^>]+(?:name|property)=["\']author["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']author["\']',
        r'<a[^>]+id=["\']js_name["\'][^>]*>(.*?)</a>',
        r'<strong class=["\']profile_nickname["\']>\s*(.*?)\s*</strong>',
        r'"nickname"\s*:\s*"([^"]+)"',
    ]
    candidates: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, html_text, re.S | re.I):
            candidate = _strip_tags(str(match))
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _wechat_ownership_check(source_name: str, html_text: str, candidate: TavilySearchResult) -> dict[str, Any]:
    normalized_source = _normalize_wechat_account_name(source_name)
    html_candidates = _extract_wechat_account_candidates(html_text)
    normalized_candidates = [_normalize_wechat_account_name(item) for item in html_candidates if item]
    matched_candidate = next((item for item in normalized_candidates if item == normalized_source), "")

    if matched_candidate:
        return {
            "status": "matched",
            "source_name": source_name,
            "normalized_source": normalized_source,
            "matched_name": matched_candidate,
            "evidence": {"html_candidates": html_candidates},
        }

    search_evidence = []
    for text in (candidate.title, candidate.content, (candidate.raw or {}).get("title", ""), (candidate.raw or {}).get("content", "")):
        text = _collapse_whitespace(str(text))
        if not text:
            continue
        search_evidence.append(text[:200])
        if normalized_source and normalized_source in _normalize_wechat_account_name(text):
            return {
                "status": "assumed",
                "source_name": source_name,
                "normalized_source": normalized_source,
                "matched_name": "",
                "evidence": {
                    "html_candidates": html_candidates,
                    "search_evidence": search_evidence,
                },
            }

    return {
        "status": "mismatch" if html_candidates else "unknown",
        "source_name": source_name,
        "normalized_source": normalized_source,
        "matched_name": "",
        "evidence": {
            "html_candidates": html_candidates,
            "search_evidence": search_evidence,
        },
    }


class _BlogSourceDiscoveryParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.feed_urls: list[str] = []
        self.article_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag == "link":
            rel = attrs_dict.get("rel", "").lower()
            href = attrs_dict.get("href", "").strip()
            link_type = attrs_dict.get("type", "").lower()
            if href and "alternate" in rel and any(keyword in link_type for keyword in ("rss+xml", "atom+xml", "xml")):
                self.feed_urls.append(urljoin(self.base_url, href))
        elif tag == "a":
            href = attrs_dict.get("href", "").strip()
            if href:
                self.article_links.append(urljoin(self.base_url, href))


def _same_netloc(left: str, right: str) -> bool:
    left_netloc = urlparse(left).netloc.lower()
    right_netloc = urlparse(right).netloc.lower()
    if not left_netloc or not right_netloc:
        return False
    return left_netloc == right_netloc


def _is_probably_article_url(url: str, base_url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not _same_netloc(url, base_url):
        return False
    path = parsed.path.rstrip("/")
    if not path or path in {"/", ""}:
        return False
    lowered = path.lower()
    ignored_prefixes = (
        "/tag",
        "/tags",
        "/category",
        "/categories",
        "/author",
        "/about",
        "/search",
        "/privacy",
        "/terms",
        "/feed",
        "/rss",
        "/atom",
    )
    if any(lowered.startswith(prefix) for prefix in ignored_prefixes):
        return False
    if re.search(r"/page/\d+/?$", lowered):
        return False
    return True


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


class _PageTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
            return
        if self.skip_depth == 0 and tag in {"p", "div", "br", "li", "section", "article"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth > 0:
            self.skip_depth -= 1
            return
        if self.skip_depth == 0 and tag in {"p", "div", "li", "section", "article"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        return _normalize_spaces(_decode_html("".join(self.parts)))


@dataclass(slots=True)
class BlogSource:
    type: str
    name: str
    enabled: bool = True
    url: str | None = None
    profile_url: str | None = None
    search_keyword: str | None = None
    feed_url: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BlogSource":
        url = data.get("url")
        profile_url = data.get("profile_url")
        return cls(
            type=str(data.get("type", "")).strip(),
            name=str(data.get("name", "")).strip(),
            enabled=bool(data.get("enabled", True)),
            url=(str(url).strip() or None) if url else (str(profile_url).strip() or None) if profile_url else None,
            profile_url=(str(profile_url).strip() or None) if profile_url else None,
            search_keyword=(str(data.get("search_keyword")).strip() or None) if data.get("search_keyword") else None,
            feed_url=(str(data.get("feed_url")).strip() or None) if data.get("feed_url") else None,
        )


@dataclass(slots=True)
class DiaryEntry:
    title: str
    url: str
    summary: str
    thinking: str
    source_name: str
    source_type: str
    published_at: datetime
    content_excerpt: str = ""
    raw: dict[str, Any] | None = None

    @property
    def key(self) -> str:
        return self.url or f"{self.source_name}:{self.title}"

    def to_raw_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["published_at"] = self.published_at.isoformat()
        return payload

    def render_markdown(self) -> str:
        lines = [f"- [{self.title}]({self.url})"]
        summary_points = _markdown_points(self.summary)
        if summary_points:
            lines.extend(f"  - {point}" for point in summary_points)
        elif self.summary.strip():
            lines.append(f"  - {self.summary.strip()}")
        thinking_points = _markdown_points(self.thinking)
        if thinking_points:
            lines.extend(f"  - {point}" for point in thinking_points)
        return "\n".join(lines)


@dataclass(slots=True)
class SearchExperience:
    timestamp: str
    source_name: str
    source_type: str
    strategy: str
    query_signature: str
    query_variant: str
    candidate_count: int
    url_match_count: int
    published_date_hit_rate: float
    page_fetch_success_rate: float
    fallback_used: bool
    latency_ms: int
    warnings: list[str]
    details: dict[str, Any] | None = None

    def to_raw_dict(self) -> dict[str, Any]:
        return asdict(self)


class WechatSogouCompatClient:
    search_base = "https://weixin.sogou.com/weixin"
    history_page_re = re.compile(r"var msgList = (.*?)}}]};", re.S)
    account_result_re = re.compile(
        r'uigs="account_name_\d+"\s+href="([^"]+)"[^>]*>(.*?)</a>',
        re.S,
    )

    def search_profile_url(self, keyword: str) -> str | None:
        query = quote_plus(keyword)
        url = f"{self.search_base}?type=1&page=1&ie=utf8&query={query}"
        try:
            text = _request_text(url)
        except (HTTPError, URLError):
            return None

        candidates: list[tuple[str, str]] = []
        for href, title_html in self.account_result_re.findall(text):
            title = _strip_tags(title_html)
            candidates.append((href, title))

        if not candidates:
            return None

        for href, title in candidates:
            if keyword in title or title == keyword:
                return _decode_html(href)

        return _decode_html(candidates[0][0])

    def get_history(self, *, keyword: str | None = None, profile_url: str | None = None) -> dict[str, Any]:
        if not profile_url:
            if not keyword:
                raise ValueError("keyword or profile_url is required")
            profile_url = self.search_profile_url(keyword)
            if not profile_url:
                return {}

        try:
            text = _request_text(profile_url, referer=self.search_base)
        except (HTTPError, URLError):
            return {}

        if "链接已过期" in text:
            return {}

        history_match = self.history_page_re.search(text)
        if not history_match:
            return {}

        article_json = json.loads(history_match.group(1) + "}}]}")
        articles: list[dict[str, Any]] = []
        for item in article_json.get("list", []):
            comm_msg_info = item.get("comm_msg_info") or {}
            app_msg_ext_info = item.get("app_msg_ext_info") or {}
            if str(comm_msg_info.get("type", "")) != "49":
                continue

            send_id = comm_msg_info.get("id", "")
            msg_datetime = int(comm_msg_info.get("datetime", 0) or 0)

            primary = self._build_article(send_id, msg_datetime, app_msg_ext_info, main=True)
            if primary:
                articles.append(primary)

            if int(app_msg_ext_info.get("is_multi", 0) or 0) == 1:
                for multi in app_msg_ext_info.get("multi_app_msg_item_list", []) or []:
                    extra = self._build_article(send_id, msg_datetime, multi, main=False)
                    if extra:
                        articles.append(extra)

        return {
            "gzh": self._parse_profile_info(text),
            "article": articles,
        }

    def _build_article(self, send_id: Any, msg_datetime: int, data: dict[str, Any], *, main: bool) -> dict[str, Any] | None:
        content_url = _ensure_absolute_url(_decode_html(str(data.get("content_url", "") or "")))
        if not content_url:
            return None
        return {
            "send_id": send_id,
            "datetime": msg_datetime,
            "type": "49",
            "main": 1 if main else 0,
            "title": str(data.get("title", "") or ""),
            "abstract": str(data.get("digest", "") or ""),
            "fileid": data.get("fileid", ""),
            "content_url": content_url,
            "source_url": str(data.get("source_url", "") or ""),
            "cover": str(data.get("cover", "") or ""),
            "author": str(data.get("author", "") or ""),
            "copyright_stat": data.get("copyright_stat", ""),
        }

    def _parse_profile_info(self, text: str) -> dict[str, str]:
        def find(pattern: str, default: str = "") -> str:
            match = re.search(pattern, text, re.S)
            return _strip_tags(match.group(1)) if match else default

        name = find(r'<strong class="profile_nickname">\s*(.*?)\s*</strong>')
        account = find(r"微信号:\s*([^<\s]+)")
        intro = find(r'<label class="profile_desc_label"[^>]*>功能介绍</label>\s*<div class="profile_desc_value"[^>]*>(.*?)</div>')
        auth = find(r'<label class="profile_desc_label"[^>]*>帐号主体</label>\s*<div class="profile_desc_value"[^>]*>(.*?)</div>')
        headimage_match = re.search(r'<span class="radius_avatar profile_avatar">\s*<img src="([^"]+)"', text, re.S)
        headimage = _decode_html(headimage_match.group(1)) if headimage_match else ""
        return {
            "wechat_name": name,
            "wechat_id": account,
            "introduction": intro,
            "authentication": auth,
            "headimage": headimage,
        }

    def fetch_article_text(self, url: str) -> tuple[str, str]:
        try:
            html_text = _request_text(url, referer=url)
        except (HTTPError, URLError):
            return "", ""

        if "链接已过期" in html_text:
            return "", ""

        title_match = re.search(r"<title>(.*?)</title>", html_text, re.S)
        title = _strip_tags(title_match.group(1)) if title_match else ""

        extractor = _ArticleTextExtractor()
        extractor.feed(html_text)
        content = extractor.text()
        if not content:
            page_extractor = _PageTextExtractor()
            page_extractor.feed(html_text)
            content = page_extractor.text()

        if content:
            return title, content

        meta_match = re.search(
            r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
            html_text,
            re.S | re.I,
        )
        if meta_match:
            return title, _strip_tags(meta_match.group(1))

        return title, ""


class EntrySummarizer:
    def __init__(self, system_prompt: str | None = None) -> None:
        self._llm_service = None
        self.system_prompt = system_prompt or DEFAULT_SUMMARY_SYSTEM_PROMPT

    def summarize(self, entry: dict[str, Any], article_text: str) -> tuple[str, str]:
        if self._should_use_llm():
            result = self._summarize_with_llm(entry, article_text)
            if result:
                return result
        return self._fallback_summary(entry, article_text)

    def _should_use_llm(self) -> bool:
        try:
            from src.services.llm_service import llm_service  # type: ignore
        except Exception:
            return False

        self._llm_service = llm_service
        return True

    def _summarize_with_llm(self, entry: dict[str, Any], article_text: str) -> tuple[str, str] | None:
        if not self._llm_service:
            return None

        content_preview = _collapse_whitespace(article_text)
        if len(content_preview) > 2200:
            content_preview = content_preview[:2200]

        payload = {
            "source": entry.get("source_name", ""),
            "title": entry.get("title", ""),
            "abstract": entry.get("abstract", ""),
            "content": content_preview,
        }
        messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ]

        try:
            response = self._llm_service.chat(messages)
            content = response.choices[0].message.content.strip()
            data = self._parse_json_block(content)
            summary = _collapse_whitespace(str(data.get("summary", "")))
            thinking = _collapse_whitespace(str(data.get("thinking", "")))
            if summary:
                return summary, thinking
        except Exception:
            return None
        return None

    def _parse_json_block(self, content: str) -> dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        return {}

    def _fallback_summary(self, entry: dict[str, Any], article_text: str) -> tuple[str, str]:
        title = _collapse_whitespace(str(entry.get("title", "")))
        abstract = _collapse_whitespace(str(entry.get("abstract", "")))
        snippet = _collapse_whitespace(article_text)
        if len(snippet) > 240:
            snippet = snippet[:240].rstrip("，。；；,. ") + "..."

        if abstract and snippet:
            summary = f"核心观点：{abstract[:90]}"
            if snippet:
                summary = f"{summary}\n可复用点：{snippet[:110]}"
            thinking = "已压缩为条目，不直接复制正文。"
        elif abstract:
            summary = f"核心观点：{abstract[:110]}"
            thinking = "来源正文未能完整解析，先保留搜索摘要。"
        elif snippet:
            summary = f"核心观点：{snippet[:90]}"
            thinking = "基于正文首段整理，后续可补抓正文。"
        else:
            summary = f"核心观点：{title or '技术更新'}"
            thinking = "仅有标题，后续可补抓正文。"

        if not summary:
            summary = f"核心观点：{title or '技术更新'}"
        return summary, thinking


class DiaryWriter:
    def __init__(self, diary_root: Path) -> None:
        self.diary_root = diary_root

    def diary_path_for_date(self, target_date: datetime) -> Path:
        return self.diary_root / f"{target_date.strftime(DEFAULT_DATE_FORMAT)}.md"

    def ensure_template(self, path: Path) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# 每日记录\n\n## 科研\n-\n\n## 工程博客\n- [标题](URL)\n  - 核心观点：...\n  - 可复用点：...\n  - 思考：...\n\n\n## others\n\n-\n",
            encoding="utf-8",
        )

    def append_entries(self, path: Path, entries: list[DiaryEntry]) -> dict[str, Any]:
        self.ensure_template(path)
        existing = path.read_text(encoding="utf-8")
        section_start = existing.find("## 工程博客")
        if section_start == -1:
            section_start = len(existing)
            section_end = len(existing)
            section_body = ""
        else:
            section_end = self._find_next_heading(existing, section_start + len("## 工程博客"))
            section_body = existing[section_start:section_end]

        existing_keys = self._extract_existing_keys(section_body)
        new_entries = [entry for entry in entries if entry.key not in existing_keys]

        if not new_entries:
            return {"added": 0, "skipped": len(entries), "path": str(path)}

        insertion = "\n\n".join(entry.render_markdown() for entry in new_entries)
        if not insertion.endswith("\n"):
            insertion += "\n"

        if section_start == len(existing):
            updated = existing.rstrip() + "\n\n## 工程博客\n" + insertion + "\n## others\n\n-\n"
        else:
            prefix = existing[:section_end].rstrip()
            suffix = existing[section_end:].lstrip("\n")
            if prefix.endswith("## 工程博客"):
                prefix += "\n"
            updated = prefix + "\n" + insertion + suffix
            if not updated.endswith("\n"):
                updated += "\n"

        path.write_text(updated, encoding="utf-8")
        return {"added": len(new_entries), "skipped": len(entries) - len(new_entries), "path": str(path)}

    def _find_next_heading(self, text: str, start: int) -> int:
        matches = list(re.finditer(r"^##\s+", text[start:], re.M))
        if not matches:
            return len(text)
        return start + matches[0].start()

    def _extract_existing_keys(self, section_body: str) -> set[str]:
        keys: set[str] = set()
        for match in re.finditer(r"\((https?://[^)]+)\)", section_body):
            keys.add(match.group(1))
        return keys


class ExperienceWriter:
    def __init__(self, experience_root: Path) -> None:
        self.experience_root = experience_root

    def append_records(self, records: list[SearchExperience]) -> dict[str, Any]:
        if not records:
            return {"written": False, "count": 0, "path": ""}

        self.experience_root.mkdir(parents=True, exist_ok=True)
        path = self.experience_root / "experience.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record.to_raw_dict(), ensure_ascii=False) + "\n")
        return {"written": True, "count": len(records), "path": str(path)}


class BlogDiaryService:
    def __init__(self, config_path: str | Path = DEFAULT_CONFIG_PATH) -> None:
        self.config_path = Path(config_path)
        self.repo_root = _repo_root()
        self.config = _load_yaml(self.repo_root / self.config_path)
        self.web_search_client = TavilySearchClient(self.repo_root / "config/web_search.yaml")
        summary_prompt_cfg = self.config.get("summary_prompt")
        system_prompt = ""
        if isinstance(summary_prompt_cfg, dict):
            system_prompt = str(summary_prompt_cfg.get("system", "") or "").strip()
        self.summarizer = EntrySummarizer(system_prompt=system_prompt or None)
        diary_root = self.repo_root / str(self.config.get("diary_root", "data/diary"))
        self.writer = DiaryWriter(diary_root)
        experience_root = self.repo_root / str(self.config.get("experience_root", "data/raw/web_search"))
        self.experience_writer = ExperienceWriter(experience_root)
        chain_root_cfg = self.config.get("chain_log_root", self.config.get("progress_root", "data/raw/runs"))
        self.chain_log_root = self.repo_root / str(chain_root_cfg)

    def run(self, target_date: datetime | None = None, *, dry_run: bool = False) -> dict[str, Any]:
        target_date = target_date or self._yesterday_in_shanghai()
        target_date = target_date.astimezone(SHANGHAI_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        raw_sources = self.config.get("sources")
        sources = [BlogSource.from_dict(item) for item in raw_sources or []]
        if raw_sources is None:
            sources = [BlogSource(type="wechat", name="阿里云开发者")]

        entries: list[DiaryEntry] = []
        warnings: list[str] = []
        experiences: list[SearchExperience] = []
        diary_added = 0
        diary_skipped = 0
        diary_path = self.writer.diary_path_for_date(target_date)
        chain_log_path = self.chain_log_root / f"{target_date.strftime('%Y-%m-%d')}.jsonl"
        chain_log_path.parent.mkdir(parents=True, exist_ok=True)

        def log_progress(message: str) -> None:
            print(message, file=sys.stderr, flush=True)

        def append_chain_record(record: dict[str, Any]) -> None:
            with open(chain_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        def make_entry_sink(source: BlogSource):
            def sink(entry: DiaryEntry) -> dict[str, Any]:
                nonlocal diary_added, diary_skipped
                if dry_run:
                    result = {"added": 1, "skipped": 0, "path": str(diary_path), "dry_run": True}
                else:
                    result = self.writer.append_entries(diary_path, [entry])
                    diary_added += int(result.get("added", 0))
                    diary_skipped += int(result.get("skipped", 0))
                    append_chain_record(
                        {
                            "event": "entry_written",
                            "date": target_date.date().isoformat(),
                            "source_name": source.name,
                            "source_type": source.type,
                            "entry": entry.to_raw_dict(),
                            "write_result": result,
                            "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                        }
                    )
                log_progress(f"[entry] {source.type}:{source.name} -> {entry.title}")
                return result

            return sink

        append_chain_record(
            {
                "event": "run_start",
                "date": target_date.date().isoformat(),
                "source_count": len(sources),
                "dry_run": dry_run,
                "diary_path": str(diary_path),
                "chain_log_path": str(chain_log_path),
                "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
            }
        )
        log_progress(f"[run] start {target_date.date().isoformat()} sources={len(sources)}")
        for source in sources:
            if not source.enabled:
                append_chain_record(
                    {
                        "event": "source_skip",
                        "date": target_date.date().isoformat(),
                        "source_name": source.name,
                        "source_type": source.type,
                        "reason": "disabled",
                        "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                    }
                )
                continue
            try:
                log_progress(f"[source] start {source.type}:{source.name}")
                append_chain_record(
                    {
                        "event": "source_start",
                        "date": target_date.date().isoformat(),
                        "source_name": source.name,
                        "source_type": source.type,
                        "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                    }
                )
                entry_sink = make_entry_sink(source)
                if source.type == "wechat":
                    collected, source_warnings, source_experiences = self.collect_wechat_entries(
                        source, target_date, entry_sink=entry_sink, event_sink=append_chain_record
                    )
                elif source.type == "blog":
                    collected, source_warnings, source_experiences = self.collect_blog_entries(
                        source, target_date, entry_sink=entry_sink, event_sink=append_chain_record
                    )
                elif source.type == "rss":
                    collected, source_warnings, source_experiences = self.collect_rss_entries(
                        source, target_date, entry_sink=entry_sink, event_sink=append_chain_record
                    )
                else:
                    log_progress(f"[source] skip {source.type}:{source.name}")
                    append_chain_record(
                        {
                            "event": "source_skip",
                            "date": target_date.date().isoformat(),
                            "source_name": source.name,
                            "source_type": source.type,
                            "reason": "unsupported_type",
                            "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                        }
                    )
                    continue
            except Exception as exc:
                source_warnings = [f"来源处理失败：{source.name} - {exc}"]
                source_experiences = []
                collected = []
                log_progress(f"[source] error {source.type}:{source.name} -> {exc}")
                append_chain_record(
                    {
                        "event": "source_error",
                        "date": target_date.date().isoformat(),
                        "source_name": source.name,
                        "source_type": source.type,
                        "error": str(exc),
                        "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                    }
                )

            entries.extend(collected)
            warnings.extend(source_warnings)
            experiences.extend(source_experiences)
            entries = self._dedupe_entries(entries)

            if not dry_run:
                raw_result = self._write_raw_snapshot(target_date, entries, warnings)
                experience_result = self.experience_writer.append_records(source_experiences)
            else:
                raw_result = {"path": "", "written": False}
                experience_result = {"written": False, "count": 0, "path": ""}

            append_chain_record(
                {
                    "event": "source_done",
                    "date": target_date.date().isoformat(),
                    "source_name": source.name,
                    "source_type": source.type,
                    "entry_count": len(collected),
                    "warning_count": len(source_warnings),
                    "experience_count": len(source_experiences),
                    "warnings": source_warnings,
                    "raw_result": raw_result,
                    "experience_result": experience_result,
                    "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                }
            )
            log_progress(
                f"[source] done {source.type}:{source.name} entries={len(collected)} warnings={len(source_warnings)}"
            )

        entries.sort(key=lambda item: item.published_at, reverse=True)
        entries = self._dedupe_entries(entries)

        if dry_run:
            write_result = {"added": len(entries), "skipped": 0, "path": str(diary_path), "dry_run": True}
            raw_result = {"path": "", "written": False}
            experience_result = {"written": False, "count": 0, "path": ""}
        else:
            write_result = {
                "added": diary_added,
                "skipped": diary_skipped,
                "path": str(diary_path),
                "streaming": True,
            }
            raw_result = self._write_raw_snapshot(target_date, entries, warnings)
            experience_result = {"written": True, "count": len(experiences), "path": str(self.experience_writer.experience_root / "experience.jsonl")}

        append_chain_record(
            {
                "event": "run_end",
                "date": target_date.date().isoformat(),
                "entry_count": len(entries),
                "warning_count": len(warnings),
                "write_result": write_result,
                "raw_result": raw_result,
                "experience_result": experience_result,
                "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
            }
        )

        return {
            "date": target_date.date().isoformat(),
            "entry_count": len(entries),
            "entries": [entry.to_raw_dict() for entry in entries],
            "write_result": write_result,
            "raw_result": raw_result,
            "experience_result": experience_result,
            "warnings": warnings,
        }

    def _make_experience_record(
        self,
        *,
        source: BlogSource,
        strategy: str,
        query_signature: str,
        query_variant: str,
        candidate_count: int,
        url_match_count: int,
        published_date_hit_count: int,
        page_fetch_success_count: int,
        fallback_used: bool,
        latency_ms: int,
        warnings: list[str],
        details: dict[str, Any] | None = None,
    ) -> SearchExperience:
        hit_rate = (published_date_hit_count / candidate_count) if candidate_count else 0.0
        fetch_rate = (page_fetch_success_count / candidate_count) if candidate_count else 0.0
        return SearchExperience(
            timestamp=datetime.now(tz=SHANGHAI_TZ).isoformat(),
            source_name=source.name,
            source_type=source.type,
            strategy=strategy,
            query_signature=query_signature,
            query_variant=query_variant,
            candidate_count=candidate_count,
            url_match_count=url_match_count,
            published_date_hit_rate=round(hit_rate, 4),
            page_fetch_success_rate=round(fetch_rate, 4),
            fallback_used=fallback_used,
            latency_ms=latency_ms,
            warnings=warnings,
            details=details,
        )

    def collect_wechat_entries(
        self,
        source: BlogSource,
        target_date: datetime,
        entry_sink: Any | None = None,
        event_sink: Any | None = None,
    ) -> tuple[list[DiaryEntry], list[str], list[SearchExperience]]:
        started_at = time.perf_counter()
        warnings: list[str]
        if event_sink is not None:
            event_sink(
                {
                    "event": "wechat_discovery_start",
                    "date": target_date.date().isoformat(),
                    "source_name": source.name,
                    "source_type": source.type,
                    "query_signature": f'site:mp.weixin.qq.com/s/ "{source.name}"',
                    "query_variant": "wechat_title",
                    "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                }
            )
        candidates, warnings = self.web_search_client.discover_wechat_articles(source.name, target_date)
        if event_sink is not None:
            event_sink(
                {
                    "event": "wechat_discovery_done",
                    "date": target_date.date().isoformat(),
                    "source_name": source.name,
                    "source_type": source.type,
                    "candidate_count": len(candidates),
                    "warning_count": len(warnings),
                    "warnings": list(warnings),
                    "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                }
            )
        if not candidates:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            experience = self._make_experience_record(
                source=source,
                strategy="tavily_wechat_article_discovery",
                query_signature=f'site:mp.weixin.qq.com/s/ "{source.name}"',
                query_variant="wechat_title_plus_date",
                candidate_count=0,
                url_match_count=0,
                published_date_hit_count=0,
                page_fetch_success_count=0,
                fallback_used=False,
                latency_ms=latency_ms,
                warnings=list(warnings),
                details={"target_date": target_date.date().isoformat()},
            )
            return [], warnings, [experience]

        target_day = target_date.date()
        entries: list[DiaryEntry] = []
        page_fetch_success_count = 0
        fallback_used = False
        published_date_hit_count = 0

        for index, candidate in enumerate(candidates):
            if event_sink is not None:
                event_sink(
                    {
                        "event": "wechat_candidate",
                        "date": target_date.date().isoformat(),
                        "source_name": source.name,
                        "source_type": source.type,
                        "url": candidate.url,
                        "candidate_title": candidate.title,
                        "candidate_published_at": candidate.published_at.isoformat() if candidate.published_at else "",
                        "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                    }
                )

            fetched_title, article_text, article_html = _fetch_page_title_and_text(candidate.url, referer=candidate.url)
            if article_text:
                page_fetch_success_count += 1
            else:
                fallback_used = True

            candidate_title = _collapse_whitespace(candidate.title)
            fetched_title = _collapse_whitespace(fetched_title)
            if candidate_title and not _looks_like_url(candidate_title):
                title = candidate_title
            elif fetched_title and not _looks_like_url(fetched_title):
                title = fetched_title
            else:
                title = source.name

            abstract = _collapse_whitespace(candidate.content)
            published_at = candidate.published_at or (target_date + timedelta(minutes=index))
            time_check_pass = published_at.date() == target_day
            if event_sink is not None:
                event_sink(
                    {
                        "event": "wechat_time_check",
                        "date": target_day.isoformat(),
                        "source_name": source.name,
                        "source_type": source.type,
                        "url": candidate.url,
                        "published_at": published_at.isoformat(),
                        "target_day": target_day.isoformat(),
                        "status": "pass" if time_check_pass else "fail",
                        "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                    }
                )
            if published_at.date() != target_day:
                warnings.append(f"微信公众号 URL 发现器命中非目标日期文章：{source.name} - {candidate.url}")
                continue

            ownership = _wechat_ownership_check(source.name, article_html, candidate)
            ownership_status = str(ownership.get("status", "unknown"))
            if event_sink is not None:
                event_sink(
                    {
                        "event": "wechat_ownership_check",
                        "date": target_day.isoformat(),
                        "source_name": source.name,
                        "source_type": source.type,
                        "url": candidate.url,
                        "status": ownership_status,
                        "matched_name": ownership.get("matched_name", ""),
                        "evidence": ownership.get("evidence", {}),
                        "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                    }
                )
            if ownership_status == "mismatch":
                warnings.append(f"微信公众号归属校验未通过：{source.name} - {candidate.url}")
                continue

            published_date_hit_count += 1
            if not article_text:
                warnings.append(f"微信公众号正文抓取失败，改用搜索摘要：{source.name} - {candidate.url}")

            summary, thinking = self.summarizer.summarize(
                {
                    "source_name": source.name,
                    "title": title,
                    "abstract": abstract,
                    "content_url": candidate.url,
                },
                article_text or abstract,
            )

            if not thinking:
                thinking = "微信公众号当天新增内容，已按时间窗自动收录。"

            if event_sink is not None:
                event_sink(
                    {
                        "event": "wechat_summarized",
                        "date": target_day.isoformat(),
                        "source_name": source.name,
                        "source_type": source.type,
                        "url": candidate.url,
                        "summary_length": len(summary),
                        "thinking_length": len(thinking),
                        "used_page_text": bool(article_text),
                        "summary_preview": summary[:120],
                        "thinking_preview": thinking[:120],
                        "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                    }
                )

            entry = DiaryEntry(
                title=title or "未命名文章",
                url=candidate.url,
                summary=summary,
                thinking=thinking,
                source_name=source.name,
                source_type="wechat",
                published_at=published_at,
                content_excerpt=_collapse_whitespace((article_text or abstract)[:500]),
                raw={
                    "article": {
                        "url": candidate.url,
                        "title": candidate.title,
                        "content": candidate.content,
                        "published_at": candidate.published_at.isoformat() if candidate.published_at else "",
                        "search_result": candidate.raw or {},
                    },
                    "validation": {
                        "time_check": {
                            "status": "pass" if time_check_pass else "fail",
                            "target_day": target_day.isoformat(),
                            "published_at": published_at.isoformat(),
                        },
                        "ownership_check": ownership,
                    },
                    "discovery": "tavily",
                },
            )
            entries.append(entry)
            if entry_sink is not None:
                entry_sink(entry)
            if event_sink is not None:
                event_sink(
                    {
                        "event": "wechat_entry_ready",
                        "date": target_day.isoformat(),
                        "source_name": source.name,
                        "source_type": source.type,
                        "url": candidate.url,
                        "title": entry.title,
                        "published_at": entry.published_at.isoformat(),
                        "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                    }
                )

        if not entries:
            warnings.append(f"微信公众号 URL 搜索在昨天窗口内没有可写入的文章：{source.name}")

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        experience = self._make_experience_record(
            source=source,
            strategy="tavily_wechat_article_discovery",
            query_signature=f'site:mp.weixin.qq.com/s/ "{source.name}"',
            query_variant="wechat_title_plus_date",
            candidate_count=len(candidates),
            url_match_count=len(entries),
            published_date_hit_count=published_date_hit_count,
            page_fetch_success_count=page_fetch_success_count,
            fallback_used=fallback_used,
            latency_ms=latency_ms,
            warnings=list(warnings),
            details={"target_date": target_day.isoformat()},
        )
        return entries, warnings, [experience]

    def collect_blog_entries(
        self,
        source: BlogSource,
        target_date: datetime,
        entry_sink: Any | None = None,
        event_sink: Any | None = None,
    ) -> tuple[list[DiaryEntry], list[str], list[SearchExperience]]:
        started_at = time.perf_counter()
        base_url = source.url or source.feed_url
        if not base_url:
            warning = f"博客源缺少 url：{source.name}"
            experience = self._make_experience_record(
                source=source,
                strategy="blog_page_or_feed",
                query_signature="missing_base_url",
                query_variant="none",
                candidate_count=0,
                url_match_count=0,
                published_date_hit_count=0,
                page_fetch_success_count=0,
                fallback_used=False,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                warnings=[warning],
                details={"target_date": target_date.date().isoformat()},
            )
            return [], [warning], [experience]

        target_day = target_date.date()
        warnings: list[str] = []
        entries: list[DiaryEntry] = []
        experiences: list[SearchExperience] = []

        feed_candidates = self._blog_feed_candidates(source)
        feed_success_count = 0
        for feed_url in feed_candidates:
            feed_entries, feed_warnings, feed_experiences = self._collect_blog_feed_entries(
                source=source,
                feed_url=feed_url,
                target_day=target_day,
                entry_sink=entry_sink,
                event_sink=event_sink,
            )
            entries.extend(feed_entries)
            warnings.extend(feed_warnings)
            experiences.extend(feed_experiences)
            if feed_entries:
                feed_success_count += len(feed_entries)

        if entries:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            experiences.append(
                self._make_experience_record(
                    source=source,
                    strategy="blog_page_or_feed",
                    query_signature=base_url,
                    query_variant="feed_first",
                    candidate_count=len(feed_candidates),
                    url_match_count=len(entries),
                    published_date_hit_count=len(entries),
                    page_fetch_success_count=feed_success_count,
                    fallback_used=False,
                    latency_ms=latency_ms,
                    warnings=list(warnings),
                    details={"target_date": target_day.isoformat(), "feed_candidates": feed_candidates},
                )
            )
            return entries, warnings, experiences

        page_entries, page_warnings, page_experiences = self._collect_blog_page_entries(
            source=source,
            base_url=base_url,
            target_day=target_day,
            entry_sink=entry_sink,
            event_sink=event_sink,
        )
        entries.extend(page_entries)
        warnings.extend(page_warnings)
        experiences.extend(page_experiences)

        if not entries:
            warnings.append(f"博客在昨天窗口内没有可写入的文章：{source.name}")

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        experiences.append(
            self._make_experience_record(
                source=source,
                strategy="blog_page_or_feed",
                query_signature=base_url,
                query_variant="page_fallback",
                candidate_count=len(feed_candidates) or len(page_entries) or 1,
                url_match_count=len(entries),
                published_date_hit_count=len(entries),
                page_fetch_success_count=len(page_entries),
                fallback_used=bool(page_entries),
                latency_ms=latency_ms,
                warnings=list(warnings),
                details={"target_date": target_day.isoformat(), "feed_candidates": feed_candidates},
            )
        )

        return entries, warnings, experiences

    def _blog_feed_candidates(self, source: BlogSource) -> list[str]:
        candidates: list[str] = []
        if source.feed_url:
            candidates.append(source.feed_url)
        if source.url:
            base = source.url.rstrip("/")
            candidates.extend(
                [
                    base + "/feed",
                    base + "/feed/",
                    base + "/feed.xml",
                    base + "/rss",
                    base + "/rss.xml",
                    base + "/atom.xml",
                    base + "/index.xml",
                ]
            )
            try:
                html_text = _request_text(source.url, referer=source.url)
            except (HTTPError, URLError):
                html_text = ""
            if html_text:
                parser = _BlogSourceDiscoveryParser(source.url)
                parser.feed(html_text)
                candidates.extend(parser.feed_urls)
        return _dedupe_preserve_order([candidate for candidate in candidates if candidate])

    def _collect_blog_feed_entries(
        self,
        *,
        source: BlogSource,
        feed_url: str,
        target_day: Any,
        entry_sink: Any | None = None,
        event_sink: Any | None = None,
    ) -> tuple[list[DiaryEntry], list[str], list[SearchExperience]]:
        try:
            xml_text = _request_text(feed_url, referer=source.url or feed_url)
        except (HTTPError, URLError) as exc:
            warning = f"博客 feed 抓取失败：{source.name} - {feed_url} - {exc}"
            experience = self._make_experience_record(
                source=source,
                strategy="blog_feed",
                query_signature=feed_url,
                query_variant="feed",
                candidate_count=0,
                url_match_count=0,
                published_date_hit_count=0,
                page_fetch_success_count=0,
                fallback_used=False,
                latency_ms=0,
                warnings=[warning],
                details={"feed_url": feed_url},
            )
            return [], [warning], [experience]

        try:
            from xml.etree import ElementTree as ET

            root = ET.fromstring(xml_text)
        except Exception as exc:
            warning = f"博客 feed 解析失败：{source.name} - {feed_url} - {exc}"
            experience = self._make_experience_record(
                source=source,
                strategy="blog_feed",
                query_signature=feed_url,
                query_variant="feed",
                candidate_count=0,
                url_match_count=0,
                published_date_hit_count=0,
                page_fetch_success_count=0,
                fallback_used=False,
                latency_ms=0,
                warnings=[warning],
                details={"feed_url": feed_url},
            )
            return [], [warning], [experience]

        collected: list[DiaryEntry] = []
        warnings: list[str] = []
        page_fetch_success_count = 0

        for item in root.iter():
            if item.tag.endswith("item"):
                title = _collapse_whitespace("".join(item.findtext("title", default="")))
                link = _collapse_whitespace("".join(item.findtext("link", default="")))
                description = _strip_tags(item.findtext("description", default=""))
                pub_date_text = item.findtext("pubDate") or item.findtext("published") or ""
                try:
                    published_at = parsedate_to_datetime(pub_date_text)
                    if published_at.tzinfo is None:
                        published_at = published_at.replace(tzinfo=UTC)
                    published_at = published_at.astimezone(SHANGHAI_TZ)
                except Exception:
                    continue
                if published_at.date() != target_day:
                    continue
                if not link:
                    continue

                fetched_title, article_text, html_text = _fetch_page_title_and_text(link, referer=feed_url)
                if article_text:
                    page_fetch_success_count += 1
                if not title:
                    title = fetched_title.strip()
                page_published_at = _extract_page_published_at(html_text)
                if page_published_at and page_published_at.date() != target_day:
                    continue
                summary, thinking = self.summarizer.summarize(
                    {
                        "source_name": source.name,
                        "title": title,
                        "abstract": description,
                        "content_url": link,
                    },
                    article_text or description,
                )
                entry = DiaryEntry(
                    title=title or "未命名文章",
                    url=link,
                    summary=summary,
                    thinking=thinking or "技术博客当天新增内容，已自动收录。",
                    source_name=source.name,
                    source_type="blog",
                    published_at=page_published_at or published_at,
                    content_excerpt=_collapse_whitespace((article_text or description)[:500]),
                    raw={
                        "feed_url": feed_url,
                        "page_published_at": page_published_at.isoformat() if page_published_at else "",
                    },
                )
                collected.append(entry)
                if entry_sink is not None:
                    entry_sink(entry)
                if event_sink is not None:
                    event_sink(
                        {
                            "event": "blog_feed_entry_ready",
                            "date": target_day.isoformat(),
                            "source_name": source.name,
                            "source_type": source.type,
                            "url": link,
                            "title": entry.title,
                            "published_at": entry.published_at.isoformat(),
                            "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                        }
                    )

        if collected:
            experience = self._make_experience_record(
                source=source,
                strategy="blog_feed",
                query_signature=feed_url,
                query_variant="feed",
                candidate_count=len(collected),
                url_match_count=len(collected),
                published_date_hit_count=len(collected),
                page_fetch_success_count=page_fetch_success_count,
                fallback_used=page_fetch_success_count < len(collected),
                latency_ms=0,
                warnings=list(warnings),
                details={"feed_url": feed_url},
            )
            return collected, warnings, [experience]
        warning = f"博客 feed 在昨天窗口内没有可写入的文章：{source.name} ({feed_url})"
        experience = self._make_experience_record(
            source=source,
            strategy="blog_feed",
            query_signature=feed_url,
            query_variant="feed",
            candidate_count=0,
            url_match_count=0,
            published_date_hit_count=0,
            page_fetch_success_count=page_fetch_success_count,
            fallback_used=False,
            latency_ms=0,
            warnings=[warning],
            details={"feed_url": feed_url},
        )
        return [], [warning], [experience]

    def _collect_blog_page_entries(
        self,
        *,
        source: BlogSource,
        base_url: str,
        target_day: Any,
        entry_sink: Any | None = None,
        event_sink: Any | None = None,
    ) -> tuple[list[DiaryEntry], list[str], list[SearchExperience]]:
        try:
            html_text = _request_text(base_url, referer=base_url)
        except (HTTPError, URLError) as exc:
            warning = f"博客主页抓取失败：{source.name} - {base_url} - {exc}"
            experience = self._make_experience_record(
                source=source,
                strategy="blog_page",
                query_signature=base_url,
                query_variant="homepage",
                candidate_count=0,
                url_match_count=0,
                published_date_hit_count=0,
                page_fetch_success_count=0,
                fallback_used=False,
                latency_ms=0,
                warnings=[warning],
                details={"base_url": base_url},
            )
            return [], [warning], [experience]

        parser = _BlogSourceDiscoveryParser(base_url)
        parser.feed(html_text)
        candidates = [
            link
            for link in parser.article_links
            if _is_probably_article_url(link, base_url)
        ]
        candidates = _dedupe_preserve_order(candidates)[:25]

        collected: list[DiaryEntry] = []
        warnings: list[str] = []
        page_fetch_success_count = 0
        for content_url in candidates:
            title, article_text, article_html = _fetch_page_title_and_text(content_url, referer=base_url)
            if not article_html:
                continue
            if article_text:
                page_fetch_success_count += 1
            published_at = _extract_page_published_at(article_html)
            if not published_at or published_at.date() != target_day:
                continue
            summary, thinking = self.summarizer.summarize(
                {
                    "source_name": source.name,
                    "title": title,
                    "abstract": "",
                    "content_url": content_url,
                },
                article_text,
            )
            entry = DiaryEntry(
                title=title or "未命名文章",
                url=content_url,
                summary=summary,
                thinking=thinking or "技术博客当天新增内容，已自动收录。",
                source_name=source.name,
                source_type="blog",
                published_at=published_at,
                content_excerpt=_collapse_whitespace(article_text[:500]),
                raw={
                    "page_url": base_url,
                    "page_published_at": published_at.isoformat(),
                },
            )
            collected.append(entry)
            if entry_sink is not None:
                entry_sink(entry)
            if event_sink is not None:
                event_sink(
                    {
                        "event": "blog_page_entry_ready",
                        "date": target_day.isoformat(),
                        "source_name": source.name,
                        "source_type": source.type,
                        "url": content_url,
                        "title": entry.title,
                        "published_at": entry.published_at.isoformat(),
                        "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                    }
                )

        if collected:
            experience = self._make_experience_record(
                source=source,
                strategy="blog_page",
                query_signature=base_url,
                query_variant="homepage",
                candidate_count=len(candidates),
                url_match_count=len(collected),
                published_date_hit_count=len(collected),
                page_fetch_success_count=page_fetch_success_count,
                fallback_used=page_fetch_success_count < len(collected),
                latency_ms=0,
                warnings=list(warnings),
                details={"base_url": base_url},
            )
            return collected, warnings, [experience]
        warning = f"博客主页在昨天窗口内没有可写入的文章：{source.name}"
        experience = self._make_experience_record(
            source=source,
            strategy="blog_page",
            query_signature=base_url,
            query_variant="homepage",
            candidate_count=len(candidates),
            url_match_count=0,
            published_date_hit_count=0,
            page_fetch_success_count=page_fetch_success_count,
            fallback_used=False,
            latency_ms=0,
            warnings=[warning],
            details={"base_url": base_url},
        )
        return [], [warning], [experience]

    def collect_rss_entries(
        self,
        source: BlogSource,
        target_date: datetime,
        entry_sink: Any | None = None,
        event_sink: Any | None = None,
    ) -> tuple[list[DiaryEntry], list[str], list[SearchExperience]]:
        if not source.feed_url:
            warning = f"RSS 源缺少 feed_url：{source.name}"
            experience = self._make_experience_record(
                source=source,
                strategy="rss",
                query_signature="missing_feed_url",
                query_variant="rss",
                candidate_count=0,
                url_match_count=0,
                published_date_hit_count=0,
                page_fetch_success_count=0,
                fallback_used=False,
                latency_ms=0,
                warnings=[warning],
                details={},
            )
            return [], [warning], [experience]

        try:
            xml_text = _request_text(source.feed_url)
        except (HTTPError, URLError) as exc:
            warning = f"RSS 抓取失败：{source.name} - {exc}"
            experience = self._make_experience_record(
                source=source,
                strategy="rss",
                query_signature=source.feed_url,
                query_variant="rss",
                candidate_count=0,
                url_match_count=0,
                published_date_hit_count=0,
                page_fetch_success_count=0,
                fallback_used=False,
                latency_ms=0,
                warnings=[warning],
                details={"feed_url": source.feed_url},
            )
            return [], [warning], [experience]

        try:
            from xml.etree import ElementTree as ET

            root = ET.fromstring(xml_text)
        except Exception as exc:
            warning = f"RSS 解析失败：{source.name} - {exc}"
            experience = self._make_experience_record(
                source=source,
                strategy="rss",
                query_signature=source.feed_url,
                query_variant="rss",
                candidate_count=0,
                url_match_count=0,
                published_date_hit_count=0,
                page_fetch_success_count=0,
                fallback_used=False,
                latency_ms=0,
                warnings=[warning],
                details={"feed_url": source.feed_url},
            )
            return [], [warning], [experience]

        target_day = target_date.date()
        entries: list[DiaryEntry] = []
        page_fetch_success_count = 0
        for item in root.findall(".//item"):
            title = _normalize_spaces("".join(item.findtext("title", default="")))
            link = _normalize_spaces("".join(item.findtext("link", default="")))
            description = _strip_tags(item.findtext("description", default=""))
            pub_date_text = item.findtext("pubDate") or item.findtext("published") or ""
            try:
                published_at = parsedate_to_datetime(pub_date_text)
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=UTC)
                published_at = published_at.astimezone(SHANGHAI_TZ)
            except Exception:
                continue
            if published_at.date() != target_day:
                continue

            summary, thinking = self.summarizer.summarize(
                {
                    "source_name": source.name,
                    "title": title,
                    "abstract": description,
                    "content_url": link,
                },
                description,
            )
            if description:
                page_fetch_success_count += 1
            entry = DiaryEntry(
                title=title or "未命名文章",
                url=link,
                summary=summary,
                thinking=thinking or "RSS 源当天新增内容，已自动收录。",
                source_name=source.name,
                source_type="rss",
                published_at=published_at,
                content_excerpt=description[:500],
                raw={"description": description, "pubDate": pub_date_text},
            )
            entries.append(entry)
            if entry_sink is not None:
                entry_sink(entry)
            if event_sink is not None:
                event_sink(
                    {
                        "event": "rss_entry_ready",
                        "date": target_day.isoformat(),
                        "source_name": source.name,
                        "source_type": source.type,
                        "url": link,
                        "title": entry.title,
                        "published_at": entry.published_at.isoformat(),
                        "timestamp": datetime.now(tz=SHANGHAI_TZ).isoformat(),
                    }
                )

        if not entries:
            warning = f"RSS 在昨天窗口内没有可写入的文章：{source.name}"
            experience = self._make_experience_record(
                source=source,
                strategy="rss",
                query_signature=source.feed_url,
                query_variant="rss",
                candidate_count=0,
                url_match_count=0,
                published_date_hit_count=0,
                page_fetch_success_count=page_fetch_success_count,
                fallback_used=False,
                latency_ms=0,
                warnings=[warning],
                details={"feed_url": source.feed_url},
            )
            return [], [warning], [experience]
        experience = self._make_experience_record(
            source=source,
            strategy="rss",
            query_signature=source.feed_url,
            query_variant="rss",
            candidate_count=len(entries),
            url_match_count=len(entries),
            published_date_hit_count=len(entries),
            page_fetch_success_count=page_fetch_success_count,
            fallback_used=page_fetch_success_count < len(entries),
            latency_ms=0,
            warnings=[],
            details={"feed_url": source.feed_url},
        )
        return entries, [], [experience]

    def _dedupe_entries(self, entries: list[DiaryEntry]) -> list[DiaryEntry]:
        seen: set[str] = set()
        unique: list[DiaryEntry] = []
        for entry in entries:
            if entry.key in seen:
                continue
            seen.add(entry.key)
            unique.append(entry)
        return unique

    def _write_raw_snapshot(self, target_date: datetime, entries: list[DiaryEntry], warnings: list[str]) -> dict[str, Any]:
        raw_root = self.repo_root / str(self.config.get("raw_root", "data/raw/wechat"))
        raw_root.mkdir(parents=True, exist_ok=True)
        path = raw_root / f"{target_date.strftime('%Y-%m-%d')}.json"
        payload = {
            "date": target_date.date().isoformat(),
            "generated_at": datetime.now(tz=SHANGHAI_TZ).isoformat(),
            "entry_count": len(entries),
            "warnings": warnings,
            "entries": [entry.to_raw_dict() for entry in entries],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"path": str(path), "written": True}

    def _yesterday_in_shanghai(self) -> datetime:
        return datetime.now(tz=SHANGHAI_TZ) - timedelta(days=1)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch blog and WeChat updates into diary drafts.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Config path relative to repo root.")
    parser.add_argument("--date", default="", help="Target date in YYYY-MM-DD format. Defaults to yesterday in Asia/Shanghai.")
    parser.add_argument("--dry-run", action="store_true", help="Print result without writing files.")
    parser.add_argument("--json", action="store_true", help="Print JSON output only.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    service = BlogDiaryService(args.config)
    target_date = None
    if args.date:
        target_date = datetime.fromisoformat(args.date).replace(tzinfo=SHANGHAI_TZ)

    result = service.run(target_date=target_date, dry_run=args.dry_run)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json:
        print(output)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
