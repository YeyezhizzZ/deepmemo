# Wiki 设计优化：阶段性思考记录

> 写这份文件的目的：因为对话额度有限，把每一轮的深度分析过程持久化下来，防止断点后丢失上下文。后续可以直接读这个文件恢复思路。

---

## 一、当前状态快照 (2026-05-26)

### 1.1 data/wiki/ 目录已被删除
- 上次会话（05-24）虽然重构了 `merger.py`、`link_resolver.py`、`graph.py` 等模块代码
- 但 `data/wiki/` 目录目前不存在，说明用户可能手动清空了旧 wiki 或从未跑过新 Rebuild
- 这意味着所有代码改进还未经过真实全量编译验证
- **下一步必须先跑一次 Rebuild 并观察输出质量**

### 1.2 日记数据概况
- 85 篇日记，`0301.md` ~ `0524.md`，总计约 1900 行
- 大文件集中在 4-5 月（0410=12K, 0417=15K, 0501=15K, 0511=12K, 0513=13K, 0522=17K）
- 常见 section: `科研` (41篇), `工程博客` (31篇), `开发经验` (13篇), `others` (38篇)
- 高频跨日记概念: Agent(58篇), Memory(38篇), Skill(35篇), RAG(24篇), Wiki/知识库(20篇)

### 1.3 之前的 wiki 输出质量（05-24 诊断）
- 111 concepts, 53 entities, 1 synthesis, 60 sources = 225 total pages
- **每个页面只有 1 个 source** → source_overlap 权重（最高 4.0）全部失灵
- **23% wikilinks 悬空** → direct_link 大量丢失
- **大量近义概念未合并** → agentic-query-rewriting vs agentic-rewrites, 6+ skill 概念, 7+ memory 概念
- Louvain 被 source 日期节点污染 → 回退到连通分量
- synthesis 仅 1 个 → 综合决策页严重不足

---

## 二、design.md 现状审视 —— 哪里写得好，哪里有问题

### 2.1 写得好的部分
1. **三层架构定位**（raw → wiki → policy）清晰且与 ingest-rules.md 和 schema.md 完全一致
2. **4D 边权公式**有精确的数学表达和代码对应关系
3. **Louvain 排除 source 节点**的设计合理且已在代码中落地
4. **自进化路线图**（Episodic → Semantic → Procedural）方向正确，与用户日记 0501.md 中引用的 Experience Compression Spectrum 论文一致

### 2.2 存在的核心问题

#### 问题 A：Evidence Card 概念提出但未落地
- design.md 第 4.1 节提出了 `evidence.py` 模块和 `EvidenceCard` 数据结构
- 但实际代码中没有这个模块。当前的 `ingest_analyzer.py` 直接让 LLM 输出 `{source, entities[], concepts[], syntheses[]}` 的 JSON
- LLM 一步到位同时做了"抽取"和"分类"两件事，这导致：
  1. 提取粒度不可控 —— LLM 自行决定什么算 entity、什么算 concept
  2. 无法追溯每个 bullet 来自哪段原文
  3. 合并时只能按标题相似度合并，无法做证据级别的去重
- **建议**：是否真的需要引入 Evidence Card 中间层？需要权衡：
  - 好处：可追溯性强、合并精度高、证据可被多页面复用
  - 代价：多一个 LLM 调用步骤、增加 pipeline 复杂度、需要额外的存储结构
  - **我的判断**：对于个人知识库规模（85 篇日记），Evidence Card 的 ROI 不高。更务实的做法是优化 LLM prompt，让它输出更精细的 JSON（带 `source_section` 和 `evidence_bullets` 字段），而不是引入全新的中间表示层。

#### 问题 B：registry.json 未实现
- design.md 提出了 `registry.json` 作为 canonical 入口
- 但实际系统用的是文件系统上的 `data/wiki/**/*.md` 文件本身作为 canonical 存储
- `index.md` 充当目录索引
- **我的判断**：registry.json 是好的设计，可以作为增量 ingest 时的快速 lookup 缓存。但它不应该成为"唯一真值"，因为那会导致 registry 和实际文件不同步。更合理的做法是：
  - 每次 Rebuild 后，从实际生成的 wiki 页面反向生成 registry.json 作为**派生缓存**
  - 增量 ingest 时先查 registry.json 做快速 slug/title/alias 匹配
  - 如果 registry 和文件不一致（corruption），以文件为准重建 registry

