# DeepMemo 自迭代知识引擎 v1 设计文档

> **状态**: Implemented as Knowledge Engine v1 / Future gaps tracked in `docs/specs/proposed/knowledge-engine-v2-roadmap.md`
> **创建**: 2026-06-20
> **参考**: Qoder 知识引擎 2.0 "编译式知识" 理念

---

## 〇、设计决策记录

| # | 决策项 | 结论 | 理由 |
|---|--------|------|------|
| D-1 | Card 存储格式 | **YAML** | Agent 检索友好、结构化原生、按字段增量更新 |
| D-2 | Phase 1 与现有 Wiki 的关系 | **直接改写** | 现有 Wiki 方案粗糙，不做并行直接替换 |
| D-3 | 对话知识提取触发时机 | **方案 C：两者兼有** | Session 关闭时触发 + 每 N 轮自动触发，兼顾显式控制与自动沉淀 |
| D-4 | 是否引入轻量向量检索 | **v1 不引入，v2 再加** | 优先保证交付速度，BM25 + Tag 索引在个人规模够用 |
| D-5 | 实施优先级 | 按 Phase 1→2→3→4 顺序执行 | 先建 Card 基础 → 检索集成 → 飞轮 → 前端 |

---

## 一、项目背景

### 1.1 核心理念

Andrej Karpathy 的 LLM Wiki 理念指出：人类维护 Wiki 的"记账成本"增长快于知识价值，但 LLM 的维护成本趋近于零。由此产生新范式——**编译式知识**：把知识"编译"一次，然后持续复用和增长。

Qoder 知识引擎 2.0 在软件工程领域落地了这一理念，其核心创新：
- **两步凝练**（Knowledge Card + RepoWiki 分层）
- **双轮自迭代**（代码侧 + 对话侧）
- **人机共建**（人可编辑 AI 生成的知识）

本文档将这套思路适配到 DeepMemo 的**个人知识管理**场景。当前已落地的是 v1 Knowledge Card 真值层；RepoWiki、commit 飞轮、团队共享和企业治理不属于 v1 已实现范围。

### 1.2 DeepMemo 已有基础

| 层 | 现状 | 评价 |
|---|---|---|
| 原始信号层 | `data/diary/` 111 篇日记 + `data/raw/` 博客抓取 | ✅ 完整 |
| 知识编译层 | `src/wiki/` 两阶段 LLM Ingest → 262+ Wiki 页面 | ⚠️ 粗糙，一步到位，人机混用 |
| 知识图谱层 | `src/wiki/graph.py` Louvain 社区发现 | ✅ 可复用 |
| 检索层 | `src/ai/local_search_agent.py` ripgrep 全文检索 | ⚠️ 无结构化快速通道 |
| 问答层 | QueryRewriter → QueryRouter → LocalSearch → AnswerComposer | ✅ 可扩展 |
| 记忆层 | agent-memory / user-memory (Markdown, <3KB) | ⚠️ 孤立，不与 Wiki 联动 |
| 变更感知 | watchdog 文件监控 → file_meta dirty 标记 | ✅ 可复用 |

### 1.3 要解决的核心问题

1. **单层产物**：现有 Wiki 页面同时服务人和 Agent，两者需求冲突
2. **手动触发**：Wiki 重建需要显式调用 `/wiki/rebuild`，不自动
3. **对话不沉淀**：Chat 历史只存 SQLite，知识不回流
4. **检索粗放**：ripgrep 全文匹配，无结构化索引加速
5. **记忆割裂**：agent-memory / user-memory 与 Wiki 系统各自为政

---

## 二、总体架构

### 2.1 "看山三境" 两步凝练

```
原始信号（Diary + Raw + Chat）
  ↓ 第一步凝练（LLM 提取 + 结构化）
Knowledge Card (YAML)  ← 给 Agent 用：高密度、单一职责、可索引
  ↓ 第二步凝练（LLM 合成 + 叙事组织）
RepoWiki (Markdown)    ← 给人看：连贯叙事、知识地图、可浏览
```

### 2.2 架构全景

