# 项目结构

```text
DeepMemo/
├── app/                 # React + Vite frontend
├── config/              # LLM, web search, wiki prompt and source configs
├── data/                # local knowledge base
├── docs/                # specs, archive and this VitePress wiki
├── scripts/             # verification and helper scripts
├── src/                 # FastAPI backend and AI/wiki modules
├── tests/               # pytest API/unit/e2e tests
├── data.db              # default SQLite metadata database
└── pyproject.toml       # Python project definition
```

## `app/`

前端工作模式：

- Editor：文件树、Vditor 所见即所得编辑器、保存和 assets 上传。
- QA：会话列表、聊天输入、SSE 流式回答、引用跳转。
- Wiki：社区图谱、节点详情、Wiki 页面搜索、重建按钮。

重要文件：

| Path | Description |
|:---|:---|
| `app/src/App.tsx` | 主界面和工作流 |
| `app/src/api.ts` | 前端 API client |
| `app/src/types.ts` | 前端类型 |
| `app/vite.config.ts` | Vite 代理配置 |
| `app/tests/browser/` | Playwright 测试 |

## `src/`

| Path | Description |
|:---|:---|
| `src/app/main.py` | FastAPI app、routers、startup/shutdown |
| `src/app/database.py` | SQLite 初始化 |
| `src/app/core/` | 文件、assets、watcher 等核心服务 |
| `src/routers/` | FS、chat、wiki、pulse、citations 等路由 |
| `src/ai/` | RAG、query routing、local/web search、answer composer |
| `src/models/` | Pydantic schemas |
| `src/wiki/` | Wiki ingest、graph、health、frontmatter、storage |

## `data/`

| Path | Description |
|:---|:---|
| `data/diary/` | 日记 |
| `data/ideas/` | 想法 |
| `data/memory/` | 长期记忆 |
| `data/raw/` | 原始抓取或输入材料 |
| `data/mock/` | 公开 demo 数据 |
| `data/policy/` | Wiki 策略包 |
| `data/assets/` | 上传图片 |
| `data/wiki/` | 生成的 Wiki 页面 |

## `docs/`

| Path | Description |
|:---|:---|
| `docs/specs/current/` | Human-reviewed baseline specs |
| `docs/specs/goals/` | Goal specs |
| `docs/specs/deprecated.md` | D 类废弃行为 |
| `docs/archive/` | 历史材料，不是设计权威 |
| `docs/.vitepress/` | 项目 wiki 站点配置 |
| `docs/guide/`, `docs/how-to/`, `docs/reference/`, `docs/explanation/` | Diátaxis 文档内容 |