#### 问题 C：Embedding 候选召回未实现
- design.md 4.2 提到"对 title、summary、evidence bullets 建 embedding，只召回 topK 近邻进入候选簇"
- 实际代码中 `merger.py` 只使用了 Levenshtein + Jaccard 字符串相似度
- Embedding 是更强的语义匹配手段，但需要：
  1. 本地 embedding 模型或 API 调用
  2. 向量存储/索引
  3. 增量维护逻辑
- **我的判断**：当前 85 篇日记生成约 100-200 个候选页面，Levenshtein+Jaccard 已经足够。Embedding 应该作为 P2 优化，在页面数超过 500 时再引入。

#### 问题 D：Health Gate 的"不允许静默降级死链"与现实矛盾
- design.md 4.3 说"不应再把死链静默降级成普通文本后假装健康"
- 但在实际使用中，如果 LLM 生成了引用 `[[LLM Memory Systems]]` 但没有对应页面，有两种选择：
  1. 保留双括号但标记为红色 → 对终端用户体验差，前端需要额外处理
  2. 降级为普通文本 → 信息损失小（文本内容保留），但丢失了链接信号
- **我的判断**：更合理的策略是**两阶段处理**：
  1. Rebuild 期间：保留所有 wikilinks 不做降级，输出 health report
  2. Health report 中列出所有 unresolved links，标注频率和可能匹配
  3. 用户/系统可以选择：创建新页面、添加 alias、或确认降级
  4. 前端渲染时，unresolved wikilinks 显示为带警告样式的链接（如虚线下划线）

#### 问题 E：Synthesis 生成机制缺失
- 这是最大的空白。之前 225 个页面中只有 1 个 synthesis
- design.md 5.3 只用了 3 行描述"利用 Louvain 社区生成 synthesis"
- 但没有具体的触发条件、prompt 设计、质量检查机制
- **需要补充的设计**：
  1. **触发条件**：当某个社区包含 >= 5 个概念页面且社区内边密度 >= 0.2 时，触发 synthesis 生成
  2. **输入组装**：收集社区内所有成员的 summary + evidence bullets，按时间排序
  3. **Prompt 设计**：要求 LLM 产出：核心问题是什么（Question）、各方观点综述（Evidence）、权衡与取舍（Tradeoffs）、矛盾与演进（Contradictions）、待跟进方向（Follow-ups）
  4. **质量检查**：synthesis 必须引用至少 3 个不同的 concept/entity 页面

#### 问题 F：LLM Prompt 质量不高
- `ingest_analyzer.py:279-286` 的 system prompt 只有 5 行，非常简陋
- 没有给出 JSON schema 示例
- 没有指定 entity vs concept 的判断标准
- 没有注入 `ingest-rules.md` 中定义的"什么该进/什么不该进 wiki"的规则
- **建议**：将 policy 文件内容自动注入到 LLM prompt 中，特别是 ingest-rules.md 的核心规则

---

## 三、从日记数据中发现的知识模式（指导设计优化）

### 3.1 跨日记的概念演进链

通过仔细阅读日记，我发现了明确的"概念演进链"：

**链路 1: Skill 蒸馏与进化**
- `0427.md`：SkillFoundry（论文，从 GitHub/论文中自动提取 286 个 skill）
- `0427.md`：SkillsBench（评测，skill 在不同领域效果差异巨大）
- `0427.md`：腾讯-Skill蒸馏（分 L1确定化/L2扩散化/L3启发化 三层）
- `0427.md`：Karpathy-LLM Wiki（知识编译的原始灵感来源）
- `0501.md`：Experience Compression Spectrum（统一 memory/skill/rule 为压缩层级 L0-L3）
- `0501.md`：Trace2Skill（从轨迹并行提取 skill patch）
- `0501.md`：AutoRefine（skill + subagent 两种经验形态）
- `0501.md`：ClawTrace（cost-aware 的 skill 蒸馏）
- `0522.md`：腾讯-Skill实践结论（skill 不一定更好，存在虹吸、token成本等问题）
- `0522.md`：Agent 四阶段演进（被动→工作流→自主→自进化，skill 是自进化的核心）

