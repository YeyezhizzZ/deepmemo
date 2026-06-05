# AI HOT 数据获取实现方案

## 目标

定时获取 AI HOT 每日精选资讯，数据落地到 `data/raw/daily/`。

---

## API 文档

**Base URL:** `https://aihot.virxact.com`

**必须带 User-Agent**，默认 curl UA 会被 403。

```bash
export UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
```

### 端点概览

| Endpoint | 说明 |
|----------|------|
| `GET /api/public/items` | 全部 AI 动态（精选/全部/分类/时间/搜索） |
| `GET /api/public/daily` | 最新 AI HOT 日报 |
| `GET /api/public/daily/{YYYY-MM-DD}` | 指定日期日报 |
| `GET /api/public/dailies` | 日报归档列表 |

### GET /api/public/items

查询参数：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `mode` | `"selected"` \| `"all"` | `"selected"` | selected=精选，all=全部 |
| `category` | 5类之一 | 无 | `ai-models` / `ai-products` / `industry` / `paper` / `tip` |
| `since` | ISO datetime | 无 | ISO 8601（如 `2026-05-01T00:00:00Z`），早于7天自动截断 |
| `take` | integer 1-100 | 50 | 每页条数 |
| `cursor` | opaque string | 无 | 分页 token，原样回传 |
| `q` | string | 无 | 关键词搜索 |

响应：

```json
{
  "count": 2,
  "hasNext": true,
  "nextCursor": "eyJhIjoxNzE0OTk1MjAwMDAwLCJpIjoiY205eHl6MTIzIn0",
  "items": [
    {
      "id": "cm9abc456def789ghi012jkl3",
      "title": "Anthropic 发布 Claude Opus 4.7",
      "title_en": "Anthropic Releases Claude Opus 4.7",
      "url": "https://www.anthropic.com/news/claude-opus-4-7",
      "source": "Anthropic Blog",
      "publishedAt": "2026-05-07T15:30:00.000Z",
      "summary": "...",
      "category": "ai-models"
    }
  ]
}
```

字段可为 null：`title_en` / `summary` / `publishedAt` / `category`

category 取值：`ai-models` / `ai-products` / `industry` / `paper` / `tip` / null

### GET /api/public/daily

最新日报，每日北京时间 08:00 生成。

响应：

```json
{
  "date": "2026-05-07",
  "generatedAt": "2026-05-07T00:05:00.000Z",
  "windowStart": "2026-05-06T00:00:00.000Z",
  "windowEnd": "2026-05-07T00:00:00.000Z",
  "lead": {
    "title": "主标题",
    "leadParagraph": "摘要..."
  },
  "sections": [
    { "label": "模型发布/更新", "items": [...] },
    { "label": "产品发布/更新", "items": [...] },
    { "label": "行业动态", "items": [...] },
    { "label": "论文研究", "items": [...] },
    { "label": "技巧与观点", "items": [...] }
  ],
  "flashes": [...]
}
```

### GET /api/public/daily/{YYYY-MM-DD}

指定日期日报，404 当日无报。

### GET /api/public/dailies

日报索引 discovery。

| 参数 | 默认 | 说明 |
|------|------|------|
| `take` | 30 | 最大 180 |

### ETag 缓存

items API 支持弱 ETag，适合 cron 轮询：

```bash
# 第一次请求
curl -H "User-Agent: $UA" -D - -o body.json \
  'https://aihot.virxact.com/api/public/items?mode=selected&take=5'
# 拿到 ETag 后下次带上
curl -H "User-Agent: $UA" -H 'If-None-Match: W/"items-d0112022d1961325"' \
  -D - -o /dev/null 'https://aihot.virxact.com/api/public/items?mode=selected&take=5'
# → 304 表示无新内容
```

### 注意事项

- `cursor` 是不透明 token，原样回传，不要解析或递增
- `since` 必须是 ISO 8601（`2026-05-01T00:00:00Z`），不是时间戳
- `take` 上限 100，想要更多需翻页
- 时间窗口仅 7 天，更早的走 `/daily` 或 `/dailies`
- `category` 不可多选
- 限流 600r/m/IP，超限 429

---

## 数据目录

```
data/raw/
└── daily/
    └── MMD.md        # 月日命名，如 57.md（省略每位前置0）
```

