from pathlib import Path
import subprocess

from src.knowledge.card_store import CardStore
from src.knowledge.commit_compiler import CommitKnowledgeCompiler
from src.knowledge.models import EvidenceSource, KnowledgeCard


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    (repo / "src").mkdir()
    (repo / "src" / "retriever.py").write_text("def search():\n    return 'cards first'\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "feat: use card-first retrieval")
    return repo


def test_compile_commit_creates_idempotent_card_with_commit_source(tmp_path: Path, test_data_dir: Path):
    repo = make_repo(tmp_path)
    compiler = CommitKnowledgeCompiler(data_dir=test_data_dir, repo_dir=repo)

    first = compiler.compile_commit("HEAD")
    second = compiler.compile_commit("HEAD")

    assert first.card_slugs == second.card_slugs
    assert len(first.card_slugs) == 1
    card = CardStore(test_data_dir).load(first.card_slugs[0])
    assert card is not None
    assert card.type == "decision"
    assert "src/retriever.py" in card.key_facts
    assert card.sources[0].path.startswith("git:")
    assert git(repo, "rev-parse", "--short", "HEAD") in card.sources[0].path


def test_compile_commit_preserves_human_edited_definition(tmp_path: Path, test_data_dir: Path):
    repo = make_repo(tmp_path)
    compiler = CommitKnowledgeCompiler(data_dir=test_data_dir, repo_dir=repo)
    result = compiler.compile_commit("HEAD")
    store = CardStore(test_data_dir)
    card = store.load(result.card_slugs[0])
    assert card is not None
    card.definition = "Human reviewed commit interpretation."
    card.human_edited = True
    card.human_edited_fields.append("definition")
    store.save(card)

    compiler.compile_commit("HEAD")

    updated = store.load(result.card_slugs[0])
    assert updated is not None
    assert updated.definition == "Human reviewed commit interpretation."
    assert len(updated.sources) == 1
