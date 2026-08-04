# 旧版 Wiki 探索流程

> **已废弃**：本页描述的 Wiki 工作区、`/wiki/rebuild` 和图谱浏览流程已从主应用移除，不可作为操作手册使用。

旧方案把 `data/wiki/` 页面建模为 `source`、`entity`、`concept`、`synthesis` 和 `query` 节点，并基于直接链接、来源交集、Adamic-Adar 与 Louvain 社区检测构图。相关内容保留用于解释早期技术取舍。

当前界面请使用 `Knowledge` 工作区：

- `Overview` 查看统计和关系概览。
- `Reader` 阅读由 Cards 生成的页面。
- `Review` 处理确认、隐藏和重写建议。
- `Cards` 编辑受保护的结构化知识。

当前行为与接口以 [Knowledge Engine Spec](/specs/current/knowledge-engine) 为准。
