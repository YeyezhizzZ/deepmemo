# 架构设计

要做一个做知识库问答助手的ai部分

## 技术选型

- 编程语言：python
- 构建虚拟环境：uv
- api框架：fastapi
- llm配置文件：config/llm_api.yaml
- llm初始化：openaisdk

## 核心链路

知识库问答使用 RAG 思路，但第一阶段不做 embedding、不建向量索引。系统先通过本地搜索 Agent 从 Markdown 知识库中召回证据，再把检索内容合并到 prompt 中，由 LLM 生成回答。

整体链路：

1. 用户输入问题。
2. QueryRouter 判断问题是否适合本地知识库回答。
3. LocalSearchAgent 在本地知识库中搜索、读取、归纳相关内容。
4. AnswerComposer 基于本地证据生成回答。
5. 如果本地知识库没有高相关内容，且问题需要外部信息，再触发 WebSearchAgent 作为 fallback。

## 本地召回方案

采用一个安全封装的 Codex / Claude Code 混合版本地搜索 Agent，不同时实现 Claude Code 和 Codex 两套召回算法。

核心思想：

- 借鉴 Claude Code 的工具封装和安全边界，把底层文件搜索能力封装成受控 tool。
- 借鉴 Codex 的动态搜索方式，让 LLM 根据问题自主决定搜索关键词、阅读路径和总结策略。
- 底层优先使用 ripgrep，但不向 Agent 暴露任意 shell 命令。
- 适配 MB 级个人 Markdown 知识库，避免过早引入 embedding、向量库和索引维护复杂度。

### LocalSearchAgent

LocalSearchAgent 是默认召回模块。它不直接回答用户，而是负责在知识库中找到可引用的本地证据，并输出结构化检索结论。

Agentic Loop：

1. 根据用户问题拆解可能的关键词、主题、时间范围和目录范围。
2. 调用 `glob_files` 定位候选 Markdown 文件。
3. 调用 `grep_content` 查找匹配片段。
4. 调用 `read_lines` 阅读必要上下文。
5. 根据已读内容决定是否继续搜索、换关键词或结束。
6. 输出证据摘要、来源文件和相关性判断。

### 工具设计

不要只暴露一个 `search(query)`，而是拆成几个可组合的安全工具：

- `glob_files(pattern)`：按文件名或目录模式查找候选文件。
- `grep_content(query, path=None, context=5, mode="content")`：基于 ripgrep 搜索正文内容。
- `read_lines(path, start, end)`：读取指定文件的指定行范围。
- `count_matches(query, path=None)`：统计关键词分布，用于判断影响范围或主题覆盖度。

`grep_content` 的模式：

- `files_with_matches`：只返回匹配文件路径，适合大范围定位。
- `content`：返回匹配行和少量上下文，适合确认具体内容。
- `count`：只返回命中次数，适合评估主题分布。

### 安全边界

- Agent 只能访问知识库根目录 `data/` 下的内容。
- 所有文件路径必须经过 realpath 校验，解析后的真实路径必须位于 `data/` 内，防止 `../` 路径穿越。
- 默认只读取 Markdown 文件，即 `data/**/*.md`。
- 禁止向 Agent 暴露任意 shell。
- 底层 `subprocess` 只允许调用白名单命令，例如 `rg`。
- 单次搜索结果超过 250 条时强制截断，并提醒 LLM 细化搜索词。
- 单次 `read_lines` 限制最大读取行数，避免一次性加载过多上下文。
- `.claude/`、`config/`、源码目录、数据库文件和其他项目配置默认不参与召回。

## WebSearchAgent

websearch 只作为 fallback，不作为默认召回。

触发条件：

- 用户明确要求联网搜索、查看最新信息或查询外部资料。
- 本地知识库没有高相关内容。
- 用户问题本身依赖实时信息，例如价格、版本、新闻、政策、活动日期等。
- 本地笔记只提供了线索，需要外部资料补充背景。

回答时必须区分本地知识库证据和外部搜索补充，避免把外部信息误认为用户自己的知识库内容。

## 模块划分

```text
QueryRouter
  -> LocalSearchAgent
       -> glob_files
       -> grep_content
       -> read_lines
       -> count_matches
       -> summarize_evidence
  -> WebSearchAgent
  -> AnswerComposer
```

