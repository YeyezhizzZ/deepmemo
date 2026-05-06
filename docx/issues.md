# DeepMemo 问题记录

## 1. 硬编码问题

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


## 7. 没有多轮对话机制

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

在进入检索前，新增 query rewrite 步骤，把依赖上下文的追问改写成独立问题。

示例：
- 用户追问：`第二点再展开一下`
- 历史上下文：上一轮回答列出了“导出按钮分享链接方案”的三点
- 改写后查询：`导出按钮分享链接方案中的第二点，即后端生成 share_id 和保存会话快照，应该如何实现？`

实现原则：
- 改写结果只用于检索和回答构建，不替换用户原始消息
- 如果用户问题本身完整，不强行改写
- 改写失败时回退到原始 `user_message`

### 3. 短期上下文和长期记忆分开

多轮对话只解决当前会话内的上下文延续，不等同于长期记忆。

建议分层：
- `conversation_history`：最近几轮对话，用于追问、省略指代、连续任务
- `session_summary`：会话变长后生成滚动摘要，用于压缩较早上下文
- `knowledge_evidence`：本轮根据用户问题自动检索出来的材料
- `memory`：后续再考虑用户偏好、项目规则、长期事实，不放进本次 MVP

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

**决策人**: gzy
**状态**: 待确认

## 8. Web Search Skill 实现

**背景**: 当前 DeepMemo 已有本地 Skill（技术写作、深度研究），但缺少联网搜索能力。用户在使用问答模式时，无法实时获取外部信息。

**确认方案**: 不依赖 Claude Code harness，也不把 Web Search 做成纯 prompt Skill。DeepMemo 后端独立实现 `WebSearchAgent`，MVP 阶段先复用现有 `.claude/skills/duckduckgo-search/scripts/search.py` 脚本作为受控搜索执行器。

原因：
- 当前模型调用链路是 FastAPI 后端直接调用 DeepSeek / OpenAI-compatible API，LLM API 不会自动读取 `.claude/skills`，也不会自动执行 Skill 里的脚本
- `.claude/skills/duckduckgo-search/SKILL.md` 可以作为工具说明和引用规范，但真正联网搜索必须由后端代码触发
- 复用现有 DuckDuckGo 脚本可以避免第一版引入 Claude Code SDK、MCP server 或第三方付费搜索 API

### MVP 执行链路

```text
用户问题 / 用户选择 Web Search 工具
  -> QueryRouter 判断是否需要外部信息
  -> LocalSearchAgent 先检索本地知识库
  -> 本地证据不足或问题明确需要联网时
  -> WebSearchAgent 调用 .claude/skills/duckduckgo-search/scripts/search.py --json
  -> 解析 title / url / snippet
  -> AnswerComposer 把外部搜索结果作为补充证据传给 DeepSeek
  -> 回复中明确区分“本地知识库证据”和“外部搜索补充”
```

### 执行方式

MVP 使用 `inline`，搜索结果直接参与本轮回答。

暂不做 `job`。只有深度研究、多轮网页阅读、生成报告等长任务场景才需要升级为后台任务。

### 与本地 RAG 的融合策略

- 本地知识库优先，不默认联网
- 用户明确要求“联网 / 搜索 / 最新 / 新闻 / 价格 / 版本 / 政策”等，允许触发 Web Search
- 问题需要实时或外部信息，且本地检索低置信度时，Web Search 作为 fallback
- 个人事实、个人记录、历史学习日志以本地知识库为准
- 外部搜索只能作为补充材料，不能伪装成本地知识库内容

### 实现注意事项

- `WebSearchAgent` 只允许调用白名单脚本 `.claude/skills/duckduckgo-search/scripts/search.py`
- 调用脚本时固定使用参数数组，不拼接 shell 字符串，避免命令注入
- 默认使用 `--type text --num 5 --json`
- 对脚本执行设置超时，例如 10 秒
- 解析结果后只保留 `title`、`href/url`、`body/snippet` 等必要字段
- 单次搜索结果限制条数和文本长度，避免 prompt 膨胀
- 脚本依赖 `ddgs`，需要在 `pyproject.toml` 中登记依赖或在启动时给出清晰错误提示

### 后续增强

- 第二阶段可把脚本调用替换为 `DuckDuckGoProvider` Python provider，减少 subprocess 依赖
- 生产稳定性不足时可接入 Brave / Tavily / SerpAPI 等 API provider
- 如果后续引入 Claude Code SDK，可把 Claude Code WebSearch 作为深度研究 job tool，而不是替换普通问答链路

**涉及位置**:
- `.claude/skills/duckduckgo-search/` - 现有搜索 Skill 说明和脚本
- `src/ai/web_search_agent.py` - 调用搜索脚本并返回结构化外部证据
- `src/ai/types.py` - 扩展 Web Search 结果结构，保留 title / url / snippet
- `src/ai/service.py` - 在本地证据不足或路由需要联网时触发 WebSearchAgent
- `src/ai/answer_composer.py` - 合并本地证据和外部搜索补充，并要求回答区分来源
- `src/ai/chat_tools.py` - 可选：注册 `web-search` Chat Tool，允许用户手动选择
- `pyproject.toml` - 可选：登记 `ddgs` 依赖

**决策人**: gzy
**状态**: 已确认 MVP 方案，待实现
