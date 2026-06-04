# Wiki Ingestion

* **Status**: Current / Human Reviewed

## 1. Scope
将无结构的碎念 Markdown（Diary）转化为结构化的 Wiki 页面。

## 2. Preserved Behaviors
* **增量构建与缓存**：使用 MD5 值与 `registry.json` 进行对比，避免未修改的文章浪费大模型 Token。
* **两段式提取**：LLM 执行 Analysis 分析（实体、概念、综合、矛盾），再执行 Generation 生成格式化的 Markdown FILE。

## 3. Evidence
* `src/wiki/ingest_pipeline.py`
* `src/wiki/ingest_analyzer.py`

## 4. Current Flow
遍历 Diary -> 检查 Cache -> LLM 解析元数据 -> Heuristic/LLM Merger -> LLM 生成内容块 -> Link Resolver 更新内链 -> 写入磁盘并更新 Registry。
