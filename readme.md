<div align="center">

# DeepMe

**自带作者公开知识库的可追溯问答产品**

默认站点连接作者经过筛选的公开知识库。访客可以询问项目经历、技术决策和长期复盘，也可以临时上传自己的 Markdown、TXT 或 PDF 问答。

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=111111)
![Vite](https://img.shields.io/badge/Vite-6-646CFF?style=flat-square&logo=vite&logoColor=white)
![Local First](https://img.shields.io/badge/Local--first-Markdown-2F80ED?style=flat-square)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

</div>

---

## Why DeepMe

DeepMe 把个人长期记录变成一个有证据边界的公开问答入口。

- **问我**，默认连接作者公开知识版本，适合个人展示和面试前了解。
- **问你的资料**，匿名上传文件，在独立临时空间中问答，默认24小时删除。
- **回答可追溯**，事实回答绑定文件、行号或 PDF 页码，并记录知识版本。
- **可以自部署**，拉取项目后替换 `public-knowledge/`，即可部署自己的站点。
- **Markdown 仍是真值**，索引和模型输出都可以重建，不替代原文。

---

## Features

### 公开知识分身

- 公开知识目录按内容哈希构建不可变版本。
- 新版本构建失败时继续使用旧版本。
- 匿名会话通过签名 Cookie 隔离。
- 问答不会把模型常识包装成作者经历。

### 临时文件问答

- 支持 `.md`、`.txt` 和可提取文本的 `.pdf`。
- API 流式写盘，Worker 异步解析和构建索引。
- 每个 workspace 拥有独立 scope、版本、会话和引用。
- 主动删除后立即阻断访问，随后清理物理文件。

### 版本级检索

- 中文二元与三元 Ngram 基础召回。
- 可选 Embedding 与 LLM 精排。
- Embedding 或精排失败时自动退化为 Ngram。
- SQLite 索引跟随知识版本，不依赖外部向量数据库。

---

## Public Knowledge

默认公开内容位于 `public-knowledge/`。自部署时直接替换该目录中的 Markdown。

私人 `data/` 仍被 Git 忽略，不会自动进入公开知识版本。

---

## Quick Start

### Requirements

- Python 3.11+
- Node.js 18+
- [uv](https://github.com/astral-sh/uv)
- 可选 Docker 和 Docker Compose

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

从示例创建模型配置。该文件已被 `.gitignore` 忽略。

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
    embedding_model: "your-embedding-model-name"
    max_tokens: 1200
    temperature: 0.7
```

`llm.use` 必须指向 `llm` 下的 provider。接口需要兼容 OpenAI Chat Completions。

### 3. Run Locally

> 所有命令默认从项目根目录 `deepmemo/` 执行。

后端 API

```bash
DEEPME_PUBLIC_SOURCE_DIR=./public-knowledge \
uv run uvicorn src.app.main:app --reload
```

Worker

```bash
DEEPME_PUBLIC_SOURCE_DIR=./public-knowledge \
uv run python -m src.deepme.worker
```

前端

```bash
cd app
npm run dev
```

打开 http://127.0.0.1:5173。API 文档位于 http://127.0.0.1:8000/docs。

### 4. Run with Docker

```bash
cp .env.example .env
cp config/example.yaml config/llm_api.yaml
docker compose up --build
```

打开 http://127.0.0.1:8080。

---

## Project Structure

```text
deepmemo/
├── app/                    # DeepMe React 前端
├── src/deepme/             # scope、版本、检索、上传与 Worker
├── src/app/                # FastAPI 与 SQLite
├── public-knowledge/       # 默认公开知识目录
├── runtime/                # 版本、上传和索引，默认忽略
├── tests/                  # API、单元、E2E 与 Browser 测试
├── docs/                   # PRD、架构与 Specs
├── Dockerfile
└── compose.yaml
```

---

## Architecture

```text
Public Markdown / Temporary Upload
  -> Immutable Knowledge Version
  -> SQLite Ngram + Optional Embedding Index
  -> Query Rewrite
  -> Hybrid Retrieval
  -> Optional LLM Rerank
  -> Grounded Answer
  -> Versioned Citations
```

详细设计见 [DeepMe 系统架构](docs/design/deepme-system-architecture.md)。

---

## Tech Stack

- Frontend 使用 React 18、TypeScript、Vite、Lucide React
- Backend 使用 FastAPI、Pydantic、SQLite
- AI 使用 OpenAI-compatible Chat Completions 与 Embedding API
- Retrieval 使用 SQLite FTS5、Ngram、可选 Embedding 与 LLM Rerank
- Document 支持 Markdown、TXT、pypdf

---

## Verification

快速回归包含 API、单元测试和前端构建

```bash
uv run python scripts/verify.py --mode quick
```

完整回归还需要先安装 Playwright Chromium

```bash
cd app
npx playwright install chromium
cd ..
uv run python scripts/verify.py --mode full
```

文档站

```bash
cd docs/wiki
npm ci
npm run docs:build
```

---

## Security Notes

- `data/*` 和 `runtime/` 默认不提交。
- `config/llm_api.yaml`、`.env`、`*.db`、`.claude/` 已被 `.gitignore` 忽略。
- 每次问答从 session 解析 scope，客户端不能覆盖。
- 上传文件名不参与磁盘路径，所有路径都经过根目录校验。
- 文档内容不会触发工具、Web Search 或知识写入。
- 上传片段会发送给配置的模型服务，部署者需要选择符合隐私要求的供应商。

---

## License

DeepMe is open-sourced under the [MIT License](LICENSE).
