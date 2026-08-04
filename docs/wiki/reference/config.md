# 配置项

## 环境变量

| Name | Default | 用途 |
|:---|:---|:---|
| `DEEPMEMO_DATA_DIR` | `data/` | 知识库根目录 |
| `DEEPMEMO_DB_PATH` | `data.db` | SQLite 数据库路径 |
| `DEEPMEMO_LLM_CONFIG` | `config/llm_api.yaml` | LLM YAML 配置路径 |
| `DEEPMEMO_KNOWLEDGE_USE_LLM` | `0` | 设为 `1` 时允许 Card 编译使用 LLM，失败时回退启发式提取 |
| `DEEPMEMO_WATCHER_MODE` | 空 | 设置为 `polling` 时使用 polling watcher |
| `DEEPMEMO_API_PROXY_TARGET` | `http://localhost:8000` | Vite 开发代理目标 |
| `VITE_API_BASE_URL` | `/api` | 前端运行时 API base URL |
| `DEEPMEMO_BASE_URL` | `http://127.0.0.1:5173` | 浏览器测试 base URL |

## `config/llm_api.yaml`

DeepMemo 支持两种格式。推荐新格式，用 `llm.use` 指定 provider：

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

旧格式仍兼容：顶层第一个 key 会被当作 provider。

```yaml
siliconflow:
  api_key: "${YOUR_API_KEY}"
  api_base: "https://api.siliconflow.cn/v1"
  model: "deepseek-ai/DeepSeek-V3"
```

字段由 `src/services/llm_service.py` 在首次 LLM 调用时读取。当前实现使用 OpenAI SDK，因此 provider 需要提供 OpenAI-compatible 的 `api_base`。缺少该文件不影响编辑器、Knowledge 工作区和无网络测试。

## `config/web_search.yaml`

Web search 默认由 `src/ai/web_search_agent.py` 读取。

```yaml
enabled: true
provider: "open_websearch"

open_websearch:
  engines:
    - "bing"
  limit: 10

tavily:
  api_key: "${TAVILY_API_KEY}"
```

支持的 provider：

| Provider | 说明 |
|:---|:---|
| `open_websearch` | 通过 MCP provider 执行搜索 |
| `tavily` | 使用 Tavily API |
| `disabled` | 禁用 Web search |

即使启用了 Web search，RAG 流程也只会在 `needs_web=true` 且本地证据置信度很低时触发。

## `config/wiki_prompts.yaml`

Wiki ingest 和 merger 会读取该文件中的 prompt。文件不存在或为空时，相关模块会使用空 system prompt 并输出 warning。

## `data/knowledge/`

Knowledge Engine 将 Cards、索引、审阅状态和 RepoWiki 写入 `data/knowledge/`。它们是本地知识库的派生产物；旧 `/wiki/*` API 和 `data/wiki/` 不再属于当前产品接口。
