# 写第一篇日记

本教程从 Editor 模式开始，创建并保存一篇 Markdown 日记。

## 打开 Editor

进入前端后选择 `Editor`。左侧是 `data/` 文件树，主区域是 Vditor 所见即所得编辑器，右侧会显示当前文件相关信息。

## 创建目录和文件

在文件树里创建目录，例如：

```text
diary/2026/
```

再创建一个 Markdown 文件：

```text
diary/2026/2026-06-05.md
```

## 写内容

在编辑器中输入：

```markdown
# 2026-06-05

## 今天在做

- 跑通 DeepMemo
- 记录第一个本地 Markdown 知识片段
```

编辑时文件状态会从 `synced` 变为 `dirty` 或草稿态。保存成功后，状态回到 `synced`。

## 插入图片

把图片拖入 Vditor。前端会调用 `/api/fs/upload-asset`，后端根据关联 Markdown 路径把图片保存到 `data/assets/` 下，并返回 Vditor 可识别的 JSON。

## 保存

使用界面保存按钮或 `Ctrl+S`。保存会调用 `/api/fs/write`，写入本地 Markdown，并更新 `file_meta` 中的 hash 和同步状态。
