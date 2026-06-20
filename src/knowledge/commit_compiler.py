from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.knowledge.card_store import CardStore, DATA_DIR
from src.knowledge.models import CompileResult, EvidenceSource, KnowledgeCard


class CommitKnowledgeCompiler:
    def __init__(
        self,
        data_dir: str | Path | None = None,
        repo_dir: str | Path | None = None,
        store: CardStore | None = None,
    ):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.repo_dir = Path(repo_dir) if repo_dir else Path(__file__).resolve().parents[2]
        self.store = store or CardStore(self.data_dir)

    def compile_commit(self, commit: str) -> CompileResult:
        metadata = self._read_commit(commit)
        card = self._card_from_commit(metadata)
        existing = self.store.load(card.slug)
        if existing:
            card = self._merge(card, existing)
        self.store.save(card)
        return CompileResult(compiled_files=metadata["files"], card_slugs=[card.slug])

    def _read_commit(self, commit: str) -> dict:
        full_hash = self._git("rev-parse", commit)
        short_hash = self._git("rev-parse", "--short", commit)
        subject = self._git("show", "-s", "--format=%s", commit)
        body = self._git("show", "-s", "--format=%b", commit)
        author = self._git("show", "-s", "--format=%an", commit)
        branch = self._git("rev-parse", "--abbrev-ref", "HEAD")
        files = [line.strip() for line in self._git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines() if line.strip()]
        if not files:
            files = [line.strip() for line in self._git("show", "--pretty=", "--name-only", commit).splitlines() if line.strip()]
        stats = self._git("show", "--stat", "--oneline", "--no-renames", commit)
        return {
            "hash": full_hash,
            "short_hash": short_hash,
            "subject": subject,
            "body": body,
            "author": author,
            "branch": branch,
            "files": files,
            "stats": stats,
        }

    def _card_from_commit(self, metadata: dict) -> KnowledgeCard:
        short_hash = metadata["short_hash"]
        subject = metadata["subject"] or f"Commit {short_hash}"
        card_type = self._infer_type(subject, metadata["body"])
        files = metadata["files"][:8]
        definition = self._definition(subject, metadata["body"], files)
        facts = [
            f"Commit: {metadata['hash']}",
            f"Branch: {metadata['branch']}",
            f"Author: {metadata['author']}",
        ]
        facts.extend(files)
        evidence = subject
        if metadata["body"]:
            evidence = f"{subject}\n{metadata['body']}".strip()
        return KnowledgeCard(
            slug=f"commit-{short_hash}",
            title=subject,
            type=card_type,
            density="medium",
            definition=definition,
            key_facts=facts,
            sources=[
                EvidenceSource(
                    path=f"git:{short_hash}",
                    evidence=evidence[:500],
                    confidence=0.75,
                )
            ],
            tags=["commit", "code-flywheel", card_type],
            aliases=[metadata["hash"], short_hash],
        )

    def _infer_type(self, subject: str, body: str) -> str:
        text = f"{subject}\n{body}".lower()
        if any(term in text for term in ("fix", "bug", "debug", "lesson", "regression")):
            return "lesson"
        if any(term in text for term in ("refactor", "pattern", "standard", "convention")):
            return "pattern"
        return "decision"

    def _definition(self, subject: str, body: str, files: list[str]) -> str:
        changed = ", ".join(files[:5]) if files else "no files reported"
        intent = body.strip().splitlines()[0] if body.strip() else subject
        return f"{intent} Changed files: {changed}."

    def _merge(self, incoming: KnowledgeCard, existing: KnowledgeCard) -> KnowledgeCard:
        protected = set(existing.human_edited_fields if existing.human_edited else [])
        merged = KnowledgeCard.from_dict(existing.to_dict())
        for field in ("title", "type", "density", "definition"):
            if field not in protected:
                setattr(merged, field, getattr(incoming, field))
        merged.key_facts = self._merge_list(merged.key_facts, incoming.key_facts)
        merged.related_cards = self._merge_list(merged.related_cards, incoming.related_cards)
        merged.tags = sorted(self._merge_list(merged.tags, incoming.tags))
        merged.aliases = self._merge_list(merged.aliases, incoming.aliases)
        merged.sources = self._merge_sources(merged.sources, incoming.sources)
        merged.updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        merged.update_count += 1
        return merged

    def _merge_list(self, original: list[str], incoming: list[str]) -> list[str]:
        result = list(original)
        seen = set(result)
        for value in incoming:
            if value not in seen:
                result.append(value)
                seen.add(value)
        return result

    def _merge_sources(self, original: list[EvidenceSource], incoming: list[EvidenceSource]) -> list[EvidenceSource]:
        result = list(original)
        seen = {(source.path, source.evidence) for source in result}
        for source in incoming:
            key = (source.path, source.evidence)
            if key not in seen:
                result.append(source)
                seen.add(key)
        return result

    def _git(self, *args: str) -> str:
        if any("\x00" in arg or "\n" in arg or "\r" in arg for arg in args):
            raise ValueError("invalid git argument")
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_dir,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip()
