# Tavily API 文档

## 基础信息

- **官网**: https://tavily.com
- **API Base URL**: `https://api.tavily.com`
- **认证方式**: API Key（通过 `Authorization: Bearer` header 传递）
- **SDK**: 提供 Python（同步/异步）和 JavaScript SDK

## 获取 API Key

访问 https://app.tavily.com 注册，每月免费 1000 Credits，无需信用卡。

**API Key 配置位置**: `config/llm_api.yaml`

## 客户端初始化

### 同步客户端

```python
from tavily import TavilyClient

client = TavilyClient("tvly-YOUR_API_KEY")
```

### 异步客户端

```python
from tavily import AsyncTavilyClient

client = AsyncTavilyClient("tvly-YOUR_API_KEY")
```

### 项目隔离

```python
# 方式一：初始化时传入
client = TavilyClient("tvly-YOUR_API_KEY", project_id="your-project-id")

# 方式二：环境变量
import os
os.environ["TAVILY_PROJECT"] = "your-project-id"
client = TavilyClient("tvly-YOUR_API_KEY")
```

### 代理配置

```python
proxies = {
  "http": "<your HTTP proxy>",
  "https": "<your HTTPS proxy>",
}
client = TavilyClient("tvly-YOUR_API_KEY", proxies=proxies)
```

## 费用说明

| 功能 | 费用 |
|------|------|
| `basic` 搜索 | 1 Credit / 请求 |
| `advanced` 搜索 | 2 Credits / 请求 |
| `basic` 提取 | 1 Credit / 5 个成功提取的 URL |
| `advanced` 提取 | 2 Credits / 5 个成功提取的 URL |
| Crawl/Map（无 instructions） | 1 Credit / 10 页 |
| Crawl/Map（有 instructions） | 2 Credits / 10 页 |

## 核心接口

### 1. Search API

**端点**: `POST /search`
**SDK 方法**: `client.search(query, **kwargs)`

执行搜索查询，返回 AI 优化的搜索结果。

#### 请求参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | **必填** | 搜索查询词 |
| `search_depth` | string | `"basic"` | 搜索深度：`"basic"` / `"advanced"` |
| `topic` | string | `"general"` | 搜索类别：`"general"` / `"news"` / `"finance"` |
| `time_range` | string | null | 时间范围：`"day"` / `"week"` / `"month"` / `"year"` 或 `"d"`/`"w"`/`"m"`/`"y"` |
| `start_date` | string | null | 开始日期（YYYY-MM-DD） |
| `end_date` | string | null | 结束日期（YYYY-MM-DD） |
| `max_results` | int | 5 | 最大返回结果数（0-20） |
| `chunks_per_source` | int | 3 | 每来源返回的 chunk 数量（仅 `advanced` 深度可用） |
| `include_images` | bool | false | 包含图片列表 |
| `include_image_descriptions` | bool | false | 图片添加 LLM 生成的描述 |
| `include_answer` | bool/string | false | 包含 LLM 生成的答案（`"basic"`/`"advanced"`） |
| `include_raw_content` | bool/string | false | 包含原始 HTML（`"markdown"`/`"text"`） |
| `include_domains` | list | [] | 限定来源域名（最多 300 个） |
| `exclude_domains` | list | [] | 排除的域名（最多 150 个） |
| `country` | string | null | 结果优先的国家（topic 为 `general` 时可用） |
| `auto_parameters` | bool | false | 自动配置搜索参数（可能自动使用 `advanced`） |
| `exact_match` | bool | false | 精确匹配短语（用引号包裹查询词） |
| `include_favicon` | bool | false | 包含网站 favicon |
| `include_usage` | bool | false | 包含用量信息 |
| `timeout` | float | 60 | 请求超时秒数 |

#### 响应字段

```json
{
  "query": "Who is Leo Messi?",
  "results": [
    {
      "title": "Source 1 Title",
      "url": "Source 1 URL",
      "content": "Source 1 Content（AI 提取的最相关片段）",
      "score": 0.99,
      "raw_content": "完整 HTML 内容（当 include_raw_content=true）",
      "published_date": "2024-01-15（仅 news 主题）",
      "favicon": "https://example.com/favicon.ico",
      "images": [{"url": "...", "description": "..."}]
    }
  ],
  "answer": "LLM 生成的答案（当 include_answer=true）",
  "images": [{"url": "...", "description": "..."}],
  "response_time": 1.09,
  "request_id": "123e4567-e89b-12d3-a456-426614174111"
}
```

#### Python 示例

```python
from tavily import TavilyClient

client = TavilyClient(api_key="tvly-YOUR_API_KEY")
response = client.search(
    query="Who is Leo Messi?",
    include_images=True,
    include_image_descriptions=True,
    search_depth="advanced",
    max_results=5
)
print(response)
```

#### Exact Match 示例

```python
response = client.search(
    query='"John Smith" CEO Acme Corp',
    exact_match=True
)
```