## 分阶段实现

第一阶段：实现 LocalSearchAgent。

- 完成本地 Markdown 搜索工具封装。
- 支持多轮搜索、阅读、证据归纳。
- 先不做 embedding 和向量索引。
- 先不默认启用 websearch。

第二阶段：增强 QueryRouter。

- 识别时间范围、目录范围和问题类型。
- 对“最近”“上周”“某个月”等问题优先搜索 diary、weekly、monthly。
- 对“想法”“长期主题”等问题优先搜索 ideas。

第三阶段：加入 WebSearchAgent fallback。

- 只在本地知识库召回失败或问题明确需要外部信息时触发。
- 输出答案时标注哪些来自本地知识库，哪些来自外部搜索。

## 实现进度

### 2026-05-03

状态：本轮已把 AI 模块接入后端聊天链路。第一阶段完成；第二阶段完成基础路由；第三阶段完成 fallback 接口和管线集成，但默认不启用联网 provider。

已完成：

- `src/ai/local_tools.py`：实现 `glob_files`、`grep_content`、`read_lines`、`count_matches` 的安全封装。所有路径都限制在 `data/` 下，默认只读 Markdown，并通过 `realpath` 防止 `../` 路径穿越。底层搜索只调用白名单 `rg`，不暴露任意 shell。
- `src/ai/local_search_agent.py`：实现第一阶段 LocalSearchAgent。根据问题和路由 hints 生成搜索词，执行多轮 grep，按命中位置读取上下文，输出结构化 evidence、来源文件、行号和相关性分数。
- `src/ai/query_router.py`：实现基础 QueryRouter。能识别想法类问题优先搜 `data/ideas`，时间/学习记录类问题优先搜 `data/2026`，记忆类问题优先搜 `data/memory`，并识别可能需要外部信息的问题。
- `src/ai/answer_composer.py`：实现 AnswerComposer。把本地证据合并进 prompt，要求回答标注来源；LLM 调用失败时返回本地证据摘要，不让接口直接崩掉。
- `src/ai/web_search_agent.py`：实现 WebSearchAgent 的 provider 注入接口。MVP 默认禁用；接入 provider 后可返回外部 snippets，并由 AnswerComposer 明确区分本地证据和外部补充。
- `src/ai/service.py`：实现 KnowledgeQAService，总管线为 `QueryRouter -> LocalSearchAgent -> WebSearchAgent fallback -> AnswerComposer`。
- `src/app/main.py`、`src/routers/chat.py`：把 `/chat` 从直接调用 LLM 改为调用 KnowledgeQAService；同时修正历史消息中数据库角色 `ai` 传给 OpenAI 前需要映射为 `assistant` 的问题，并避免把当前用户消息重复追加进 LLM 历史。

验证记录：

- `python3 -m compileall src/ai src/app src/routers`
- `python3 -c "from src.ai.local_tools import KnowledgeBaseTools; tools=KnowledgeBaseTools(); print(len(tools.glob_files('ideas').files)); print(tools.grep_content('DeepMemo', path='ideas', context=1).hits[0].path)"`
- `python3 -c "from src.ai.query_router import QueryRouter; from src.ai.local_search_agent import LocalSearchAgent; q='DeepMemo 的想法是什么'; route=QueryRouter().route(q); result=LocalSearchAgent().search(q, route); print(route.path_hints); print(result.searched_queries); print(len(result.evidence)); print(result.evidence[0].source_id if result.evidence else 'NO')"`
- `python3 -c "from src.ai.local_tools import KnowledgeBaseTools; tools=KnowledgeBaseTools(); print(tools.grep_content('-not-a-flag', mode='content').message or 'ok')"`
- `python3 -c "from src.ai.local_tools import KnowledgeBaseTools; tools=KnowledgeBaseTools(); ... tools.glob_files('../*.md') ..."` 验证 glob 路径穿越会被拒绝。
- `python3 -c "from src.app.main import app; print(app.title)"`

后续可增强：

- QueryRouter 可以继续加入更精确的日期解析，把“上周”“四月”等映射到具体文件范围。
- WebSearchAgent 需要真实外部搜索 provider 后才启用；当前实现只提供可注入接口和回答侧区分逻辑。

### 2026-05-03 系统集成补充

