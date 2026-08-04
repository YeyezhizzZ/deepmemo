from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.knowledge.activity_log import append_activity
from src.knowledge.card_compiler import KnowledgeCardCompiler
from src.knowledge.card_store import CardStore
from src.knowledge.commit_compiler import CommitKnowledgeCompiler
from src.knowledge.evaluation import KnowledgeEvaluator
from src.knowledge.maintenance import KnowledgeMaintainer
from src.knowledge.models import CompileResult, KnowledgeCard
from src.knowledge.repowiki import RepoWikiBuilder
from src.knowledge.retriever import KnowledgeRetriever
from src.knowledge.view_model import KnowledgeViewService


DATA_DIR = Path(os.getenv("DEEPMEMO_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
_EDITABLE_CARD_FIELDS = {
    "title",
    "type",
    "density",
    "definition",
    "key_facts",
    "related_cards",
    "tags",
    "aliases",
}


class CompileFileRequest(BaseModel):
    path: str


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=8, ge=1, le=50)


class CompileCommitRequest(BaseModel):
    commit: str = "HEAD"


class RewriteRequest(BaseModel):
    instruction: str = ""


class PinCardFieldRequest(BaseModel):
    field: str


class EvalRequest(BaseModel):
    min_health: float = Field(default=0.0, ge=0.0, le=100.0)
    min_citation_coverage: float = Field(default=0.0, ge=0.0, le=100.0)
    min_citation_precision: float = Field(default=0.0, ge=0.0, le=100.0)
    record: bool = True


def _store() -> CardStore:
    return CardStore(DATA_DIR)


def _compiler() -> KnowledgeCardCompiler:
    return KnowledgeCardCompiler(DATA_DIR)


def _compile_result_response(result: CompileResult) -> dict:
    if (
        result.errors
        and not result.compiled_files
        and not result.card_slugs
        and not result.candidate_ids
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Knowledge compilation failed",
                "errors": result.errors,
            },
        )
    return result.to_dict()


@router.get("/cards")
def list_cards(type: str | None = None, tag: str | None = None) -> dict[str, list[dict]]:
    return {"cards": [card.to_dict() for card in _store().list_cards(card_type=type, tag=tag)]}


@router.get("/cards/{slug}")
def get_card(slug: str) -> dict:
    try:
        card = _store().load(slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if card is None:
        raise HTTPException(status_code=404, detail="Knowledge card not found")
    return card.to_dict()


@router.put("/cards/{slug}")
def update_card(slug: str, updates: dict[str, Any]) -> dict:
    store = _store()
    try:
        card = store.load(slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if card is None:
        raise HTTPException(status_code=404, detail="Knowledge card not found")

    for field, value in updates.items():
        if field not in _EDITABLE_CARD_FIELDS:
            raise HTTPException(status_code=400, detail=f"Unsupported card field: {field}")
        setattr(card, field, value)
        if field not in card.human_edited_fields:
            card.human_edited_fields.append(field)
    card.human_edited = True
    store.save(KnowledgeCard.from_dict(card.to_dict()))
    return store.load(slug).to_dict()


@router.delete("/cards/{slug}")
def delete_card(slug: str) -> dict:
    try:
        deleted = _store().delete(slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge card not found")
    return {"slug": slug, "deleted": True}


@router.post("/compile")
def compile_all() -> dict:
    return _compile_result_response(_compiler().compile_all())


@router.post("/compile/file")
def compile_file(request: CompileFileRequest) -> dict:
    try:
        return _compile_result_response(_compiler().compile_file(request.path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/candidates")
def list_compile_candidates() -> dict:
    return {"candidates": _compiler().list_candidates()}


@router.post("/candidates/{candidate_id}/approve")
def approve_compile_candidate(candidate_id: str) -> dict:
    try:
        return _compiler().approve_candidate(candidate_id).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/candidates/{candidate_id}/reject")
def reject_compile_candidate(candidate_id: str) -> dict:
    try:
        return _compiler().reject_candidate(candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/compile/commit")
def compile_commit(request: CompileCommitRequest) -> dict:
    try:
        return CommitKnowledgeCompiler(DATA_DIR).compile_commit(request.commit).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/search")
def search_cards(request: SearchRequest) -> dict:
    retriever = KnowledgeRetriever(DATA_DIR)
    results = retriever.search(request.query, limit=request.limit)
    append_activity(
        DATA_DIR,
        "query",
        request.query[:160],
        [f"Pages: {', '.join(result['slug'] for result in results) or '(none)'}"],
    )
    return {"results": results, "warnings": retriever.last_warnings}


@router.get("/stats")
def stats() -> dict:
    return _store().load_index().stats


@router.get("/health")
def health() -> dict:
    store = _store()
    maintainer = KnowledgeMaintainer(DATA_DIR, store=store)
    maintainer.update_staleness_scores()
    index = store.load_index()
    return {
        "stats": index.stats,
        "orphan_cards": maintainer.detect_orphans(),
        "index_path": str(store.index_path),
    }


@router.post("/maintain")
def maintain() -> dict:
    return KnowledgeMaintainer(DATA_DIR).run_maintenance().to_dict()


@router.post("/eval")
def evaluate_knowledge(request: EvalRequest) -> dict:
    return KnowledgeEvaluator(DATA_DIR).evaluate(
        min_health=request.min_health,
        min_citation_coverage=request.min_citation_coverage,
        min_citation_precision=request.min_citation_precision,
        record=request.record,
    )


@router.post("/repowiki/rebuild")
def rebuild_repowiki() -> dict:
    return RepoWikiBuilder(DATA_DIR).rebuild()


@router.get("/repowiki/pages")
def list_repowiki_pages() -> dict:
    return {"pages": [page.to_dict() for page in RepoWikiBuilder(DATA_DIR).list_pages()]}


@router.get("/repowiki/pages/{slug}")
def get_repowiki_page(slug: str) -> dict:
    try:
        return RepoWikiBuilder(DATA_DIR).load_page(slug).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/view")
def get_knowledge_view() -> dict:
    return KnowledgeViewService(DATA_DIR).build_view()


@router.get("/view/pages")
def list_knowledge_view_pages() -> dict:
    return {"pages": KnowledgeViewService(DATA_DIR).list_pages()}


@router.get("/view/pages/{slug}")
def get_knowledge_view_page(slug: str) -> dict:
    try:
        return KnowledgeViewService(DATA_DIR).get_page(slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/view/review")
def list_knowledge_review_items() -> dict:
    return {"items": KnowledgeViewService(DATA_DIR).review_queue()}


@router.post("/view/review/{item_id}/confirm")
def confirm_knowledge_review_item(item_id: str) -> dict:
    try:
        return KnowledgeViewService(DATA_DIR).confirm_review_item(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/view/review/{item_id}/hide")
def hide_knowledge_review_item(item_id: str) -> dict:
    try:
        return KnowledgeViewService(DATA_DIR).hide_review_item(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/view/review/{item_id}/rewrite")
def rewrite_knowledge_review_item(item_id: str, request: RewriteRequest) -> dict:
    try:
        return KnowledgeViewService(DATA_DIR).request_rewrite(item_id, instruction=request.instruction)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/view/review/{item_id}/apply")
def apply_knowledge_review_item(item_id: str) -> dict:
    try:
        return KnowledgeViewService(DATA_DIR).apply_review_item(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/view/cards/{slug}/pin")
def pin_knowledge_card_field(slug: str, request: PinCardFieldRequest) -> dict:
    try:
        return KnowledgeViewService(DATA_DIR).pin_card_field(slug, request.field)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