→ 这条链路横跨 3 篇日记（0427, 0501, 0522），涉及至少 8 个不同的论文/博客/实践
→ 当前系统会为每个论文/博客独立生成 concept/entity，但**不会**自动发现它们属于同一条技术演进链
→ **这正是 synthesis 页面应该自动生成的内容**

**链路 2: RAG 演进**
- `0410.md`：从 Naive RAG → GraphRAG → LightRAG 的完整技术选型分析
- `0427.md`：RAG vs LLM Wiki vs Graphify 的横向对比
- `0427.md`：RAG 评估全攻略
- 多篇日记提到 "context engineering" 这个上位概念

**链路 3: Agent 系统架构**
- `0522.md`：阿里云-Agent 四阶段演变（ReAct → 工作流 → 自主 → 自进化）
- `0522.md`：6 个核心 Agent 技术维度（Prompt/Planning/Memory/Tools/Workflow/Environment）
- `0511.md`：Harness Engineering 与团队知识库（5层×5类型×3级成熟度）
- `0425.md`：AI Code Review 的工程实践
- `0425.md`：Vibe Coding 方法论

### 3.2 当前提取粒度问题

问题在于：LLM 提取时把"RAG 演进"这个主题拆成了 5 个独立的 concepts（agentic-search, agentic-query-rewriting, agentic-rewrites, ...），每个只有 1 个 source。但从知识结构来看，它们应该是：
1. 一个**主概念**：`rag-evolution`（综合页，跟踪从 naive → graph → light 的技术路线）
2. 若干**子实体**：`graphrag`(entity), `lightrag`(entity), `naive-rag`(concept)
3. 一个**synthesis**：`rag-vs-wiki-vs-graphify`（技术选型对比分析）

→ **优化方向**：Prompt 中应该注入"层级抽取"的指令，要求 LLM 不仅抽取平铺的概念，还要标注概念之间的关系（上下位、演进、对比、互补）

### 3.3 日记中"待讨论"段落的特殊价值

我发现用户在日记中会写 `待讨论：` 段落，例如：
- `0501.md`: "待讨论：现有系统缺少能根据经验价值、频率、泛化性，自适应选择压缩层级的系统"
- `0501.md`: "待讨论：skill不是单一形态，应该按静态动态分？"
- `0501.md`: "待讨论：skill的组成：如何生成这种有特定作用文件"

这些是用户的**原创洞察**，是最高价值的知识种子。当前系统完全没有特殊处理它们。

→ **优化方向**：
- 在 Evidence 抽取阶段，`待讨论` 段落应被标记为 `importance: high`
- 它们应该优先进入 concept 或 synthesis 页面的 "Open Questions" 或 "Follow-ups" section
- 可以被追踪：如果后续日记中出现了回答这些问题的内容，应该自动关联

---

## 四、具体的 design.md 优化方案

### 优化 1：砍掉过度设计，保留务实方案

**砍掉**：
- `evidence.py` 模块和 EvidenceCard 中间表示层 → 对 85 篇日记规模不值得
- Embedding 候选召回 → P2 再做
- `registry.json` 作为独立真值 → 改为从实际文件派生的缓存

**保留并深化**：
- 全局语义合并（merger.py）→ 但需要优化 LLM prompt
- 链接解析 → 改为两阶段（保留 + 报告，而非静默降级）
- Louvain 排除 source → 已验证合理

### 优化 2：补充 Synthesis 自动生成的详细设计

这是当前最大的空白。需要具体设计：
- 触发条件
- 上下文组装策略
- Prompt 模板
- 质量校验规则
- 前端展示方式

### 优化 3：LLM Prompt 增强

当前 `analyze_entry()` 的 prompt 太简陋。需要：
1. 注入 `ingest-rules.md` 中的核心判断规则
2. 给出完整的 JSON output schema（带 example）
3. 要求标注 `source_section`（来自日记的哪个 section）
4. 要求标注概念间的关系类型（is-a, evolves-from, compares-to, complements）
5. 对 `待讨论` 段落做特殊标记（importance: high, type: open_question）

### 优化 4：补充增量 Ingest 的对齐策略

当前 `ingest_pipeline.py` 的 `auto_ingest` 在增量模式下：
1. 先跑 LLM 分析
2. 再跑 LLM 生成 FILE blocks
3. 然后 parse + 对齐已有页面

