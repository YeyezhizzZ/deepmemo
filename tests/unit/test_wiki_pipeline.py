import sys
import unittest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch

# Ensure workspace root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.wiki.ingest_analyzer import WikiDraft, WikiSection
from src.wiki.merger import word_jaccard_similarity, Levenshtein_distance, heuristic_clustering, merge_candidate_drafts
from src.wiki.link_resolver import LinkResolutionIndex, resolve_text_links, resolve_draft_links
from src.wiki.ingest import _build_knowledge_pages_from_analyses, MockDiaryEntry
from src.wiki.ingest_writer import build_canonical_registry, write_generated_wiki
from src.wiki.ingest_pipeline import parse_markdown_to_draft
from src.wiki.evidence import build_drafts_from_evidence, extract_evidence_cards
from src.wiki.graph import GraphNode, _source_overlap, build_diary_graph
from src.wiki.health import build_wiki_health_report


class TestWikiReconstruction(unittest.TestCase):
    def test_heuristics(self):
        # 1. Similarity
        self.assertAlmostEqual(word_jaccard_similarity("Agent Skill", "Agent Skill"), 1.0)
        self.assertAlmostEqual(word_jaccard_similarity("Agent Skill", "agent-skill!"), 1.0)
        self.assertTrue(word_jaccard_similarity("Agent Skill", "Agent Skill Distillation") >= 0.6)
        
        # 2. Levenshtein distance
        self.assertEqual(Levenshtein_distance("Agent Skill", "Agent Skills"), 1)
        self.assertEqual(Levenshtein_distance("Agent Skill", "Agent Skill"), 0)

    def test_merger_clustering(self):
        drafts = [
            WikiDraft(
                page_type="concept",
                slug="agent-skill-distillation",
                title="Agent Skill Distillation",
                summary="Extracting skill definitions.",
                sources=["diary/2026/0425.md"],
                sections=[WikiSection("Evidence", ["Evidence 1"])]
            ),
            WikiDraft(
                page_type="concept",
                slug="agent-skill-distill",
                title="Agent Skill Distill",
                summary="Method to compress agent skills.",
                sources=["diary/2026/0430.md"],
                sections=[WikiSection("Evidence", ["Evidence 2"])]
            )
        ]
        
        # Merge without LLM (falls back to heuristics)
        merged = merge_candidate_drafts(drafts, use_llm=False)
        self.assertEqual(len(merged), 1)
        m = merged[0]
        self.assertEqual(m.title, "Agent Skill Distillation")
        self.assertIn("diary/2026/0425.md", m.sources)
        self.assertIn("diary/2026/0430.md", m.sources)
        # Verify section merged
        evidence_section = [s for s in m.sections if s.heading == "Evidence"]
        self.assertEqual(len(evidence_section), 1)
        self.assertIn("Evidence 1", evidence_section[0].bullets)
        self.assertIn("Evidence 2", evidence_section[0].bullets)

    def test_link_resolver(self):
        index = LinkResolutionIndex()
        index.add_page("Agent Skill Distillation", "agent-skill-distillation", ["Agent Skill", "Skill Evolver"])
        
        # Test direct title resolution
        res1 = index.resolve("Agent Skill Distillation")
        self.assertIsNotNone(res1)
        self.assertEqual(res1[1], "agent-skill-distillation")
        
        # Test alias resolution
        res2 = index.resolve("Agent Skill")
        self.assertIsNotNone(res2)
        self.assertEqual(res2[1], "agent-skill-distillation")
        
        # Test slug resolution
        res3 = index.resolve("agent-skill-distillation")
        self.assertIsNotNone(res3)
        self.assertEqual(res3[1], "agent-skill-distillation")

        # Test string replacement
        text = "This matches [[Agent Skill]] and also [[Non Existent Concept]] or [[Agent Skill Distillation|Skill Distill]]."
        resolved_str, resolved_count, unresolved_count = resolve_text_links(text, index)
        
        self.assertIn("[[Agent Skill Distillation]]", resolved_str)
        self.assertIn("[[Agent Skill Distillation|Skill Distill]]", resolved_str)
        self.assertIn("[[Non Existent Concept]]", resolved_str)  # preserved, not downgraded
        self.assertEqual(resolved_count, 2)
        self.assertEqual(unresolved_count, 1)

    def test_markdown_parser(self):
        content = """---
type: concept
title: Super Memory
tags: [agent, memory]
sources: ["diary/2026/0510.md"]
---
# Super Memory

## Definition
- Large context retrieval mechanism.

## Evidence
- Used in project DeepMemo.
"""
        draft = parse_markdown_to_draft(content, "wiki/concepts/super-memory.md")
        self.assertEqual(draft.page_type, "concept")
        self.assertEqual(draft.title, "Super Memory")
        self.assertEqual(draft.slug, "super-memory")
        self.assertIn("diary/2026/0510.md", draft.sources)
        self.assertEqual(len(draft.sections), 2)

    def test_auto_ingest_writes_generated_blocks_without_real_llm(self):
        from src.wiki.ingest_pipeline import auto_ingest

        generation = """---FILE: wiki/sources/source.md---
---
type: source
title: Source
tags: [test]
sources: ["source.md"]
related: []
---
# Source

## Summary
- Test summary.
---END FILE---"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "source.md"
            wiki_dir = root / "wiki"
            source_path.write_text("# Source\n\nTest summary.\n", encoding="utf-8")

            with patch("src.wiki.ingest_pipeline.run_analysis", return_value="analysis"), patch(
                "src.wiki.ingest_pipeline.run_generation",
                return_value=generation,
            ):
                result = auto_ingest(str(source_path), wiki_dir=wiki_dir)

            self.assertIn("wiki/sources/source.md", result.written_paths)
            self.assertTrue((wiki_dir / "sources" / "source.md").is_file())

    def test_evidence_cards_promote_recurring_concepts(self):
        entries = [
            MockDiaryEntry(
                path="data/diary/0522.md",
                title="0522",
                content="""# 每日记录

