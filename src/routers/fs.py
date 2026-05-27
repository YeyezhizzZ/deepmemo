from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from typing import Optional

from src.app.core.asset_manager import save_image_asset
from src.app.core.fs_manager import (
    DATA_DIR,
    read_file_content,
    write_file_content,
    move_file,
    scan_directory_tree,
    update_sync_status,
    create_file,
    create_directory,
)

router = APIRouter(prefix="/api/fs", tags=["filesystem"])


class WriteRequest(BaseModel):
    path: str
    content: str


class MoveRequest(BaseModel):
    old_path: str
    new_path: str


class SyncStatusRequest(BaseModel):
    path: str
    sync_status: str


class CreateFileRequest(BaseModel):
    path: str
    content: str = ""


class CreateDirRequest(BaseModel):
    path: str


@router.get("/tree")
def get_tree():
    """递归扫描 data/ 目录，返回嵌套 JSON"""
    return scan_directory_tree()


@router.get("/content")
def get_content(path: str):
    """读取物理文件并返回字符串"""
    try:
        return {"path": path, "content": read_file_content(path)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/write")
def write_file(data: WriteRequest):
    """接收 Markdown 内容并写入物理磁盘，同时更新 file_hash"""
    try:
        result = write_file_content(data.path, data.content)
        return {"message": "File written successfully", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/move")
def move_file_api(data: MoveRequest):
    """处理重命名或拖拽移动"""
    try:
        result = move_file(data.old_path, data.new_path)
        return {"message": "File moved successfully", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/sync-status")
def patch_sync_status(data: SyncStatusRequest):
    """更新文件的 sync_status"""
    try:
        update_sync_status(data.path, data.sync_status)
        return {"message": "Sync status updated", "path": data.path, "sync_status": data.sync_status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-file")
def create_file_api(data: CreateFileRequest):
    """创建新文件"""
    try:
        result = create_file(data.path, data.content)
        return {"message": "File created successfully", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-directory")
def create_directory_api(data: CreateDirRequest):
    """创建新目录"""
    try:
        result = create_directory(data.path)
        return {"message": "Directory created successfully", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-asset")
async def upload_asset(
    source_path: str = Form(...),
    files: list[UploadFile] = File(..., alias="file[]"),
):
    """保存 Markdown 图片附件，并返回 Vditor 可识别的上传结果。"""
    succ_map = {}
    err_files = []

    for upload in files:
        filename = upload.filename or "image.png"
        try:
            result = save_image_asset(
                data_dir=DATA_DIR,
                source_path=source_path,
                original_filename=filename,
                content_type=upload.content_type or "",
                content=await upload.read(),
            )
            succ_map[filename] = result["markdown_path"]
        except ValueError:
            err_files.append(filename)

    return {
        "code": 0,
        "msg": "",
        "data": {
            "errFiles": err_files,
            "succMap": succ_map,
        },
    }