```
┌─────────────────────────────────────────────────────────────┐
│                     人机共建接口 (Layer 6)                    │
│  前端 Card 浏览/编辑 · /knowledge 命令 · 健康面板            │
├─────────────────────────────────────────────────────────────┤
│                   自迭代飞轮 (Layer 5)                        │
│  飞轮1: Watchdog 文件变更 → Card 增量编译                    │
│  飞轮2: Chat 对话完成 → 知识提取 → Card 更新                 │
│  飞轮3: 定时维护 → 衰减评分 · 孤儿检测 · 矛盾标注           │
├─────────────────────────────────────────────────────────────┤
│                   检索增强层 (Layer 4)                        │
│  Card 索引检索(Tag+BM25) → ripgrep 兜底 → Evidence 组装     │
├─────────────────────────────────────────────────────────────┤
│                  RepoWiki 合成层 (Layer 3)                    │
│  Knowledge Cards → LLM 叙事合成 → data/wiki/ Markdown       │
├─────────────────────────────────────────────────────────────┤
│               Knowledge Card 编译层 (Layer 2)                │
│  原始信号 → LLM 提取 → 去重合并 → data/knowledge/cards/     │
├─────────────────────────────────────────────────────────────┤
│                   原始信号层 (Layer 1)                        │
│  data/diary/ · data/raw/ · Chat Sessions · (未来: Git)      │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、数据模型

### 3.1 Knowledge Card (YAML)

存储路径：`data/knowledge/cards/{slug}.yaml`

```yaml
# ─── 标识 ───
id: "kc-a1b2c3d4"
slug: "louvain-community-detection"
title: "Louvain 社区发现算法"
type: concept          # entity | concept | decision | pattern | lesson
density: high          # high | medium | low

# ─── 核心内容（高密度，给 Agent 检索用）───
definition: "基于模块度优化的层次聚类算法，用于大规模网络的社区划分"
key_facts:
  - "时间复杂度 O(n log n)，适合大规模图"
  - "DeepMemo 中用于 wiki/graph.py 的知识节点聚类"
  - "边权重模型：Direct Link 3.0 + Source Overlap 4.0 + Adamic-Adar 1.5"

# ─── 溯源（知识有出处，区别于 RAG）───
sources:
  - path: "diary/0314.md"
    evidence: "Louvain 算法在 graph.py 中用于社区发现"
    confidence: 0.9
  - path: "conversations/sess-xyz.md"
    evidence: "用户确认选择 Louvain 的原因是模块度可解释性"
    confidence: 0.95

# ─── 关联 ───
related_cards:
  - "knowledge-graph"
  - "wiki-generation"
tags:
  - "algorithm"
  - "graph"
  - "wiki-infrastructure"
aliases:
  - "Louvain"
  - "社区发现"

