import json
import subprocess
from pathlib import Path

from src.ai.types import (
    CountMatch,
    FileSearchResult,
    GrepContentResult,
    GrepHit,
    GrepMode,
    LineRef,
    ReadLinesResult,
)


class KnowledgeBaseAccessError(ValueError):
    """Raised when a requested path escapes the allowed knowledge base root."""


class KnowledgeBaseTools:
    def __init__(
        self,
        root_path: str | Path | None = None,
        *,
        max_results: int = 250,
        max_read_lines: int = 120,
        rg_command: str = "rg",
        timeout_seconds: int = 10,
    ):
        repo_root = Path(__file__).resolve().parents[2]
        self.root_path = (Path(root_path) if root_path else repo_root / "data").resolve()
        self.max_results = max_results
        self.max_read_lines = max_read_lines
        self.rg_command = rg_command
        self.timeout_seconds = timeout_seconds

    def glob_files(self, pattern: str = "**/*.md") -> FileSearchResult:
        pattern = (pattern or "**/*.md").strip()
        if not pattern:
            pattern = "**/*.md"
        self._ensure_safe_glob_pattern(pattern)

        candidates: list[Path] = []
        if self._looks_like_path(pattern):
            target = self._resolve_path(pattern, allow_dir=True, must_exist=False)
            if target.exists() and target.is_dir():
                candidates.extend(target.rglob("*.md"))
            elif target.exists():
                candidates.append(target)

        candidates.extend(self.root_path.glob(pattern))
        if not pattern.endswith(".md") and not pattern.endswith("*.md"):
            candidates.extend(self.root_path.glob(f"{pattern.rstrip('/')}/**/*.md"))

        files: list[str] = []
        seen: set[str] = set()
        truncated = False
        for candidate in sorted(candidates):
            if len(files) >= self.max_results:
                truncated = True
                break
            if not candidate.is_file() or not self._is_allowed_markdown(candidate):
                continue
            rel = self._relative_path(candidate)
            if rel not in seen:
                files.append(rel)
                seen.add(rel)

        message = None
        if truncated:
            message = f"结果超过 {self.max_results} 条，已截断；请细化文件模式。"
        return FileSearchResult(files=files, truncated=truncated, message=message)

    def grep_content(
        self,
        query: str,
        path: str | None = None,
        *,
        context: int = 5,
        mode: GrepMode = "content",
    ) -> GrepContentResult:
        query = query.strip()
        if not query:
            return GrepContentResult(query=query, mode=mode, message="搜索词为空。")
        if mode not in ("files_with_matches", "content", "count"):
            raise ValueError(f"Unsupported grep mode: {mode}")

        context = min(max(context, 0), 20)
        target = self._resolve_path(path, allow_dir=True) if path else self.root_path
        if target.is_file() and not self._is_allowed_markdown(target):
            raise KnowledgeBaseAccessError("只能搜索 Markdown 文件。")
        search_files = self._search_files(target) if target.is_dir() else [target]

        base_cmd = [
            self.rg_command,
            "--fixed-strings",
            "--smart-case",
            "--glob",
            "*.md",
            "--max-columns",
            "500",
        ]

        if mode == "files_with_matches":
            return self._grep_files_with_matches(query, mode, base_cmd, search_files)

        if mode == "count":
            return self._grep_count(query, mode, base_cmd, search_files)

        return self._grep_content(query, mode, base_cmd, search_files, context)

    def count_matches(self, query: str, path: str | None = None) -> GrepContentResult:
        return self.grep_content(query, path=path, mode="count")

    def read_lines(self, path: str, start: int, end: int) -> ReadLinesResult:
        target = self._resolve_path(path, allow_dir=False)
        if not self._is_allowed_markdown(target):
            raise KnowledgeBaseAccessError("只能读取 Markdown 文件。")

        start = max(1, start)
        end = max(start, end)
        requested = end - start + 1
        truncated = requested > self.max_read_lines
        if truncated:
            end = start + self.max_read_lines - 1

        lines: list[LineRef] = []
        with target.open("r", encoding="utf-8") as handle:
            for index, text in enumerate(handle, start=1):
                if index < start:
                    continue
                if index > end:
                    break
                lines.append(LineRef(path=self._relative_path(target), line_number=index, text=text.rstrip("\n")))

        message = None
        if truncated:
            message = f"单次 read_lines 限制为 {self.max_read_lines} 行，已截断。"
        return ReadLinesResult(path=self._relative_path(target), start=start, end=end, lines=lines, truncated=truncated, message=message)

    def _grep_files_with_matches(
        self,
        query: str,
        mode: GrepMode,
        base_cmd: list[str],
        search_files: list[Path],
    ) -> GrepContentResult:
        files: list[str] = []
        truncated = False
        for file_path in search_files:
            if len(files) >= self.max_results:
                truncated = True
                break
            result = self._run_rg([*base_cmd, "--files-with-matches", "--", query, str(file_path)])
            if result.returncode == 0:
                files.append(self._relative_path(file_path))

        return GrepContentResult(
            query=query,
            mode=mode,
            files=files,
            truncated=truncated,
            message=self._limit_message(truncated),
        )

    def _grep_count(
        self,
        query: str,
        mode: GrepMode,
        base_cmd: list[str],
        search_files: list[Path],
    ) -> GrepContentResult:
        counts: list[CountMatch] = []
        truncated = False
        for file_path in search_files:
            if len(counts) >= self.max_results:
                truncated = True
                break
            result = self._run_rg([*base_cmd, "--count-matches", "--with-filename", "--", query, str(file_path)])
            parsed = self._parse_count_result(query, mode, result.stdout, result.returncode)
            if parsed.counts:
                counts.extend(parsed.counts)

        counts.sort(key=lambda item: item.count, reverse=True)
        return GrepContentResult(
            query=query,
            mode=mode,
            counts=counts,
            truncated=truncated,
            message=self._limit_message(truncated),
        )

    def _grep_content(
        self,
        query: str,
        mode: GrepMode,
        base_cmd: list[str],
        search_files: list[Path],
        context: int,
    ) -> GrepContentResult:
        hits: list[GrepHit] = []
        truncated = False
        for file_path in search_files:
            if len(hits) >= self.max_results:
                truncated = True
                break
            result = self._run_rg(
                [
                    *base_cmd,
                    "--json",
                    "--line-number",
                    "--context",
                    str(context),
                    "--",
                    query,
                    str(file_path),
                ]
            )
            parsed = self._parse_content_result(query, mode, result.stdout, result.returncode, context)
            truncated = truncated or parsed.truncated
            for hit in parsed.hits:
                if len(hits) >= self.max_results:
                    truncated = True
                    break
                hits.append(hit)

        return GrepContentResult(
            query=query,
            mode=mode,
            hits=hits,
            truncated=truncated,
            message=self._limit_message(truncated),
        )

    def _parse_files_result(
        self,
        query: str,
        mode: GrepMode,
        stdout: str,
        returncode: int,
    ) -> GrepContentResult:
        if returncode == 1:
            return GrepContentResult(query=query, mode=mode)

        files: list[str] = []
        truncated = False
        for line in stdout.splitlines():
            if len(files) >= self.max_results:
                truncated = True
                break
            candidate = Path(line)
            if self._is_allowed_markdown(candidate):
                files.append(self._relative_path(candidate))

        return GrepContentResult(
            query=query,
            mode=mode,
            files=files,
            truncated=truncated,
            message=self._limit_message(truncated),
        )

    def _parse_count_result(
        self,
        query: str,
        mode: GrepMode,
        stdout: str,
        returncode: int,
    ) -> GrepContentResult:
        if returncode == 1:
            return GrepContentResult(query=query, mode=mode)

        counts: list[CountMatch] = []
        truncated = False
        for line in stdout.splitlines():
            if len(counts) >= self.max_results:
                truncated = True
                break
            path_text, _, count_text = line.rpartition(":")
            if not path_text or not count_text.isdigit():
                continue
            candidate = Path(path_text)
            if self._is_allowed_markdown(candidate):
                counts.append(CountMatch(path=self._relative_path(candidate), count=int(count_text)))

        counts.sort(key=lambda item: item.count, reverse=True)
        return GrepContentResult(
            query=query,
            mode=mode,
            counts=counts,
            truncated=truncated,
            message=self._limit_message(truncated),
        )

    def _parse_content_result(
        self,
        query: str,
        mode: GrepMode,
        stdout: str,
        returncode: int,
        context: int,
    ) -> GrepContentResult:
        if returncode == 1:
            return GrepContentResult(query=query, mode=mode)

        hits: list[GrepHit] = []
        before_buffer: list[LineRef] = []
        active_hit: GrepHit | None = None
        truncated = False

        for raw_line in stdout.splitlines():
            if len(hits) >= self.max_results:
                truncated = True
                break

            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            if event_type == "begin":
                before_buffer = []
                active_hit = None
                continue

            data = event.get("data") or {}
            if event_type not in ("match", "context"):
                continue

            path_text = ((data.get("path") or {}).get("text") or "").strip()
            line_number = int(data.get("line_number") or 0)
            line_text = ((data.get("lines") or {}).get("text") or "").rstrip("\n")
            if not path_text or not line_number:
                continue

            candidate = Path(path_text)
            if not self._is_allowed_markdown(candidate):
                continue
            ref = LineRef(path=self._relative_path(candidate), line_number=line_number, text=line_text)

            if event_type == "context":
                if active_hit and active_hit.path == ref.path and ref.line_number > active_hit.line_number:
                    active_hit.context_after.append(ref)
                    active_hit.context_after = active_hit.context_after[:context]
                else:
                    before_buffer.append(ref)
                    before_buffer = before_buffer[-context:]
                continue

            before = [
                item
                for item in before_buffer
                if item.path == ref.path and item.line_number < ref.line_number
            ][-context:]
            active_hit = GrepHit(
                path=ref.path,
                line_number=ref.line_number,
                text=ref.text,
                context_before=before,
                context_after=[],
            )
            hits.append(active_hit)
            before_buffer = []

        return GrepContentResult(
            query=query,
            mode=mode,
            hits=hits,
            truncated=truncated,
            message=self._limit_message(truncated),
        )

    def _run_rg(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("未找到 ripgrep，请先安装 rg。") from exc

        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.strip() or "ripgrep 搜索失败。")
        return result

    def _search_files(self, target: Path) -> list[Path]:
        candidates = target.rglob("*.md")
        files = [
            candidate
            for candidate in candidates
            if candidate.is_file() and self._is_allowed_markdown(candidate)
        ]
        return sorted(files, key=self._search_sort_key)

    def _search_sort_key(self, path: Path) -> tuple[int, int, int, str]:
        diary_date = self._diary_filename_date(path)
        rel_path = self._relative_path(path)
        if diary_date:
            month, day = diary_date
            return (0, -month, -day, rel_path)
        return (1, 0, 0, rel_path)

    def _diary_filename_date(self, path: Path) -> tuple[int, int] | None:
        rel_parts = path.resolve().relative_to(self.root_path).parts
        if not rel_parts or rel_parts[0] != "diary":
            return None

        stem = path.stem
        if not stem.isdigit() or len(stem) < 2:
            return None
        if len(stem) == 2:
            month = int(stem[0])
            day = int(stem[1])
        elif len(stem) == 3:
            month = int(stem[0])
            day = int(stem[1:])
        else:
            month = int(stem[:-2])
            day = int(stem[-2:])

        if 1 <= month <= 12 and 1 <= day <= 31:
            return month, day
        return None

    def _looks_like_path(self, pattern: str) -> bool:
        return not any(token in pattern for token in ("*", "?", "[", "]"))

    def _ensure_safe_glob_pattern(self, pattern: str) -> None:
        incoming = Path(pattern)
        if incoming.is_absolute() or ".." in incoming.parts:
            raise KnowledgeBaseAccessError("glob pattern 必须是 data/ 内的相对路径，且不能包含 ..。")

    def _resolve_path(self, path: str | Path | None, *, allow_dir: bool, must_exist: bool = True) -> Path:
        if path is None or str(path).strip() == "":
            return self.root_path

        incoming = Path(path)
        candidate = incoming if incoming.is_absolute() else self.root_path / incoming
        candidate = candidate.resolve()
        self._ensure_inside_root(candidate)

        if must_exist and not candidate.exists():
            raise FileNotFoundError(f"路径不存在：{path}")
        if must_exist and candidate.is_dir() and not allow_dir:
            raise KnowledgeBaseAccessError("当前工具需要具体 Markdown 文件路径。")
        return candidate

    def _ensure_inside_root(self, path: Path) -> None:
        try:
            path.relative_to(self.root_path)
        except ValueError as exc:
            raise KnowledgeBaseAccessError("路径必须位于 data/ 知识库目录内。") from exc

    def _is_allowed_markdown(self, path: Path) -> bool:
        path = path.resolve()
        self._ensure_inside_root(path)
        if path.suffix.lower() != ".md":
            return False
        rel_parts = path.relative_to(self.root_path).parts
        return not any(part.startswith(".") for part in rel_parts)

    def _relative_path(self, path: Path) -> str:
        path = path.resolve()
        self._ensure_inside_root(path)
        return path.relative_to(self.root_path).as_posix()

    def _limit_message(self, truncated: bool) -> str | None:
        if not truncated:
            return None
        return f"结果超过 {self.max_results} 条，已截断；请细化搜索词。"
