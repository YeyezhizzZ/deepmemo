# Wiki Graph

* **Status**: Deprecated / Superseded by Knowledge Engine

## 1. Scope
旧 Wiki graph 基于生成的 Wiki 页面构图，不再是当前产品行为。

## 2. Preserved Behaviors
* 主应用不再暴露 `/wiki/graph`。
* 前端不再提供 Wiki graph workspace。
* Agent 检索不依赖 Wiki graph；使用 Knowledge Card-first retrieval。

## 3. Evidence
* `docs/specs/deprecated.md`
* `src/knowledge/retriever.py`

## 4. Current Flow
无当前运行流。旧 Wiki graph 属于 D 类行为，不得作为新需求依赖或扩展。