---

### 2. Extract API

**端点**: `POST /extract`
**SDK 方法**: `client.extract(urls, **kwargs)`

从指定 URL 提取网页内容，支持批量处理（最多 20 个 URL）。

#### 请求参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `urls` | string/list | **必填** | 单个 URL 或 URL 列表（最多 20 个） |
| `query` | string | null | 用户意图，用于对提取内容块进行重排序 |
| `chunks_per_source` | int | 3 | 每来源返回的 chunk 数量（1-5，仅当 `query` 提供时可用） |
| `extract_depth` | string | `"basic"` | 提取深度：`"basic"` / `"advanced"`（后者提取表格等更多数据） |
| `include_images` | bool | false | 在响应中包含图片列表 |
| `include_favicon` | bool | false | 包含网站 favicon |
| `format` | string | `"markdown"` | 内容格式：`"markdown"` / `"text"` |
| `timeout` | float | null | 超时秒数（basic 默认 10s，advanced 默认 30s，1-60 秒） |
| `include_usage` | bool | false | 包含用量信息 |

#### 响应字段

```json
{
  "results": [
    {
      "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
      "raw_content": "提取的正文内容（当 query 提供时为顶部 chunk 以 [...] 分隔）",
      "images": ["https://..."],
      "favicon": "https://wikipedia.org/favicon.ico"
    }
  ],
  "failed_results": [
    {"url": "https://failed.com", "error": "错误原因"}
  ],
  "response_time": 1.23,
  "request_id": "123e4567-e89b-12d3-a456-426614174111"
}
```

#### Python 示例

```python
from tavily import TavilyClient

client = TavilyClient(api_key="tvly-YOUR_API_KEY")
response = client.extract(
    urls=[
        "https://en.wikipedia.org/wiki/Artificial_intelligence",
        "https://en.wikipedia.org/wiki/Machine_learning",
        "https://en.wikipedia.org/wiki/Data_science",
    ],
    include_images=True
)
print(response)
```

---

### 3. Crawl API

**端点**: `POST /crawl`
**SDK 方法**: `client.crawl(url, **kwargs)`

基于图遍历的网站抓取工具，可并行探索数百条路径，支持内置提取和智能发现。

#### 请求参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | string | **必填** | 爬取的根 URL |
| `max_depth` | int | 1 | 最大爬取深度（1-5） |
| `max_breadth` | int | 20 | 每层最大跟随链接数（1-500） |
| `limit` | int | 50 | 总共处理的链接数上限 |
| `instructions` | string | null | 自然语言指令（提供后费用变为 2 Credits / 10 页） |
| `select_paths` | list | null | 正则模式，只选择匹配特定路径的 URL（如 `"/docs/.*"`） |
| `select_domains` | list | null | 正则模式，只爬取特定域名（如 `"^docs\.example\.com$"`） |
| `exclude_paths` | list | null | 正则模式，排除匹配路径的 URL（如 `"/private/.*"`） |
| `exclude_domains` | list | null | 正则模式，排除特定域名（如 `"^private\.example\.com$"`） |
| `allow_external` | bool | true | 是否跟随外部域名链接 |
| `include_images` | bool | false | 在爬取结果中包含图片 |
| `extract_depth` | string | `"basic"` | 提取深度：`"basic"` / `"advanced"` |
| `format` | string | `"markdown"` | 内容格式：`"markdown"` / `"text"` |
| `include_favicon` | bool | false | 包含网站 favicon |
| `timeout` | float | 150 | 超时秒数（10-150 秒） |
| `include_usage` | bool | false | 包含用量信息 |
| `chunks_per_source` | int | 3 | 每来源 chunk 数量（1-5，仅当 `instructions` 提供时可用） |

#### 响应字段

```json
{
  "base_url": "https://docs.tavily.com",
  "results": [
    {
      "url": "https://docs.tavily.com/sdk/python/quick-start",
      "raw_content": "页面提取的正文内容",
      "images": ["https://..."],
      "favicon": "https://mintlify.s3-us-west-1.amazonaws.com/tavilyai/_generated/favicon/apple-touch-icon.png?v=3"
    }
  ],
  "response_time": 9.07,
  "request_id": "123e4567-e89b-12d3-a456-426614174111"
}
```

#### Python 示例

```python
from tavily import TavilyClient

client = TavilyClient(api_key="tvly-YOUR_API_KEY")
response = client.crawl(
    url="https://docs.tavily.com",
    instructions="Find information on the Python SDK",
    max_depth=2
)
print(response)
```

---

### 4. Map API

**端点**: `POST /map`
**SDK 方法**: `client.map(url, **kwargs)` 或 `client.mapping(url, **kwargs)`

基于图遍历的站点导航工具，生成完整的站点 URL 地图。（只返回 URL，不返回内容）

