# 配置 LLM API

DeepMemo 默认从 `config/llm_api.yaml` 读取 LLM 配置。先复制不含真实密钥的模板：

```bash
cp config/example.yaml config/llm_api.yaml
```

也可以通过 `DEEPMEMO_LLM_CONFIG` 指向其他 YAML 文件。LLM 客户端采用延迟初始化，因此编辑器、Knowledge 工作区和测试在没有该文件时仍可运行。

## 推荐格式

```yaml
llm:
  use: openai_compatible
  openai_compatible:
    api_key: "${YOUR_API_KEY}"
    api_base: "https://api.example.com/v1"
    model: "your-model-name"
    max_tokens: 1200
    temperature: 0.7
```

`llm.use` 的值要和 `llm` 下的 provider key 一致。

## 旧格式

旧格式会把顶层第一个 key 当作 provider：

```yaml
openai_compatible:
  api_key: "${YOUR_API_KEY}"
  api_base: "https://api.example.com/v1"
  model: "your-model-name"
```

保留旧格式只是为了兼容，不建议新配置继续使用。

## Web search

Web search 配置在 `config/web_search.yaml`：

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

禁用外部搜索：

```yaml
enabled: false
provider: "disabled"
```

## 验证配置

启动后端：

```bash
uv run uvicorn src.app.main:app --reload
```

再打开前端提问。首次调用 LLM 时，若配置不存在、无法解析或缺少必填字段，回答会返回明确的配置错误。
