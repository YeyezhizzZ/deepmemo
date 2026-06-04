# Open Questions & Tech Debt

本文件记录尚未决定的 B 类与 Unknown 类内容。**绝对不能将此文件中的内容作为 AI 编程的需求！**

## 1. 巨型单体文件架构 (Monolithic Architecture)
* **Target**: 前端的 `App.tsx` (近 3000 行) 和后端的 `blog_fetcher.py` (超 2100 行)。
* **Status**: Human Review 决定**先不管**，等待 Spec 彻底确定稳定之后，再发起重构。目前作为已知的技术债保留。

## 2. Web Search Agent 的抽象泄漏
* **Target**: `src/ai/web_search_agent.py`
* **Status**: 实现了 Provider 抽象，但在 `extract/crawl/map` 功能上硬编码直连了 Tavily。Human Review 决定**暂不修改**，因为 Web 搜索技术选型尚未最终确定。

## 3. Wiki 图谱与本地搜索的边界
* **Target**: Wiki Graph (Louvain, `src/wiki/`) vs FS 本地检索 (`rg`)。
* **Status**: 目前两者存在平行演进，甚至存在重复的基础代码实现（如 `_slugify` 的不同版本）。需在未来进行架构收敛。
