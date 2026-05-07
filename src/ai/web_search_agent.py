import asyncio
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path

import yaml

from src.ai.types import WebSearchResult, WebExtractResult, WebCrawlResult, WebMapResult


SearchProvider = Callable[[str], list[str]]
AsyncSearchProvider = Callable[[str], Awaitable[list[str]]]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_yaml_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_tavily_config() -> dict:
    """加载 Tavily 配置，兼容旧的 llm_api.yaml 和新的 web_search.yaml。"""
    legacy_config = _load_yaml_config(_repo_root() / "config" / "llm_api.yaml").get("tavily", {})
    web_config = load_web_search_config().get("tavily", {})
    return {**(legacy_config or {}), **(web_config or {})}


def create_tavily_provider():
    """创建 Tavily 搜索 provider 函数"""
    from tavily import TavilyClient

    config = load_tavily_config()
    api_key = config.get("api_key")
    if not api_key:
        raise ValueError("Tavily API key 未配置，请检查 config/web_search.yaml 或 config/llm_api.yaml")

    client = TavilyClient(api_key=api_key)

    def provider(query: str) -> list[str]:
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=5,
            include_answer=False,
            include_raw_content=False,
        )
        results = response.get("results", [])
        return [r.get("content", "") for r in results if r.get("content")]

    return provider


class WebSearchAgent:
    def __init__(
        self,
        *,
        enabled: bool = False,
        provider: SearchProvider | None = None,
        async_provider: AsyncSearchProvider | None = None,
        provider_error: str | None = None,
    ):
        self.enabled = enabled
        self.provider = provider
        self.async_provider = async_provider
        self.provider_error = provider_error

    def search(self, query: str) -> WebSearchResult:
        """网页搜索，返回文本片段列表"""
        if not self.enabled:
            return WebSearchResult(
                enabled=False,
                used=False,
                message="WebSearchAgent 已预留接口，但当前 MVP 默认禁用联网搜索。",
            )

        if self.provider_error:
            return WebSearchResult(
                enabled=True,
                used=False,
                message=self.provider_error,
            )

        if not self.provider and not self.async_provider:
            return WebSearchResult(
                enabled=True,
                used=False,
                message="WebSearchAgent 已启用，但尚未配置具体 web search provider。",
            )

        try:
            if self.async_provider:
                snippets = self._run_async_provider(query)
            elif self.provider:
                snippets = self.provider(query)
            else:
                snippets = []
        except Exception as exc:
            return WebSearchResult(
                enabled=True,
                used=False,
                message=f"外部搜索 provider 执行失败：{exc}",
            )

        return WebSearchResult(
            enabled=True,
            used=bool(snippets),
            snippets=snippets,
            message=None if snippets else "外部搜索没有返回可用结果。",
        )

    def _run_async_provider(self, query: str) -> list[str]:
        if not self.async_provider:
            return []

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.async_provider(query))

        result: list[str] = []
        error: BaseException | None = None

        def runner() -> None:
            nonlocal result, error
            try:
                result = asyncio.run(self.async_provider(query))
            except BaseException as exc:
                error = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()

        if error:
            raise error
        return result

    def extract(self, urls: str | list[str]) -> WebExtractResult:
        """从指定 URL 提取网页内容"""
        if not self.enabled:
            return WebExtractResult(
                enabled=False,
                used=False,
                message="WebSearchAgent 未启用。",
            )

        from tavily import TavilyClient

        config = load_tavily_config()
        client = TavilyClient(api_key=config["api_key"])

        response = client.extract(urls=urls, include_images=False)
        results = response.get("results", [])
        failed_results = response.get("failed_results", [])

        return WebExtractResult(
            enabled=True,
            used=True,
            results=results,
            failed_results=failed_results,
            message=None if results else "提取没有返回可用结果。",
        )

    def crawl(self, url: str, instructions: str | None = None, **kwargs) -> WebCrawlResult:
        """智能爬取，从指定 URL 开始图遍历并提取内容"""
        if not self.enabled:
            return WebCrawlResult(
                enabled=False,
                used=False,
                message="WebSearchAgent 未启用。",
            )

        from tavily import TavilyClient

        config = load_tavily_config()
        client = TavilyClient(api_key=config["api_key"])

        params = {"url": url}
        if instructions:
            params["instructions"] = instructions
        params.update(kwargs)

        response = client.crawl(**params)
        base_url = response.get("base_url", "")
        results = response.get("results", [])

        return WebCrawlResult(
            enabled=True,
            used=True,
            base_url=base_url,
            results=results,
            message=None if results else "爬取没有返回可用结果。",
        )

    def map(self, url: str, instructions: str | None = None, **kwargs) -> WebMapResult:
        """站点图，生成 URL 列表（不返回内容）"""
        if not self.enabled:
            return WebMapResult(
                enabled=False,
                used=False,
                message="WebSearchAgent 未启用。",
            )

        from tavily import TavilyClient

        config = load_tavily_config()
        client = TavilyClient(api_key=config["api_key"])

        params = {"url": url}
        if instructions:
            params["instructions"] = instructions
        params.update(kwargs)

        response = client.map(**params)
        base_url = response.get("base_url", "")
        results = response.get("results", [])

        return WebMapResult(
            enabled=True,
            used=True,
            base_url=base_url,
            results=results,
            message=None if results else "站点图没有返回可用 URL。",
        )


def load_web_search_config() -> dict:
    """从 config/web_search.yaml 加载配置"""
    return _load_yaml_config(_repo_root() / "config" / "web_search.yaml")


def create_enabled_web_agent():
    """创建启用状态的 WebSearchAgent（根据 config 选择 provider）"""
    cfg = load_web_search_config()
    if not cfg.get("enabled", False):
        return WebSearchAgent(enabled=False)

    provider_name = cfg.get("provider", "disabled")

    if provider_name == "open_websearch":
        try:
            from src.ai.providers.open_websearch import mcp_search_async
        except ModuleNotFoundError as exc:
            if exc.name != "mcp":
                raise
            return WebSearchAgent(
                enabled=True,
                provider_error="Open-WebSearch provider 缺少 Python 依赖 `mcp`，请运行 `uv add mcp` 后重启后端，或在 config/web_search.yaml 中禁用 web search。",
            )

        provider_config = cfg.get("open_websearch", {}) or {}
        engines = provider_config.get("engines") or None
        limit = int(provider_config.get("limit", 10))

        async def provider(query: str) -> list[str]:
            return await mcp_search_async(query, engines=engines, limit=limit)

        return WebSearchAgent(
            enabled=True,
            async_provider=provider,
        )
    elif provider_name == "tavily":
        try:
            provider = create_tavily_provider()
        except (ModuleNotFoundError, ValueError) as exc:
            return WebSearchAgent(enabled=True, provider_error=str(exc))
        return WebSearchAgent(enabled=True, provider=provider)
    else:
        return WebSearchAgent(enabled=False)
