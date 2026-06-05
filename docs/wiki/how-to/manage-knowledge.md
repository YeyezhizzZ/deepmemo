# 管理知识库

DeepMemo 的知识库根目录是 `data/`，可用 `DEEPMEMO_DATA_DIR` 改写。

## 推荐目录

| Path | 用途 |
|:---|:---|
| `data/diary/` | 日记和每日记录 |
| `data/ideas/` | 想法、草案、灵感 |
| `data/memory/` | 长期记忆 |
| `data/raw/` | 抓取材料、原始输入 |
| `data/mock/` | demo 数据 |
| `data/wiki/` | 生成 Wiki 页面 |
| `data/policy/` | Wiki 策略 |
| `data/assets/` | 图片等附件 |

## 文件命名

日记建议使用日期：

```text
data/diary/2026/2026-06-05.md
```

主题资料建议使用清晰短名：

```text
data/ideas/local-first-search.md
```

## 同步状态

`file_meta.sync_status` 有五种状态：

| Status | 含义 |
|:---|:---|
| `synced` | 文件内容与记录一致 |
| `dirty` | 文件发生变更，等待后续处理 |
| `draft` | 草稿态 |
| `processing` | 正在处理 |
| `error` | 处理失败 |

后台 watcher 会监听 `data/` 下 Markdown 变化，计算 MD5，并把真正变更的文件标记为 `dirty`。

## 前端管理

Editor 模式的文件树支持创建、读取、写入、移动和重命名。Wiki 目录由 LLM 和 Wiki 模块维护，前端编辑模式会过滤掉 `data/wiki`，避免把生成页面和原始知识混在同一个编辑流里。