问题是第 2 步的 LLM 已经"自由发挥"写了完整页面，再去对齐已有页面就变成了"事后补救"。

→ **更好的流程**：
1. 先跑 LLM 分析，抽取候选 terms + 关系
2. 拿候选 terms 去匹配已有页面的 title/slug/aliases（确定性匹配，不需要 LLM）
3. 对于匹配上的：直接 patch 已有页面（追加 source、合并 evidence bullets）
4. 对于没匹配上的：检查是否满足 ingest-rules.md 中"什么该进 wiki"的条件，满足才创建新页面

### 优化 5：补充 graph.py 中的已知 bug 修复计划

来自 wiki code architecture researcher 的发现：
1. **Bug: 重复 `_type_affinity()` 函数**（line 630 vs line 861）→ 第一个定义是死代码，synthesis 相关的 affinity 值丢失
2. **Bug: `link_resolver.py` 模糊匹配过于激进** → 6 字符以上的 lookup_str 会误匹配
3. **Dead code**: `buildWikiGraph()` in App.tsx 是空函数
4. **Dead code**: `filteredCommunities` in ModeSidebar 被计算但未渲染

---

## 五、下一步行动计划

### 立即可做（不需要跑代码）
1. ✅ 把以上思考写入 think.md（本文件）
2. [ ] 根据上述分析优化 design.md
3. [ ] 把 LLM prompt 优化方案写进 design.md

### 需要跑代码验证
4. [ ] 修复 `graph.py` 中的 `_type_affinity()` 重复定义 bug
5. [ ] 优化 `ingest_analyzer.py` 的 LLM prompt
6. [ ] 跑一次全量 Rebuild，验证合并效果
7. [ ] 观察 Rebuild 后的 sources 数量分布（是否每个概念有多个 source）

### 中期优化
8. [ ] 实现 Synthesis 自动生成
9. [ ] 实现 Health Report（代替静默降级死链）
10. [ ] 优化增量 Ingest 流程（先匹配再生成）

---

## 六、关于 Evidence Card 的取舍思考

这是我反复权衡后的判断，记录下来供后续参考。

**Evidence Card 的理想**：
```yaml
id: "0522-abc123"
source_path: "data/diary/0522.md"
source_section: "工程博客"
statement: "Agent Memory 通过上下文卸载 + Mermaid 画布，最高节省 61.38% Token"
terms: ["Agent Memory", "Context Offloading", "Mermaid"]
importance: high
relation_type: supports  # 支持某个 concept
```

**好处**：
- 每个知识断言都有精确的来源定位
- 合并时可以做证据级别的去重（两个不同页面可能引用同一条 evidence）
- 可以回答"这个结论的原始出处是哪里"

**代价**：
- 需要额外的 LLM 调用来做细粒度抽取
- 85 篇日记可能产出 500-1000 条 evidence，管理复杂度上升
- 需要额外的存储结构（JSON 或 SQLite）
- 对个人知识库来说，用户很少需要"精确到某一句话的溯源"

**我的结论**：
对于当前规模，**不做独立的 Evidence Card 层**。但可以在 LLM prompt 中要求抽取时带上 `source_section` 字段，这样至少知道每个概念来自日记的哪个 section（科研/工程博客/开发经验/others）。这是 90% 的收益只花 10% 的成本。

---

## 七、关于中文 vs 英文页面标题的思考

日记内容 95% 是中文，但当前的 wiki 页面标题全部是英文 kebab-case（如 `agent-skill-distillation`）。

这是 `schema.md` 的规定：`用英文和 kebab-case`。

但问题是：
1. 用户搜索时更可能输入中文（"技能蒸馏" 而不是 "agent skill distillation"）
2. 日记中的概念名称有时就是中文的（"上下文工程"、"确定化激活"）
3. 英文标题在 wikilink 中不直观

**建议**：
- 保持 slug 为英文 kebab-case（文件系统兼容性）
- 但 title 应该用中英双语格式：`title: "经验压缩谱系 (Experience Compression Spectrum)"`
- aliases 中同时包含纯中文和纯英文版本
- 搜索和 wikilink 解析应该同时支持中英文匹配

---

*以上思考记录于 2026-05-26，待后续与用户讨论后决定具体实施优先级。*