#### 请求参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | string | **必填** | 站点图的根 URL |
| `max_depth` | int | 1 | 最大探索深度（1-5） |
| `max_breadth` | int | 20 | 每层最大跟随链接数（1-500） |
| `limit` | int | 50 | 总共处理的链接数上限 |
| `instructions` | string | null | 自然语言指令（提供后费用变为 2 Credits / 10 页） |
| `select_paths` | list | null | 正则模式，只选择匹配特定路径的 URL |
| `select_domains` | list | null | 正则模式，只爬取特定域名 |
| `exclude_paths` | list | null | 正则模式，排除匹配路径的 URL |
| `exclude_domains` | list | null | 正则模式，排除特定域名 |
| `allow_external` | bool | true | 是否在结果中包含外部域名链接 |
| `timeout` | float | 150 | 超时秒数（10-150 秒） |
| `include_usage` | bool | false | 包含用量信息 |

#### 响应字段

```json
{
  "base_url": "https://docs.tavily.com",
  "results": [
    "https://docs.tavily.com/sdk/javascript/quick-start",
    "https://docs.tavily.com/sdk/javascript/reference"
  ],
  "response_time": 8.43,
  "request_id": "123e4567-e89b-12d3-a456-426614174111"
}
```

#### Python 示例

```python
from tavily import TavilyClient

client = TavilyClient(api_key="tvly-YOUR_API_KEY")
response = client.map(
    url="https://docs.tavily.com",
    instructions="Find information on the JavaScript SDK"
)
print(response)
```

---

### 5. Hybrid RAG

**SDK 类**: `TavilyHybridClient`

Tavily Hybrid RAG 是 Search API 的扩展，可同时从网络和本地 MongoDB 数据库检索内容。

#### 初始化参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `api_key` | string | **必填** | Tavily API Key |
| `db_provider` | string | `"mongodb"` | 数据库提供者（目前仅支持 `"mongodb"`） |
| `collection` | object | **必填** | MongoDB collection 引用 |
| `index` | string | **必填** | 向量搜索索引名称 |
| `embeddings_field` | string | `"embeddings"` | 存储 embeddings 的字段名 |
| `content_field` | string | `"content"` | 存储文本内容的字段名 |
| `embedding_function` | function | Cohere | 自定义 embedding 函数 |
| `ranking_function` | function | Cohere Rerank | 自定义排序函数 |

#### search 方法参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | **必填** | 搜索查询 |
| `max_results` | int | 10 | 返回的最大总结果数 |
| `max_local` | int | null | 最大本地（数据库）结果数 |
| `max_foreign` | int | null | 最大外部（网络）结果数 |
| `save_foreign` | bool/function | false | 是否保存网络搜索结果到数据库 |

支持的额外参数：`search_depth`, `topic`, `include_raw_content`, `include_domains`, `exclude_domains`

#### 设置步骤

1. 准备 MongoDB collection 和向量搜索索引
2. 获取 Cohere API Key（用于默认 embedding 和 ranking）
3. 安装依赖：`pip install cohere pymongo`

#### Python 示例

```python
from pymongo import MongoClient
from tavily import TavilyHybridClient

db = MongoClient("mongodb+srv://YOUR_MONGO_URI")["YOUR_DB"]

hybrid_rag = TavilyHybridClient(
    api_key="tvly-YOUR_API_KEY",
    db_provider="mongodb",
    collection=db.get_collection("YOUR_COLLECTION"),
    index="YOUR_VECTOR_SEARCH_INDEX",
    embeddings_field="YOUR_EMBEDDINGS_FIELD",
    content_field="YOUR_CONTENT_FIELD"
)

# 搜索
results = hybrid_rag.search("Who is Leo Messi?", max_results=5)

# 保存网络结果到数据库
results = hybrid_rag.search("Who is Leo Messi?", save_foreign=True)

# 自定义保存函数
def save_document(document):
    if document['score'] < 0.5:
        return None
    return {
        'content': document['content'],
        'site_title': document['title'],
        'site_url': document['url'],
        'added_at': datetime.now()
    }

results = hybrid_rag.search("Who is Leo Messi?", save_foreign=save_document)
```

---

## 错误响应

所有接口共享以下错误响应：

| 状态码 | 说明 |
|--------|------|
| 400 | 请求无效（如未提供 URL、URL 数量超限等） |
| 401 | API Key 缺失或无效 |
| 403 | URL 不支持 |
| 429 | 请求频率超限 |
| 432 | Key 额度或套餐限制超限 |
| 433 | PayGo 额度超限 |
| 500 | 服务器内部错误 |

---

## 与 Claude Code 集成

Tavily 可作为 MCP Server 调用，配合 Claude Code 使用。

## 参考链接

- 完整文档: https://docs.tavily.com
- API Index: https://docs.tavily.com/llms.txt
- 控制台: https://app.tavily.com
- Python SDK: https://docs.tavily.com/sdk/python/reference
- JavaScript SDK: https://docs.tavily.com/sdk/javascript/reference