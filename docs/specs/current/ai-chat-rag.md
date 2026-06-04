# AI Chat & RAG

* **Status**: Current / Human Reviewed

## 1. Scope
涵盖系统核心的问答流水线，包括流式生成、上下文改写以及本地检索。

## 2. Preserved Behaviors
* **SSE 流式输出**：通过 `StreamingResponse` 传递 Event Stream 回复。
* **基于权重的检索**：Local Search 作为主引擎，默认被开启并必须有证据支持才触发证据流。
* **有条件的 Web Fallback**：仅在 Local Search 证据 Confidence 极低，且路由判断 `needs_web=True` 时，才会触发外部搜索引擎（Web Search）。

## 3. Evidence
* `src/ai/service.py` (`KnowledgeQAService`)
* `src/routers/chat.py`

## 4. Current Flow
User Question -> `QueryRewriter` (改写) -> `QueryRouter` (决定路径) -> `LocalSearch` (基于 `rg` 本地搜索 MD 文件) -> Fallback WebSearch -> `AnswerComposer` (拼接 Prompt 并调用 LLM) -> SSE 传回前端。

## 5. Interfaces / Related Files
* `llm_service.py` 提供模型通信基础。

## 6. Known Gaps
* 缺少完善的意图识别，极度依赖写死的硬编码。

## 7. Regression Risks
* 如果误改了证据拼装格式（如把 `[1]` 改错），前端引用面板可能无法正常解析。
