from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from src.deepme.retrieval import VersionIndexBuilder, VersionedChunkSearchAgent
from src.deepme.runtime import get_runtime


class FakeEmbeddingLLM:
    def embedding_model(self):
        return "fake-embedding"

    def embed(self, texts):
        return [
            [
                float("灵感" in text),
                float("视频" in text),
                float(len(text) % 7),
            ]
            for text in texts
        ]


def test_version_index_ngram_retrieval_preserves_lineage(tmp_path):
    settings = replace(
        get_runtime().settings,
        runtime_dir=tmp_path / "runtime",
        retrieval_mode="ngram",
        rerank_enabled=False,
    )
    documents = tmp_path / "documents"
    documents.mkdir()
    content = "# 灵感 Agent\n\n批量生产创意视频时，单步 Prompt 容易造成同质化。\n"
    (documents / "project.md").write_text(content, encoding="utf-8")
    sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    manifest = {
        "files": [
            {
                "path": "project.md",
                "display_name": "灵感 Agent 项目",
                "source_type": "markdown",
                "sha256": sha256,
            }
        ]
    }
    index_path = tmp_path / "index" / "search.sqlite3"

    stats = VersionIndexBuilder(settings).build(
        documents_root=documents,
        manifest=manifest,
        index_path=index_path,
    )
    result = VersionedChunkSearchAgent(
        index_path,
        settings,
    ).search("创意视频为什么会同质化")

    assert stats["chunk_count"] == 1
    assert stats["embedding_count"] == 0
    assert result.evidence
    assert result.evidence[0].path == "project.md"
    assert result.evidence[0].display_name == "灵感 Agent 项目"
    assert result.evidence[0].content_hash
    assert "单步 Prompt" in result.evidence[0].excerpt


def test_version_index_hybrid_embedding_is_optional(tmp_path):
    settings = replace(
        get_runtime().settings,
        runtime_dir=tmp_path / "runtime",
        retrieval_mode="hybrid",
        rerank_enabled=False,
    )
    documents = tmp_path / "documents"
    documents.mkdir()
    content = "# 视频\n\n灵感生成依赖知识检索。\n"
    (documents / "note.md").write_text(content, encoding="utf-8")
    manifest = {
        "files": [
            {
                "path": "note.md",
                "display_name": "视频笔记",
                "source_type": "markdown",
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        ]
    }
    index_path = tmp_path / "search.sqlite3"
    llm = FakeEmbeddingLLM()

    stats = VersionIndexBuilder(settings, llm=llm).build(
        documents_root=documents,
        manifest=manifest,
        index_path=index_path,
    )
    result = VersionedChunkSearchAgent(
        index_path,
        settings,
        llm=llm,
    ).search("灵感视频")

    assert stats["embedding_count"] == 1
    assert stats["embedding_model"] == "fake-embedding"
    assert result.evidence


def test_pdf_source_map_sets_page_range(tmp_path):
    settings = replace(
        get_runtime().settings,
        runtime_dir=tmp_path / "runtime",
        retrieval_mode="ngram",
        rerank_enabled=False,
    )
    documents = tmp_path / "documents"
    maps = tmp_path / "maps"
    documents.mkdir()
    maps.mkdir()
    content = "# Report\n\n## Page 1\n\nalpha context\n\n## Page 2\n\nbeta evidence\n"
    (documents / "report.md").write_text(content, encoding="utf-8")
    (maps / "report.json").write_text(
        json.dumps(
            {
                "source_type": "pdf",
                "page_count": 2,
                "ranges": [
                    {"start_line": 3, "end_line": 6, "page": 1},
                    {"start_line": 7, "end_line": 10, "page": 2},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "files": [
            {
                "path": "report.md",
                "display_name": "report.pdf",
                "source_type": "pdf",
                "source_map_file": "report.json",
                "page_count": 2,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        ]
    }
    index_path = tmp_path / "search.sqlite3"
    VersionIndexBuilder(settings).build(
        documents_root=documents,
        source_maps_root=maps,
        manifest=manifest,
        index_path=index_path,
    )

    result = VersionedChunkSearchAgent(index_path, settings).search("beta evidence")

    assert result.evidence
    assert result.evidence[0].source_type == "pdf"
    assert result.evidence[0].page_end == 2
