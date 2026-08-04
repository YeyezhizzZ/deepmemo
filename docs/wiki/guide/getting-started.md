# 5 分钟快速上手

本教程会把 DeepMemo 在本地跑起来，并打开前端的三种工作模式。

## 前置条件

- Python 3.11+
- Node.js 18+
- `uv`
- `rg`，也就是 ripgrep

## 安装依赖

在仓库根目录安装后端依赖：

```bash
uv sync --all-groups
```

安装前端依赖：

```bash
cd app
npm ci
cd ..
```

## 配置 LLM

仅编辑和浏览 Knowledge 时可以跳过此步。使用 QA 或 AI 补完前，复制模板并替换 provider 配置：

```bash
cp config/example.yaml config/llm_api.yaml
```

```yaml
llm:
  use: siliconflow
  siliconflow:
    api_key: "${YOUR_API_KEY}"
    api_base: "https://api.siliconflow.cn/v1"
    model: "deepseek-ai/DeepSeek-V3"
    max_tokens: 1200
    temperature: 0.7
```

任何 OpenAI-compatible provider 都可以使用同一结构。

## 启动后端

```bash
uv run uvicorn src.app.main:app --reload
```

确认 API 返回：

```text
http://localhost:8000
```

## 启动前端

另开一个终端：

```bash
cd app
npm run dev
```

打开：

```text
http://localhost:5173
```

你会看到 Editor、QA、Knowledge 三种模式。`data/mock/` 中的数据用于公开 demo，包含 `deepmemo`、`demo`、`mock` 相关问题时会被 query router 优先路由到这里。
