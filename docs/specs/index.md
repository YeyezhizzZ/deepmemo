# DeepMemo Spec 体系导航

DeepMemo 的 spec 体系给 AI coding agent 和人类协作者提供共同的行为边界。代码库是事实观察来源，`docs/specs/current/` 才是已经 Human Review 的行为基线。

## 核心原则

1. 本地 Markdown 是用户知识真值。
2. 行为代码必须先有 spec。
3. 回归保护必须测试优先。
4. 测试模型采用 L1 API、L2 单元、L3 场景的沙漏结构。
5. 验证必须隔离真实 `data/`、`data.db`、LLM 和外部网络。

## Baseline Specs

- [Constitution](./constitution)
- [AI Chat & RAG](./ai-chat-rag)
- [Query Routing](./query-routing)
- [Wiki Graph](./wiki-graph)
- [Wiki Ingestion](./wiki-ingestion)
- [File System Watcher](./fs-watcher)
- [Asset Manager](./asset-manager)
- [Test Infrastructure](./test-infrastructure)
- [Agentic Testing](./agentic-testing)

## 生命周期

- `goals/`：准备实施的目标入口，只有 Ready 状态的 Goal 才能进入编码。
- `current/`：已经实现并确认要保留的 A 类行为。
- `proposed/`：尚未确认的未来设计。
- `review/`：讨论材料，不是需求。
- `deprecated.md`：D 类废弃行为，不要依赖、扩展或修复其边缘问题。
