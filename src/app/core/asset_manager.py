import posixpath
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath


IMAGE_EXTENSIONS = {
    ".apng",
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class AssetPaths:
    asset_path: str
    markdown_path: str
    static_path: str
    filename: str


def build_asset_paths(source_path: str, original_filename: str, now: datetime | None = None) -> AssetPaths:
    now = now or datetime.now()
    source = _validate_markdown_source_path(source_path)
    filename = build_asset_filename(original_filename, now)
    asset_path = _asset_directory_for_source(source, now) / filename
    source_parent = source.parent.as_posix()
    markdown_path = posixpath.relpath(asset_path.as_posix(), source_parent)

    return AssetPaths(
        asset_path=asset_path.as_posix(),
        markdown_path=markdown_path,
        static_path=f"/{asset_path.as_posix()}",
        filename=filename,
    )


def build_asset_filename(original_filename: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    source = PurePosixPath(original_filename)
    ext = source.suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image type: {ext or '(none)'}")

    stem = source.stem.strip().lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    if not stem:
        stem = "image"

    return f"{now:%Y%m%d-%H%M%S}-{stem}{ext}"


def build_vditor_upload_response(original_filename: str, markdown_path: str) -> dict:
    return {
        "code": 0,
        "msg": "",
        "data": {
            "errFiles": [],
            "succMap": {
                original_filename: markdown_path,
            },
        },
    }


def save_image_asset(
    data_dir: Path,
    source_path: str,
    original_filename: str,
    content_type: str,
    content: bytes,
    now: datetime | None = None,
) -> dict:
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError("Image is larger than 10MB")
    if not content_type.startswith("image/"):
        raise ValueError("Only image uploads are supported")

    paths = build_asset_paths(source_path, original_filename, now)
    target_path = _next_available_path(data_dir / paths.asset_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)

    asset_path = target_path.relative_to(data_dir).as_posix()
    markdown_path = _markdown_path_for_asset(source_path, asset_path)
    return {
        "asset_path": asset_path,
        "markdown_path": markdown_path,
        "static_path": f"/{asset_path}",
        "filename": target_path.name,
    }


def _validate_markdown_source_path(source_path: str) -> PurePosixPath:
    source = PurePosixPath(source_path.replace("\\", "/"))
    if source.is_absolute() or ".." in source.parts:
        raise ValueError("Source path must stay inside data")
    if len(source.parts) < 2 or source.parts[0] == "assets" or source.suffix.lower() != ".md":
        raise ValueError("Asset uploads are only supported for Markdown source files")
    return source


def _markdown_path_for_asset(source_path: str, asset_path: str) -> str:
    source = _validate_markdown_source_path(source_path)
    return posixpath.relpath(asset_path, source.parent.as_posix())


def _asset_directory_for_source(source: PurePosixPath, fallback: datetime) -> PurePosixPath:
    if source.parts[0] == "diary":
        return PurePosixPath("assets", "diary", _diary_date_from_source(source, fallback))
    return PurePosixPath("assets", *source.with_suffix("").parts)


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path

    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _diary_date_from_source(source: PurePosixPath, fallback: datetime) -> str:
    stem = source.stem
    if stem.isdigit() and len(stem) in (3, 4):
        mmdd = stem.zfill(4)
        year = _year_from_source(source, fallback)
        try:
            return datetime(year, int(mmdd[:2]), int(mmdd[2:])).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return fallback.strftime("%Y-%m-%d")


def _year_from_source(source: PurePosixPath, fallback: datetime) -> int:
    for part in source.parts:
        if part.isdigit() and len(part) == 4:
            return int(part)
    return fallback.year
