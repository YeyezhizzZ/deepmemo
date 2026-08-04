from __future__ import annotations

import re
import hashlib
from pathlib import Path

from src.knowledge.card_compiler import KnowledgeCardCompiler
from src.knowledge.card_store import CardStore, DATA_DIR
from src.knowledge.models import EvidenceSource, KnowledgeCard, SourceSnapshot
from src.knowledge.source_store import SourceStore


CONFIRM_TERMS = ("对", "没错", "就是这样", "按这个", "确认", "沉淀", "决策")
CORRECTION_TERMS = ("不对", "应该是", "其实", "纠正", "踩坑")


class ConversationMemoryExtractor:
    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.store = CardStore(self.data_dir)
        self.source_store = SourceStore(self.data_dir)

    def extract(self, session_id: str, messages: list[dict]) -> list[KnowledgeCard]:
        if len(messages) < 4:
            return []
        signal_type = self._classify_signal(messages)
        if signal_type is None:
            return []
        snapshot = self._write_conversation_raw(session_id, messages)
        card = self._generate_card_draft(signal_type, messages, snapshot)
        existing = self.store.load(card.slug)
        if existing:
            card = KnowledgeCardCompiler(data_dir=self.data_dir, store=self.store)._merge_with_existing(card, existing)
        self.store.save(card)
        return [card]

    def _classify_signal(self, messages: list[dict]) -> str | None:
        text = "\n".join(str(message.get("content") or "") for message in messages)
        if any(term in text for term in CORRECTION_TERMS):
            return "lesson"
        if any(term in text for term in CONFIRM_TERMS):
            return "decision"
        if "模式" in text or "pattern" in text.lower():
            return "pattern"
        if "是什么" in text or "概念" in text:
            return "concept"
        return None

    def _generate_card_draft(
        self,
        signal_type: str,
        messages: list[dict],
        snapshot: SourceSnapshot,
    ) -> KnowledgeCard:
        user_lines = [
            str(message.get("content") or "").strip()
            for message in messages
            if str(message.get("role") or "") == "user" and str(message.get("content") or "").strip()
        ]
        seed = user_lines[0] if user_lines else str(messages[0].get("content") or "Conversation insight")
        title = self._title_from_text(seed)
        slug = self._slugify(title)
        definition = self._compact(" / ".join(user_lines[:2]) or seed, limit=160)
        evidence = self.source_store.excerpt(snapshot, 1, snapshot.line_count)
        return KnowledgeCard(
            slug=slug,
            title=title,
            type=signal_type,
            density="medium",
            definition=definition,
            key_facts=[self._compact(line, limit=180) for line in user_lines[:5]],
            sources=[
                EvidenceSource(
                    path=snapshot.origin_path,
                    evidence=evidence,
                    confidence=0.75,
                    source_id=snapshot.source_id,
                    source_hash=snapshot.source_hash,
                    start_line=1,
                    end_line=snapshot.line_count,
                )
            ],
            tags=["conversation", signal_type],
            confidence=0.75,
            provenance_state="inferred",
            model_id="deterministic-conversation-adapter",
            prompt_version="conversation-adapter-v1",
        )

    def _write_conversation_raw(
        self,
        session_id: str,
        messages: list[dict],
    ) -> SourceSnapshot:
        rel_path = f"raw/conversations/{session_id}.md"
        path = self.data_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# Conversation {session_id}", ""]
        for message in messages:
            role = str(message.get("role") or "unknown")
            content = str(message.get("content") or "").strip()
            if content:
                lines.extend([f"## {role}", content, ""])
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return self.source_store.ingest_path(rel_path, source_type="conversation")

    def _title_from_text(self, text: str) -> str:
        compact = self._compact(text, limit=40)
        compact = re.sub(r"[。.!?？].*$", "", compact).strip()
        return compact or "Conversation Insight"

    def _compact(self, text: str, *, limit: int) -> str:
        compact = " ".join(text.split())
        return compact[:limit].rstrip()

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        if slug:
            return slug
        digest = hashlib.md5(value.encode("utf-8")).hexdigest()[:8]
        return f"conversation-{digest}"
