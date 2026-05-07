"""
Open-WebSearch MCP provider for WebSearchAgent.

Uses the Model Context Protocol (MCP) to communicate with the Open-WebSearch server
running in stdio mode.

Usage:
    from src.ai.providers.open_websearch import mcp_search_sync
    snippets = mcp_search_sync("今天天气如何")
"""

import asyncio
import json
from pathlib import Path

from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession


def _get_open_websearch_path() -> str:
    """Get the absolute path to the Open-WebSearch build index.js"""
    repo_root = Path(__file__).parent.parent.parent.parent
    return str(repo_root / "reference" / "open-webSearch" / "build" / "index.js")


async def mcp_search_async(
    query: str,
    engines: list[str] | None = None,
    limit: int = 10,
) -> list[str]:
    """
    Async web search via Open-WebSearch MCP.

    Args:
        query: Search query string
        engines: List of search engines to use (default: ["bing"])
        limit: Maximum number of results (default: 10)

    Returns:
        List of snippets in format "title: description"
    """
    open_websearch_path = _get_open_websearch_path()
    server_params = StdioServerParameters(
        command="node",
        args=[open_websearch_path],
        env={"MODE": "stdio"},
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            result = await session.call_tool(
                "search",
                arguments={
                    "query": query,
                    "limit": limit,
                    "engines": engines or ["bing"],
                },
            )

            if result.isError:
                return []

            # Parse JSON from content[0].text
            if not result.content or not hasattr(result.content[0], "text"):
                return []

            try:
                data = json.loads(result.content[0].text)
            except json.JSONDecodeError:
                return []

            results_list = data.get("results", [])
            snippets = []
            for item in results_list:
                title = item.get("title", "")
                description = item.get("description", "")
                snippets.append(f"{title}: {description}")

            return snippets


def mcp_search_sync(query: str, engines: list[str] | None = None, limit: int = 10) -> list[str]:
    """
    Synchronous wrapper for mcp_search_async.
    Use this for sync contexts (non-async endpoints).
    """
    return asyncio.run(mcp_search_async(query, engines, limit))
