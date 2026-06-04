# Project Wiki Generation

## 1. Goal
基于用户的 Markdown 日记语料，通过提取、去重、LLM 总结等手段，生成系统性关联的双链结构化知识库（Wiki），并通过图谱展示知识点。

## 2. Why this goal matters
日记是碎片化的流，用户难以系统性追溯。Wiki 生成能把流式信息转化为结构化智库，是产品的核心价值闭环。

## 3. Related Specs
* **Current Specs**: `wiki-graph.md`, `wiki-ingestion.md`
* **Open Questions**: Wiki vs 本地搜索边界模糊问题

## 4. Desired Behavior
* 能够通过增量分析（MD5 哈希比对）减少无意义的 LLM 调用。
* 系统需通过 Louvain 算法将相关的节点聚类成 Community 并高亮。
* 能够定期或通过指令自动执行，对未梳理的 Markdown 文件进行入库整理。

## 5. Non-goals
* 改变用户原始的 Markdown 日记。
* 构建纯实时搜索引擎（这部分交给 RAG 处理）。

## 6. Requirements
* 新版改动不能影响已有的 `frontmatter` 解析格式。
* 任何依赖大模型的处理必须具备 fallback 机制（启发式正则匹配等）。

## 7. Acceptance Criteria
* 当执行重建命令时，必须能够正确解析带嵌套和多种引用标记的 Markdown。
* Health 报告能够正确捕捉到 dangling links 和 stub pages。

## 8. Implementation Strategy
（待具体扩展：见独立 Issue / 计划分配）

## 9. Task Breakdown
- [ ] 待定：基于具体的 OpenSpec Proposal 进行填充

## 10. Validation Plan
* 运行完整的测试套件。
* 查看 `data/wiki` 输出结果是否合法。

## 11. Docs Sync Requirements
* 更新对应的 Current Spec 细节。
