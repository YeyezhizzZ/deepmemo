from pathlib import Path

from src.knowledge.card_compiler import KnowledgeCardCompiler
from src.knowledge.card_store import CardStore


def test_compile_file_creates_card_and_cache_entry(tmp_path: Path):
    data_dir = tmp_path / "data"
    source = data_dir / "diary" / "0620.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# Knowledge Engine\n\nTags: deepmemo, architecture\n\n- Compiles diary notes into YAML cards.\n",
        encoding="utf-8",
    )

    compiler = KnowledgeCardCompiler(data_dir=data_dir)
    result = compiler.compile_file("diary/0620.md")

    assert result.compiled_files == ["diary/0620.md"]
    assert result.card_slugs == ["knowledge-engine"]

    card = CardStore(data_dir=data_dir).load("knowledge-engine")
    assert card is not None
    assert card.title == "Knowledge Engine"
    assert card.tags == ["architecture", "deepmemo"]
    assert card.sources[0].path == "diary/0620.md"
    assert (data_dir / "knowledge" / ".compile-cache.json").exists()


def test_compile_all_reads_diary_and_raw_markdown(tmp_path: Path):
    data_dir = tmp_path / "data"
    (data_dir / "diary").mkdir(parents=True)
    (data_dir / "raw").mkdir(parents=True)
    (data_dir / "diary" / "0620.md").write_text("# Daily Note\n\nA local markdown truth.", encoding="utf-8")
    (data_dir / "raw" / "blog.md").write_text("# Blog Insight\n\nA raw captured source.", encoding="utf-8")

    result = KnowledgeCardCompiler(data_dir=data_dir).compile_all()

    assert result.compiled_files == ["diary/0620.md", "raw/blog.md"]
    assert result.card_slugs == ["blog-insight", "daily-note"]


def test_compile_preserves_human_edited_fields(tmp_path: Path):
    data_dir = tmp_path / "data"
    source = data_dir / "diary" / "0620.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Knowledge Engine\n\nInitial generated definition.", encoding="utf-8")

    compiler = KnowledgeCardCompiler(data_dir=data_dir)
    compiler.compile_file("diary/0620.md")

    store = CardStore(data_dir=data_dir)
    card = store.load("knowledge-engine")
    card.definition = "Human reviewed definition."
    card.human_edited = True
    card.human_edited_fields = ["definition"]
    store.save(card)

    source.write_text("# Knowledge Engine\n\nReplacement generated definition.\n\nTags: reviewed", encoding="utf-8")
    compiler.compile_file("diary/0620.md")

    merged = store.load("knowledge-engine")
    assert merged.definition == "Human reviewed definition."
    assert merged.update_count == 1
    assert merged.tags == ["reviewed"]
