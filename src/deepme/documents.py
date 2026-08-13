from __future__ import annotations

import json
import multiprocessing
import queue
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from src.deepme.settings import DeepMeSettings


class DocumentParseError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedDocument:
    markdown: str
    source_type: str
    page_count: int | None
    source_map: list[dict]


class DocumentNormalizer:
    def __init__(self, settings: DeepMeSettings):
        self.settings = settings

    def normalize(self, path: Path, original_name: str) -> NormalizedDocument:
        extension = Path(original_name).suffix.lower()
        if extension in {".md", ".txt"}:
            return self._normalize_text(path, extension)
        if extension == ".pdf":
            return self._normalize_pdf(path, original_name)
        raise DocumentParseError(f"unsupported file extension: {extension}")

    def normalize_with_timeout(
        self,
        path: Path,
        original_name: str,
    ) -> NormalizedDocument:
        context = multiprocessing.get_context("spawn")
        result_queue = context.Queue(maxsize=1)
        process = context.Process(
            target=_normalize_in_child,
            args=(self.settings, path, original_name, result_queue),
            daemon=True,
        )
        process.start()
        process.join(self.settings.parse_timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(5)
            raise DocumentParseError("document parsing timed out")
        try:
            status, payload = result_queue.get(timeout=1)
        except queue.Empty as exc:
            raise DocumentParseError("document parser exited without a result") from exc
        finally:
            result_queue.close()
        if status == "error":
            raise DocumentParseError(str(payload))
        if not isinstance(payload, NormalizedDocument):
            raise DocumentParseError("document parser returned an invalid result")
        return payload

    def write(
        self,
        document: NormalizedDocument,
        *,
        markdown_path: Path,
        source_map_path: Path,
    ) -> None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        source_map_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(document.markdown, encoding="utf-8")
        source_map_path.write_text(
            json.dumps(
                {
                    "source_type": document.source_type,
                    "page_count": document.page_count,
                    "ranges": document.source_map,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _normalize_text(self, path: Path, extension: str) -> NormalizedDocument:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentParseError("text file must be UTF-8") from exc
        if "\x00" in text:
            raise DocumentParseError("text file contains NUL bytes")
        if len(text) > self.settings.normalized_max_chars:
            raise DocumentParseError("normalized text exceeds character limit")
        if not text.endswith("\n"):
            text += "\n"
        line_count = max(1, len(text.splitlines()))
        return NormalizedDocument(
            markdown=text,
            source_type="markdown" if extension == ".md" else "text",
            page_count=None,
            source_map=[
                {
                    "start_line": 1,
                    "end_line": line_count,
                    "page": None,
                }
            ],
        )

    def _normalize_pdf(self, path: Path, original_name: str) -> NormalizedDocument:
        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            raise DocumentParseError("PDF cannot be opened") from exc
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")
            except Exception as exc:
                raise DocumentParseError("encrypted PDF is not supported") from exc
            if not unlocked:
                raise DocumentParseError("encrypted PDF is not supported")
        if len(reader.pages) > self.settings.pdf_max_pages:
            raise DocumentParseError("PDF exceeds page limit")

        lines = [f"# {Path(original_name).name}", ""]
        source_map: list[dict] = []
        extracted_chars = 0
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                raise DocumentParseError(
                    f"PDF page {page_number} cannot be extracted"
                ) from exc
            text = text.replace("\x00", "").strip()
            page_lines = [f"## Page {page_number}", ""]
            if text:
                page_lines.extend(text.splitlines())
            else:
                page_lines.append("[No extractable text]")
            page_lines.append("")
            start_line = len(lines) + 1
            lines.extend(page_lines)
            end_line = len(lines)
            source_map.append(
                {
                    "start_line": start_line,
                    "end_line": end_line,
                    "page": page_number,
                }
            )
            extracted_chars += len(text)
            if len("\n".join(lines)) > self.settings.normalized_max_chars:
                raise DocumentParseError("normalized PDF exceeds character limit")

        if extracted_chars == 0:
            raise DocumentParseError("PDF has no extractable text")
        return NormalizedDocument(
            markdown="\n".join(lines).rstrip() + "\n",
            source_type="pdf",
            page_count=len(reader.pages),
            source_map=source_map,
        )


def _normalize_in_child(
    settings: DeepMeSettings,
    path: Path,
    original_name: str,
    result_queue,
) -> None:
    try:
        result = DocumentNormalizer(settings).normalize(path, original_name)
    except Exception as exc:
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))
        return
    result_queue.put(("ok", result))
