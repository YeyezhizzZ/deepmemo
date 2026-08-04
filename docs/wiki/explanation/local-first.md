# Local-first 哲学

DeepMemo 的第一原则是：本地 Markdown 是来源真值。应用可以帮你索引、检索、总结和生成 Knowledge Cards，但不能把 SQLite、LLM 输出或云服务变成长期知识所有权的中心。

## 为什么坚持 Markdown

Markdown 文件有几个朴素但重要的优点：

- 可以被任何编辑器打开。
- 可以用 Git、备份软件或普通文件夹同步。
- 不需要平台账号才能读写。
- 适合日记、想法、长期记忆和原始资料共存。

这意味着 DeepMemo 不是把你的知识迁移到另一个封闭系统里，而是在本地文件之上提供工作台。

## SQLite 的角色

SQLite 保存的是元数据，而不是知识正文：

| 表 | 用途 |
|:---|:---|
| `session` | 聊天会话、主题、摘要、消息 id 列表 |
| `message` | 用户和 AI 消息、引用信息 |
| `file_meta` | 文件路径、MD5、同步状态 |

知识正文仍在 `data/*.md`。如果数据库损坏，长期知识仍应能从文件恢复。

## Knowledge 产物也是本地文件

Knowledge Engine 会把日记等碎片化语料编译为 `data/knowledge/cards/` 下的 YAML Cards，并从 Cards 生成 `data/knowledge/repowiki/` Markdown 页面。它们是派生产物，但仍是可检查和备份的普通本地文件。

这个设计有一个克制点：Cards 和 RepoWiki 不替代原始日记。原文负责事实和语境，Knowledge 层负责结构化视图和人工审阅。

## 为什么没有默认 Vector DB

个人知识库通常是 MB 到低 GB 级别，`ripgrep` 对这类 Markdown 搜索足够快。默认使用 `rg` 可以避免维护嵌入索引、向量库 schema、重建任务和额外存储。

需要语义扩展时，LLM 可以参与查询改写和答案合成；但本地搜索仍是主要证据入口。