# ─── 元数据 ───
created_at: "2026-06-20"
updated_at: "2026-06-20"
update_count: 3
staleness_score: 0.1      # 0=刚更新, 1=严重过时
human_edited: false        # 人工编辑过的字段不会被自动覆盖
human_edited_fields: []    # 记录哪些字段被人工编辑
```

### 3.2 Card 类型体系

| 类型 | 定义 | 来源 | 示例 |
|------|------|------|------|
| **entity** | 具体的人、工具、项目、产品 | Diary, Raw | Karpathy, Claude Code, GraphRAG |
| **concept** | 方法、理论、模式、框架 | Diary, Raw | RAG, Prompt Engineering, Knowledge Compilation |
| **decision** | 设计选择、架构决定、取舍理由 | Chat, Diary | "选 Louvain 而非 PageRank 的原因" |
| **pattern** | 反复出现的问题解法 | Chat, Diary | "ripgrep 检索 + LLM 兜底的模式" |
| **lesson** | 踩坑记录、经验教训、纠正 | Chat, Diary | "frontmatter 嵌套引号导致解析失败" |

### 3.3 Card 索引

存储路径：`data/knowledge/index.json`

```json
{
  "version": 1,
  "cards": {
    "louvain-community-detection": {
      "title": "Louvain 社区发现算法",
      "type": "concept",
      "tags": ["algorithm", "graph"],
      "key_terms": ["louvain", "社区发现", "模块度", "聚类"],
      "related": ["knowledge-graph", "wiki-generation"],
      "staleness": 0.1,
      "source_count": 2,
      "human_edited": false
    }
  },
  "tag_index": {
    "algorithm": ["louvain-community-detection"],
    "graph": ["louvain-community-detection", "knowledge-graph"]
  },
  "type_index": {
    "concept": ["louvain-community-detection", "knowledge-graph"],
    "entity": ["karpathy", "claude-code"]
  },
  "stats": {
    "total_cards": 0,
    "by_type": {},
    "avg_staleness": 0.0,
    "last_compile": null
  },
  "updated_at": "2026-06-20T00:00:00"
}
```

### 3.4 编译缓存

存储路径：`data/knowledge/.compile-cache.json`

```json
{
  "version": 1,
  "entries": {
    "diary/0620.md": {
      "hash": "md5-hex",
      "last_compiled": "2026-06-20T00:00:00",
      "card_slugs": ["louvain-community-detection", "deepmemo-architecture"]
    }
  }
}
```

---

## 四、模块设计

### 4.1 目录结构变更

```
src/
├── ai/                    # 不变
├── app/                   # 不变
├── knowledge/             # 【新增】知识引擎核心
│   ├── __init__.py
│   ├── models.py          # KnowledgeCard, CardIndex 数据模型
│   ├── card_compiler.py   # Card 编译器（Diary/Raw → Card）
│   ├── card_store.py      # Card YAML 存储 + JSON 索引维护
│   ├── retriever.py       # 结构化检索（Tag + BM25 + Card 索引）
│   ├── conversation_memory.py  # 对话知识提取
│   └── maintenance.py     # 定期维护（衰减、孤儿、矛盾）
├── routers/
│   ├── knowledge.py       # 【新增】Knowledge Card API
│   └── ...                # 现有 router 不变
├── wiki/                  # 【改写】Card → Wiki 合成
│   ├── ingest_pipeline.py # 改写：输入从 Diary 变为 Card
│   ├── ingest_analyzer.py # 改写：分析逻辑迁入 card_compiler
│   └── ...                # 其他模块按需调整
├── models/
└── services/

data/
├── diary/                 # 不变
├── raw/                   # 不变
├── knowledge/             # 【新增】
│   ├── cards/             # YAML Knowledge Cards
│   ├── index.json         # 全量索引
│   └── .compile-cache.json
├── wiki/                  # 保留，内容改由 Card 驱动生成
├── memory/                # 不变
└── policy/                # 不变
```

### 4.2 Layer 2：Knowledge Card 编译器

#### `src/knowledge/models.py`

```python
@dataclass
class EvidenceSource:
    path: str               # 原始文件路径
    evidence: str           # 摘录的证据文本
    confidence: float       # 置信度 0.0-1.0

@dataclass
class KnowledgeCard:
    id: str
    slug: str
    title: str
    type: str               # entity | concept | decision | pattern | lesson
    density: str            # high | medium | low
    definition: str
    key_facts: list[str]
    sources: list[EvidenceSource]
    related_cards: list[str]
    tags: list[str]
    aliases: list[str]
    created_at: str
    updated_at: str
    update_count: int
    staleness_score: float
    human_edited: bool
    human_edited_fields: list[str]
