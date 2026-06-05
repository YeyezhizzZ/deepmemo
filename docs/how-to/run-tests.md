# 运行测试

DeepMemo 使用沙漏测试模型：L1 API 合约、L2 单元、L3 场景 E2E 和浏览器测试。

## 快速验证

```bash
uv run python scripts/verify.py --mode quick
```

该命令会运行：

- `pytest tests -q --tb=short -m "not e2e"`
- `cd app && npm run build`

## 完整验证

```bash
uv run python scripts/verify.py --mode full
```

完整模式会额外运行：

```bash
cd app
npm run test:browser
```

## 分层运行

API 合约测试：

```bash
uv run pytest tests/api/ -q --tb=short
```

单元测试：

```bash
uv run pytest tests/unit/ -q --tb=short
```

E2E 测试：

```bash
uv run pytest tests/e2e/ -q --tb=short
```

## 测试隔离

测试必须使用临时 `data/` 和临时 SQLite。LLM、外部网络和第三方服务默认 mock，除非明确做集成验证。

## 文档站验证

项目 wiki 的构建命令是：

```bash
cd docs
npm run docs:build
```
