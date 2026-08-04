<div align="center">

# DeepMemo

**本地优先的 Markdown 知识库创作与问答工作台**

不要高估一天的产出，也不要小看一周的积淀。DeepMemo 帮你把零散记录沉淀成可编辑、可检索、可追溯的个人知识系统，并通过 Editor、QA、Knowledge 三个工作区连接创作、问答和知识整理。

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=111111)
![Vite](https://img.shields.io/badge/Vite-6-646CFF?style=flat-square&logo=vite&logoColor=white)
![Local First](https://img.shields.io/badge/Local--first-Markdown-2F80ED?style=flat-square)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

</div>

---

## Why DeepMemo

AI 时代的信息流像多线程任务一样不断抢占注意力：课程、科研、工程实践、技术追新、内容创作和生活本身都在同时运行。DeepMemo 的目标不是再造一个封闭笔记软件，而是给个人 Markdown 知识库加上一层透明的 AI 工作台。

- **文件在你手里**：`data/` 下的 `.md` 文件是唯一真值，离开 DeepMemo 也能继续用编辑器、Git 或 Obsidian 打开。
- **创作和检索闭环**：编辑器模式负责记录和整理，问答模式负责激活和串联。
- **回答可追溯**：DeepMemo 不只给结论，还会把回答绑定到本地 Markdown 片段，使用 `[1]`、`[2]` 这样的引用回到源文件。
- **适合个人长期积累**：可以按目录自然生长，不需要一开始就设计复杂知识库。

---

## Screenshots
<p align="center">
  <img src="docs/design/screenshots/editor-mode.png" alt="DeepMemo Editor Mode" width="850" />
</p>
<p align="center">
  <img src="docs/design/screenshots/qa-mode.png" alt="DeepMemo Q&A Mode" width="850" />
</p>

---

## Features

### 文件系统驱动的编辑器

- 左侧 Data Explorer 直接映射本地 `data/` 目录。
- 支持读取、创建、保存 Markdown 文件和创建文件夹。
- 使用 Vditor 提供所见即所得编辑，并支持 `Ctrl/Cmd + S` 保存。
- 文件状态使用 `synced`、`dirty`、`draft`、`processing`、`error` 标记，便于区分本地变更状态。
- 内置基础格式化和面向当前文档的 AI 补完入口。

### 本地知识库问答

- `LocalSearchAgent` 会在 `data/**/*.md` 中检索相关片段，将本地 Markdown 相关信息交给 LLM 生成回答。
- 回答正文中的 `[1]`、`[2]` 引用会绑定到具体文件片段，右侧 Source Panel 可查看原文上下文。
- 支持查询引用了当前文件的历史会话，方便从文件回到对话。

### Knowledge Engine

- 将 Markdown 和会话增量编译为可审阅的 Knowledge Cards。
- 提供 Overview、Reader、Review、Cards 四种知识视图。
- 支持卡片维护、人工字段保护、关系浏览和 RepoWiki 重建。

### 可选的外部信息补充

- WebSearchAgent 默认关闭，只有配置后才会在本地证据不足且问题依赖外部实时信息时 fallback。
- 回答侧会区分本地知识库证据和外部搜索补充，避免把外部信息误认为个人记录。

---

## Demo Data

仓库只发布可公开的 mock 知识库数据：

- `data/mock/example1.md`：DeepMemo 的产品定位和问答流程示例。
- `data/mock/example2.md`：AI 时代个人多线程学习和记录压力的案例故事。

真实个人知识库会被 `.gitignore` 忽略，只有 `data/mock/` 会进入 Git。启动后可以在问答模式尝试“DeepMemo 如何保证回答可追溯？”。

---

## Quick Start

### Requirements

- Python 3.11+
- Node.js 18+
- [uv](https://github.com/astral-sh/uv)
- [ripgrep](https://github.com/BurntSushi/ripgrep)，本地 Markdown 检索依赖 `rg`

### 1. Install

```bash
git clone https://github.com/YeyezhizzZ/deepmemo.git
cd deepmemo

uv sync --all-groups

cd app
npm ci
cd ..
```

### 2. Configure LLM

仅编辑、浏览 Knowledge 和运行测试时不需要 LLM 配置。使用 QA 或 AI 补完前，从示例创建本地配置；该文件已被 `.gitignore` 忽略。

```bash
cp config/example.yaml config/llm_api.yaml
```

```yaml
llm:
  use: openai_compatible
  openai_compatible:
    api_key: "replace-with-your-api-key"
    api_base: "https://api.example.com/v1"
    model: "your-model-name"
    max_tokens: 1200
    temperature: 0.7
```

`llm.use` 必须指向 `llm` 下的 provider。接口需要兼容 OpenAI Chat Completions。

### 3. Run

> 所有命令默认从项目根目录 `deepmemo/` 执行。

后端 API，默认端口 `8000`：

```bash
uv run uvicorn src.app.main:app --reload
```

前端应用，默认端口 `5173`：

```bash
cd app
npm run dev
```

打开 http://127.0.0.1:5173 使用 DeepMemo。后端 API 文档位于 http://127.0.0.1:8000/docs。

---

## Project Structure

```text
deepmemo/
├── app/                    # React + Vite + TypeScript 前端
│   ├── src/
│   └── tests/browser/      # Playwright 场景
├── src/                    # FastAPI 后端
│   ├── ai/                 # RAG、检索、回答生成、WebSearch fallback
│   ├── app/                # 应用入口、数据库、文件监听
│   ├── knowledge/          # Card 编译、维护、检索和 RepoWiki
│   ├── routers/            # chat、fs、diary、pulse、citations API
│   └── services/           # LLM provider 封装
├── tests/                  # API、单元和 E2E 测试
├── docs/                   # specs、设计文档和 VitePress Wiki
├── data/mock/              # 可公开示例知识库
└── config/example.yaml     # LLM 配置模板
```

---

## Architecture

```text
User Question
  -> QueryRewriter
  -> QueryRouter
  -> LocalSearchAgent
       -> glob_files
       -> grep_content
       -> read_lines
  -> WebSearchAgent fallback, optional
  -> AnswerComposer
  -> Markdown answer with citations

Markdown / Conversation
  -> KnowledgeCardCompiler
  -> data/knowledge/cards
  -> View Model / Review Queue / RepoWiki
```

DeepMemo 当前采用轻量 RAG 思路：先不引入 embedding 和向量数据库，而是使用安全封装的本地搜索工具在 Markdown 文件中召回证据。这样更适合个人 MB 级知识库，也降低了索引维护成本。

---

## Tech Stack

- Frontend：React 18、TypeScript、Vite、Vditor、Lucide React
- Backend：FastAPI、Pydantic、SQLite
- AI：OpenAI-compatible Chat Completions API
- Local search：ripgrep + 受控文件读取工具
- Optional web search：Tavily、Open-WebSearch MCP

---

## Verification

快速回归（API、单元测试和前端构建）：

```bash
uv run python scripts/verify.py --mode quick
```

完整回归还需要先安装 Playwright Chromium：

```bash
cd app
npx playwright install chromium
cd ..
uv run python scripts/verify.py --mode full
```

文档站：

```bash
cd docs/wiki
npm ci
npm run docs:build
```

---

## Security Notes

- `data/*` 默认不提交，只发布 `data/mock/**`。
- `config/llm_api.yaml`、`.env`、`*.db`、`.claude/` 已被 `.gitignore` 忽略。
- 本地检索工具只允许访问 `data/` 下的 Markdown 文件，并会校验路径，避免 `../` 越界读取。
- 发布前请确认没有把真实日记、API Key、私有记忆或本地 agent 配置加入 Git。

---

## License

DeepMemo is open-sourced under the [MIT License](LICENSE).
