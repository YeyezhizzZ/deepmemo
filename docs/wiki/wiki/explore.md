# 探索 Wiki 图谱

Wiki 模式把碎片化日记整理成结构化页面，并用图谱展示实体、概念和综合观点之间的关系。

## 打开 Wiki 模式

进入 `Wiki` 模式。左侧是 Wiki 页面列表和操作区，主区域显示社区图谱，右侧显示节点详情。

## 重建 Wiki

点击 `重建 Wiki`。前端会调用：

```http
POST /wiki/rebuild
```

默认请求体相当于：

```json
{ "clean": false }
```

## 等待 ingest

重建流程会遍历源 Markdown，检查 MD5 和 registry 缓存。变更文件进入两阶段 LLM 处理：

1. Analysis：提取实体、概念、综合、矛盾等结构。
2. Generation：生成带 frontmatter 的 Wiki Markdown 页面。

## 浏览图谱

图谱节点类型包括 `source`、`entity`、`concept`、`synthesis` 和 `query`。系统用直接链接、来源交集、Adamic-Adar 等信号计算边权，再运行 Louvain 社区检测。

## 搜索和定位

使用左侧搜索框过滤 Wiki 页面。点击节点会切换右侧详情，并展示相关链接和 backlinks。
