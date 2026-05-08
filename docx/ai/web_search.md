# Web Search 方案调研

## 方案概览

| 类型 | 方案 | 价格 | 特点 |
|------|------|------|------|
| API | Tavily | 1000次/月免费 | AI 优化结果，自动提取核心内容 |
| API | SerpApi | 250次/月免费 | Google 全功能，数据最全 |
| API | Google Search API | 按量计费 | 官方 API |
| SDK | Claude Code 内置 | - | 通过工具调用，claude-code 专属 |
| MCP | Brave Search | 免费 | Anthropic 官方推荐，独立索引，隐私优先 |
| MCP | Tavily | - | AI 优化，自动提取内容 |
| MCP | Exa MCP | - | 语义搜索，代码搜索强 |
| MCP | PlaywrightMCP | - | 网页内容抓取 |
| MCP | Open-WebSearch | 免费 | 开源多引擎（Bing/DuckDuckGo） |
| Skill | duckduckgo-search | 免费 | 已有脚本，网络访问受限 |

## 方案对比

### 1. API 类

#### Tavily
- **官网**: tavily.com
- **定价**: 1000次/月 免费（付费从 $5/月 起）
- **优点**: AI 优化搜索结果、自动提取正文、效果好
- **缺点**: 有额度限制、需要 API Key
- **详细文档**: `reference/tavily_sdk_reference.md`

#### SerpApi
- **官网**: serpapi.com
- **定价**: 250次/月 免费（付费从 $50/月 起）
- **优点**: Google 全功能覆盖、数据最全
- **缺点**: 价格较高

#### Google Search API
- **优点**: 官方 API，稳定
- **缺点**: 需要信用卡、按次计费

### 2. MCP 类

#### Brave Search（推荐）
- **官网**: brave.com/search/api
- **定价**: 免费/按量
- **优点**:
  - Anthropic 官方推荐
  - 独立索引，隐私优先
  - 支持 Web Search 和 Local Search
  - 可以直接获取正文（snippet）
- **缺点**: 需要申请 API Key

#### Tavily MCP
- **优点**: AI 优化结果，效果好
- **缺点**: 与 Tavily API 共享额度

#### Exa MCP
- **官网**: exa.ai
- **优点**: 语义搜索强、代码搜索能力强
- **缺点**: 收费

#### Open-WebSearch
- **官网**: cloud.tencent.com/developer/mcp/server/11739
- **定价**: 完全免费
- **优点**: 开源多引擎（Bing/DuckDuckGo）
- **缺点**: 国内访问不稳定
- **具体实现**: `reference/open-websearch/`（开源项目源代码）

#### PlaywrightMCP
- **优点**: 可以抓取动态网页内容
- **缺点**: 需要浏览器环境

### 3. SDK / 工具调用类

#### Claude Code 内置 Web Search/Fetch
- **使用方式**: 通过 `mcp__web` 工具调用
- **优点**: Claude Code 直接集成，无需额外配置
- **缺点**: 只在 Claude Code 环境可用，非通用方案

### 4. Skill 类

#### duckduckgo-search（已有）
- **路径**: `.claude/skills/duckduckgo-search/`
- **现状**: 脚本已存在，但网络访问受限（被墙）
- **问题**: 无法在大陆直接访问 DuckDuckGo

## 建议方案

### MVP 阶段（推荐）

**已实现**: Tavily API

已在 `src/ai/web_search_agent.py` 中实现：
- `create_tavily_provider()` 函数，调用 Tavily Search API
- API Key 配置于 `config/llm_api.yaml`
- 安装: `uv pip install tavily-python`

**备选**: Brave Search MCP

如需切换，可申请 Brave Search API：
- Anthropic 官方推荐
- 隐私优先，独立索引
- 免费额度够用

### 长期方案

**Brave Search MCP + PlaywrightMCP**

- Brave Search 负责搜索和摘要
- PlaywrightMCP 负责深度抓取需要登录的页面

## 实现建议

1. **优先测试 Brave Search MCP**
   - 申请 API Key
   - 配置 MCP server
   - 测试搜索效果

2. **降级方案**
   - 如果 Brave Search 不稳定
   - 回退到 duckduckgo-search（需要代理）
   - 或 Tavily API

3. **集成方式**
   - 后端通过 MCP 协议调用
   - 参考 Claude Code 的 mcp 工具调用方式
   - 保持与现有 duckduckgo-search 脚本的接口兼容

## 参考链接

- Brave Search API: https://api.search.brave.com/app/documentation/web-search/get-started
- Tavily: https://tavily.com
- SerpApi: https://serpapi.com
- Open-WebSearch MCP: https://cloud.tencent.com/developer/mcp/server/11739
- Exa: https://exa.ai