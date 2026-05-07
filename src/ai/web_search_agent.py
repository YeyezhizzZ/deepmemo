"""
WebSearch Agent - 集成网页搜索、提取、爬取、站点图功能。

当前支持的 provider:
  - Tavily: 配置于 `config/llm_api.yaml` 的 `tavily.api_key`

启用方式: 初始化时传入 provider 函数
示例:
    from src.ai.providers.tavily import create_tavily_provider
    agent = WebSearchAgent(enabled=True, provider=create_tavily_provider())
"""

import asyncio
from collections.abc import Callable, Coroutine

import yaml
from pathlib import Path

from src.ai.types import WebSearchResult, WebExtractResult, WebCrawlResult, WebMapResult


def load_tavily_config() -> dict:
    """从 config/llm_api.yaml 加载 Tavily 配置"""
    config_file = Path(__file__).parent.parent.parent / "config" / "llm_api.yaml"
    with open(config_file) as f:
        cfg = yaml.safe_load(f)
    return cfg.get("tavily", {})


def create_tavily_provider():
    """创建 Tavily 搜索 provider 函数"""
    from tavily import TavilyClient

    config = load_tavily_config()
    api_key = config.get("api_key")
    if not api_key:
        raise ValueError("Tavily API key 未配置，请检查 config/llm_api.yaml")

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
        provider: Callable[[str], list[str]] | None = None,
        async_provider: Callable[[str], Coroutine] | None = None,
    ):
        self.enabled = enabled
        self.provider = provider
        self.async_provider = async_provider

    def search(self, query: str) -> WebSearchResult:
        """网页搜索，返回文本片段列表"""
        if not self.enabled:
            return WebSearchResult(
                enabled=False,
                used=False,
                message="WebSearchAgent 已预留接口，但当前 MVP 默认禁用联网搜索。",
            )

        if not self.provider and not self.async_provider:
            return WebSearchResult(
                enabled=True,
                used=False,
                message="WebSearchAgent 已启用，但尚未配置具体 web search provider。",
            )

        if self.async_provider:
            snippets = asyncio.run(self.async_provider(query))
        else:
            snippets = self.provider(query)

        return WebSearchResult(
            enabled=True,
            used=bool(snippets),
            snippets=snippets,
            message=None if snippets else "外部搜索没有返回可用结果。",
        )

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
    config_file = Path(__file__).parent.parent.parent / "config" / "web_search.yaml"
    with open(config_file) as f:
        return yaml.safe_load(f)


def create_enabled_web_agent():
    """创建启用状态的 WebSearchAgent（根据 config 选择 provider）"""
    cfg = load_web_search_config()
    provider_name = cfg.get("provider", "disabled")

    if provider_name == "open_websearch":
        from src.ai.providers.open_websearch import mcp_search_async
        return WebSearchAgent(
            enabled=True,
            async_provider=mcp_search_async,
        )
    elif provider_name == "tavily":
        return WebSearchAgent(
            enabled=True,
            provider=create_tavily_provider(),
        )
    else:
        return WebSearchAgent(enabled=False)