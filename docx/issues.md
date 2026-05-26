# DeepMemo 问题记录

## Issue 模板

```md
## N. 标题

**类型**: Bug / 功能 / 技术债 / 调研
**状态**: 待确认 / 待实现 / 进行中 / 已修复 / 已完成

**问题描述**: 一句话说明要解决什么。

**目标**: 希望达到的结果。

**涉及位置**:
- `path/to/file.py` - 简要说明

**决策人**: gzy
**备注**: 可选补充。
```

## 1. 硬编码问题

**类型**: 技术债
**问题描述**: 后端读取文件时存在写死内容，优先检索固定目录结构。

**涉及位置**:

1. `src/routers/diary.py` - `AutoDraftRequest.output_dir` 默认值为 `"diary"`
2. `src/app/core/fs_manager.py` - `scan_directory_tree` 固定扫描 `data/` 下的 `diary/`, `ideas/`, `memory/`, `raw/` 子目录
3. `src/app/core/watcher.py` - 固定监听 `.md` 文件

**确认方案**:

### 1. 配置文件负责系统默认规则

新增 `config/fs_config.yaml`，用于管理知识库文件系统的默认规则，避免后端散落硬编码。

建议配置项：

```yaml
knowledge_base:
  root: data
  visible_dirs:
    - diary
    - ideas
    - memory
    - raw
  allowed_extensions:
    - .md
  default_search_dirs:
    - diary
    - ideas
    - memory
```

用途：
- `root`：知识库根目录，替代代码里写死的 `data/`
- `visible_dirs`：前端文件树默认展示的目录
- `allowed_extensions`：Watcher 和文件读取允许处理的文件类型
- `default_search_dirs`：问答模式自动检索的默认目录范围

**决策人**: gzy
**状态**: 已确认（2026-05-04）


## 2. 没有多轮对话机制

**类型**: 功能
**现状**: 当前问答更接近单轮 RAG，每次请求主要围绕本轮 `user_message` 做路由、检索和回答，没有稳定地把同一会话内的历史消息纳入上下文。

**问题影响**:
- 用户追问“继续展开”“刚才那个文件”“第二点是什么意思”时，后端缺少上一轮语义上下文，容易答非所问
- 对话无法自然沉淀为连续任务，例如连续改稿、连续研究、逐步整理笔记
- Tool 和引用结果只作用于单轮时，后续追问难以复用前文已经建立的上下文

**实现思路**:

### 1. 会话历史作为独立上下文层

后端 `ChatRequest` 继续保留 `session_id`，处理请求时按 `session_id` 从数据库读取最近若干轮消息，构建 conversation history。

建议策略：
- 默认读取最近 6-10 轮用户 / AI 消息
- 只把对话正文、已选工具和必要的引用摘要纳入 history
- 不把完整 citation 原文反复塞入 prompt，避免 token 膨胀
- 历史消息和本轮检索 evidence 分层组织，最终由 AnswerComposer 统一组装

### 2. 多轮追问先做上下文改写
第一次消息不做query rewrite，之后的消息在进入检索前，新增 query rewrite 步骤，把依赖上下文的追问改写成独立问题。

示例：
- 用户追问：`第二点再展开一下`
- 历史上下文：上一轮回答列出了“导出按钮分享链接方案”的三点
- 改写后查询：`导出按钮分享链接方案中的第二点，即后端生成 share_id 和保存会话快照，应该如何实现？`

实现原则：
- 改写结果只用于检索和回答构建，不替换用户原始消息
- 如果用户问题本身完整，不强行改写
- 改写失败时回退到原始 `user_message`

### 3. 短期/长期/会话记忆分层

多轮对话的上下文体系分为三层：

| 记忆类型 | 内容 | 生命周期 |
|----------|------|----------|
| **短期记忆** (conversation_history) | 最近 6-10 轮用户/AI 消息、已选工具、引用摘要 | 当前会话，存数据库 |
| **会话记忆** (session_topic) | 本轮会话主要围绕的主题/目标，在第一轮时写入 | 当前会话，存数据库 |
| **长期记忆** (user.memory) | 用户偏好、项目规则、长期事实，来源于 MEMORY.md | 跨会话，持久化 |

