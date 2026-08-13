# DeepMe Versioned Retrieval

* **Status**: Proposed

## 1. Context

当前 Scope 基础仍使用 `rg` 搜索完整 Markdown。公开知识和上传文件扩大后，需要稳定的中文召回、PDF 页码引用和可重建索引，同时不能引入外部向量数据库。

## 2. Intended Behavior

- 每个知识版本构建独立 SQLite 索引。
- 文档按标题、段落和字符上限切片。
- Chunk 保存文件、行号、页码和 SHA256。
- 基础召回使用中文二元与三元 Ngram。
- 配置 Embedding 后使用向量召回，并与 Ngram 结果做 RRF 融合。
- 配置 LLM 精排后只对候选 Chunk 排序。
- Embedding 或精排失败时退化为 Ngram，不中断问答。
- 引用必须来自当前 scope 和版本。
- 索引属于派生数据，可以从版本文档和 manifest 重建。

## 3. Alternative Approaches

直接部署向量数据库会增加自部署和数据删除成本。继续使用固定字符串检索无法稳定覆盖中文同义表达。MVP 使用版本内 SQLite FTS5、Ngram 和可选 Embedding。

## 4. Risks & Dependencies

- SQLite FTS5 在部分环境可能不可用，需要扫描回退。
- Embedding 会把文档片段发送给模型服务。
- LLM 精排输出必须限制为候选 `chunk_id`。
- 索引构建失败不能发布知识版本。
