from pathlib import Path

import pytest

from src.knowledge.card_compiler import KnowledgeCardCompiler
from src.knowledge.card_store import CardStore
from src.knowledge.knowledge_llm import OpenAIKnowledgeProvider
from src.services.llm_service import LLMService
from tests.fake_knowledge_provider import FakeKnowledgeProvider


def write_source(data_dir: Path, body: str, name: str = "note.md") -> Path:
    path = data_dir / "diary" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_unchanged_source_skips_all_llm_calls(tmp_path: Path):
    data_dir = tmp_path / "data"
    write_source(data_dir, "# Stable Concept\n\nThe compiled fact is stable.\n")
    provider = FakeKnowledgeProvider()
    compiler = KnowledgeCardCompiler(data_dir, provider=provider)

    first = compiler.compile_all()
    calls_after_first = (provider.extract_calls, provider.generate_calls)
    second = compiler.compile_all()

    assert first.compiled_files == ["diary/note.md"]
    assert second.compiled_files == []
    assert second.skipped_files == ["diary/note.md"]
    assert (provider.extract_calls, provider.generate_calls) == calls_after_first


def test_changed_source_keeps_immutable_snapshots_and_refreshes_page(tmp_path: Path):
    data_dir = tmp_path / "data"
    source = write_source(data_dir, "# Evolving Concept\n\nOriginal fact.\n")
    provider = FakeKnowledgeProvider()
    compiler = KnowledgeCardCompiler(data_dir, provider=provider)
    compiler.compile_file("diary/note.md")

    source.write_text("# Evolving Concept\n\nUpdated grounded fact.\n", encoding="utf-8")
    result = compiler.compile_file("diary/note.md")

    snapshots = list((data_dir / "knowledge" / "sources").glob("src-*/*.md"))
    card = CardStore(data_dir).load("evolving-concept")
    assert result.compiled_files == ["diary/note.md"]
    assert len(snapshots) == 2
    assert card is not None
    assert card.definition == "Updated grounded fact."
    assert card.update_count == 1
    assert card.sources[0].source_hash in {path.stem for path in snapshots}


def test_low_confidence_page_is_held_until_approved(tmp_path: Path):
    data_dir = tmp_path / "data"
    write_source(data_dir, "# Review Required\n\nA weakly supported claim.\n")
    provider = FakeKnowledgeProvider(confidence=0.4)
    compiler = KnowledgeCardCompiler(data_dir, provider=provider)

    result = compiler.compile_file("diary/note.md")

    assert result.card_slugs == []
    assert len(result.candidate_ids) == 1
    assert CardStore(data_dir).load("review-required") is None
    candidate = compiler.list_candidates()[0]
    assert candidate["reasons"] == ["low-confidence"]

    approved = compiler.approve_candidate(result.candidate_ids[0])
    assert approved.slug == "review-required"
    assert CardStore(data_dir).load("review-required") is not None
    assert compiler.list_candidates() == []


def test_candidate_cannot_be_approved_after_source_changes(tmp_path: Path):
    data_dir = tmp_path / "data"
    source = write_source(data_dir, "# Stale Candidate\n\nOriginal evidence.\n")
    compiler = KnowledgeCardCompiler(
        data_dir,
        provider=FakeKnowledgeProvider(confidence=0.4),
    )
    result = compiler.compile_file("diary/note.md")

    source.write_text("# Stale Candidate\n\nChanged evidence.\n", encoding="utf-8")

    with pytest.raises(ValueError, match="changed after generation"):
        compiler.approve_candidate(result.candidate_ids[0])


def test_deleted_source_marks_unowned_page_orphaned(tmp_path: Path):
    data_dir = tmp_path / "data"
    source = write_source(data_dir, "# Disposable Concept\n\nTemporary evidence.\n")
    compiler = KnowledgeCardCompiler(
        data_dir,
        provider=FakeKnowledgeProvider(),
    )
    compiler.compile_all()
    source.unlink()

    result = compiler.compile_all()

    card = CardStore(data_dir).load("disposable-concept")
    assert result.deleted_files == ["diary/note.md"]
    assert card is not None
    assert card.orphaned is True
    assert card.staleness_score == 1.0


def test_missing_llm_configuration_is_an_explicit_compile_error(tmp_path: Path):
    data_dir = tmp_path / "data"
    write_source(data_dir, "# Requires LLM\n\nGrounded input remains untouched.\n")
    provider = OpenAIKnowledgeProvider(
        LLMService(tmp_path / "missing-llm-config.yaml")
    )

    result = KnowledgeCardCompiler(data_dir, provider=provider).compile_file(
        "diary/note.md"
    )

    assert result.compiled_files == []
    assert result.errors
    assert "LLM 未配置" in result.errors[0]
    assert CardStore(data_dir).load("requires-llm") is None
