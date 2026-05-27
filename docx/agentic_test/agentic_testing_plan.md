# DeepMemo Agentic Testing 确定方案

> 本文是确定版设计稿。它基于当前 DeepMemo 代码结构修订，不再作为开放讨论稿。

## 结论

DeepMemo 的回归保护采用“代码化测试资产 + agent 执行协议”的组合。

- 测试资产必须落在仓库里，用 `pytest`、`npm run build` 和后续 Playwright E2E 表达。
- skill / AGENTS 规则只负责约束 agent 何时补测试、跑哪些命令、如何处理失败。
- 不把测试本体写进 skill；否则测试不可重复、不可审计，也无法被人类独立运行。

## 当前代码事实

当前仓库已经不是纯 Markdown 知识库，而是一个本地优先应用：

- 后端：FastAPI，入口为 `src/app/main.py`。
- 前端：React + Vite，位于 `app/`。
- 数据库：SQLite，默认文件为 `data.db`。
- 文件系统真值：`data/`。
- 主要路由：
  - `/api/fs/*`
  - `/sessions*`
  - `/chat*`
  - `/api/chat/citations`
  - `/api/chat/file-references`
  - `/wiki*`
  - `/api/diary/*`
  - `/api/pulse/*`

现有测试分散在 `src/` 内，例如：

- `src/app/core/test_asset_manager.py`
- `src/app/core/test_fs_manager.py`
- `src/app/test_static_assets.py`
- `src/routers/test_fs_assets.py`
- `src/wiki/test_reconstruction.py`

这些测试有价值，但缺少统一入口、共享 fixture 和分层策略。

## 当前落地进度

截至目前，DeepMemo 已经完成了第一轮测试基础设施和一批高价值回归测试：

- `tests/` 已建立，pytest 集中收口。
- `tests/conftest.py` 已提供临时 `data/` 和临时 SQLite 隔离。
- `scripts/verify.py` 已作为统一 quick/full 验证入口。
- `app/tests/browser/` 已落地 Playwright 浏览器烟雾测试。
- `scripts/run_browser_tests.py` 已负责托管本地前后端并执行浏览器测试。
- `scripts/verify.py --mode full` 已包含 browser Playwright tests。
- 已沉淀的 L1 / L3 测试覆盖了：
  - `fs` 的创建、读取、写入、移动、tree、上传、路径穿越
  - `sessions` 生命周期与消息级联删除
  - `chat` 的消息保存、citation、file references、stream、tool 错误分支
  - `wiki` 的页面 CRUD、tree、graph、health、policy、ingest、rebuild 以及冲突分支
  - `diary` 的 auto-draft
  - `pulse` 的 today 聚合

这意味着第一版已经不是“空方案”，而是可持续扩展的测试底座。

## 测试模型

DeepMemo 使用“沙漏型”测试模型。

### L1：API 合约测试

L1 是第一优先级。它保护系统边界，不绑定内部实现。

覆盖对象：

- 请求路径、请求体和查询参数
- 响应状态码
- 响应字段结构
- 安全边界，例如路径穿越
- 数据持久化的外部可见结果

L1 测试放在 `tests/api/`。

### L2：极简纯函数测试

L2 只测试稳定、纯粹、低变动的函数。它不覆盖复杂业务编排。

适合测试：

- 路径归一化
- frontmatter 解析
- Markdown 页面解析
- 图片路径生成
- wiki 图谱/合并里的稳定算法

不优先测试：

- LLM 业务编排
- wiki ingest 的中间状态
- chat 的内部上下文组装细节
- 未来经常被 agent 重构的业务控制流

L2 测试放在 `tests/unit/`。

### L3：Agentic E2E 场景测试

L3 保护真实用户闭环。每个场景先用自然语言写入 `tests/e2e/scenarios.yaml`，再用可执行测试实现。

第一版已经完成后端 `TestClient` 链路；前端浏览器 E2E 已进入 Playwright 阶段。

L3 测试放在 `tests/e2e/`。

## 第一版实施范围

第一版不追求一次覆盖全部 endpoint，而是先建立能持续扩展的闭环：

1. 引入 `pytest`。
2. 新建 `tests/` 分层目录。
3. 迁移现有有效测试。
4. 建立共享 fixture：
   - 临时 `data/` 目录
   - 临时 SQLite DB
   - FastAPI TestClient
   - mock LLM answer
5. 补第一批高价值 API 合约测试：
   - root health
   - static assets mount
   - session lifecycle
   - citations
   - file references path normalization
   - fs create/read/write/move/tree/upload
   - fs path traversal blocked
6. 建立自然语言场景库。
7. 增加统一验证命令。
8. 更新 agent 测试规则。

## 第一版不做的事

以下内容进入后续迭代：

- 35 个 endpoint 的完整覆盖。
- Playwright 浏览器 E2E。
- GitHub Actions CI。
- 真实 LLM 调用测试。
- 大量内部业务流程单测。

## 文件结构

第一版落地后的目标结构：

```text
tests/
├── __init__.py
├── conftest.py
├── api/
│   ├── __init__.py
│   ├── test_app.py
│   ├── test_fs.py
│   ├── test_sessions.py
│   ├── test_chat_references.py
│   └── test_citations.py
├── unit/
│   ├── __init__.py
│   ├── test_asset_manager.py
│   ├── test_fs_manager.py
│   └── test_wiki_pipeline.py
└── e2e/
    ├── __init__.py
    ├── scenarios.yaml
    └── test_scenarios.py
```

统一验证入口：

```text
scripts/verify.py
```

支持：

```bash
uv run python scripts/verify.py --mode quick
uv run python scripts/verify.py --mode full
```

## 验证策略

`quick` 每次改代码后必须跑：

1. `uv run pytest tests -q --tb=short -m "not e2e"`
2. `npm run build`，工作目录为 `app/`

`full` 在较大改动或提交前跑：

1. `uv run pytest tests -q --tb=short`
2. `npm run build`，工作目录为 `app/`

## Agent 执行规则

每次 agent 修改 `src/`、`app/src/`、`tests/` 或测试相关配置后：

1. 必须运行 `uv run python scripts/verify.py --mode quick`。
2. 如果新增 API，必须补 `tests/api/` 合约测试。
3. 如果新增用户闭环，必须先写 `tests/e2e/scenarios.yaml` 场景，再实现测试。
4. 如果修复 bug，必须把 bug 固化为回归测试。
5. 测试失败时，默认假设实现发生了回归；不得为了通过而削弱测试断言，除非这是明确的需求变更。

## 后续路线

### 第二版

- 覆盖 `/wiki/*` 主要 API。
- 覆盖 `/api/diary/auto-draft` 和 `/api/pulse/today`。
- 将更多踩过坑的场景加入 `scenarios.yaml`。

### 第三版

- 引入 Playwright，并把浏览器闭环沉淀为仓库内测试代码。
- 代码位置：
  - `app/tests/browser/`
  - `scripts/run_browser_tests.py`
- MCP / 浏览器交互工具只用于探索页面结构、调试 selector、确认流程，不作为最终回归资产。
- 当前已落地的浏览器 smoke flow：
  - 打开应用
  - 文件树加载
  - 切换编辑器 / Wiki 模式
- 后续继续扩展到真实前端闭环：
  - 创建/编辑/保存 Markdown
  - 图片上传
  - 问答引用展示
- 浏览器测试已接入 `scripts/verify.py --mode full`，成为可重复执行的回归资产，而不是临时脚本。

### 第四版

- 根据项目发布节奏决定是否接 GitHub Actions。
