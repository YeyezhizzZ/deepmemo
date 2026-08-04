from pathlib import Path

from src.knowledge.card_compiler import KnowledgeCardCompiler
from src.knowledge.card_store import CardStore
from src.knowledge.evaluation import KnowledgeEvaluator
from src.knowledge.models import EvidenceSource, KnowledgeCard
from tests.fake_knowledge_provider import FakeKnowledgeProvider


def test_fast_eval_reports_grounded_compiler_output(tmp_path: Path):
    data_dir = tmp_path / "data"
    source = data_dir / "raw" / "paper.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Grounded Page\n\nA cited source statement.\n", encoding="utf-8")
    KnowledgeCardCompiler(
        data_dir,
        provider=FakeKnowledgeProvider(),
    ).compile_all()

    report = KnowledgeEvaluator(data_dir).evaluate(
        min_health=90,
        min_citation_coverage=90,
        min_citation_precision=100,
    )

    assert report["threshold_violations"] == []
    assert report["citations"]["coverage_percent"] == 100.0
    assert report["citations"]["precision_percent"] == 100.0
    assert report["citations"]["source_utilization_percent"] == 100.0
    assert (
        data_dir / "knowledge" / ".deepmemo" / "eval" / "history.jsonl"
    ).exists()


def test_fast_eval_fails_precision_gate_for_untraceable_legacy_page(tmp_path: Path):
    data_dir = tmp_path / "data"
    CardStore(data_dir).save(
        KnowledgeCard(
            slug="legacy-page",
            title="Legacy Page",
            type="concept",
            definition="A page without immutable line evidence.",
            sources=[
                EvidenceSource(
                    path="raw/missing.md",
                    evidence="untraceable",
                    confidence=0.5,
                )
            ],
        )
    )

    report = KnowledgeEvaluator(data_dir).evaluate(
        min_citation_precision=100,
        record=False,
    )

    assert report["citations"]["precision_percent"] == 0.0
    assert report["threshold_violations"]


def test_empty_wiki_is_a_valid_unmeasured_baseline(tmp_path: Path):
    report = KnowledgeEvaluator(tmp_path / "data").evaluate(record=False)

    assert report["health"]["score"] == 100.0
    assert report["citations"]["coverage_percent"] == 100.0
    assert report["citations"]["precision_percent"] == 100.0