分层策略：
- `conversation_history`：用于追问、省略指代、连续任务
- `session_topic`：第一轮对话后从用户问题和回答提取，贯穿整个会话，帮助理解本轮在解决什么问题
- `session_summary`：会话变长（10轮以上）后生成滚动摘要，用于压缩较早上下文
- `memory`：后续再考虑，不放进本次 MVP

**短期记忆**只保留对话正文和必要引用，不含完整 citation 原文，避免 token 膨胀。

**会话记忆**在第一轮时写入，`session_topic` 可以是"用户询问项目架构"、"用户请求代码审查"等，贯穿整个会话帮助维持上下文一致性。

### 4. 前端先不做复杂交互

MVP 阶段前端保持现有对话 UI，只需要确保每轮请求都带上稳定的 `session_id`。

后续增强：
- 新建对话时生成新的 `session_id`
- 切换历史会话时恢复完整消息列表
- Tool 可以支持 `session` 级固定，但默认仍是 `next_message`
- 在调试模式显示“本轮使用了最近 N 条历史消息”

**涉及位置**:
- `src/routers/chat.py` - 接收请求并根据 `session_id` 调用多轮问答服务
- `src/app/chat/service.py` - 读取会话历史、保存消息、协调 query rewrite 和 answer compose
- `src/ai/query_router.py` 或新增 `src/ai/query_rewriter.py` - 根据历史上下文改写追问
- `src/ai/answer_composer.py` - 组装 history、evidence、本轮问题和最终引用
- `app/src/App.tsx` - 确保请求携带稳定 `session_id`，切换会话时恢复历史消息

**已完成（MVP，2026-05-08）**:
- 后端按 `session_id` 读取会话历史，默认只取最近 20 条消息
- 历史消息进入 prompt 前移除完整引用块，只保留轻量引用摘要
- 新增 `src/ai/query_rewriter.py`，在检索前把多轮追问改写成独立查询
- `KnowledgeQAService` 使用改写后的 `retrieval_query` 做路由、本地检索和外部搜索，用户原始问题仍用于回答展示
- `AnswerComposer` 分层组装原始问题、改写查询、会话历史、本轮 evidence 和外部补充
- 本轮没有新 evidence 时，可以基于会话历史回答追问，并提示没有新增本地引用
- `session` 表新增 `session_topic` 和 `session_summary` 字段，支持会话主题和较早上下文摘要
- 前端 session 类型和 API 映射同步支持 `session_topic` / `session_summary`

**未完成 / 后续增强**:
- `src/app/chat/service.py` 还未拆分，当前会话历史读取、保存和摘要逻辑仍在 `src/routers/chat.py`
- `session_topic` 目前是轻量规则生成，尚未用 LLM 从首轮问答中提取稳定主题
- `session_summary` 目前是轻量滚动摘录，尚未做 LLM 语义摘要和压缩策略
- 历史上下文尚未持久化已选 Tool 元数据，`message` 表还没有 `tool_id` / `metadata_json`
- 长期记忆 `MEMORY.md` / `user.memory` 尚未纳入本次 MVP
- 前端还未支持 `session` 级固定 Tool，也未在调试模式显示“本轮使用了最近 N 条历史消息”

**决策人**: gzy
**状态**: MVP 已完成（2026-05-08），剩余增强待实现


## 4. 公众号搜索拿不到 profile_url

**类型**: Bug
**状态**: 已完成（Tavily-only URL 发现，2026-05-19）

**问题描述**: blog-diary-fetch 在抓微信公众号时，第一步通过搜狗微信搜索获取公众号主页 `profile_url` 经常失败，导致后续历史页解析与正文抽取都无法继续。

**目标**: 稳定拿到公众号当天文章 `article_url`，不再依赖搜狗 `profile_url`；如果 Tavily 没有返回可用文章 URL，要返回细分 warning，而不是只输出泛化失败。

