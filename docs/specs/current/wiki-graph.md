# Wiki Graph

* **Status**: Current / Human Reviewed

## 1. Scope
基于知识库构建图谱，提取概念、实体并进行拓扑分析。

## 2. Preserved Behaviors
* **Louvain 社区发现**：使用改进的 Louvain 算法计算不同节点之间的 Community。
* **边权重模型**：整合直接链接（Direct Link）、资源交集（Source Overlap）、Adamic-Adar 算法等生成复杂的 Edge 权重。

## 3. Evidence
* `src/wiki/graph.py`

## 4. Current Flow
读取生成的 Wiki 页面 (Frontmatter + Markdown Links) -> 构建邻接矩阵 -> 运行社区发现算法 -> 输出 graph.json。
