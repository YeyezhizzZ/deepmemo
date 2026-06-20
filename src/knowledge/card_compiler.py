from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from src.knowledge.card_store import CardStore, DATA_DIR
from src.knowledge.models import CompileResult, EvidenceSource, KnowledgeCard


class KnowledgeCardCompiler:
    def __init__(self, data_dir: str | Path | None = None, store: CardStore | None = None, use_llm: bool | None = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.store = store or CardStore(self.data_dir)
        self.cache_path = self.data_dir / "knowledge" / ".compile-cache.json"
        self.use_llm = use_llm if use_llm is not None else os.getenv("DEEPMEMO_KNOWLEDGE_USE_LLM", "").lower() in {"1", "true", "yes"}

    def compile_all(self) -> CompileResult:
        files: list[Path] = []
        for dirname in ("diary", "raw"):
            root = self.data_dir / dirname
            if root.exists():
                files.extend(sorted(root.rglob("*.md")))

        compiled_files: list[str] = []
        card_slugs: set[str] = set()
        warnings: list[str] = []
        for path in files:
            try:
                result = self.compile_file(self.store.relative_path(path))
            except (FileNotFoundError, ValueError) as exc:
                warnings.append(str(exc))
                continue
            compiled_files.extend(result.compiled_files)
            card_slugs.update(result.card_slugs)
        return CompileResult(compiled_files=compiled_files, card_slugs=sorted(card_slugs), warnings=warnings)

    def compile_file(self, path: str | Path) -> CompileResult:
        source_path = self.store.resolve_source_path(path, must_exist=True)
        rel_path = self.store.relative_path(source_path)
        content = source_path.read_text(encoding="utf-8")
        drafts = self._extract_via_llm(content, rel_path) if self.use_llm else []
        if not drafts:
            drafts = [self._extract_heuristic(content, rel_path)]
        saved_slugs: list[str] = []
        for draft in drafts:
            existing = self.store.load(draft.slug)
            card = self._merge_with_existing(draft, existing) if existing else draft
            self.store.save(card)
            saved_slugs.append(card.slug)
        self._update_cache(rel_path, source_path, saved_slugs)
        return CompileResult(compiled_files=[rel_path], card_slugs=saved_slugs)

    def compile_conversation(self, session_id: str, messages: list[dict]) -> CompileResult:
        from src.knowledge.conversation_memory import ConversationMemoryExtractor

        cards = ConversationMemoryExtractor(data_dir=self.data_dir).extract(session_id, messages)
        return CompileResult(
            compiled_files=[source.path for card in cards for source in card.sources],
            card_slugs=sorted({card.slug for card in cards}),
        )

    def _extract_via_llm(self, content: str, source_path: str) -> list[KnowledgeCard]:
        try:
            from src.services.llm_service import llm_service
        except Exception:
            return []
        prompt = (
            "Extract concise Knowledge Cards from the source. Return JSON array with "
            "slug,title,type,definition,key_facts,tags,aliases,confidence."
        )
        try:
            response = llm_service.chat(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": content[:20000]},
                ]
            )
            raw = response.choices[0].message.content or ""
            parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
            if not isinstance(parsed, list):
                return []
        except Exception:
            return []

        cards: list[KnowledgeCard] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                cards.append(
                    KnowledgeCard(
                        slug=str(item.get("slug") or self._slugify(str(item.get("title") or ""))),
                        title=str(item.get("title") or item.get("slug") or "Knowledge Card"),
                        type=str(item.get("type") or "concept"),
                        definition=str(item.get("definition") or ""),
                        key_facts=[str(value) for value in item.get("key_facts") or []],
                        sources=[
                            EvidenceSource(
                                path=source_path,
                                evidence=str(item.get("definition") or item.get("title") or ""),
                                confidence=float(item.get("confidence") or 0.7),
                            )
                        ],
                        tags=[str(value) for value in item.get("tags") or []],
                        aliases=[str(value) for value in item.get("aliases") or []],
                    )
                )
            except (TypeError, ValueError):
                continue
        return cards

    def _extract_heuristic(self, content: str, source_path: str) -> KnowledgeCard:
        title = self._extract_title(content) or Path(source_path).stem
        slug = self._slugify(title)
        body_lines = [line.strip() for line in content.splitlines() if line.strip()]
        facts = self._extract_key_facts(body_lines, title)
        definition = self._extract_definition(body_lines, title)
        tags = self._extract_tags(content)
        evidence = definition or (facts[0] if facts else title)
        return KnowledgeCard(
            slug=slug,
            title=title,
            type="concept",
            density="medium",
            definition=definition or title,
            key_facts=facts,
            sources=[EvidenceSource(path=source_path, evidence=evidence, confidence=0.6)],
            tags=tags,
            aliases=[],
        )

    def _merge_with_existing(self, new_card: KnowledgeCard, existing: KnowledgeCard) -> KnowledgeCard:
        protected = set(existing.human_edited_fields if existing.human_edited else [])
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        merged = KnowledgeCard.from_dict(existing.to_dict())

        for field in ("title", "type", "density", "definition"):
            if field not in protected:
                setattr(merged, field, getattr(new_card, field))
        merged.key_facts = self._merge_list(merged.key_facts, new_card.key_facts)
        merged.sources = self._merge_sources(merged.sources, new_card.sources)
        merged.related_cards = self._merge_list(merged.related_cards, new_card.related_cards)
        merged.tags = sorted(self._merge_list(merged.tags, new_card.tags))
        merged.aliases = self._merge_list(merged.aliases, new_card.aliases)
        merged.updated_at = now
        merged.update_count += 1
        return merged

    def _update_cache(self, rel_path: str, source_path: Path, card_slugs: list[str]) -> None:
        cache = {"version": 1, "entries": {}}
        if self.cache_path.exists():
            with self.cache_path.open("r", encoding="utf-8") as handle:
                cache = json.load(handle)
        cache.setdefault("entries", {})[rel_path] = {
            "hash": hashlib.md5(source_path.read_bytes()).hexdigest(),
            "last_compiled": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "card_slugs": card_slugs,
        }
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=2)

    def _extract_title(self, content: str) -> str | None:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return None

    def _extract_definition(self, lines: list[str], title: str) -> str:
        for line in lines:
            if line.startswith("#") or line.lower().startswith("tags:"):
                continue
            return line.lstrip("-* ").strip()
        return title

    def _extract_key_facts(self, lines: list[str], title: str) -> list[str]:
        facts: list[str] = []
        for line in lines:
            if line.startswith("#") or line.lower().startswith("tags:"):
                continue
            normalized = line.lstrip("-* ").strip()
            if normalized and normalized != title and normalized not in facts:
                facts.append(normalized)
            if len(facts) >= 5:
                break
        return facts

    def _extract_tags(self, content: str) -> list[str]:
        tags: set[str] = set()
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("tags:"):
                for value in stripped.split(":", 1)[1].split(","):
                    tag = self._slugify(value.strip())
                    if tag:
                        tags.add(tag)
        return sorted(tags)

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value.lower()).strip("-")
        return slug or "untitled"

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
