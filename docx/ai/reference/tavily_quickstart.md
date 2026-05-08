# Tavily Quickstart

## 安装

```bash
pip install tavily-python
```

## 快速开始

### 搜索

```python
from tavily import TavilyClient

tavily_client = TavilyClient(api_key="tvly-YOUR_API_KEY")
response = tavily_client.search("Who is Leo Messi?")

print(response)
```

### 提取网页内容

```python
from tavily import TavilyClient

tavily_client = TavilyClient(api_key="tvly-YOUR_API_KEY")
response = tavily_client.extract("https://en.wikipedia.org/wiki/Lionel_Messi")

print(response)
```

### 智能爬取

```python
from tavily import TavilyClient

tavily_client = TavilyClient(api_key="tvly-YOUR_API_KEY")
response = tavily_client.crawl("https://docs.tavily.com", instructions="Find all pages on the Python SDK")

print(response)
```

## 获取 API Key

访问 https://app.tavily.com 注册，每月免费 1000 Credits，无需信用卡。

**API Key 配置位置**: `config/llm_api.yaml`

## 功能特性

| 功能 | 方法 | 说明 |
|------|------|------|
| 搜索 | `client.search()` | 完整的 Tavily Search 功能 |
| 提取 | `client.extract()` | 从 URL 提取网页内容 |
| 爬取 | `client.crawl()` | 智能图遍历网站并提取内容 |
| 站点图 | `client.map()` | 生成站点 URL 地图 |

## 相关链接

- Python SDK 完整文档: `reference/tavily_sdk_reference.md`
- GitHub: https://github.com/tavily-ai/tavily-python
- PyPI: https://pypi.org/project/tavily-python