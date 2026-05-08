from src.ai.answer_composer import AnswerComposer
from src.ai.chat_tools import ChatTool
from src.ai.local_search_agent import LocalSearchAgent
from src.ai.query_rewriter import QueryRewriter
from src.ai.query_router import QueryRouter
from src.ai.types import KnowledgeAnswer, KnowledgeAnswerStream
from src.ai.web_search_agent import WebSearchAgent, create_enabled_web_agent
from src.services.llm_service import llm_service


class KnowledgeQAService:
    def __init__(
        self,
        *,
        router: QueryRouter | None = None,
        local_search_agent: LocalSearchAgent | None = None,
        web_search_agent: WebSearchAgent | None = None,
        answer_composer: AnswerComposer | None = None,
        query_rewriter: QueryRewriter | None = None,
    ):
        self.router = router or QueryRouter()
        self.local_search_agent = local_search_agent or LocalSearchAgent()
        self.web_search_agent = web_search_agent or create_enabled_web_agent()
        self.answer_composer = answer_composer or AnswerComposer(llm_service)
        self.query_rewriter = query_rewriter or QueryRewriter(llm_service)

    def answer(
        self,
        question: str,
        *,
        history: list[dict] | None = None,
        tool: ChatTool | None = None,
    ) -> KnowledgeAnswer:
        rewrite = self.query_rewriter.rewrite(question, history=history)
        retrieval_query = rewrite.rewritten_query
        route = self.router.route(retrieval_query)
        local_result = self.local_search_agent.search(retrieval_query, route=route)

        web_result = None
        if route.needs_web and not local_result.high_confidence:
            web_result = self.web_search_agent.search(retrieval_query)

        content = self.answer_composer.compose(
            question,
            local_result,
            route,
            history=history,
            retrieval_query=retrieval_query,
            web_result=web_result,
            tool=tool,
        )
        return KnowledgeAnswer(
            content=content,
            route=route,
            local_result=local_result,
            retrieval_query=retrieval_query,
            rewrite_changed=rewrite.changed,
            web_result=web_result,
        )

    def answer_stream(
        self,
        question: str,
        *,
        history: list[dict] | None = None,
        tool: ChatTool | None = None,
    ) -> KnowledgeAnswerStream:
        rewrite = self.query_rewriter.rewrite(question, history=history)
        retrieval_query = rewrite.rewritten_query
        route = self.router.route(retrieval_query)
        local_result = self.local_search_agent.search(retrieval_query, route=route)

        web_result = None
        if route.needs_web and not local_result.high_confidence:
            web_result = self.web_search_agent.search(retrieval_query)

        chunks = self.answer_composer.compose_stream(
            question,
            local_result,
            route,
            history=history,
            retrieval_query=retrieval_query,
            web_result=web_result,
            tool=tool,
        )
        return KnowledgeAnswerStream(
            chunks=chunks,
            route=route,
            local_result=local_result,
            retrieval_query=retrieval_query,
            rewrite_changed=rewrite.changed,
            web_result=web_result,
        )


knowledge_qa_service = KnowledgeQAService()
