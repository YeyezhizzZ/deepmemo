# 体验 AI 问答

QA 模式用于基于本地 Markdown 的问答。它默认先查本地，再在特定条件下使用 Web fallback。

## 创建会话

进入 `QA` 模式，点击新建会话。会话会保存到 SQLite 的 `session` 表。

## 提问

可以先问一个和 demo 数据相关的问题：

```text
DeepMemo 是什么？
```

包含 `deepmemo`、`demo` 或 `mock` 的问题会路由到 `data/mock`，便于公开演示。

## 观察流式回答

使用 `/chat/stream` 时，前端会收到 SSE 事件：

- `token`：正在生成的片段。
- `done`：消息已经保存。
- `error`：生成或保存出现异常。

## 查看引用

回答中的 `[1]`、`[2]` 是本地证据引用。点击引用后可以看到来源文件和片段。引用信息保存在 `message.citations` 中，用于之后查询“哪些对话引用了这个文件”。

## 理解 Web fallback

Web search 不会默认触发。只有 query router 判断 `needs_web=true`，且本地结果置信度很低时，DeepMemo 才会调用外部搜索。