```

#### `src/knowledge/card_compiler.py`

```python
class KnowledgeCardCompiler:
    """
    将原始信号编译为 Knowledge Card。

    核心流程：
    1. 读取原始信号（Diary / Raw / Conversation）
    2. LLM 提取知识点 → 初步 Card 列表
    3. 与已有 Card 做合并 & 去重（slug 匹配 + 语义判断）
    4. 写入/更新 data/knowledge/cards/{slug}.yaml
    5. 更新 index.json

    增量策略：
    - MD5 哈希缓存，只编译变更的文件
    - 防抖机制：5 分钟内多次变更合并为一次编译
    """

    def compile_all(self) -> CompileResult:
        """全量编译所有 Diary + Raw"""

    def compile_file(self, path: Path) -> list[KnowledgeCard]:
        """增量编译单个文件"""

    def compile_conversation(self, session_id: str, messages: list[dict]) -> list[KnowledgeCard]:
        """从对话中提取 Card"""

    def _extract_via_llm(self, content: str, source_path: str) -> list[KnowledgeCard]:
        """LLM 提取知识点"""

    def _extract_heuristic(self, content: str, source_path: str) -> list[KnowledgeCard]:
        """无 LLM 时的启发式 fallback"""

    def _merge_with_existing(self, new_card: KnowledgeCard, existing: KnowledgeCard) -> KnowledgeCard:
        """
        合并策略：
        - human_edited_fields 中的字段不覆盖
        - evidence (sources) 追加而非替换
        - key_facts 去重后追加
        - tags / aliases 取并集
        - update_count + 1
        """
```

#### LLM Prompt 设计（Card 提取）

```
你是知识编译器。从以下原始文本中提取结构化的知识卡片。

每张卡片必须是独立的、可检索的知识单元。

提取规则：
1. 一个概念/实体/决策 = 一张卡
2. definition 用一句话说清楚
3. key_facts 不超过 5 条，每条一行
4. confidence 基于证据强度评分
5. 不要生成空泛无信息量的卡片

输出 JSON 格式：
[{
  "slug": "kebab-case-name",
  "title": "标题",
  "type": "concept|entity|decision|pattern|lesson",
  "definition": "一句话定义",
  "key_facts": ["事实1", "事实2"],
  "tags": ["标签1"],
  "aliases": ["别名1"],
  "confidence": 0.8
}]
```

### 4.3 Layer 3：RepoWiki 合成（改写现有 Wiki）

**直接改写** `src/wiki/ingest_pipeline.py`，将输入源从 Diary 切换为 Knowledge Card。

#### 改写前 vs 改写后

```
改写前：
  Diary → LLM Analysis → (entity/concept/synthesis 提取) → Wiki Markdown

改写后：
  Knowledge Cards → LLM Synthesis → (叙事组织 + 交叉引用) → Wiki Markdown
