from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.ai.types import Evidence, LocalSearchResult, RouteDecision
from src.deepme.settings import DeepMeSettings
from src.services.llm_service import LLMService, llm_service


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    path: str
    display_name: str
    source_type: str
    start_line: int
    end_line: int
    page_start: int | None
    page_end: int | None
    text: str
    content_hash: str


class VersionIndexBuilder:
    def __init__(
        self,
        settings: DeepMeSettings,
        *,
        llm: LLMService | None = None,
    ):
        self.settings = settings
        self.llm = llm or llm_service

    def build(
        self,
        *,
        documents_root: Path,
        manifest: dict,
        index_path: Path,
        source_maps_root: Path | None = None,
    ) -> dict:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix="search-",
            suffix=".sqlite3",
            dir=index_path.parent,
        )
        os.close(fd)
        temp_path = Path(temp_name)
        chunks: list[Chunk] = []
        try:
            with sqlite3.connect(temp_path) as conn:
                self._create_schema(conn)
                for item in manifest.get("files", []):
                    chunks.extend(
                        self._index_document(
                            conn,
                            documents_root=documents_root,
                            source_maps_root=source_maps_root,
                            item=item,
                        )
                    )
                embedding_count, embedding_model = self._build_embeddings(conn, chunks)
                conn.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES ('chunk_count', ?)",
                    (str(len(chunks)),),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES ('embedding_count', ?)",
                    (str(embedding_count),),
                )
                if embedding_model:
                    conn.execute(
                        "INSERT OR REPLACE INTO metadata (key, value) VALUES ('embedding_model', ?)",
                        (embedding_model,),
                    )
                conn.commit()
            os.replace(temp_path, index_path)
        finally:
            temp_path.unlink(missing_ok=True)
        return {
            "chunk_count": len(chunks),
            "embedding_count": embedding_count,
            "embedding_model": embedding_model,
        }

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE document (
                document_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                display_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                line_count INTEGER NOT NULL,
                page_count INTEGER
            );
            CREATE TABLE chunk (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                display_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                page_start INTEGER,
                page_end INTEGER,
                text TEXT NOT NULL,
                content_hash TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE chunk_fts USING fts5(
                chunk_id UNINDEXED,
                title,
                body,
                ngrams,
                tokenize = 'unicode61'
            );
            CREATE TABLE chunk_embedding (
                chunk_id TEXT PRIMARY KEY,
                model_id TEXT NOT NULL,
                vector TEXT NOT NULL
            );
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )

    def _index_document(
        self,
        conn: sqlite3.Connection,
        *,
        documents_root: Path,
        source_maps_root: Path | None,
        item: dict,
    ) -> list[Chunk]:
        relative_path = str(item["path"])
        path = (documents_root / relative_path).resolve()
        try:
            path.relative_to(documents_root.resolve())
        except ValueError as exc:
            raise ValueError("document path escapes version root") from exc
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        display_name = str(item.get("display_name") or relative_path)
        source_type = str(item.get("source_type") or "markdown")
        source_map = self._load_source_map(
            source_maps_root,
            item.get("source_map_file"),
        )
        document_id = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:24]
        conn.execute(
            """
            INSERT INTO document (
                document_id, source_path, display_name, source_type,
                sha256, line_count, page_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                relative_path,
                display_name,
                source_type,
                item["sha256"],
                len(lines),
                item.get("page_count"),
            ),
        )

        chunks: list[Chunk] = []
        for start_line, end_line, chunk_text in _split_markdown(lines):
            page_start, page_end = _page_range(source_map, start_line, end_line)
            content_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
            chunk_id = hashlib.sha256(
                f"{relative_path}:{start_line}:{end_line}:{content_hash}".encode("utf-8")
            ).hexdigest()[:32]
            chunk = Chunk(
                chunk_id=chunk_id,
                document_id=document_id,
                path=relative_path,
                display_name=display_name,
                source_type=source_type,
                start_line=start_line,
                end_line=end_line,
                page_start=page_start,
                page_end=page_end,
                text=chunk_text,
                content_hash=content_hash,
            )
            chunks.append(chunk)
            conn.execute(
                """
                INSERT INTO chunk (
                    chunk_id, document_id, source_path, display_name, source_type,
                    start_line, end_line, page_start, page_end, text, content_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.chunk_id,
                    chunk.document_id,
                    chunk.path,
                    chunk.display_name,
                    chunk.source_type,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.page_start,
                    chunk.page_end,
                    chunk.text,
                    chunk.content_hash,
                ),
            )
            conn.execute(
                "INSERT INTO chunk_fts (chunk_id, title, body, ngrams) VALUES (?, ?, ?, ?)",
                (
                    chunk.chunk_id,
                    display_name,
                    chunk.text,
                    _ngram_text(f"{display_name}\n{chunk.text}"),
                ),
            )
        return chunks

    def _load_source_map(
        self,
        source_maps_root: Path | None,
        source_map_file: str | None,
    ) -> list[dict]:
        if source_maps_root is None or not source_map_file:
            return []
        path = (source_maps_root / source_map_file).resolve()
        try:
            path.relative_to(source_maps_root.resolve())
        except ValueError as exc:
            raise ValueError("source map path escapes root") from exc
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("ranges") or [])

    def _build_embeddings(
        self,
        conn: sqlite3.Connection,
        chunks: list[Chunk],
    ) -> tuple[int, str | None]:
        if self.settings.retrieval_mode != "hybrid" or not chunks:
            return 0, None
        try:
            model_id = self.llm.embedding_model()
            vectors: list[list[float]] = []
            for start in range(0, len(chunks), 64):
                batch = chunks[start : start + 64]
                vectors.extend(self.llm.embed([item.text for item in batch]))
            if len(vectors) != len(chunks):
                raise ValueError("embedding batch size mismatch")
            for chunk, vector in zip(chunks, vectors, strict=True):
                if not vector or not all(math.isfinite(float(value)) for value in vector):
                    raise ValueError("embedding contains invalid values")
                conn.execute(
                    "INSERT INTO chunk_embedding (chunk_id, model_id, vector) VALUES (?, ?, ?)",
                    (
                        chunk.chunk_id,
                        model_id,
                        json.dumps([float(value) for value in vector]),
                    ),
                )
            return len(vectors), model_id
        except Exception:
            return 0, None