日报 JSON 只作为同步过程中的临时文件：先落地到 `data/raw/daily/{YYYY-MM-DD}.json`，本地 Python 渲染出 `MMD.md` 后立即删除。

这里的 `raw/daily` 就是 DeepMemo 的每日 AI 新闻原始层。它不再挂在 `ai_hot/` 下面，避免多一层语义包装。

## 获取逻辑 `src/ai/ai_hot_agent.py`

### 核心功能

1. **获取最新日报** `fetch_daily()`
   - 调用 `GET /api/public/daily`
   - 写入临时文件 `data/raw/daily/{YYYY-MM-DD}.json`

2. **渲染 Markdown** `render_daily_markdown(json_path)`
   - 读取本地日报 JSON
   - 写入 `data/raw/daily/MMD.md`

3. **日常同步** `sync_daily()` / CLI `sync`
   - 拉取日报 JSON
   - 本地渲染 Markdown
   - 渲染成功后删除日报 JSON

### 字段映射

```python
DAILY_FIELDS = [
    "date", "generatedAt", "windowStart", "windowEnd",
    "lead", "sections", "flashes"
]
```

### User-Agent 配置

```python
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
```

## 调度方案

### 服务器 Cron 定时

由全天运行的服务器负责每日同步。服务器目录与本地 DeepMemo 目录共享，因此服务器生成 `data/raw/daily/MMD.md` 后，本地电脑会通过共享目录自动看到 Markdown 文件。

本地电脑不运行 cron，避免本地和服务器同时写同一个 Markdown 文件。

#### 服务器部署步骤

1. 确认服务器上的共享目录里有完整 DeepMemo 项目：

```sh
cd /path/to/DeepMemo
ls src/ai/ai_hot_agent.py
```

2. 确认服务器安装 `uv`，并初始化 Python 环境：

```sh
which uv
cd /path/to/DeepMemo
uv sync
```

3. 在服务器手动跑通一次同步：

```sh
cd /path/to/DeepMemo
uv run python src/ai/ai_hot_agent.py sync
```

成功输出类似：

```json
{
  "date": "2026-05-08",
  "jsonPath": "data/raw/daily/2026-05-08.json",
  "markdownPath": "data/raw/daily/58.md",
  "deletedJson": true
}
```

此时服务器目录应只保留 Markdown：

```sh
find data/raw -maxdepth 3 -type f | sort
```

预期：

```text
data/raw/daily/58.md
```

4. 配置服务器 crontab。

如果服务器时区是北京时间：

```cron
10 8 * * * cd /path/to/DeepMemo && /path/to/uv run python src/ai/ai_hot_agent.py sync >> /path/to/DeepMemo/ai_hot_cron.log 2>&1
```

如果服务器时区是 UTC，北京时间 08:10 等于 UTC 00:10：

```cron
10 0 * * * cd /path/to/DeepMemo && /path/to/uv run python src/ai/ai_hot_agent.py sync >> /path/to/DeepMemo/ai_hot_cron.log 2>&1
```

其中 `/path/to/uv` 用服务器上 `which uv` 的输出替换，不建议在 cron 中直接写 `uv`，避免 cron 环境变量缺失。

#### 验证与排错

查看 cron 是否配置成功：

```sh
crontab -l
```

查看同步日志：

```sh
tail -100 /path/to/DeepMemo/ai_hot_cron.log
```

常见问题：

- 服务器没网或 AI HOT API 异常：日志里会出现请求失败。
- cron 找不到 `uv`：把 cron 中的 `uv` 改成 `which uv` 输出的绝对路径。
- 服务器时区不是北京时间：使用 UTC 版本 cron，或先用 `date` 确认服务器当前时区。
- 共享目录同步延迟：服务器已生成 Markdown，但本地稍后才出现，属于同步服务本身的延迟。

---

## 依赖

- 使用 Python 标准库 `urllib` / `json` / `datetime` / `pathlib`

## 进度

- [x] 确定调度方案：每日北京时间 08:10 cron
- [x] 实现 `src/ai/ai_hot_agent.py`
- [x] 初始化数据目录
- [x] 测试 fetch_daily
- [x] 实现 JSON -> Markdown 渲染
- [x] 同步成功后删除日报 JSON
- [x] 删除本地电脑 cron，避免重复同步
- [x] 在服务器配置 cron 定时任务