**涉及位置**:
- `.agents/skills/blog-diary-fetch/src/app/core/blog_fetcher.py` - `TavilySearchClient.discover_wechat_articles()` / `BlogDiaryService.collect_wechat_entries()`
- `.agents/skills/blog-diary-fetch/tests/test_wechat_web_search.py` - Tavily URL 发现、空结果 warning、正文降级回归测试
- `.agents/skills/blog-diary-fetch/config/web_search.yaml` - Tavily API key 与启用配置
- `.agents/skills/blog-diary-fetch/SKILL.md` - 公众号抓取流程说明

**备注**: 已移除搜狗 `profile_url` / 历史页 fallback，当前实现只保留 Tavily 文章 URL 发现 + 微信文章页抓正文的链路，适合通过定时任务自动生成日记草稿。

**决策人**: gzy

## 3. 工程博客更新自动生成日记

**类型**: 功能
**问题描述**: 目前工程博客链接需要手动查看、摘录和写入日记。希望维护一组工程博客/RSS/网页链接和微信公众号列表，每天自动判断是否有昨天的新内容；如果有更新，就抓取正文、生成摘要，并合并生成当天日记草稿。

**当前状态**:

### 可行性确认

| 来源 | 可爬取性 | 说明 |
|------|----------|------|
| Anthropic | ✅ 可以 | 标准博客，有公开页面 |
| LangChain | ✅ 可以 | 标准博客，有公开页面 |
| Microsoft | ✅ 可以 | 标准博客，有公开页面 |
| Jina | ✅ 可以 | 标准博客，有公开页面 |
| OpenAI | ✅ 可以 | 标准博客，有公开页面 |
| 微信公众号 (mp.weixin.qq.com) | ✅ 可用但有限制 | 通过 Tavily Web Search 发现公众号当天文章 URL，再按文章页发布时间和正文抽取结果过滤昨天内容；适合每日自动化增量抓取 |

### 订阅源列表

