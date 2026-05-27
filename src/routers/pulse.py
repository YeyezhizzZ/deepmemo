import os
import subprocess
from pathlib import Path
from datetime import datetime, date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

DATA_DIR = Path(os.getenv("DEEPMEMO_DATA_DIR", Path(__file__).parent.parent.parent.parent / "data"))

router = APIRouter(prefix="/api/pulse", tags=["pulse"])


class PulseTodayResponse(BaseModel):
    date: str
    git_commits: list[dict]
    raw_materials: list[dict]


@router.get("/today", response_model=PulseTodayResponse)
def get_today_pulse():
    """聚合今日 Git Commits 和原始素材"""
    today = date.today().isoformat()

    # 获取今日 git commits
    git_commits = get_today_git_commits()

    # 获取 raw 目录下的素材
    raw_materials = get_raw_materials()

    return PulseTodayResponse(
        date=today,
        git_commits=git_commits,
        raw_materials=raw_materials
    )


def get_today_git_commits() -> list[dict]:
    """获取今日的 Git 提交记录"""
    try:
        today = date.today()
        result = subprocess.run(
            ["git", "log", "--since", f"{today.isoformat()} 00:00:00",
             "--until", f"{today.isoformat()} 23:59:59",
             "--pretty=format:%H|%s|%an|%ai", "--no-merges"],
            capture_output=True,
            text=True,
            cwd=DATA_DIR.parent
        )
        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0],
                    "subject": parts[1],
                    "author": parts[2],
                    "date": parts[3]
                })
        return commits
    except Exception:
        return []


def get_raw_materials(base_path: str = "raw") -> list[dict]:
    """扫描 raw 目录下的素材文件"""
    raw_dir = DATA_DIR / base_path
    if not raw_dir.exists():
        return []

    materials = []
    for item in sorted(raw_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        materials.append({
            "name": item.name,
            "path": str(item.relative_to(DATA_DIR)),
            "type": "directory" if item.is_dir() else "file",
            "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat()
        })
    return materials