## 工程博客
[腾讯技术工程-Agent Memory](https://example.com): 用 Mermaid 画布做 Agent Memory 压缩。
- Agent Memory 通过 Mermaid 保留任务状态。
""",
            ),
            MockDiaryEntry(
                path="data/diary/0523.md",
                title="0523",
                content="""# 每日记录

## 工程博客
[阿里云-Agent Memory 实践](https://example.com): Agent Memory 从向量检索转向文件系统化。
""",
            ),
        ]

        cards = extract_evidence_cards(entries)
        entity_pages, concept_pages = build_drafts_from_evidence(cards)

        self.assertGreaterEqual(len(cards), 2)
        self.assertIn("agent-memory", concept_pages)
        draft = concept_pages["agent-memory"]
        self.assertEqual(draft.title, "Agent Memory")
        self.assertIn("data/diary/0522.md", draft.sources)
        self.assertIn("data/diary/0523.md", draft.sources)
        self.assertTrue(any(section.heading == "Evidence" for section in draft.sections))

    def test_full_knowledge_builder_uses_evidence_first_candidates(self):
        entries = [
            MockDiaryEntry(
                path="data/diary/0522.md",
                title="0522",
                content="""# 每日记录

## 工程博客
[腾讯技术工程-Agent Memory](https://example.com): 用 Mermaid 画布做 Agent Memory 压缩。
""",
            ),
            MockDiaryEntry(
                path="data/diary/0523.md",
                title="0523",
                content="""# 每日记录

## 工程博客
[阿里云-Agent Memory 实践](https://example.com): Agent Memory 从向量检索转向文件系统化。
""",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            _source_pages, _entity_pages, concept_pages, _synthesis_pages = _build_knowledge_pages_from_analyses(
                entries,
                {},
                diary_dir=Path(tmp) / "does-not-exist",
                wiki_dir=Path(tmp) / "wiki",
            )

        self.assertIn("agent-memory", concept_pages)
        self.assertEqual(concept_pages["agent-memory"].sources, ["data/diary/0522.md", "data/diary/0523.md"])

    def test_canonical_registry_keeps_aliases_and_sources(self):
        draft = WikiDraft(
            page_type="concept",
            slug="agent-memory",
            title="Agent Memory",
            summary="Memory for agents.",
            tags=["concept"],
            sources=["data/diary/0522.md", "data/diary/0523.md"],
            aliases=["Agent Memory 实践"],
        )

        registry = build_canonical_registry([draft])

        self.assertEqual(registry["version"], 1)
        self.assertEqual(registry["pages"][0]["slug"], "agent-memory")
        self.assertEqual(registry["pages"][0]["aliases"], ["Agent Memory 实践"])
        self.assertEqual(registry["pages"][0]["sources"], ["data/diary/0522.md", "data/diary/0523.md"])

    def test_write_generated_wiki_supports_staging_directory(self):
        draft = WikiDraft(
            page_type="concept",
            slug="agent-memory",
            title="Agent Memory",
            summary="Memory for agents.",
            tags=["concept"],
            sources=["data/diary/0522.md"],
        )

        with tempfile.TemporaryDirectory() as tmp:
            wiki_dir = Path(tmp) / "wiki_next"
            write_generated_wiki(
                wiki_dir=wiki_dir,
                entries=[],
                source_pages={},
                entity_pages={},
                concept_pages={"agent-memory": draft},
                synthesis_pages={},
            )

            self.assertTrue((wiki_dir / "concepts" / "agent-memory.md").is_file())
            self.assertTrue((wiki_dir / "registry.json").is_file())

    def test_health_report_detects_dangling_links_and_duplicate_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_dir = Path(tmp)
            concepts = wiki_dir / "concepts"
            concepts.mkdir(parents=True)
            (concepts / "agentic-query-rewriting.md").write_text(
                """---
title: Agentic Query Rewriting
type: concept
tags: []
sources: ["data/diary/0412.md"]
status: active
related: []
---
# Agentic Query Rewriting

## Related
[[Missing Concept]]
""",
                encoding="utf-8",
            )
            (concepts / "agentic-rewrites.md").write_text(
                """---
title: Agentic Rewrites
type: concept
tags: []
sources: ["data/diary/0420.md"]
status: active
related: []
---
# Agentic Rewrites
""",
                encoding="utf-8",
            )

            report = build_wiki_health_report(wiki_dir)

        self.assertEqual(report["pages"]["total"], 2)
        self.assertEqual(report["links"]["dangling_count"], 1)
        self.assertEqual(report["links"]["dangling"][0]["target"], "Missing Concept")
        self.assertGreaterEqual(len(report["duplicates"]["candidates"]), 1)

    def test_graph_build_excludes_source_nodes_without_key_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki_dir = Path(tmp)
            (wiki_dir / "sources").mkdir(parents=True)
            (wiki_dir / "concepts").mkdir(parents=True)
            (wiki_dir / "sources" / "0522.md").write_text(
                """---
title: 0522 Source
type: source
tags: []
sources: ["data/diary/0522.md"]
status: active
related: []
---
# 0522 Source

## Related
[[Agent Memory]]
""",
                encoding="utf-8",
            )
            (wiki_dir / "concepts" / "agent-memory.md").write_text(
                """---
title: Agent Memory
type: concept
tags: [agent, memory]
sources: ["data/diary/0522.md"]
status: active
related: []
---
# Agent Memory
""",
                encoding="utf-8",
            )

            graph = build_diary_graph(wiki_dir)

        self.assertEqual(graph["meta"]["total_nodes"], 2)
        self.assertGreaterEqual(graph["meta"]["total_communities"], 1)

    def test_semantic_source_overlap_uses_jaccard_union_denominator(self):
        nodes = {
            "concept:a": GraphNode(
                path="concept:a",
                title="A",
                type="concept",
                status="active",
            ),
            "concept:b": GraphNode(
                path="concept:b",
                title="B",
                type="concept",
                status="active",
            ),
        }
        support_sets = {
            "concept:a": {"data/diary/1.md", "data/diary/2.md", "data/diary/3.md"},
            "concept:b": {"data/diary/1.md", "data/diary/4.md", "data/diary/5.md"},
        }

        overlap = _source_overlap("concept:a", "concept:b", nodes, {}, support_sets)

        self.assertAlmostEqual(overlap, 0.2)


if __name__ == "__main__":
    unittest.main()
