import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

DATABASE_PATH = Path(os.getenv("DEEPMEMO_DB_PATH", Path(__file__).parent.parent.parent / "data.db"))
DATA_DIR = Path(os.getenv("DEEPMEMO_DATA_DIR", Path(__file__).parent.parent.parent / "data"))

router = APIRouter(prefix="/api/diary", tags=["diary"])


class AutoDraftRequest(BaseModel):
    raw_dir: Optional[str] = "raw"
    output_dir: Optional[str] = "diary"


@router.post("/auto-draft")
def auto_draft(request: AutoDraftRequest):
    """扫描 data/raw/ 下最新的 Markdown 文件，调用 LLM 生成日记草稿，返回给前端审核"""
    try:
        raw_path = DATA_DIR / request.raw_dir
        if not raw_path.exists():
            raise HTTPException(status_code=404, detail=f"Directory not found: {request.raw_dir}")

        # 递归扫描 raw 目录，兼容 ai_hot 这类子目录化的爬取结果
        md_files = sorted(
            (path for path in raw_path.rglob("*.md") if path.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not md_files:
            return {"message": "No raw files found", "draft": ""}

        latest_file = md_files[0]
        content = latest_file.read_text(encoding="utf-8")

        # TODO: 调用 LLM 根据语料生成日记草稿
        # 暂时返回读取的内容作为占位
        return {
            "source_file": str(latest_file.name),
            "draft": content,
            "message": "Draft generated (placeholder - LLM integration pending)"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