class VersionedChunkSearchAgent:
    def __init__(
        self,
        index_path: Path,
        settings: DeepMeSettings,
        *,
        llm: LLMService | None = None,
        max_evidence: int = 8,
    ):
        self.index_path = index_path
        self.settings = settings
        self.llm = llm or llm_service
        self.max_evidence = max_evidence

    def search(
        self,
        question: str,
        route: RouteDecision | None = None,
    ) -> LocalSearchResult:
        del route
        if not self.index_path.is_file():
            return _empty_result(question, "knowledge version index is missing")
        with sqlite3.connect(self.index_path) as conn:
            conn.row_factory = sqlite3.Row
            lexical = self._lexical_candidates(conn, question, limit=30)
            semantic = self._semantic_candidates(conn, question, limit=30)
            ranked = self._fuse(lexical, semantic)
            ranked = self._rerank(conn, question, ranked[:20])
            rows = self._load_chunks(conn, ranked[: self.max_evidence])

        evidence = [
            Evidence(
                path=row["source_path"],
                start_line=int(row["start_line"]),
                end_line=int(row["end_line"]),
                excerpt=_numbered_excerpt(row["text"], int(row["start_line"])),
                score=max(0.35, 1.0 - index * 0.08),
                query=question,
                display_name=row["display_name"],
                source_type=row["source_type"],
                page_start=row["page_start"],
                page_end=row["page_end"],
                content_hash=row["content_hash"],
            )
            for index, row in enumerate(rows)
        ]
        return LocalSearchResult(
            question=question,
            evidence=evidence,
            searched_queries=[question],
            searched_paths=["version-index"],
            message=None if evidence else "当前知识版本没有检索到相关证据。",
        )

    def _lexical_candidates(
        self,
        conn: sqlite3.Connection,
        query: str,
        *,
        limit: int,
    ) -> list[str]:
        tokens = _ngrams(query)
        if not tokens:
            return []
        expression = " OR ".join(
            f'"{token.replace(chr(34), "")}"' for token in tokens[:64]
        )
        try:
            rows = conn.execute(
                """
                SELECT chunk_id, bm25(chunk_fts, 0.0, 1.0, 0.5, 3.0) AS rank
                FROM chunk_fts
                WHERE chunk_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (expression, limit),
            ).fetchall()
            return [str(row["chunk_id"]) for row in rows]
        except sqlite3.OperationalError:
            query_tokens = set(tokens)
            scored = []
            for row in conn.execute("SELECT chunk_id, text FROM chunk"):
                overlap = len(query_tokens & set(_ngrams(str(row["text"]))))
                if overlap:
                    scored.append((overlap, str(row["chunk_id"])))
            scored.sort(key=lambda item: (-item[0], item[1]))
            return [chunk_id for _, chunk_id in scored[:limit]]

    def _semantic_candidates(
        self,
        conn: sqlite3.Connection,
        query: str,
        *,
        limit: int,
    ) -> list[str]:
        if self.settings.retrieval_mode != "hybrid":
            return []
        rows = conn.execute(
            "SELECT chunk_id, vector FROM chunk_embedding"
        ).fetchall()
        if not rows:
            return []
        try:
            vectors = self.llm.embed([query])
            if len(vectors) != 1:
                return []
            query_vector = vectors[0]
        except Exception:
            return []
        scored = [
            (
                _cosine(query_vector, json.loads(row["vector"])),
                str(row["chunk_id"]),
            )
            for row in rows
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [chunk_id for _, chunk_id in scored[:limit]]

    def _fuse(self, lexical: list[str], semantic: list[str]) -> list[str]:
        scores: dict[str, float] = {}
        for candidates in (lexical, semantic):
            for rank, chunk_id in enumerate(candidates, start=1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (60 + rank)
        return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))

    def _rerank(
        self,
        conn: sqlite3.Connection,
        query: str,
        chunk_ids: list[str],
    ) -> list[str]:
        if not self.settings.rerank_enabled or len(chunk_ids) < 2:
            return chunk_ids
        rows = self._load_chunks(conn, chunk_ids)
        candidates = [
            {
                "chunk_id": row["chunk_id"],
                "text": str(row["text"])[:1200],
            }
            for row in rows
        ]
        try:
            response = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是检索精排器。只能返回候选 chunk_id 的 JSON 数组，"
                            "按与问题的相关性从高到低排序，不要输出解释。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"query": query, "candidates": candidates},
                            ensure_ascii=False,
                        ),
                    },
                ]
            )
            content = (response.choices[0].message.content or "").strip()
            if content.startswith("```"):
                content = content.strip("`").replace("json\n", "", 1).strip()
            ordered = json.loads(content)
            allowed = set(chunk_ids)
            result = [str(item) for item in ordered if str(item) in allowed]
            result.extend(item for item in chunk_ids if item not in result)
            return result
        except Exception:
            return chunk_ids

    def _load_chunks(
        self,
        conn: sqlite3.Connection,
        chunk_ids: list[str],
    ) -> list[sqlite3.Row]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = conn.execute(
            f"SELECT * FROM chunk WHERE chunk_id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
        by_id = {str(row["chunk_id"]): row for row in rows}
        return [by_id[item] for item in chunk_ids if item in by_id]


def _split_markdown(
    lines: list[str],
    *,
    max_chars: int = 1800,
) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    start = 0
    current: list[str] = []
    current_chars = 0
    for index, line in enumerate(lines):
        line_size = len(line) + 1
        should_break = bool(
            current
            and (
                current_chars + line_size > max_chars
                or (line.startswith("#") and current_chars >= 400)
            )
        )
        if should_break:
            chunks.append((start + 1, index, "\n".join(current).strip()))
            start = index
            current = []
            current_chars = 0
        current.append(line)
        current_chars += line_size
    if current:
        chunks.append((start + 1, len(lines), "\n".join(current).strip()))
    return [chunk for chunk in chunks if chunk[2]]


def _normalize_text(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9\u4e00-\u9fff]+", value.lower()))


def _ngrams(value: str) -> list[str]:
    compact = _normalize_text(value)
    if not compact:
        return []
    tokens: list[str] = []
    for size in (2, 3):
        tokens.extend(
            compact[index : index + size]
            for index in range(max(0, len(compact) - size + 1))
        )
    tokens.extend(re.findall(r"[a-z][a-z0-9_-]{1,}", value.lower()))
    return list(dict.fromkeys(tokens))


def _ngram_text(value: str) -> str:
    return " ".join(_ngrams(value))


def _page_range(
    ranges: list[dict],
    start_line: int,
    end_line: int,
) -> tuple[int | None, int | None]:
    pages = [
        int(item["page"])
        for item in ranges
        if item.get("page") is not None
        and int(item["end_line"]) >= start_line
        and int(item["start_line"]) <= end_line
    ]
    if not pages:
        return None, None
    return min(pages), max(pages)


def _numbered_excerpt(text: str, start_line: int) -> str:
    return "\n".join(
        f"{line_number}: {line}"
        for line_number, line in enumerate(text.splitlines(), start=start_line)
    )


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _empty_result(question: str, message: str) -> LocalSearchResult:
    return LocalSearchResult(
        question=question,
        evidence=[],
        searched_queries=[question],
        searched_paths=["version-index"],
        message=message,
    )
