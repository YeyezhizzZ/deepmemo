from __future__ import annotations

import re
from pathlib import Path

from src.knowledge.card_store import CardStore, DATA_DIR
from src.knowledge.models import KnowledgeCard


class KnowledgeCommandHandler:
    def __init__(self, data_dir: str | Path | None = None, store: CardStore | None = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.store = store or CardStore(self.data_dir)

    def is_command(self, message: str) -> bool:
        return message.strip().startswith("/knowledge")

    def handle(self, message: str) -> str:
        text = message.strip()
        parts = text.split(maxsplit=2)
        if len(parts) == 1:
            return self._help()
        action = parts[1].lower()
        rest = parts[2] if len(parts) > 2 else ""

        try:
            if action == "list":
                return self._list()
            if action == "show":
                return self._show(rest)
            if action == "add":
                return self._add(rest)
            if action == "update":
                return self._update(rest)
            if action == "pin":
                return self._pin(rest)
        except ValueError as exc:
            return f"Knowledge 命令失败：{exc}"
        return f"不支持的 Knowledge 命令：{action}\n\n{self._help()}"

    def _list(self) -> str:
        cards = self.store.list_cards()
        if not cards:
            return "暂无 Knowledge Cards。"
        lines = ["Knowledge Cards:"]
        for card in sorted(cards, key=lambda item: item.title.lower()):
            lines.append(f"- `{card.slug}` {card.title} ({card.type})")
        return "\n".join(lines)

    def _show(self, rest: str) -> str:
        slug = rest.strip()
        if not slug:
            raise ValueError("请输入 Card slug。")
        card = self.store.load(slug)
        if card is None:
            raise ValueError(f"未找到 Card：{slug}")
        facts = "\n".join(f"- {fact}" for fact in card.key_facts)
        if facts:
            facts = f"\n\n{facts}"
        return f"## {card.title}\n\n`{card.slug}` · {card.type}\n\n{card.definition}{facts}"

    def _add(self, rest: str) -> str:
        title, definition = self._split_payload(rest)
        slug = self._slugify(title)
        if self.store.load(slug):
            raise ValueError(f"Card 已存在：{slug}")
        card = KnowledgeCard(
            slug=slug,
            title=title,
            type="concept",
            definition=definition,
            key_facts=[definition],
            tags=["chat-command"],
            human_edited=True,
            human_edited_fields=["title", "definition", "key_facts", "tags"],
        )
        self.store.save(card)
        return f"已创建 Knowledge Card：`{slug}`"

    def _update(self, rest: str) -> str:
        slug, definition = self._split_payload(rest)
        card = self.store.load(slug.strip())
        if card is None:
            raise ValueError(f"未找到 Card：{slug}")
        card.definition = definition
        card.human_edited = True
        if "definition" not in card.human_edited_fields:
            card.human_edited_fields.append("definition")
        self.store.save(KnowledgeCard.from_dict(card.to_dict()))
        return f"已更新 Knowledge Card：`{card.slug}`"

    def _pin(self, rest: str) -> str:
        values = rest.split()
        if len(values) != 2:
            raise ValueError("用法：/knowledge pin <slug> <field>")
        slug, field = values
        card = self.store.load(slug)
        if card is None:
            raise ValueError(f"未找到 Card：{slug}")
        allowed_fields = set(card.to_dict()) - {"id", "slug", "created_at"}
        if field not in allowed_fields:
            raise ValueError(f"不能固定字段：{field}")
        card.human_edited = True
        if field not in card.human_edited_fields:
            card.human_edited_fields.append(field)
        self.store.save(KnowledgeCard.from_dict(card.to_dict()))
        return f"已固定 `{slug}` 的 `{field}` 字段。"

    def _split_payload(self, rest: str) -> tuple[str, str]:
        if "::" not in rest:
            raise ValueError("用法需要 `标题或slug :: 内容`。")
        left, right = rest.split("::", 1)
        left = left.strip()
        right = right.strip()
        if not left or not right:
            raise ValueError("标题/slug 和内容不能为空。")
        return left, right

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value.lower()).strip("-")
        return slug or "untitled"

    def _help(self) -> str:
        return (
            "支持的 Knowledge 命令：\n"
            "- `/knowledge list`\n"
            "- `/knowledge show <slug>`\n"
            "- `/knowledge add <title> :: <definition>`\n"
            "- `/knowledge update <slug> :: <definition>`\n"
            "- `/knowledge pin <slug> <field>`"
        )
