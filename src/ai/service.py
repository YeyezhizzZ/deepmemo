from src.ai.answer_composer import AnswerComposer
from src.ai.chat_tools import ChatTool
from src.ai.local_search_agent import LocalSearchAgent
from src.ai.query_router import QueryRouter
from src.ai.types import KnowledgeAnswer, KnowledgeAnswerStream
from src.ai.web_search_agent import WebSearchAgent
from src.services.llm_service import llm_service


class KnowledgeQAService:
    def __init__(
        self,
        *,
        router: QueryRouter | None = None,
        local_search_agent: LocalSearchAgent | None = None,
        web_search_agent: WebSearchAgent | None = None,
        answer_composer: AnswerComposer | None = None,
    ):
        self.router = router or QueryRouter()
        self.local_search_agent = local_search_agent or LocalSearchAgent()
        self.web_search_agent = web_search_agent or WebSearchAgent(enabled=False)
        self.answer_composer = answer_composer or AnswerComposer(llm_service)

    def answer(
        self,
        question: str,
        *,
        history: list[dict] | None = None,
        tool: ChatTool | None = None,
    ) -> KnowledgeAnswer:
        route = self.router.route(question)
        local_result = self.local_search_agent.search(question, route=route)

        web_result = None
        if route.needs_web and not local_result.high_confidence:
            web_result = self.web_search_agent.search(question)

        content = self.answer_composer.compose(
            question,
            local_result,
            route,
            history=history,
            web_result=web_result,
            tool=tool,
        )
        return KnowledgeAnswer(
            content=content,
            route=route,
            local_result=local_result,
            web_result=web_result,
        )

    def answer_stream(
        self,
        question: str,
        *,
        history: list[dict] | None = None,
        tool: ChatTool | None = None,
    ) -> KnowledgeAnswerStream:
        route = self.router.route(question)
        local_result = self.local_search_agent.search(question, route=route)

        web_result = None
        if route.needs_web and not local_result.high_confidence:
            web_result = self.web_search_agent.search(question)

        chunks = self.answer_composer.compose_stream(
            question,
            local_result,
            route,
            history=history,
            web_result=web_result,
            tool=tool,
        )
        return KnowledgeAnswerStream(
            chunks=chunks,
            route=route,
            local_result=local_result,
            web_result=web_result,
        )


knowledge_qa_service = KnowledgeQAService()