**国外工程博客**（可爬取）:
- [Anthropic工程博客](https://www.anthropic.com/engineering)
- [LangChain博客](https://blog.langchain.com)
- [Microsoft研究博客](https://www.microsoft.com/en-us/research/blog/)
- [Jina新闻](https://jina.ai/news)
- [OpenAI公司公告](https://openai.com/news/company-announcements/)

**微信公众号**（可自动抓取，作为重点来源）:
- [阿里云开发者](https://mp.weixin.qq.com/s/bl77_Mb85C4AKe8h4__V6Q)
- [大淘宝技术](https://mp.weixin.qq.com/s/b7iygA6YIqFJ-b9Yr3EzHA)
- [得物技术](https://mp.weixin.qq.com/s/lvcH96VS6dgKvrrk4sQgDA)
- [火山引擎](https://mp.weixin.qq.com/s/Fi51gTsAMp3h0VftECRDCQ)
- [快手技术](https://mp.weixin.qq.com/s/Bxjh9Kj4n_y4E5gJGRhoRA)
- [腾讯技术工程](https://mp.weixin.qq.com/s/ri_lxDGayM-e5A0oAW59Fw)
- [腾讯云开发者](https://mp.weixin.qq.com/s/Laz4W0180y9yGW0b6EpUMQ)
- [小红书技术](https://mp.weixin.qq.com/s/cAxohCGF2mpYBn5rU3S1Ew)
- [字节跳动技术团队](https://mp.weixin.qq.com/s/mbvoeTuDR-lJ_u1TYw6-FQ)
- [美团技术团队](https://mp.weixin.qq.com/s/LuCy56KRYk4W-USpDUViyg)
- [百度geek说](https://mp.weixin.qq.com/s/tpUKOGBouUmRYEnSu1PaDQ)

### 日记模板（参考）

文件路径: `.claude/templates/daily.md`

```markdown
# 每日记录

## 科研
-

## 工程博客
[标题](URL)：一句话摘要
嵌套思考（无缩进）


## others

-
```

### 实现方案

**调度**: 每天北京时间凌晨 4 点触发一次定时任务（Codex `/loop` 或系统 `cron` 均可）。

**工作流**:
1. 读取固定订阅源配置，区分 `blog`、`rss`、`wechat` 三类来源
2. 对国外工程博客/RSS 源抓取列表页或 feed，筛选昨天 00:00-23:59（北京时间）之间的新文章
3. 对微信公众号先用 Tavily Web Search 发现 `mp.weixin.qq.com/s/...` 文章 URL，再按文章页发布时间和正文抽取结果过滤昨天内容
4. 对命中的微信公众号文章，优先抓取正文并抽取全文；如果正文抽取失败，则回退到 Tavily 搜索返回的标题和摘要
5. 用 LLM 生成「标题 + 链接 + 一句话摘要 + 嵌套思考」，并按来源去重
6. 按日期写入 `data/diary/{月日}.md`，追加到 `## 工程博客` 段落
7. 同步落盘一份原始抓取结果到 `data/raw/wechat/{YYYY-MM-DD}.json`，便于回溯和补抓

**输出格式**（参考 `.claude/templates/daily.md`）:
```markdown
## 工程博客
[标题](URL)：一句话摘要
嵌套思考（无缩进）
```

### Codex 实施要点

| 步骤 | 内容 |
|------|------|
| 1 | 创建 `scripts/fetch_blogs.py`，统一读取工程博客、RSS 和微信公众号配置 |
| 2 | 为微信公众号接入 Tavily URL 发现，按昨天时间窗过滤文章页发布时间 |
| 3 | 对命中的新文章抓正文并生成摘要，正文失败时自动降级到标题/摘要 |
| 4 | 按日期写入 `data/diary/{月日}.md`，追加到 `## 工程博客` 段落 |
| 5 | 将每次抓取结果写入 `data/raw/wechat/`，防止公众号临时链接过期后无法追溯 |
| 6 | 设置每日凌晨定时任务，保证“昨天内容”按自然日稳定入库 |

### 自动化方案对比

#### 方案 A：脚本 + LLM API + 服务器 cron

- 定时任务在服务器上直接跑 `scripts/fetch_blogs.py`
- 抓取、筛选、正文提取、摘要生成都由 Python 脚本完成
- LLM 仅负责把抓到的内容整理成更自然的摘要和思考
- 优点：链路短、易排查、部署简单
- 缺点：推理和修正能力主要依赖脚本本身，复杂场景需要手工补逻辑

#### 方案 B：skill + Codex 定时任务

- 由 Codex 按 `blog-diary-fetch` skill 的工作约定执行
- skill 负责配置、抓取、摘要、写入和原始结果落盘
- 可以借助 Codex 的分析和多步执行能力处理异常来源和文本整理
- 优点：对复杂网页和规则变化更灵活，适合边跑边修
- 缺点：需要 Codex 运行环境和任务调度支持，整体链路比纯脚本更重

**最终决策**:
- 方案 A（`脚本 + LLM API + cron`）作为最终生产方案
- 方案 B（`skill + Codex` 定时任务）保留为开发、调试、补抓和回归验证工具
- `blog-diary-fetch` skill 继续用于手动验证抓取链路、补抓指定日期和修复规则变化

**服务器落地建议**:
1. 服务器上只需要一个 cron 入口，定时执行仓库根目录的 `scripts/fetch_blogs.py`
2. 先同步仓库到最新，再在仓库根目录手动跑一次 dry-run：
   - `cd /path/to/DeepMemo`
   - `uv run python scripts/fetch_blogs.py --config config/blog_sources.yaml --dry-run --json`
3. dry-run 通过后，再切正式写入：
   - `cd /path/to/DeepMemo`
   - `uv run python scripts/fetch_blogs.py --config config/blog_sources.yaml --json`
4. cron 里不要再拆第二个“生成日记脚本”，抓取、摘要、写入已经封装在同一个入口里
5. 如果服务器上的代码还停留在旧版搜狗链路，先把根目录 `src/app/core/blog_fetcher.py` 同步到 Tavily-only + 日记生成的最终版，再上线 cron
6. 如果服务器使用 `uv` 管理项目环境，cron 直接调用 `uv run python scripts/fetch_blogs.py --config config/blog_sources.yaml --json` 即可；不要让 cron 自己拼抓取逻辑
7. 定时任务执行时必须保证工作目录是仓库根目录，否则 `config/blog_sources.yaml`、`config/web_search.yaml` 和 `data/diary/` 的相对路径会失效
8. 建议给 cron 命令补上日志重定向，方便排障：
   - `cd /path/to/DeepMemo && uv run python scripts/fetch_blogs.py --config config/blog_sources.yaml --json >> logs/blog-diary-fetch.log 2>&1`

**当前代码现状**:
- `.agents/skills/blog-diary-fetch/` 里的 skill 版本已经验证过 Tavily-only 抓取 + LLM 摘要 + 写日记链路
- 根目录生产入口已经存在，但生产核心逻辑还需要和 skill 版本再对齐一次，避免服务器跑到旧逻辑

### 最终方案

**调度**: 在服务器上用 `cron` 定时触发脚本，不依赖本地 Codex 或交互式任务。

**生产链路**:
1. `cron` 定时执行抓取脚本，读取公众号和工程博客配置
2. 脚本优先通过 Tavily 发现公众号当天文章 URL，抓取正文并落盘原始结果
3. LLM API 负责把已抓到的标题、摘要、正文整理成日记文案
4. 脚本按日期写入 `data/diary/{月日}.md`
5. 抓取失败时只影响单条来源，warning 单独记录，不中断整批任务

**角色分工**:
- `scripts/fetch_blogs.py`: 生产执行入口
- `config/blog_sources.yaml`: 来源配置
- `config/web_search.yaml`: Tavily 配置
- `blog-diary-fetch skill`: 开发、补抓、调试、回归验证

**决策理由**:
- 生产任务要求稳定、低依赖、可运维
- cron + 脚本比交互式 agent 更容易做重试、监控和审计
- Codex skill 在处理规则变化、补抓和排障时仍然有价值，但不作为主调度

**涉及位置**:
- `scripts/fetch_blogs.py` - 新增
- `data/diary/{月日}.md` - 按日期写入
- `data/raw/wechat/{YYYY-MM-DD}.json` - 原始抓取结果缓存
- `.claude/templates/daily.md` - 参考模板

**决策人**: gzy
**状态**: 待实现（由 Codex 执行）

## 4. 切换为 OpenAI Agent SDK

**类型**: 技术债 / 架构升级
**问题描述**: 当前 DeepMemo 的 chat 模块使用 `openai` Python SDK，主要面向单轮 API 调用。本地知识库的问答助手本质上是 **Agent**——需要 Tool Use、循环推理、多步骤执行，当前架构无法自然支持。

**现状**:
- 当前 chat 模块是典型的单轮 RAG + LLM 调用
- 没有 Tool Use、Function Calling 能力
- 会话管理、Query Rewrite、Answer Compose 等逻辑散落在各处，缺乏统一调度
- 如果要扩展 Agent 能力（如多次检索、反思验证、工具组合），需要重构底层

**目标**: 切换到 `openai-agents` SDK（OpenAI Agent SDK），将 DeepMemo chat 重构为真正的 **Agent** 架构。

**涉及位置**:
- `src/routers/chat.py` - 改为 Agent 入口，暴露 Agent Runner 接口
- `src/app/chat/service.py` - 拆分为 Agent Handler / Tool 定义
- `src/ai/query_router.py` - 作为 Agent Tool 或用于 Routing Agent
- `src/ai/answer_composer.py` - 作为 Agent 输出处理
- `src/ai/web_search_agent.py` - 作为 Agent Tool
- `src/ai/providers/` - 各类 Tool Provider

**实现思路**:

### 1. 安装 openai-agents SDK

```bash
uv add openai-agents
```

### 2. 定义 Agent 和 Tool

核心 Agent（用于知识库问答）：
- `knowledge_agent`：接收用户问题，调用检索工具，返回回答
- 内置 Tool：`retriever`（检索知识库）、`web_search`（网页搜索）、`memory`（读用户偏好）

路由 Agent（决定走哪个流程）：
- 根据用户问题判断是否需要搜索、是否需要生成日记、是否只是闲聊

### 3. 会话状态迁移

现有 `session_id` 机制映射到 Agent SDK 的 Session：
- 每次对话创建一个 `Session`（对应现有 `session_id`）
- 历史消息通过 SDK 的 history 管理，不再手动拼接
- `session_topic` 和 `session_summary` 可以通过 Agent 的 instructions 或 Memory Tool 实现

### 4. 渐进式迁移

MVP 阶段保持现有 API 接口不变，内部替换为 Agent SDK：
- `POST /chat` → 触发 `knowledge_agent.run(user_message, session_id=...)`
- 响应格式保持兼容，前端无感知
- 后续逐步增强 Tool 和 Agent 能力

**决策人**: gzy
**状态**: 待确认

## 5. Wiki 从每日记录升级为知识编译器

**类型**: 架构升级 / 功能
**状态**: 进行中

**问题描述**: 当前 Wiki 不应该继续以“每日记录 = 一个 wiki 页面”为基本粒度，而应该参考 `reference/llm_wiki/llm_wiki` 的设计，把 `data/diary/**/*.md` 作为原始证据层，编译成稳定的 `entity / concept / synthesis` 知识页，再基于这些知识页构建图谱与社区。

**目标**:
- 让 Wiki 成为“知识编译器”，而不是日记镜像
- 从日记中提炼高频、可复用、可追溯的知识节点
- 让图谱和社区基于知识页而不是按天分散的日记页
- 后续支持手动定义知识社区，再自动扩展相关页面

**参考设计**:
- `reference/llm_wiki/llm_wiki/README.md` 的核心思路是：
  - 原始资料层与 wiki 知识层分离
  - wiki 页面是稳定知识资产，不是原始记录的逐日拷贝
  - ingest / query / lint / graph 是主链路
  - 图谱、社区、insights 是围绕知识页组织的维护能力

**当前已完成的相关工作**:
- `src/wiki/ingest.py`
  - 已接入 `data/diary/**/*.md` 作为输入
  - 已把 ingest 改成“日记分析 -> 知识页汇总 -> `data/wiki/**/*.md` 写出”
  - 已加入增量缓存和去重
  - 已将 `source` 视为证据层，不再作为主 wiki 页面批量落盘
- `src/wiki/graph.py`
  - 已改为读取 `data/wiki/**/*.md` 做页面级图谱
  - 已用 `wikilink + sources + common neighbor + type affinity` 计算边
  - 已接入 Louvain 社区检测
  - 已补噪声过滤，避免文件名、目录名、停用词污染知识节点
- `src/routers/wiki.py`
  - 已新增 `/wiki/rebuild`，可从后端触发 `data/diary -> data/wiki` 重建
  - 已保留 `/wiki/graph` 作为图谱数据入口
- 前端
  - 已有独立 `Wiki` Workspace
  - 已接入社区图谱 + 节点详情
  - 已支持前端触发 Wiki 重建并刷新图谱
- 文档
  - 已在 `docx/frontend/frontend_v3.md` 里补充 Wiki Workspace 与重建链路说明

**遗留问题**:
- 当前知识页仍有一部分 term 噪声，需要继续收紧词抽取和页面筛选
- 目前社区仍偏向单大簇，后续需要更强的社区定义策略
- 需要支持“手动定义知识社区 -> 自动扩展相关节点”的配置模式
- 需要把知识页生成进一步从“term 采样”推进到“稳定实体 / 概念编译”

**涉及位置**:
- `reference/llm_wiki/llm_wiki/README.md` - 参考项目设计
- `src/wiki/ingest.py` - diary -> wiki 编译
- `src/wiki/graph.py` - page-level graph + community detection
- `src/routers/wiki.py` - rebuild / graph API
- `app/src/App.tsx` - Wiki Workspace UI
- `docx/frontend/frontend_v3.md` - 前端方案说明

**决策人**: gzy

## 6. Diary 缺少图片存储与展示能力

**类型**: 功能
**状态**: 已完成

**问题描述**: 当前 Markdown 笔记，尤其是 diary，缺少稳定的图片上传、存储、引用和展示链路，导致日记、idea 等文件中无法保存截图、配图或其他视觉资料。

**目标**:
- 支持在 diary 编辑/生成流程中插入图片
- 将图片保存到仓库内可管理的位置，而不是只依赖外部临时链接
- 在 Markdown 中生成可追踪、可迁移的本地图片引用
- 问答、Wiki 编译和后续摘要流程能识别图片所在的日记来源，至少不破坏现有文本链路

**涉及位置**:
- `data/diary/` - 日记 Markdown 需要支持本地图片引用
- `app/src/App.tsx` - diary 编辑界面需要支持图片插入/粘贴/上传入口
- `src/routers/diary.py` - 后端 diary 写入流程需要处理图片元数据或附件路径
- `src/app/core/fs_manager.py` - 文件树和读写规则需要允许图片资源目录
- `config/` - 建议新增或扩展附件存储路径配置

**初步方案**:
- 图片统一保存到 `data/assets/diary/YYYY-MM-DD/`，不混入 `data/diary/` Markdown 目录
- 非 diary Markdown 文件按源文件路径保存到 `data/assets/<source-without-md>/`，例如 `ideas/DeepMemo.md` 保存到 `data/assets/ideas/DeepMemo/`
- Markdown 中保存可迁移的相对路径，例如 `![说明](../assets/diary/2026-05-26/example.png)`
- 浏览器预览通过后端静态路由 `/assets/diary/YYYY-MM-DD/example.png` 访问同一份本地文件
- 前端接入 Vditor 的粘贴/拖拽上传能力，不额外做图库
- 后端负责落盘、重名处理、路径规范化、图片类型和大小校验

**路径决策**:
- 物理路径：`data/assets/diary/YYYY-MM-DD/<timestamp>-<safe-name>.<ext>`
- 非 diary 物理路径：`data/assets/<source-without-md>/<timestamp>-<safe-name>.<ext>`
- Markdown 引用路径：相对当前日记文件计算，例如 `data/diary/0526.md` 引用 `../assets/diary/2026-05-26/20260526-153012-screenshot.png`
- 静态访问路径：`/assets/diary/YYYY-MM-DD/<filename>`
- 日期来源：优先从日记文件名解析 `MMDD.md` 或 `MDD.md`，年份使用当前 diary 年份；无法解析时回退到当天日期
- 非 diary 示例：`data/ideas/DeepMemo.md` 引用 `../assets/ideas/DeepMemo/20260526-160203-architecture.png`

**实现 TODO（每步含验证）**:
- [x] 后端新增 asset 路径构造与文件名规范化函数。验证：运行单元测试，确认 `diary/0526.md` 会生成 `assets/diary/2026-05-26/...`，Markdown 路径为 `../assets/...`。
- [x] 后端新增 `/api/fs/upload-asset`，接收 Vditor multipart 上传并返回 `succMap`。验证：运行接口测试或用 `curl` 上传 PNG，确认文件写入 `data/assets/diary/...` 且响应可被 Vditor 识别。
- [x] FastAPI 挂载 `/assets` 静态目录。验证：上传后访问 `/assets/diary/YYYY-MM-DD/<filename>` 返回图片内容。
- [x] 前端 Vditor 配置上传 URL、图片类型限制和当前日记路径。验证：`npm run build` 通过，手动粘贴/拖拽图片后 Markdown 插入相对路径。
- [x] Vite dev server 代理 `/assets` 到后端。验证：开发环境中相对图片路径能在编辑器内预览。
- [x] 回归文件树和 Markdown 读写。验证：`data/assets` 可出现在文件树中，但图片不会被当作文本 Markdown 编辑；保存 diary 不破坏已有内容。

**决策人**: gzy