集成原则：遵守 `docx/design.md` 的前后端对接约定，不新增必填字段、不改变 `SessionResponse` 和 `MessageResponse` 结构。AI 能力只作为 `/chat` 的内部实现升级，对前端仍表现为发送用户消息并返回一条 `role="ai"` 的 Markdown 内容。

已完成：

- 后端 `POST /chat` 保持原请求和响应格式不变，内部改为调用 `KnowledgeQAService.answer()`。
- 前端 `app/src/api.ts` 继续使用现有 `/sessions`、`/chat`、`/chat/{session_id}/messages` 调用，无需改动数据模型。
- 前端 `app/src/App.tsx` 的页面文案、示例问题、详情面板说明已从普通聊天接口调整为本地知识库问答语义，提示用户 DeepMemo 会优先检索 `data/` 下的 Markdown 证据。
- 后端 `src/app/main.py` 增加 CORS 配置，允许 Vite 开发服务 `http://localhost:5173` 和 `http://127.0.0.1:5173` 直连后端；同时仍兼容 Vite proxy 的 `/api -> http://localhost:8000` 方式。

对接状态：

- `GET /`：前端健康检查继续使用。
- `GET /sessions`、`POST /sessions`、`DELETE /sessions/{session_id}`：会话列表、新建和删除逻辑继续使用。
- `GET /chat/{session_id}/messages`：消息历史继续按时间正序加载。
- `POST /chat`：前端无需知道 RAG 细节；后端负责路由、检索、证据注入和回答生成。

新增验证：

- `npm run build` 在 `app/` 下验证前端 TypeScript 和 Vite 构建。
- `python3 -m compileall src/ai src/app src/routers` 验证后端 AI 管线和 API 入口可编译。

### 2026-05-03 可溯源引用增强

问题：当前 case 里的回答只出现 `[证据 1:51]` 这类模型生成文本，用户无法点击定位，也无法确认这个标记对应哪个真实 chunk。可溯源链路不应该依赖 LLM 自己拼来源。

方案：

- 后端仍保持 `MessageResponse` 结构不变，不新增必填字段。
- `AnswerComposer` 只要求 LLM 在正文里使用 `[1]`、`[2]` 这种数字引用。
- LLM 生成完成后，系统基于 `LocalSearchResult.evidence` 自动追加固定格式的 `## 引用` 区块，包含 `path:start-end`、score、query 和原始 chunk。
- 历史消息传回 LLM 前会剥离旧回答里的 `## 引用` 区块，避免 chunk 在多轮对话里反复膨胀。
- 前端 `MarkdownLite` 解析 `## 引用` 区块，把正文中的 `[1]`、`[2]` 渲染成可点击引用，并在回答末尾把对应 source chunk 折叠展示。
- `LocalSearchAgent` 使用实际读取到的首尾行号作为 citation range，避免文件较短时引用到不存在的结束行。

引用区块格式：

```md
## 引用

[1] ideas/Memory.md:51-53 · score=0.90 · query=Claude Code
> 51: ...
> 52: ...
> 53: ...
```

验证记录：

- `python3 -m compileall src/ai src/app src/routers`
- `python3 -c ... AnswerComposer(LLM()).compose(...)` 验证回答会自动追加 `## 引用` 和 chunk。
- `npm run build` 在 `app/` 下验证前端解析和渲染代码可构建。

### 2026-05-03 检索优先级调整

判断：`data/2026` 的每日记录是最原始、最真实、最有用的信息源，不能只在“最近”“学习记录”这类问题中才优先触发。

调整：

- `QueryRouter` 默认把 `data/2026` 作为第一检索范围。
- 命中想法类问题时，检索顺序为 `data/2026 -> data/ideas`。
- 命中记忆类问题时，检索顺序为 `data/2026 -> data/memory`。
- 未命中特定目录时，检索顺序为 `data/2026 -> data/ideas -> data/memory`，避免泛问题绕过每日记录。

验证记录：

- `python3 -m compileall src/ai src/app src/routers`
- `python3 -c ... QueryRouter().route(...)` 验证泛问题路径为 `['2026', 'ideas', 'memory']`，想法类为 `['2026', 'ideas']`，记忆类为 `['2026', 'memory']`。
- `python3 -c ... LocalSearchAgent().search(...)` 验证 case 问题第一条证据来自 `2026/48.md:5-21`。
