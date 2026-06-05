# 脚本和命令

## 后端

安装 Python 依赖：

```bash
uv sync
```

启动 API：

```bash
uv run uvicorn src.app.main:app --reload
```

默认访问：

```text
http://localhost:8000
```

## 前端

安装依赖：

```bash
cd app
npm install
```

启动开发服务器：

```bash
cd app
npm run dev
```

构建前端：

```bash
cd app
npm run build
```

## 测试

快速验证：

```bash
uv run python scripts/verify.py --mode quick
```

完整验证：

```bash
uv run python scripts/verify.py --mode full
```

单独运行 API 测试：

```bash
uv run pytest tests/api/ -q --tb=short
```

单独运行非 E2E 测试：

```bash
uv run pytest tests -q --tb=short -m "not e2e"
```

浏览器测试：

```bash
cd app
npm run test:browser
```

## 文档站

安装文档依赖：

```bash
cd docs/wiki
npm install
```

本地预览：

```bash
cd docs/wiki
npm run docs:dev
```

构建静态站点：

```bash
cd docs/wiki
npm run docs:build
```