```

#### 改写要点

1. **`ingest_analyzer.py` 的分析逻辑**迁入 `card_compiler.py`——不再由 Wiki 模块负责知识提取
2. **`ingest_pipeline.py` 的生成逻辑**改为读取 `data/knowledge/cards/*.yaml`，按 type 分组，LLM 合成连贯 Wiki 页面
3. **`ingest_writer.py`** 保留——输出格式不变，仍然是带 frontmatter 的 Markdown
4. **`graph.py`** 保留——Louvain 社区发现的输入改为读取 Card 的 `related_cards` 关系
5. **`health.py`** 增强——新增 Card 层面的健康指标（staleness 分布、孤儿 Card、矛盾检测）
6. **`merger.py`** 简化——合并逻辑上移到 Card 层面，Wiki 层只做页面组织

#### Wiki 页面与 Card 的映射关系

| Wiki 页面类型 | 内容来源 |
|---|---|
| `entities/{slug}.md` | 聚合 type=entity 的 Card |
| `concepts/{slug}.md` | 聚合 type=concept 的 Card |
| `syntheses/{slug}.md` | 聚合多个相关 Card 的跨源综合 |
| `sources/{date}.md` | 保留，从 Diary 直接生成摘要页（不经 Card） |
| `index.md` | 从 Card Index 自动生成 |

### 4.4 Layer 4：检索增强

#### `src/knowledge/retriever.py`

```python
class KnowledgeRetriever:
    """
    分层检索策略（v1 不用向量，纯索引 + BM25 + ripgrep）：

    1. Card 索引精确命中（Tag、Type、Slug 匹配）
    2. Card key_facts BM25 关键词匹配
    3. 命中 Card 后展开 sources（追溯原始证据）
    4. 未命中时 fallback 到 ripgrep（现有 LocalSearchAgent）
    """

    def search(self, query: str) -> list[Evidence]:
        # Phase 1: Card 索引检索
        card_hits = self._search_card_index(query)

        if card_hits:
            # Phase 2: 展开 Card 的 evidence 为检索结果
            evidence = self._expand_card_evidence(card_hits)
            return evidence

        # Phase 3: Fallback 到 ripgrep
        return self._ripgrep_fallback(query)

    def _search_card_index(self, query: str) -> list[KnowledgeCard]:
        """
        索引检索（v1 实现）：
        1. 从 index.json 加载索引
        2. query 分词 → tag_index 精确匹配
        3. query → Card title/slug 模糊匹配
        4. query 关键词 → key_facts 逐条 BM25 评分
        5. 按综合得分排序返回 top-K
        """

    def _expand_card_evidence(self, cards: list[KnowledgeCard]) -> list[Evidence]:
        """
        从 Card 构造 Evidence：
        - Card.definition → 作为高置信度 Evidence
        - Card.key_facts → 逐条作为 Evidence
        - Card.sources → 追溯原始文件片段
        """
```

#### 接入 RAG Pipeline

改造 `src/ai/local_search_agent.py`：

```python
# 在 LocalSearchAgent.search() 开头插入 Card 检索
def search(self, question: str, route: RouteDecision | None = None) -> LocalSearchResult:
    # 【新增】先走 Card 结构化检索
    card_evidence = self.knowledge_retriever.search(question)
    if card_evidence:
        return LocalSearchResult(
            question=question,
            evidence=card_evidence,
            searched_queries=[question],
            searched_paths=["knowledge/cards"],
            truncated=False,
            message=None,
        )

    # 原有 ripgrep 逻辑不变
    route = route or self.router.route(question)
    ...
```

### 4.5 Layer 5：自迭代飞轮

#### 飞轮 1：文件变更 → Card 增量编译

扩展 `src/app/core/watcher.py`：

```python
async def on_file_changed(file_path: str):
    # 现有：标记 dirty
    mark_dirty(file_path)

    # 【新增】如果是 diary 或 raw 文件，触发 Card 编译
    if is_knowledge_source(file_path):
        # 防抖：5 分钟内多次变更合并
        await debounced_card_compile(file_path, delay_seconds=300)

async def debounced_card_compile(file_path: str, delay_seconds: int = 300):
    """
    防抖编译：
    1. 记录 pending 文件
    2. 等待 delay_seconds
    3. 如果期间无新变更，执行编译
    4. 如果有新变更，重置计时器
    """
```

#### 飞轮 2：Chat 对话 → 知识沉淀（方案 C：双模式触发）

##### 触发模式 A：Session 关闭时

```python
# src/routers/chat.py — Session 关闭回调
async def on_session_close(session_id: str):
    messages = load_session_messages(session_id)
    if len(messages) < 4:  # 太短的对话不提取
        return

    extractor = ConversationMemoryExtractor()
    insights = extractor.extract(session_id, messages)

    if insights:
        # 写入原始信号
        write_conversation_raw(session_id, insights)
        # 触发 Card 编译
        compiler = KnowledgeCardCompiler()
        compiler.compile_conversation(session_id, messages)
```

##### 触发模式 B：每 N 轮对话自动触发

```python
# src/routers/chat.py — 对话中间自动触发
EXTRACT_EVERY_N_TURNS = 10

async def on_message_received(session_id: str, message_count: int):
    if message_count > 0 and message_count % EXTRACT_EVERY_N_TURNS == 0:
        # 异步触发，不阻塞对话
        asyncio.create_task(
            extract_mid_conversation(session_id, recent_n=EXTRACT_EVERY_N_TURNS)
        )
```

#### `src/knowledge/conversation_memory.py`

```python
class ConversationMemoryExtractor:
    """
    从 Chat Session 中提取知识信号。

    识别模式：
    - 用户确认 ("对", "没错", "就是这样") → 确认的事实 → type: decision
    - 用户纠正 ("不对", "应该是", "其实") → 纠正信号 → type: lesson
    - 提问 + 采纳回答 ("为什么" + 后续无异议) → 决策理由 → type: decision
    - 反复问同类问题 → 知识缺口 → 不生成 Card，但标记 gap
    - 技术讨论中的结论 → type: pattern 或 concept

    过滤条件（不提取的情况）：
    - 闲聊（"你好", "谢谢"）
    - 纯命令式交互（"帮我格式化这段代码"）
    - 对话轮次 < 4
    """

    def extract(self, session_id: str, messages: list[dict]) -> list[ConversationInsight]:
        """提取知识信号"""

    def _classify_signal(self, context: list[dict]) -> str | None:
        """
        用 LLM 判断这段对话是否包含值得沉淀的知识。
        返回: "decision" | "lesson" | "pattern" | "concept" | None
        """

    def _generate_card_draft(self, signal_type: str, context: list[dict]) -> KnowledgeCard:
        """从对话上下文生成 Card 草稿"""
```

#### 飞轮 3：定期维护

```python
# src/knowledge/maintenance.py
class KnowledgeMaintainer:
    """
    定期健康维护（APScheduler cron: 每天 03:00 执行）

    任务清单：
    1. Staleness 评分更新
       - 基于 (today - updated_at).days / 30 计算
       - source 文件被修改的 Card，staleness 重置为 0

    2. 孤儿 Card 检测
       - sources 列表中的文件全部不存在 → 标记 orphan

    3. 矛盾检测
       - 同 tag 的 Card 之间 key_facts 存在语义冲突 → 标记 conflict
       - v1 用简单的关键词否定检测，v2 引入 LLM 判断

    4. 合并建议
       - title 或 aliases 高度相似的不同 Card → 建议合并
    """

    def run_maintenance(self) -> MaintenanceReport: ...
    def update_staleness_scores(self) -> None: ...
    def detect_orphans(self) -> list[str]: ...
    def detect_conflicts(self) -> list[tuple[str, str]]: ...
    def suggest_merges(self) -> list[tuple[str, str]]: ...
```

### 4.6 Layer 6：人机共建接口

#### `src/routers/knowledge.py` — API 设计

```python
# ─── Card CRUD ───
GET    /api/knowledge/cards                 # 列表，支持 ?type=&tag=&staleness_gt= 过滤
GET    /api/knowledge/cards/{slug}          # 详情
PUT    /api/knowledge/cards/{slug}          # 人工编辑（自动打 human_edited 标记）
DELETE /api/knowledge/cards/{slug}          # 删除

# ─── 编译与维护 ───
POST   /api/knowledge/compile              # 手动触发全量编译
POST   /api/knowledge/compile/file         # 增量编译指定文件，body: {path: "diary/0620.md"}
POST   /api/knowledge/maintain             # 手动触发维护
GET    /api/knowledge/health               # 健康报告

# ─── 检索 ───
POST   /api/knowledge/search               # 结构化知识检索，body: {query: "..."}

# ─── 统计 ───
GET    /api/knowledge/stats                 # 知识库统计（Card 数量、类型分布、staleness 分布）
```

#### 人工编辑保护机制

```python
async def update_card(slug: str, updates: dict):
    card = card_store.load(slug)

    for field, value in updates.items():
        setattr(card, field, value)
        # 记录哪些字段被人工编辑
        if field not in card.human_edited_fields:
            card.human_edited_fields.append(field)

    card.human_edited = True
    card.updated_at = now()
    card_store.save(card)
```

**保护规则**：当自动编译产生的新内容要更新一张 `human_edited=True` 的 Card 时：
- `human_edited_fields` 中列出的字段 → **跳过**，不覆盖
- `sources` 列表 → **追加**新 evidence，不删除已有的
- `tags` / `aliases` → **取并集**
- 其他未被人工编辑的字段 → 正常更新

---

## 五、实施路线

### Phase 1：Knowledge Card 基础 + Wiki 改写（2-3 周）

直接改写现有 Wiki 系统，建立 Card 编译能力。

| # | 任务 | 涉及文件 | 优先级 |
|---|------|---------|--------|
| 1.1 | 设计 KnowledgeCard 数据模型 | `src/knowledge/models.py` [NEW] | P0 |
| 1.2 | 实现 CardStore (YAML 读写 + JSON 索引) | `src/knowledge/card_store.py` [NEW] | P0 |
| 1.3 | 实现 CardCompiler (Diary → Card) | `src/knowledge/card_compiler.py` [NEW] | P0 |
| 1.4 | 从现有 `ingest_analyzer.py` 迁移 LLM 分析逻辑 | `src/wiki/ingest_analyzer.py` [MODIFY] | P0 |
| 1.5 | 改写 `ingest_pipeline.py`：Card → Wiki 合成 | `src/wiki/ingest_pipeline.py` [MODIFY] | P0 |
| 1.6 | 新增 Knowledge API Router | `src/routers/knowledge.py` [NEW] | P1 |
| 1.7 | 注册 Knowledge Router 到 FastAPI app | `src/app/main.py` [MODIFY] | P1 |
| 1.8 | 单元测试 + API 合约测试 | `tests/unit/test_knowledge_*.py` [NEW] | P0 |

**验收标准**：
- `POST /api/knowledge/compile` → `data/knowledge/cards/` 生成 YAML Card
- `POST /wiki/rebuild` → 从 Card 合成 Wiki 页面（替代原有流程）
- `uv run python scripts/verify.py` 全部通过

---

### Phase 2：检索增强 + Chat 知识沉淀（2 周）

| # | 任务 | 涉及文件 | 优先级 |
|---|------|---------|--------|
| 2.1 | 实现 KnowledgeRetriever | `src/knowledge/retriever.py` [NEW] | P0 |
| 2.2 | 改造 LocalSearchAgent：Card 检索优先 | `src/ai/local_search_agent.py` [MODIFY] | P0 |
| 2.3 | 实现 ConversationMemoryExtractor | `src/knowledge/conversation_memory.py` [NEW] | P0 |
| 2.4 | Chat Session 关闭时触发知识提取 | `src/routers/chat.py` [MODIFY] | P1 |
| 2.5 | 每 N 轮对话自动触发知识提取 | `src/routers/chat.py` [MODIFY] | P1 |
| 2.6 | 对话原始信号写入 `data/raw/conversations/` | `src/knowledge/conversation_memory.py` | P1 |
| 2.7 | 检索质量测试 | `tests/unit/test_retriever.py` [NEW] | P0 |

**验收标准**：
- Chat 对话结束后，`data/knowledge/cards/` 中出现从对话提取的 Card
- 问已有 Card 覆盖的问题时，Card 检索命中（不走 ripgrep）
- 每 10 轮对话自动触发一次中间提取

---

### Phase 3：自迭代飞轮（1-2 周）

| # | 任务 | 涉及文件 | 优先级 |
|---|------|---------|--------|
| 3.1 | 扩展 Watchdog：Diary 变更 → Card 增量编译 | `src/app/core/watcher.py` [MODIFY] | P0 |
| 3.2 | 实现防抖编译（5 分钟合并） | `src/knowledge/card_compiler.py` [MODIFY] | P0 |
| 3.3 | 实现 KnowledgeMaintainer | `src/knowledge/maintenance.py` [NEW] | P1 |
| 3.4 | APScheduler 定时任务注册 | `src/app/main.py` [MODIFY] | P1 |
| 3.5 | Card 变更 → Wiki 自动重合成 | `src/wiki/ingest_pipeline.py` [MODIFY] | P1 |
| 3.6 | 集成测试：模拟连续写日记 → 观察自动增长 | `tests/` [NEW] | P1 |

**验收标准**：
- 用户编辑 `diary/0621.md` → 5 分钟后 Card 自动更新 → Wiki 自动刷新
- 健康维护每天自动执行，输出 MaintenanceReport
- 全流程无需手动操作

---

### Phase 4：前端人机共建（2 周）

| # | 任务 | 涉及文件 | 优先级 |
|---|------|---------|--------|
| 4.1 | 前端 Knowledge Card 列表页 | `app/src/` [MODIFY] | P0 |
| 4.2 | 前端 Card 详情 + 编辑页 | `app/src/` [MODIFY] | P0 |
| 4.3 | 知识库健康面板 | `app/src/` [MODIFY] | P1 |
| 4.4 | Card staleness 热力图可视化 | `app/src/` [MODIFY] | P2 |
| 4.5 | 知识图谱升级（Card 关系网络） | `app/src/` [MODIFY] | P2 |
| 4.6 | Chat 中 `/knowledge` 命令支持 | `src/routers/chat.py` [MODIFY] | P2 |

**验收标准**：
- 前端可以浏览、搜索、编辑 Knowledge Card
- 人工编辑的 Card 在后续自动更新中不会被覆盖
- 健康面板展示 Card 统计、staleness 分布、孤儿/矛盾提示

---

## 六、与 Qoder 的差异化定位

| 维度 | Qoder 知识引擎 2.0 | DeepMemo 知识引擎 v1 |
|---|---|---|
| 场景 | 企业团队 + 代码仓库 | 个人开发者 + 知识笔记 |
| 知识来源 | Commit + PR + 对话 | Diary + 博客 + Chat |
| 部署 | Client-Server 分离 | 单机本地部署 |
| 协作 | 多人 + 版本锁 + 上传锁 | 单人 + 文件系统 |
| 存储 | 数据库 | 文件系统优先 (YAML + Markdown) |
| 检索 (v1) | 向量 + BM25 + 图谱 | Tag 索引 + BM25 + ripgrep |
| 检索 (v2 计划) | — | + sentence-transformers 本地向量 |
| LLM 成本 | 企业级 | 控制调用 + heuristic fallback |
| Card 格式 | 不明 | YAML（结构化原生） |
| Wiki 格式 | 不明 | Markdown + frontmatter（保持现有） |

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| LLM 提取质量不稳定 | Card 内容有噪声 | 保留 heuristic fallback + staleness 衰减自动清理 |
| YAML 文件数量爆炸 | 文件系统性能 | <10K Card 级别无压力；index.json 做内存索引 |
| Card → Wiki 合成断开 | Wiki 内容过时 | 飞轮 1 保证 Card 更新自动触发 Wiki 重合成 |
| 对话提取误判 | 无用 Card 堆积 | 过滤条件严格 + maintenance 定期清理低价值 Card |
| 改写 Wiki 影响现有功能 | 回归 bug | Phase 1 先跑通测试再上线；保持 Wiki API 接口不变 |
| 防抖机制时间窗口 | 用户连续编辑时延迟感知 | 5 分钟可配置；手动 compile 不受防抖限制 |

---

## 附录 A：LLM Token 成本估算

| 操作 | 频率 | 输入 tokens | 输出 tokens | 单次成本 (GPT-4o-mini) |
|---|---|---|---|---|
| Diary Card 编译 | 每天 1-3 次 | ~2000 | ~500 | ~$0.001 |
| Chat 知识提取 | 每天 2-5 次 | ~1500 | ~300 | ~$0.0006 |
| Wiki 合成 | 每天 0-1 次 | ~5000 | ~2000 | ~$0.003 |
| 维护检查 | 每天 1 次 | ~3000 | ~500 | ~$0.001 |
| **日均合计** | — | — | — | **~$0.01-0.02** |

个人使用场景下，月成本 < $1，完全可控。

---

## 附录 B：与现有 Spec 的关系

| 现有 Spec | 影响 | 操作 |
|---|---|---|
| `wiki-ingestion.md` | 流程改写：输入从 Diary 变为 Card | 实施后需更新 |
| `wiki-graph.md` | 输入改为读取 Card 关系 | 实施后需更新 |
| `ai-chat-rag.md` | 检索链路新增 Card 层 | 实施后需更新 |
| `fs-watcher.md` | 增加 Card 编译触发 | 实施后需更新 |
| `query-routing.md` | 不变 | 无需操作 |
| `constitution.md` | 不变 | 无需操作 |
