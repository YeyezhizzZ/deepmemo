from pathlib import Path

import yaml

from src.knowledge.card_store import CardStore
from src.knowledge.cli import main
from src.knowledge.models import EvidenceSource, KnowledgeCard


def test_cli_validate_passes_when_cards_sources_and_index_match(test_data_dir: Path):
    source = test_data_dir / "diary" / "0620.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Source\n", encoding="utf-8")
    CardStore(test_data_dir).save(
        KnowledgeCard(
            slug="valid-card",
            title="Valid Card",
            type="concept",
            definition="A valid card.",
            sources=[EvidenceSource(path="diary/0620.md", evidence="Source", confidence=0.7)],
        )
    )

    assert main(["validate", "--data-dir", str(test_data_dir)]) == 0


def test_cli_validate_fails_on_invalid_card_yaml(test_data_dir: Path):
    cards_dir = test_data_dir / "knowledge" / "cards"
    cards_dir.mkdir(parents=True)
    (cards_dir / "broken.yaml").write_text("slug: broken\ntype: not-a-type\n", encoding="utf-8")

    assert main(["validate", "--data-dir", str(test_data_dir)]) == 1


def test_cli_validate_fails_when_index_is_drifted(test_data_dir: Path):
    CardStore(test_data_dir).save(
        KnowledgeCard(
            slug="indexed-card",
            title="Indexed Card",
            type="concept",
            definition="A card.",
        )
    )
    index_path = test_data_dir / "knowledge" / "index.json"
    index_path.write_text('{"version": 1, "cards": {}}', encoding="utf-8")

    assert main(["validate", "--data-dir", str(test_data_dir)]) == 1


def test_cli_repowiki_rebuild_creates_pages(test_data_dir: Path):
    CardStore(test_data_dir).save(
        KnowledgeCard(
            slug="lesson-card",
            title="Lesson Card",
            type="lesson",
            definition="A useful debugging lesson.",
            sources=[EvidenceSource(path="raw/debug.md", evidence="lesson", confidence=0.8)],
        )
    )
    source = test_data_dir / "raw" / "debug.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Debug\n", encoding="utf-8")

    assert main(["repowiki", "rebuild", "--data-dir", str(test_data_dir)]) == 0
    page = yaml.safe_load((test_data_dir / "knowledge" / "index.json").read_text(encoding="utf-8"))
    assert page["stats"]["total_cards"] == 1
    assert (test_data_dir / "knowledge" / "repowiki" / "lessons.md").exists()
