# AI Chat & RAG

* **Status**: Current / Human Reviewed

## 1. Scope
涵盖系统核心的问答流水线，包括流式生成、上下文改写以及本地检索。

## 2. Preserved Behaviors
* **SSE 流式输出**：通过 `StreamingResponse` 传递 Event Stream 回复。
* **Card-first 本地检索**：Local Search 先查询 Knowledge Cards；命中时返回 Card evidence。
* **ripgrep fallback**：Card 未命中时才进入原有基于 `rg` 的 Markdown 本地检索。
* **有条件的 Web Fallback**：仅在 Local Search 证据 Confidence 极低，且路由判断 `needs_web=True` 时，才会触发外部搜索引擎（Web Search）。
* **对话知识沉淀**：聊天达到提取阈值时，系统会把确认、纠正、决策和模式信号写入 `raw/conversations/` 并编译为 Knowledge Cards。
* **`/knowledge` 命令截获**：以 `/knowledge` 开头的 Chat 消息在普通 QA 前处理，可 list/show/add/update/pin Knowledge Cards，并保存为普通聊天消息。

## 3. Evidence
* `src/ai/service.py` (`KnowledgeQAService`)
* `src/ai/local_search_agent.py`
* `src/routers/chat.py`
* `src/knowledge/retriever.py`
* `src/knowledge/conversation_memory.py`
* `src/knowledge/chat_commands.py`

## 4. Current Flow
User Question -> 如果是 `/knowledge` 命令则直接执行 Card 操作并保存回复；否则进入 `QueryRewriter` -> `QueryRouter` -> `LocalSearch` 先查 Knowledge Cards -> 未命中再用 `rg` 搜索 Markdown -> 条件式 WebSearch -> `AnswerComposer` -> SSE/JSON 返回。聊天消息持久化后触发轻量 conversation extraction。

## 5. Interfaces / Related Files
* `llm_service.py` 提供模型通信基础。

## 6. Known Gaps
* Card 检索为关键词/BM25-lite 评分，尚未引入向量检索。

## 7. Regression Risks
* 如果误改了证据拼装格式（如把 `[1]` 改错），前端引用面板可能无法正常解析。
* 如果 Card evidence 的 `path` 或 `source_id` 格式改变，引用面板和回答引用可能失配。
