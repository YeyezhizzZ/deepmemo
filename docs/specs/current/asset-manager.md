# Asset Manager

* **Status**: Current / Human Reviewed

## 1. Scope
管理用户通过前端编辑器上传的图片资源。

## 2. Preserved Behaviors
* **目录分配**：根据关联的 Markdown 路径动态决定存放位置（如 `assets/diary/YYYY-MM-DD`）。
* **Vditor 支持**：上传成功后返回 Vditor 格式的 JSON 结构，用于前端回显。

## 3. Evidence
* `src/app/core/asset_manager.py`

## 4. Current Flow
前端发起 FormData 请求 -> Asset Manager 校验 10MB 大小和拓展名 -> 计算目标路径并写入二进制文件 -> 返回成功或失败。
