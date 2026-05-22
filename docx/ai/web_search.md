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

## 经验沉淀机制

这套机制的目标不是“每次都把搜索跑出来”，而是把每次搜索、抓取、过滤和回退的表现沉淀下来，让下一次在相似场景里直接复用历史经验。

### 1. 统一接口

- 对上层只暴露一个结构化入口
- 输入是 `query`、`source_name`、`date_window`、`search_scope`
- 输出不是一堆原始文本，而是结构化证据包：
  - 命中的 URL 列表
  - 已解析正文
  - 发布时间
  - 失败 warning
  - 这次最终采用的策略

### 2. 场景分析

每次搜索前先显式记录场景特征，避免把“公众号文章发现”和“通用网页搜索”混为一谈。

建议记录：
- 任务类型：公众号文章发现 / 工程博客发现 / 深度网页抓取
- 来源类型：微信公众号 / 博客 / RSS / 通用搜索
- 时间窗口：昨天、最近 24 小时、指定日期
- query 风格：公众号名、关键词、带日期、带站点限定
- 复杂度：单篇、批量、是否需要正文补抓
- 约束：是否必须只保留 `mp.weixin.qq.com/s/...`

### 3. 经验记忆

每次执行都落一条经验记录，后续先查经验再搜。

建议字段：
- `query_signature`
- `source_name`
- `provider`
- `query_variant`
- `candidate_count`
- `url_match_count`
- `published_date_hit_rate`
- `page_fetch_success_rate`
- `latency_ms`
- `warnings`
- `final_strategy`

经验可以先落在 JSONL 或 SQLite：
- MVP：`data/raw/web_search/experience.jsonl`
- 稳定后：SQLite 表，便于按公众号名、日期窗、query variant 做聚合分析

### 4. 策略路由

系统不应该每次从 0 决定怎么搜，而应该根据场景特征和历史经验选策略。

公众号场景推荐的路由逻辑：
- 公众号名明确时，优先 `site:mp.weixin.qq.com/s/ "公众号名"`
- 命中率不足时，再补 `公众号名 + 微信公众号`
- 仍不足时，再补日期窗口 query
- Tavily 有 `published_date` 时优先用它
- 没有 `published_date` 时再读文章页发布时间

### 5. 检索器池

把真正执行搜索的能力当成一个“检索器池”，而不是一个固定函数。

可包含：
- Tavily 搜索
- Brave Search
- 站内页抓取
- 文章页正文抽取
- RSS / feed 解析

公众号场景里，检索器池的最小闭环是：
1. Tavily 发现文章 URL
2. 微信文章页抓正文
3. 时间校验
4. 摘要生成

### 6. 结果打包

不要把原始搜索结果直接抛给上层。上层拿到的应该是一个“证据包”。

建议结构：
- `selected_urls`
- `selected_articles`
- `fallback_used`
- `warnings`
- `raw_snapshot_path`
- `experience_record_path`

这样下次就可以：
- 先看历史上同类公众号用哪个 query variant 命中率最高
- 先看哪种检索器最稳定
- 先看正文抓取失败是不是集中在某类站点

### 7. 对公众号抓取的具体经验

- 输入是公众号名，不是主页 URL
- 优先搜索文章页 `mp.weixin.qq.com/s/...`，不要依赖 `profile_url`
- 同一公众号保留多个 query variant，但最终结果必须按 URL 去重
- 只保留昨天窗口内的文章
- 正文抓取失败时允许降级到摘要，但要记录 warning
- 每次抓取都保留 raw 结果，方便回溯和补抓

### 8. 为什么要沉淀经验

因为不同公众号、不同时间窗口、不同搜索引擎的最优策略不一样。

系统如果不沉淀经验，就会每次重新做一次“我要怎么搜”的推理；
一旦经验沉淀下来，Agent 或脚本就可以直接复用：
- 哪个 query variant 更准
- 哪个 provider 更稳
- 哪个时间窗更容易命中
- 哪类文章页更容易抓到正文

## 参考链接

- Brave Search API: https://api.search.brave.com/app/documentation/web-search/get-started
- Tavily: https://tavily.com
- SerpApi: https://serpapi.com
- Open-WebSearch MCP: https://cloud.tencent.com/developer/mcp/server/11739
- Exa: https://exa.ai
