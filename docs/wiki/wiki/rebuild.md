# 旧版 Wiki 重建流程

> **已废弃**：`POST /wiki/rebuild` 和 `GET /wiki/health` 未挂载，调用应返回 404。本页仅记录历史方案。

当前 Knowledge Engine 分成两个显式阶段：

1. 将 Markdown 编译为 Knowledge Cards：

```bash
curl -X POST http://localhost:8000/api/knowledge/compile
```

2. 从 Cards 重建只读 RepoWiki：

```bash
curl -X POST http://localhost:8000/api/knowledge/repowiki/rebuild
```

查看健康状态：

```bash
curl http://localhost:8000/api/knowledge/health
```

这些流程不会恢复旧 `data/wiki/` 或 `/wiki/*` 产品表面。完整契约见 [Knowledge Engine Spec](/specs/current/knowledge-engine)。
