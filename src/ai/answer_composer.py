from src.ai.chat_tools import ChatTool, build_tool_system_block
from src.ai.types import Evidence, LocalSearchResult, RouteDecision, WebSearchResult


class AnswerComposer:
    def __init__(self, llm_service):
        self.llm_service = llm_service

    def compose(
        self,
        question: str,
        local_result: LocalSearchResult,
        route: RouteDecision,
        *,
        history: list[dict] | None = None,
        retrieval_query: str | None = None,
        web_result: WebSearchResult | None = None,
        tool: ChatTool | None = None,
    ) -> str:
        history_messages = self._select_history(self._normalize_history(history or []), max_messages=8)
        if not local_result.has_evidence:
            if tool:
                return self._compose_tool_without_evidence(
                    question,
                    route,
                    tool,
                    history=history,
                    retrieval_query=retrieval_query,
                    web_result=web_result,
                )
            if web_result and web_result.snippets:
                return self._compose_web_only(
                    question,
                    route,
                    web_result,
                    history=history,
                    retrieval_query=retrieval_query,
                )
            if history_messages:
                return self._compose_history_without_evidence(
                    question,
                    route,
                    history=history_messages,
                    retrieval_query=retrieval_query,
                    web_result=web_result,
                )
            return self._compose_no_evidence(question, route, web_result)

        external_block = ""
        if web_result and web_result.snippets:
            external_block = f"\n\n外部搜索补充：\n{self._format_web(web_result)}"

        messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(tool=tool),
            }
        ]
        messages.extend(history_messages)
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{self._format_question_block(question, retrieval_query)}\n\n"
                    f"路由判断：{route.reason}\n\n"
                    f"本地知识库证据：\n{self._format_evidence(local_result)}"
                    f"{external_block}\n\n"
                    "请基于以上证据回答。必须区分本地知识库证据和外部搜索补充。"
                ),
            }
        )

        try:
            response = self.llm_service.chat(messages)
            content = self._prepend_job_status(response.choices[0].message.content, tool)
            return self._append_references(content, local_result)
        except Exception as exc:
            return self._compose_fallback(local_result, exc)

    def compose_stream(
        self,
        question: str,
        local_result: LocalSearchResult,
        route: RouteDecision,
        *,
        history: list[dict] | None = None,
        retrieval_query: str | None = None,
        web_result: WebSearchResult | None = None,
        tool: ChatTool | None = None,
    ):
        history_messages = self._select_history(self._normalize_history(history or []), max_messages=8)
        if not local_result.has_evidence:
            if tool:
                for chunk in self._compose_tool_without_evidence_stream(
                    question,
                    route,
                    tool,
                    history=history,
                    retrieval_query=retrieval_query,
                    web_result=web_result,
                ):
                    yield chunk
                return
            if web_result and web_result.snippets:
                for chunk in self._compose_web_only_stream(
                    question,
                    route,
                    web_result,
                    history=history,
                    retrieval_query=retrieval_query,
                ):
                    yield chunk
                return
            if history_messages:
                for chunk in self._compose_history_without_evidence_stream(
                    question,
                    route,
                    history=history_messages,
                    retrieval_query=retrieval_query,
                    web_result=web_result,
                ):
                    yield chunk
                return
            yield self._compose_no_evidence(question, route, web_result)
            return

        external_block = ""
        if web_result and web_result.snippets:
            external_block = f"\n\n外部搜索补充：\n{self._format_web(web_result)}"

        messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(tool=tool),
            }
        ]
        messages.extend(history_messages)
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{self._format_question_block(question, retrieval_query)}\n\n"
                    f"路由判断：{route.reason}\n\n"
                    f"本地知识库证据：\n{self._format_evidence(local_result)}"
                    f"{external_block}\n\n"
                    "请基于以上证据回答。必须区分本地知识库证据和外部搜索补充。"
                ),
            }
        )

        emitted = False
        try:
            status = self._job_status(tool)
            if status:
                emitted = True
                yield status
            response = self.llm_service.chat(messages, stream=True)
            for chunk in self._strip_generated_references_stream(response):
                if chunk:
                    emitted = True
                    yield chunk
            references = self._format_reference_section(local_result)
            if references:
                yield "\n\n" + references
        except Exception as exc:
            if emitted:
                return
            yield self._compose_fallback(local_result, exc)
            return

    def _build_system_prompt(self, tool: ChatTool | None = None) -> str:
        if not tool:
            return (
                "你是 DeepMemo 的个人知识库问答助手。"
                "请基于给定的对话历史和本地知识库证据回答；如果证据不足，明确说不足。"
                "回答使用中文，结论要简洁。"
                "来自本地知识库证据的相关句子后必须使用 [1]、[2] 这样的数字引用，数字来自证据编号。"
                "不要输出引用列表，系统会自动追加可点击引用块。"
                "不要把外部常识包装成用户知识库里的内容。"
            )

        return "\n\n".join(
            [
                (
                    "你是 DeepMemo 的个人知识库助手。"
                    "本轮需要结合用户问题、对话历史、本地知识库证据和所选 Chat Tool 指令回答。"
                    "回答使用中文。"
                    "本地知识库证据中的相关事实后必须使用 [1]、[2] 这样的数字引用，数字来自证据编号。"
                    "不要输出引用列表，系统会自动追加可点击引用块。"
                    "不要把缺少证据的外部事实包装成用户知识库里的内容。"
                ),
                build_tool_system_block(tool),
            ]
        )

    def _build_tool_only_system_prompt(self, tool: ChatTool) -> str:
        return "\n\n".join(
            [
                (
                    "你是 DeepMemo 的个人知识库助手。"
                    "本轮用户手动选择了 Chat Tool，但本地知识库没有检索到可引用证据。"
                    "你可以基于用户本轮输入、对话历史和所选 Skill 完成任务；如果事实材料不足，必须说明缺口或追问。"
                    "不要编造本地知识库里不存在的事实。"
                ),
                build_tool_system_block(tool),
            ]
        )

    def _compose_tool_without_evidence(
        self,
        question: str,
        route: RouteDecision,
        tool: ChatTool,
        *,
        history: list[dict] | None = None,
        retrieval_query: str | None = None,
        web_result: WebSearchResult | None = None,
    ) -> str:
        external_block = ""
        if web_result and web_result.snippets:
            external_block = f"\n\n外部搜索补充：\n{self._format_web(web_result)}"

        messages = [
            {"role": "system", "content": self._build_tool_only_system_prompt(tool)}
        ]
        messages.extend(self._select_history(self._normalize_history(history or []), max_messages=8))
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{self._format_question_block(question, retrieval_query, label='用户请求')}\n\n"
                    f"路由判断：{route.reason}\n\n"
                    "本地知识库证据：未检索到足够相关的可引用片段。"
                    f"{external_block}\n\n"
                    "请按所选 Chat Tool 的工作流处理本轮请求。"
                ),
            }
        )

        try:
            response = self.llm_service.chat(messages)
            return self._prepend_job_status(response.choices[0].message.content, tool)
        except Exception as exc:
            return "\n".join(
                [
                    f"{tool.name} 工具执行失败。",
                    f"错误：{exc}",
                    "本地知识库没有找到足够相关的可引用证据。",
                ]
            )

    def _compose_tool_without_evidence_stream(
        self,
        question: str,
        route: RouteDecision,
        tool: ChatTool,
        *,
        history: list[dict] | None = None,
        retrieval_query: str | None = None,
        web_result: WebSearchResult | None = None,
    ):
        external_block = ""
        if web_result and web_result.snippets:
            external_block = f"\n\n外部搜索补充：\n{self._format_web(web_result)}"

        messages = [
            {"role": "system", "content": self._build_tool_only_system_prompt(tool)}
        ]
        messages.extend(self._select_history(self._normalize_history(history or []), max_messages=8))
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{self._format_question_block(question, retrieval_query, label='用户请求')}\n\n"
                    f"路由判断：{route.reason}\n\n"
                    "本地知识库证据：未检索到足够相关的可引用片段。"
                    f"{external_block}\n\n"
                    "请按所选 Chat Tool 的工作流处理本轮请求。"
                ),
            }
        )

        emitted = False
        try:
            status = self._job_status(tool)
            if status:
                emitted = True
                yield status
            response = self.llm_service.chat(messages, stream=True)
            for chunk in response:
                if chunk:
                    emitted = True
                    yield chunk
        except Exception as exc:
            if emitted:
                return
            yield "\n".join(
                [
                    f"{tool.name} 工具执行失败。",
                    f"错误：{exc}",
                    "本地知识库没有找到足够相关的可引用证据。",
                ]
            )

    def _job_status(self, tool: ChatTool | None) -> str:
        if not tool or tool.execution_type != "job":
            return ""
        return (
            f"已创建{tool.name}任务。\n\n"
            "状态：正在基于当前请求和本地素材生成 Markdown 阶段性报告；PDF 生成会在后续版本接入。\n\n"
        )

    def _prepend_job_status(self, content: str, tool: ChatTool | None) -> str:
        status = self._job_status(tool)
        if not status:
            return content
        return f"{status}{content}"

    def _compose_web_only_stream(
        self,
        question: str,
        route: RouteDecision,
        web_result: WebSearchResult,
        *,
        history: list[dict] | None = None,
        retrieval_query: str | None = None,
    ):
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 DeepMemo 的个人知识库问答助手。"
                    "当前没有本地知识库证据，只能把外部搜索内容作为补充说明。"
                    "回答时必须明确标注这些内容不是本地知识库记录。"
                ),
            }
        ]
        messages.extend(self._select_history(self._normalize_history(history or []), max_messages=8))
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{self._format_question_block(question, retrieval_query)}\n\n"
                    f"路由判断：{route.reason}\n\n"
                    f"外部搜索补充：\n{self._format_web(web_result)}\n\n"
                    "请回答，并说明本地知识库没有找到相关证据。"
                ),
            }
        )
        try:
            response = self.llm_service.chat(messages, stream=True)
            for chunk in response:
                if chunk:
                    yield chunk
        except Exception as exc:
            yield "\n".join(
                [
                    "本地知识库没有找到相关证据；外部搜索返回了补充内容，但 LLM 生成失败。",
                    f"错误：{exc}",
                    self._format_web(web_result),
                ]
            )

    def _compose_history_without_evidence(
        self,
        question: str,
        route: RouteDecision,
        *,
        history: list[dict],
        retrieval_query: str | None = None,
        web_result: WebSearchResult | None = None,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 DeepMemo 的个人知识库问答助手。"
                    "本轮没有检索到新的本地知识库证据。"
                    "如果用户是在追问、展开、改写或继续处理上文，你可以基于对话历史回答。"
                    "回答时要明确本轮没有新增本地引用。"
                    "不要编造对话历史或知识库中不存在的事实。"
                ),
            }
        ]
        messages.extend(history)
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{self._format_question_block(question, retrieval_query)}\n\n"
                    f"路由判断：{route.reason}\n\n"
                    "本地知识库证据：未检索到新的可引用片段。\n\n"
                    f"{self._format_web_message(web_result)}"
                    "请优先判断这是否是对上文的追问；如果是，基于对话历史回答。"
                ),
            }
        )
        try:
            response = self.llm_service.chat(messages)
            return response.choices[0].message.content
        except Exception as exc:
            return "\n".join(
                [
                    "本轮没有检索到新的本地知识库证据，且基于会话历史生成回答失败。",
                    f"错误：{exc}",
                ]
            )

    def _compose_history_without_evidence_stream(
        self,
        question: str,
        route: RouteDecision,
        *,
        history: list[dict],
        retrieval_query: str | None = None,
        web_result: WebSearchResult | None = None,
    ):
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 DeepMemo 的个人知识库问答助手。"
                    "本轮没有检索到新的本地知识库证据。"
                    "如果用户是在追问、展开、改写或继续处理上文，你可以基于对话历史回答。"
                    "回答时要明确本轮没有新增本地引用。"
                    "不要编造对话历史或知识库中不存在的事实。"
                ),
            }
        ]
        messages.extend(history)
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{self._format_question_block(question, retrieval_query)}\n\n"
                    f"路由判断：{route.reason}\n\n"
                    "本地知识库证据：未检索到新的可引用片段。\n\n"
                    f"{self._format_web_message(web_result)}"
                    "请优先判断这是否是对上文的追问；如果是，基于对话历史回答。"
                ),
            }
        )
        emitted = False
        try:
            response = self.llm_service.chat(messages, stream=True)
            for chunk in response:
                if chunk:
                    emitted = True
                    yield chunk
        except Exception as exc:
            if emitted:
                return
            yield "\n".join(
                [
                    "本轮没有检索到新的本地知识库证据，且基于会话历史生成回答失败。",
                    f"错误：{exc}",
                ]
            )

    def _format_evidence(self, local_result: LocalSearchResult) -> str:
        blocks: list[str] = []
        for index, item in enumerate(local_result.evidence, start=1):
            blocks.append(
                "\n".join(
                    [
                        f"[证据 {index}] {item.path}:{item.start_line}-{item.end_line}",
                        f"引用编号：[{index}]",
                        f"匹配词：{item.query}",
                        item.excerpt,
                    ]
                )
            )
        return "\n\n".join(blocks)

    def _format_question_block(
        self,
        question: str,
        retrieval_query: str | None = None,
        *,
        label: str = "用户问题",
    ) -> str:
        query = (retrieval_query or "").strip()
        if query and query != question.strip():
            return f"{label}：{question}\n检索改写问题：{query}"
        return f"{label}：{question}"

    def _format_web(self, web_result: WebSearchResult) -> str:
        return "\n".join(f"[外部 {index}] {snippet}" for index, snippet in enumerate(web_result.snippets, start=1))

    def _format_web_message(self, web_result: WebSearchResult | None) -> str:
        if not web_result or not web_result.message:
            return ""
        return f"外部搜索状态：{web_result.message}\n\n"

    def _compose_web_only(
        self,
        question: str,
        route: RouteDecision,
        web_result: WebSearchResult,
        *,
        history: list[dict] | None = None,
        retrieval_query: str | None = None,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 DeepMemo 的个人知识库问答助手。"
                    "当前没有本地知识库证据，只能把外部搜索内容作为补充说明。"
                    "回答时必须明确标注这些内容不是本地知识库记录。"
                ),
            }
        ]
        messages.extend(self._select_history(self._normalize_history(history or []), max_messages=8))
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{self._format_question_block(question, retrieval_query)}\n\n"
                    f"路由判断：{route.reason}\n\n"
                    f"外部搜索补充：\n{self._format_web(web_result)}\n\n"
                    "请回答，并说明本地知识库没有找到相关证据。"
                ),
            }
        )
        try:
            response = self.llm_service.chat(messages)
            return response.choices[0].message.content
        except Exception as exc:
            return "\n".join(
                [
                    "本地知识库没有找到相关证据；外部搜索返回了补充内容，但 LLM 生成失败。",
                    f"错误：{exc}",
                    self._format_web(web_result),
                ]
            )

    def _compose_no_evidence(
        self,
        question: str,
        route: RouteDecision,
        web_result: WebSearchResult | None,
    ) -> str:
        parts = ["我没有在本地知识库里找到足够相关的记录。"]
        if route.needs_web:
            parts.append("这个问题可能依赖实时或外部信息。")
        if web_result and web_result.message:
            parts.append(web_result.message)
        parts.append("可以换一个更具体的关键词，或明确要求启用外部搜索。")
        return "\n".join(parts)

    def _compose_fallback(self, local_result: LocalSearchResult, exc: Exception) -> str:
        lines = [
            "LLM 生成暂时失败，先返回本地检索到的证据摘要。",
            f"错误：{exc}",
            "",
        ]
        for source_index, item in enumerate(local_result.evidence, start=1):
            lines.append(f"证据 {source_index}: {item.path}:{item.start_line}-{item.end_line}")
            lines.append(f"  {item.excerpt.splitlines()[0]}")
        return self._append_references("\n".join(lines), local_result)

    def _append_references(self, content: str, local_result: LocalSearchResult) -> str:
        if not local_result.evidence:
            return content

        answer = self._strip_generated_references(content).rstrip()
        references = self._format_reference_section(local_result)
        return "\n\n".join([answer, references]) if answer else references

    def _strip_generated_references(self, content: str) -> str:
        markers = (
            "\n## 引用",
            "\n### 引用",
            "\n## 参考",
            "\n### 参考",
            "LLM 生成暂时失败，先返回本地检索到的证据摘要。",
        )
        for marker in markers:
            if content.startswith(marker.lstrip()):
                return ""
            index = content.find(marker)
            if index != -1:
                return content[:index]
        return content

    def _strip_generated_references_stream(self, chunks):
        pending = ""
        markers = ("\n## 引用", "\n### 引用", "\n## 参考", "\n### 参考")
        start_markers = tuple(marker.lstrip() for marker in markers)
        keep_tail = max(len(marker) for marker in markers)

        def find_reference_marker(content: str) -> int:
            if content.startswith(start_markers):
                return 0
            indexes = [index for marker in markers if (index := content.find(marker)) != -1]
            return min(indexes) if indexes else -1

        for chunk in chunks:
            if not chunk:
                continue
            pending += chunk
            marker_index = find_reference_marker(pending)
            if marker_index != -1:
                if marker_index > 0:
                    yield pending[:marker_index]
                return

            flush_length = max(0, len(pending) - keep_tail)
            if flush_length > 0:
                yield pending[:flush_length]
                pending = pending[flush_length:]

        if pending:
            yield pending

    def _format_reference_section(self, local_result: LocalSearchResult) -> str:
        blocks = ["## 引用"]
        for index, item in enumerate(local_result.evidence, start=1):
            blocks.append(self._format_reference_item(index, item))
        return "\n\n".join(blocks)

    def _format_reference_item(self, index: int, item: Evidence) -> str:
        query = item.query.replace("\n", " ").strip()
        header = f"[{index}] {item.path}:{item.start_line}-{item.end_line}"
        if query:
            header = f"{header} (query={query})"

        excerpt_lines = item.excerpt.splitlines()[:6]
        blocks = [header]
        blocks.extend(f"> {line}" for line in excerpt_lines)
        return "\n".join(blocks)

    def _normalize_history(self, history: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for message in history:
            role = message.get("role")
            content = message.get("content")
            if not content:
                continue
            if role == "ai":
                role = "assistant"
            if role not in {"user", "assistant", "system"}:
                continue
            if role == "assistant":
                content = self._strip_generated_references(content).strip()
                if not content:
                    continue
            normalized.append({"role": role, "content": content})
        return normalized

    def _select_history(self, history: list[dict], *, max_messages: int) -> list[dict]:
        system_messages = [message for message in history if message["role"] == "system"]
        chat_messages = [message for message in history if message["role"] != "system"]
        return system_messages + chat_messages[-max_messages:]
