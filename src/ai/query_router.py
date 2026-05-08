import re
from dataclasses import dataclass

from src.ai.types import RouteDecision


@dataclass
class QueryRouter:
    realtime_terms: tuple[str, ...] = (
        "今天",
        "现在",
        "最新",
        "新闻",
        "价格",
        "股价",
        "天气",
        "版本",
        "政策",
        "活动日期",
        "联网",
        "外部资料",
        "web",
        "search",
    )
    idea_terms: tuple[str, ...] = ("想法", "idea", "ideas", "长期主题", "产品构思")
    diary_terms: tuple[str, ...] = (
        "最近",
        "今天",
        "昨天",
        "前天",
        "上周",
        "本周",
        "这个月",
        "上个月",
        "学习记录",
        "日记",
        "复盘",
        "三月",
        "四月",
        "五月",
    )
    memory_terms: tuple[str, ...] = ("记忆", "memory", "偏好", "个人信息")
    mock_terms: tuple[str, ...] = ("deepmemo", "mock", "demo", "示例", "演示", "截图", "知识库问答")

    def route(self, question: str) -> RouteDecision:
        normalized = question.strip()
        lower = normalized.lower()
        path_hints: list[str] = ["diary"]
        reasons: list[str] = ["默认把 data/diary 作为第一检索范围，因为日常记录是最高优先级本地证据。"]
        matched_scoped_directory = False

        if self._contains_any(lower, self.mock_terms):
            path_hints.insert(0, "mock")
            matched_scoped_directory = True
            reasons.append("命中演示或知识库问答相关问题，优先搜索 data/mock。")

        if self._contains_any(lower, self.idea_terms):
            path_hints.append("ideas")
            matched_scoped_directory = True
            reasons.append("命中想法类问题，在 data/diary 后补充搜索 data/ideas。")

        if self._contains_any(lower, self.diary_terms):
            matched_scoped_directory = True
            reasons.append("命中时间或学习记录问题，强化搜索 data/diary。")

        if self._contains_any(lower, self.memory_terms):
            path_hints.append("memory")
            matched_scoped_directory = True
            reasons.append("命中记忆类问题，在 data/diary 后补充搜索 data/memory。")

        if not matched_scoped_directory:
            path_hints.extend(["ideas", "memory"])
            reasons.append("未命中特定目录时，在 data/diary 后补充搜索 data/ideas 和 data/memory。")

        needs_web = self._contains_any(lower, self.realtime_terms)
        if needs_web:
            reasons.append("问题可能依赖实时或外部信息，允许在本地证据不足时 fallback。")

        query_hints = self.extract_query_hints(normalized)

        return RouteDecision(
            use_local_search=True,
            needs_web=needs_web,
            path_hints=self._dedupe(path_hints),
            query_hints=query_hints,
            reason=" ".join(reasons),
        )

    def extract_query_hints(self, question: str) -> list[str]:
        hints: list[str] = []
        quoted = re.findall(r"[`“\"']([^`“\"']+)[`”\"']", question)
        hints.extend(item.strip() for item in quoted if item.strip())

        latin_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}", question)
        hints.extend(latin_tokens)

        cleaned = re.sub(r"[？?，,。.!！:：；;\[\]（）(){}]", " ", question)
        for part in cleaned.split():
            part = part.strip()
            if len(part) >= 2 and not self._is_stopword(part):
                hints.append(part)

        compact = self._strip_question_words(question)
        if 2 <= len(compact) <= 24:
            hints.append(compact)

        return self._dedupe(hints)[:8]

    def _strip_question_words(self, value: str) -> str:
        cleaned = re.sub(r"[？?，,。.!！:：；;\s]", "", value)
        for token in (
            "我",
            "我的",
            "关于",
            "有哪些",
            "有什么",
            "是什么",
            "为什么",
            "怎么",
            "如何",
            "最近",
            "上周",
            "本周",
            "这个月",
            "请",
            "帮",
            "一下",
        ):
            cleaned = cleaned.replace(token, "")
        return cleaned

    def _is_stopword(self, value: str) -> bool:
        return value in {
            "我",
            "我的",
            "关于",
            "最近",
            "上周",
            "本周",
            "这个月",
            "一下",
            "什么",
            "哪些",
            "如何",
            "怎么",
        }

    def _contains_any(self, value: str, terms: tuple[str, ...]) -> bool:
        return any(term.lower() in value for term in terms)

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in seen:
                result.append(normalized)
                seen.add(normalized)
        return result
