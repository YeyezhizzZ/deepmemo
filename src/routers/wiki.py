from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.wiki.ingest import DiaryWikiIngestConfig, run_diary_wiki_ingest
from src.wiki.graph import build_diary_graph
from src.wiki.health import build_wiki_health_report
from src.wiki.frontmatter import build_default_frontmatter, read_markdown_page, render_markdown_page
from src.wiki.ingest_pipeline import auto_ingest
from src.wiki.path_utils import normalize_rel_path, rel_path, resolve_data_path
from src.wiki.policy import load_policy_bundle
from src.wiki.storage import create_directory, delete_path, move_path, write_text
from src.wiki.tree import build_tree, list_markdown_files


router = APIRouter(prefix="/wiki", tags=["wiki"])


class PageCreateRequest(BaseModel):
    path: str
    title: str
    type: str = "source"
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    status: str = "draft"
    owner: str | None = None
    confidence: float | None = None
    aliases: list[str] = Field(default_factory=list)


class PageWriteRequest(BaseModel):
    path: str
    content: str


class MoveRequest(BaseModel):
    old_path: str
    new_path: str


class DirectoryCreateRequest(BaseModel):
    path: str


class WikiRebuildRequest(BaseModel):
    clean: bool = False


class IngestRequest(BaseModel):
    source_path: str



def _page_payload(file_path):
    page, body = read_markdown_page(file_path)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    return {
        "path": rel_path(file_path),
        "title": page.title,
        "type": page.type,
        "status": page.status,
        "tags": page.tags,
        "sources": page.sources,
        "related": page.related,
        "last_updated": page.last_updated,
        "body": body,
        "content": file_path.read_text(encoding="utf-8"),
    }


@router.get("/tree")
def get_wiki_tree():
    return {"tree": build_tree()}


@router.get("/graph")
def get_wiki_graph():
    return build_diary_graph()


@router.get("/health")
def get_wiki_health():
    return build_wiki_health_report()


@router.post("/rebuild")
def rebuild_wiki(data: WikiRebuildRequest):
    result = run_diary_wiki_ingest(DiaryWikiIngestConfig(clean=data.clean))
    return {
        "message": "Wiki rebuilt successfully",
        **result,
        "health": build_wiki_health_report(),
    }


@router.post("/ingest")
def ingest_source(data: IngestRequest):
    """
    单文件ingest：读取源文件 → 分析 → 生成wiki页面
    参考 reference/llm_wiki/llm_wiki 的两阶段处理
    """
    from pathlib import Path

    source_path = Path(data.source_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"Source file not found: {data.source_path}")

    # 读取现有的index和overview作为上下文
    wiki_dir = Path("data/wiki")
    index_path = wiki_dir / "index.md"
    overview_path = wiki_dir / "overview.md"

    index_content = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    overview_content = overview_path.read_text(encoding="utf-8") if overview_path.exists() else ""

    try:
        result = auto_ingest(
            source_path=data.source_path,
            wiki_dir=wiki_dir,
            index=index_content,
            overview=overview_content,
        )
        return {
            "message": "Ingest completed successfully",
            "written_paths": result.written_paths,
            "warnings": result.warnings,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingest failed: {str(e)}")


@router.get("/pages")
def list_wiki_pages(page_type: str | None = Query(default=None)):
    pages: list[dict] = []
    for file_path in list_markdown_files():
        try:
            payload = _page_payload(file_path)
        except HTTPException:
            continue
        body_lines = [line.strip() for line in payload["body"].splitlines() if line.strip()]
        pages.append(
            {
                "path": payload["path"],
                "title": payload["title"],
                "type": payload["type"],
                "status": payload["status"],
                "tags": payload["tags"],
                "sources": payload["sources"],
                "related": payload["related"],
                "last_updated": payload["last_updated"],
                "summary": body_lines[0] if body_lines else "",
            }
        )
    if page_type:
        pages = [page for page in pages if page["type"] == page_type]
    return {"pages": pages}


@router.get("/page")
def get_wiki_page(path: str):
    normalized = normalize_rel_path(path)
    full_path = resolve_data_path(normalized)

    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="Page not found")

    return _page_payload(full_path)


@router.post("/page")
def create_wiki_page(data: PageCreateRequest):
    normalized = normalize_rel_path(data.path)
    full_path = resolve_data_path(normalized)
    if full_path.exists():
        raise HTTPException(status_code=409, detail="Page already exists")

    frontmatter = build_default_frontmatter(
        title=data.title,
        page_type=data.type,
        status=data.status,
        tags=data.tags,
        sources=data.sources,
        related=data.related,
    )
    frontmatter["aliases"] = data.aliases
    if data.owner:
        frontmatter["owner"] = data.owner
    if data.confidence is not None:
        frontmatter["confidence"] = data.confidence

    result = write_text(normalized, render_markdown_page(frontmatter, data.body))
    return {"message": "Page created successfully", **result, "path": normalized}


@router.put("/page")
def update_wiki_page(data: PageWriteRequest):
    normalized = normalize_rel_path(data.path)
    result = write_text(normalized, data.content)
    return {"message": "Page written successfully", **result, "path": normalized}


@router.delete("/page")
def delete_wiki_page(path: str):
    normalized = normalize_rel_path(path)
    try:
        result = delete_path(normalized)
        return {"message": "Page deleted successfully", **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/move")
def move_wiki_path(data: MoveRequest):
    try:
        result = move_path(data.old_path, data.new_path)
        return {"message": "Path moved successfully", **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/directory")
def create_wiki_directory(data: DirectoryCreateRequest):
    try:
        result = create_directory(data.path)
        return {"message": "Directory created successfully", **result}
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/policy")
def get_policy():
    return load_policy_bundle()
