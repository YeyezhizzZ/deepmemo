from src.ai.types import QueryRewriteResult


class QueryRewriter:
    def __init__(self, llm_service, *, max_history_messages: int = 8, max_message_chars: int = 700):
        self.llm_service = llm_service
        self.max_history_messages = max_history_messages
        self.max_message_chars = max_message_chars

    def rewrite(self, question: str, history: list[dict] | None = None) -> QueryRewriteResult:
        original = question.strip()
        if not original:
            return QueryRewriteResult(original_question=question, rewritten_query=question, reason="empty_question")

        normalized_history = self._select_history(self._normalize_history(history or []))
        if not normalized_history:
            return QueryRewriteResult(original_question=original, rewritten_query=original, reason="no_history")

        try:
            response = self.llm_service.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是 DeepMemo 的查询改写器。"
                            "你的任务是把依赖上下文的用户追问改写成可以独立用于检索的问题。"
                            "如果用户本轮问题已经完整、自包含，就原样输出。"
                            "只输出一个改写后的查询句，不要解释，不要加引号，不要使用 Markdown。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"对话历史：\n{self._format_history(normalized_history)}\n\n"
                            f"本轮用户问题：{original}\n\n"
                            "请输出用于检索的独立查询："
                        ),
                    },
                ]
            )
            rewritten = self._clean_rewrite(response.choices[0].message.content, original)
        except Exception as exc:
            return QueryRewriteResult(
                original_question=original,
                rewritten_query=original,
                reason=f"rewrite_failed: {exc}",
            )

        return QueryRewriteResult(
            original_question=original,
            rewritten_query=rewritten,
            changed=rewritten != original,
            reason="llm_rewrite",
        )

    def _format_history(self, history: list[dict]) -> str:
        lines: list[str] = []
        for message in history:
            if message["role"] == "user":
                role = "用户"
            elif message["role"] == "assistant":
                role = "助手"
            else:
                role = "上下文"
            content = message["content"].replace("\n", " ").strip()
            if len(content) > self.max_message_chars:
                content = f"{content[:self.max_message_chars]}..."
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

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
            else:
                content = content.strip()
            if content:
                normalized.append({"role": role, "content": content})
        return normalized

    def _select_history(self, history: list[dict]) -> list[dict]:
        system_messages = [message for message in history if message["role"] == "system"]
        chat_messages = [message for message in history if message["role"] != "system"]
        return system_messages + chat_messages[-self.max_history_messages :]

    def _strip_generated_references(self, content: str) -> str:
        markers = ("\n## 引用", "\n### 引用", "\n## 参考", "\n### 参考")
        for marker in markers:
            if content.startswith(marker.lstrip()):
                return ""
            index = content.find(marker)
            if index != -1:
                return content[:index]
        return content

    def _clean_rewrite(self, content: str | None, fallback: str) -> str:
        value = (content or "").strip()
        if not value:
            return fallback

        if value.startswith("```"):
            value = value.strip("`").strip()
            if "\n" in value:
                value = value.split("\n", 1)[1].strip()

        value = value.splitlines()[0].strip()
        value = value.removeprefix("查询：").removeprefix("改写后查询：").strip()
        value = value.strip("`'\"“”")
        if not value or len(value) > 300:
            return fallback
        return value
