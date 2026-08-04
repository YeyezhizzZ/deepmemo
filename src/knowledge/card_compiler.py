from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.knowledge.activity_log import append_activity
from src.knowledge.card_store import CardStore, DATA_DIR
from src.knowledge.compiler_state import CandidateStore, CompileLock, CompileStateStore
from src.knowledge.knowledge_llm import (
    PROMPT_VERSION,
    KnowledgeCompilerProvider,
    OpenAIKnowledgeProvider,
)
from src.knowledge.models import (
    CompileResult,
    EvidenceSource,
    ExtractedKnowledge,
    KnowledgeCard,
    SourceSnapshot,
)
from src.knowledge.source_store import SourceStore


class KnowledgeCardCompiler:
    """Incremental two-phase compiler with source-grounded review gates."""

    def __init__(
        self,
        data_dir: str | Path | None = None,
        store: CardStore | None = None,
        *,
        provider: KnowledgeCompilerProvider | None = None,
        review_all: bool = False,
        low_confidence_threshold: float = 0.65,
        use_llm: bool | None = None,
    ):
        # use_llm remains accepted for API compatibility. Disabling it no longer
        # enables heuristic writes; callers must inject an explicit test provider.
        if use_llm is False and provider is None:
            raise ValueError("heuristic knowledge compilation has been removed")
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.store = store or CardStore(self.data_dir)
        self.source_store = SourceStore(self.data_dir)
        self.state_store = CompileStateStore(self.data_dir)
        self.candidate_store = CandidateStore(self.data_dir)
        self.provider = provider or OpenAIKnowledgeProvider()
        self.review_all = review_all
        self.low_confidence_threshold = low_confidence_threshold

    def compile_all(self) -> CompileResult:
        with CompileLock(self.data_dir):
            origins = self.source_store.discover_origins()
            return self._compile_origins(origins, detect_deleted=True)

    def compile_file(self, path: str | Path) -> CompileResult:
        source_path = self.source_store.resolve_origin_path(path)
        origin = source_path.relative_to(self.data_dir.resolve()).as_posix()
        with CompileLock(self.data_dir):
            return self._compile_origins([origin], detect_deleted=False)

    def compile_conversation(self, session_id: str, messages: list[dict]) -> CompileResult:
        from src.knowledge.conversation_memory import ConversationMemoryExtractor

        cards = ConversationMemoryExtractor(data_dir=self.data_dir).extract(
            session_id,
            messages,
        )
        return CompileResult(
            compiled_files=[source.path for card in cards for source in card.sources],
            card_slugs=sorted({card.slug for card in cards}),
            prompt_version=PROMPT_VERSION,
        )

    def list_candidates(self) -> list[dict]:
        return self.candidate_store.list()

    def approve_candidate(self, candidate_id: str) -> KnowledgeCard:
        with CompileLock(self.data_dir):
            candidate = self.candidate_store.load(candidate_id)
            self._assert_candidate_fresh(candidate)
            card = KnowledgeCard.from_dict(candidate["card"])
            self.store.save(card)
            self.candidate_store.archive(candidate_id, status="approved")
        append_activity(
            self.data_dir,
            "review",
            f"Approved {card.title}",
            [f"Candidate: {candidate_id}", f"Page: {card.slug}"],
        )
        return card

    def reject_candidate(self, candidate_id: str) -> dict:
        with CompileLock(self.data_dir):
            candidate = self.candidate_store.archive(candidate_id, status="rejected")
        append_activity(
            self.data_dir,
            "review",
            f"Rejected {candidate['slug']}",
            [f"Candidate: {candidate_id}"],
        )
        return candidate

    def _compile_origins(
        self,
        origins: list[str],
        *,
        detect_deleted: bool,
    ) -> CompileResult:
        state = self.state_store.load()
        source_state = state.setdefault("sources", {})
        snapshots: dict[str, SourceSnapshot] = {}
        changed: list[SourceSnapshot] = []
        skipped: list[str] = []

        for origin in origins:
            snapshot = self.source_store.ingest_path(origin)
            snapshots[origin] = snapshot
            previous = source_state.get(origin)
            if previous and previous.get("source_hash") == snapshot.source_hash:
                skipped.append(origin)
            else:
                changed.append(snapshot)

        deleted = []
        if detect_deleted:
            current = set(origins)
            deleted = sorted(origin for origin in source_state if origin not in current)

        if not changed and not deleted:
            return CompileResult(
                skipped_files=skipped,
                prompt_version=PROMPT_VERSION,
            )

        existing_index = self._existing_index()
        affected_slugs: set[str] = set()
        extracted_by_source: dict[str, list[ExtractedKnowledge]] = {}
        errors: list[str] = []

        # Phase 1: extract all changed sources before generating any page.
        for snapshot in changed:
            previous = source_state.get(snapshot.origin_path) or {}
            affected_slugs.update(previous.get("slugs") or [])
            try:
                items = self._extract_snapshot(snapshot, existing_index)
            except Exception as exc:
                errors.append(f"{snapshot.origin_path}: extraction failed ({exc})")
                continue
            self.state_store.save_extractions(
                snapshot,
                items,
                model_id=self.provider.model_id,
                prompt_version=PROMPT_VERSION,
            )
            extracted_by_source[snapshot.source_id] = items
            affected_slugs.update(item.slug for item in items)

        deleted_entries: dict[str, dict] = {}
        for origin in deleted:
            previous = source_state.get(origin) or {}
            deleted_entries[origin] = previous
            affected_slugs.update(previous.get("slugs") or [])
            source_id = str(previous.get("source_id") or "")
            if source_id:
                self.state_store.delete_extractions(source_id)

        groups = self._group_all_extractions()
        successful_slugs: set[str] = set()
        written_slugs: list[str] = []
        candidate_ids: list[str] = []
        generation_errors: list[str] = []

        # Phase 2: regenerate every page affected by changed ownership.
        for slug in sorted(affected_slugs):
            items = groups.get(slug, [])
            existing = self.store.load(slug)
            if not items:
                if existing is not None:
                    existing.orphaned = True
                    existing.staleness_score = 1.0
                    existing.updated_at = self._now()
                    self.store.save(existing, rebuild_index=False)
                    written_slugs.append(slug)
                successful_slugs.add(slug)
                continue
            try:
                generated = self.provider.generate(slug, items, existing)
                generated = self._merge_with_existing(generated, existing)
                reasons = self._review_reasons(generated)
                if reasons:
                    candidate_ids.append(
                        self.candidate_store.write(
                            generated,
                            reasons=reasons,
                            source_hashes={
                                source.source_id: source.source_hash
                                for source in generated.sources
                                if source.source_id
                            },
                        )
                    )
                else:
                    self.store.save(generated, rebuild_index=False)
                    written_slugs.append(slug)
                successful_slugs.add(slug)
            except Exception as exc:
                generation_errors.append(f"{slug}: generation failed ({exc})")

        self.store.rebuild_index()
        errors.extend(generation_errors)

        compiled_files: list[str] = []
        for snapshot in changed:
            items = extracted_by_source.get(snapshot.source_id)
            if items is None:
                continue
            item_slugs = {item.slug for item in items}
            previous_slugs = set(
                (source_state.get(snapshot.origin_path) or {}).get("slugs") or []
            )
            if (previous_slugs | item_slugs) <= successful_slugs:
                source_state[snapshot.origin_path] = {
                    "source_id": snapshot.source_id,
                    "source_hash": snapshot.source_hash,
                    "slugs": sorted(item_slugs),
                    "compiled_at": self._now(),
                    "model_id": self.provider.model_id,
                    "prompt_version": PROMPT_VERSION,
                }
                compiled_files.append(snapshot.origin_path)

        deleted_files: list[str] = []
        for origin, previous in deleted_entries.items():
            old_slugs = set(previous.get("slugs") or [])
            if old_slugs <= successful_slugs:
                source_state.pop(origin, None)
                self.source_store.remove_origin(origin)
                deleted_files.append(origin)

        self.state_store.save(state)
        result = CompileResult(
            compiled_files=sorted(compiled_files),
            card_slugs=sorted(written_slugs),
            skipped_files=sorted(skipped),
            deleted_files=deleted_files,
            candidate_ids=sorted(candidate_ids),
            errors=errors,
            prompt_version=PROMPT_VERSION,
        )
        append_activity(
            self.data_dir,
            "compile",
            f"{len(result.compiled_files)} source(s) -> "
            f"{len(result.card_slugs)} page(s), {len(result.candidate_ids)} candidate(s)",
            [
                f"Sources: {', '.join(result.compiled_files) or '(none)'}",
                f"Pages: {', '.join(result.card_slugs) or '(none)'}",
                f"Errors: {len(result.errors)}",
            ],
        )
        return result

    def _extract_snapshot(
        self,
        snapshot: SourceSnapshot,
        existing_index: str,
    ) -> list[ExtractedKnowledge]:
        extracted: list[ExtractedKnowledge] = []
        for chunk in self.source_store.numbered_chunks(snapshot):
            extracted.extend(
                self.provider.extract(
                    snapshot,
                    chunk,
                    existing_index,
                    self.source_store,
                )
            )
        return self._merge_chunk_extractions(extracted)

    def _merge_chunk_extractions(
        self,
        items: list[ExtractedKnowledge],
    ) -> list[ExtractedKnowledge]:
        grouped: dict[str, list[ExtractedKnowledge]] = defaultdict(list)
        for item in items:
            grouped[item.slug].append(item)

        merged: list[ExtractedKnowledge] = []
        for slug in sorted(grouped):
            entries = grouped[slug]
            first = entries[0]
            merged.append(
                ExtractedKnowledge(
                    slug=slug,
                    title=first.title,
                    type=first.type,
                    summary=first.summary,
                    key_facts=self._merge_strings(
                        fact for entry in entries for fact in entry.key_facts
                    ),
                    citations=self._merge_sources(
                        source for entry in entries for source in entry.citations
                    ),
                    tags=self._merge_strings(
                        tag for entry in entries for tag in entry.tags
                    ),
                    aliases=self._merge_strings(
                        alias for entry in entries for alias in entry.aliases
                    ),
                    related_cards=self._merge_strings(
                        related
                        for entry in entries
                        for related in entry.related_cards
                    ),
                    confidence=min(entry.confidence for entry in entries),
                    provenance_state=(
                        "ambiguous"
                        if any(entry.provenance_state == "ambiguous" for entry in entries)
                        else "merged" if len(entries) > 1 else first.provenance_state
                    ),
                    contradicted_by=self._merge_strings(
                        contradiction
                        for entry in entries
                        for contradiction in entry.contradicted_by
                    ),
                )
            )
        return merged

    def _group_all_extractions(self) -> dict[str, list[ExtractedKnowledge]]:
        grouped: dict[str, list[ExtractedKnowledge]] = defaultdict(list)
        for _, items in self.state_store.iter_extractions():
            for item in items:
                grouped[item.slug].append(item)
        return grouped

    def _review_reasons(self, card: KnowledgeCard) -> list[str]:
        reasons: list[str] = []
        if self.review_all:
            reasons.append("manual-review-requested")
        if card.confidence < self.low_confidence_threshold:
            reasons.append("low-confidence")
        if card.contradicted_by or card.provenance_state == "ambiguous":
            reasons.append("contradicted")
        if card.provenance_state == "inferred":
            reasons.append("inferred")
        if not card.sources:
            reasons.append("missing-citations")
        for source in card.sources:
            try:
                self._validate_citation(source)
            except (FileNotFoundError, ValueError):
                reasons.append("invalid-citation")
                break
        if not card.definition.strip() or not card.key_facts:
            reasons.append("incomplete-page")
        return sorted(set(reasons))

    def _validate_citation(self, source: EvidenceSource) -> None:
        if not (
            source.source_id
            and source.source_hash
            and source.start_line > 0
            and source.end_line >= source.start_line
        ):
            raise ValueError("citation is missing immutable source coordinates")
        snapshot = next(
            (
                snapshot
                for snapshot in self.source_store.list_current()
                if snapshot.source_id == source.source_id
                and snapshot.source_hash == source.source_hash
            ),
            None,
        )
        if snapshot is None:
            raise FileNotFoundError(source.source_id)
        excerpt = self.source_store.excerpt(
            snapshot,
            source.start_line,
            source.end_line,
        )
        if excerpt.strip() != source.evidence.strip():
            raise ValueError("citation evidence does not match source snapshot")

    def _merge_with_existing(
        self,
        new_card: KnowledgeCard,
        existing: KnowledgeCard | None,
    ) -> KnowledgeCard:
        if existing is None:
            return new_card
        protected = set(existing.human_edited_fields if existing.human_edited else [])
        merged = KnowledgeCard.from_dict(existing.to_dict())
        scalar_fields = ("title", "type", "density", "definition")
        list_fields = ("key_facts", "related_cards", "tags", "aliases")
        for field in scalar_fields:
            if field not in protected:
                setattr(merged, field, getattr(new_card, field))
        for field in list_fields:
            if field not in protected:
                setattr(merged, field, list(getattr(new_card, field)))
        if "sources" not in protected:
            merged.sources = list(new_card.sources)
        merged.confidence = new_card.confidence
        merged.provenance_state = new_card.provenance_state
        merged.contradicted_by = list(new_card.contradicted_by)
        merged.orphaned = False
        merged.model_id = new_card.model_id
        merged.prompt_version = new_card.prompt_version
        merged.updated_at = self._now()
        merged.update_count += 1
        return KnowledgeCard.from_dict(merged.to_dict())

    def _existing_index(self) -> str:
        index = "\n".join(
            f"- {card.slug}: {card.title} — {card.definition[:160]}"
            for card in self.store.list_cards()
        )
        if len(index) <= 30_000:
            return index
        return index[:30_000] + "\n- [index truncated for extraction prompt]"

    def _assert_candidate_fresh(self, candidate: dict) -> None:
        current = {
            snapshot.source_id: snapshot.source_hash
            for snapshot in self.source_store.list_current()
        }
        expected = candidate.get("source_hashes") or {}
        stale = [
            source_id
            for source_id, source_hash in expected.items()
            if current.get(source_id) != source_hash
        ]
        if stale:
            raise ValueError(
                f"candidate sources changed after generation: {', '.join(sorted(stale))}"
            )
        card = KnowledgeCard.from_dict(candidate["card"])
        changed_paths: list[str] = []
        for source in card.sources:
            if not source.source_hash or source.path.startswith("git:"):
                continue
            path = self.source_store.resolve_origin_path(source.path, must_exist=False)
            if not path.is_file():
                changed_paths.append(source.path)
                continue
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_hash != source.source_hash:
                changed_paths.append(source.path)
        if changed_paths:
            raise ValueError(
                "candidate source files changed after generation: "
                f"{', '.join(sorted(set(changed_paths)))}"
            )

    def _merge_strings(self, values) -> list[str]:
        return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))

    def _merge_sources(self, sources) -> list[EvidenceSource]:
        result: list[EvidenceSource] = []
        seen: set[tuple[str, str, int, int]] = set()
        for source in sources:
            key = (
                source.source_id,
                source.source_hash,
                source.start_line,
                source.end_line,
            )
            if key not in seen:
                result.append(source)
                seen.add(key)
        return result

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
