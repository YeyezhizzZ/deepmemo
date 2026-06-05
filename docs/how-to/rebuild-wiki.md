# 重建 Wiki

Wiki 重建会从源 Markdown 生成结构化 Wiki 页面和图谱。

## 前端触发

进入 Wiki 模式，点击 `重建 Wiki`。前端调用：

```http
POST /wiki/rebuild
```

默认不是 clean rebuild。

## API 触发

```bash
curl -X POST http://localhost:8000/wiki/rebuild \
  -H 'Content-Type: application/json' \
  -d '{"clean": false}'
```

需要强制清理时：

```bash
curl -X POST http://localhost:8000/wiki/rebuild \
  -H 'Content-Type: application/json' \
  -d '{"clean": true}'
```

## 增量机制

Ingest 会使用 MD5 与 registry 缓存跳过未修改源文件，减少重复 LLM 调用。文件被 watcher 标为 `dirty` 后，也可被后续 Wiki 流程消费。

## 两阶段处理

1. Analysis：抽取实体、概念、综合、矛盾和来源信息。
2. Generation：生成格式化 Markdown 页面，并通过 link resolver 更新内链。

## 健康报告

`GET /wiki/health` 会返回健康报告，重点关注：

- dangling links
- duplicate candidates
- orphan pages
- stub pages

如果重建后图谱为空，先确认 `data/diary/` 是否有可处理 Markdown，再检查 LLM 配置和后端日志。
