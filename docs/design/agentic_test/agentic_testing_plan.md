# DeepMemo Spec 驱动 Agentic Testing 方案

> 本文重写 DeepMemo 的测试方法论：从“改完代码后补测试”升级为“先写可审计 Spec，再由 Agent 基于 Spec 生成测试用例和回归资产”。

## 一句话结论

DeepMemo 的 AI-Coding 质量控制核心不是让 Agent 自由发挥，而是建立一条固定链路：

```text
需求 / Bug / 想法
  -> Feature Spec
  -> Test Spec
  -> 测试用例生成
  -> 代码实现
  -> 回归验证
  -> Spec / 测试 / skill 同步沉淀
```

其中：

- **RD 角色**：把需求和实现边界写成 Feature Spec。
- **QA 角色**：基于 Feature Spec 生成 Test Spec 和测试用例。
- **Agent 角色**：执行 Spec、补测试、改代码、跑验证，并把结果回写到文档或 skill。

这里的 RD / QA 不一定是两个人，也可以由同一个人和不同 Agent 子任务承担。关键是职责拆开：先约束输入，再约束生成过程，最后约束输出验收。

## 为什么要改

DeepMemo 已经有一套基础测试体系：

- L1 API 合约测试：`tests/api/`
- L2 稳定单元测试：`tests/unit/`
- L3 场景 E2E：`tests/e2e/scenarios.yaml` 和 `tests/e2e/test_scenarios.py`
- 浏览器烟雾测试：`app/tests/browser/`
- 统一验证入口：`uv run python scripts/verify.py --mode quick|full`
- Agent 执行规则：`.agents/skills/agentic-test/`

这套体系解决了“测试资产在哪里”和“改代码后跑什么”的问题，但还不够解决 AI-Coding 的核心风险：

- Agent 对需求理解不稳定。
- 测试用例经常来自实现细节，而不是来自业务验收标准。
- Bug 修复后容易只补局部断言，没有覆盖用户闭环。
- 多轮改动后，文档、测试、skill 三者会漂移。

因此下一步不是继续堆测试数量，而是把测试生成的输入标准化。

## 当前落地

这套方法论已经在仓库里落成了可执行资产：

- `.specify/memory/constitution.md`：项目宪法，定义 Spec-first、Test-first 和隔离验证原则。
- `openspec/config.yaml`：OpenSpec 写作规则，要求中文业务语义 + 英文结构关键词。
- `openspec/specs/fs/spec.md`：文件系统 baseline spec。
- `openspec/specs/chat/spec.md`：Chat/Citation baseline spec。
- `openspec/specs/wiki/spec.md`：Wiki baseline spec。
- `openspec/specs/agentic-testing/spec.md`：agentic testing baseline spec。
- `openspec/changes/spec-to-test-pilot/`：Spec-to-Test 试点 change，用来示范 proposal、delta spec、design、tasks 的协作方式。
- `docs/design/agentic_test/spec_to_test_prompt.md`：把 OpenSpec scenarios 转成测试矩阵的固定提示词。
- `tests/e2e/scenarios.yaml`：已经给关键场景补了 `spec` 追踪字段。
- `.agents/skills/agentic-test/`：已经更新为 OpenSpec 优先的测试工作流。

开源初始化的对照结果也已经核实：

- Spec Kit 初始化会落 `.specify/templates/`、`.specify/memory/constitution.md`、`.specify/workflows/speckit/workflow.yml`、`.specify/init-options.json`、`.specify/integration.json`，以及对应 agent 的指令文件。
- OpenSpec 初始化会落 `openspec/config.yaml`、`openspec/specs/<domain>/spec.md` 和 `openspec/changes/<change-name>/...`。
- DeepMemo 只保留适合 brownfield 的部分，不把开源项目的整个脚手架原样搬进仓库。

当前文档的用途从“计划”变成“操作手册”：

- 新需求先读 `openspec/specs/<domain>/spec.md`。
- 行为变更先创建 `openspec/changes/<change-name>/`。
- 测试用例从 requirement 和 scenario 生成。
- 结果回写到 spec、test 和 skill。

## 三层约束框架

DeepMemo 采用三层约束来管理 AI 生成代码质量。

### 1. 输入约束：Feature Spec

任何非纯文档改动，如果涉及 `src/`、`app/src/`、API、数据模型、用户流程或测试策略，都应先有 Feature Spec。

Feature Spec 的目标是让 Agent 在写代码前明确：

- 要解决的问题是什么。
- 用户可观察行为是什么。
- 数据从哪里来、到哪里去。
- API 或函数边界是什么。
- 异常、空状态、权限和路径安全如何处理。
- 哪些行为必须保持兼容。
- 哪些测试层需要覆盖。

Feature Spec 不要求长，但必须可测试。一个好的 Spec 应该能直接生成测试用例。

### 2. 生成约束：Test Spec 和测试分层

QA / Agent 不直接从代码猜测试，而是从 Feature Spec 生成 Test Spec。

Test Spec 必须回答：

- 验收标准是什么。
- 正向路径有哪些。
- 负向路径有哪些。
- 边界输入有哪些。
- 哪些行为属于 API 合约。
- 哪些行为属于用户闭环。
- 哪些逻辑可以用单元测试稳定保护。
- 哪些外部依赖必须 mock。

测试仍然遵循 DeepMemo 当前的沙漏模型：

| 层级 | 目录 | 用途 |
|---|---|---|
| L1 API contract | `tests/api/` | 保护请求/响应、状态码、持久化结果、安全边界 |
| L2 stable unit | `tests/unit/` | 保护稳定纯函数、路径处理、解析、格式化、小算法 |
| L3 scenario E2E | `tests/e2e/` | 保护用户看得见的多步骤工作流 |
| Browser smoke | `app/tests/browser/` | 保护前端关键页面能加载、切换、基础交互可用 |

默认策略：优先 L1，必要时 L3，只给稳定小函数补 L2。

### 3. 输出约束：可重复验证和回写

Agent 完成实现后，不能只报告“已完成”，必须给出可重复验证证据：

- 改了哪些 Spec。
- 生成或修改了哪些测试。
- 跑了哪些命令。
- 失败过哪些测试，如何修复。
- 是否需要更新 `.agents/skills/agentic-test/` 或 `AGENTS.md`。

代码验证命令：

```bash
uv run python scripts/verify.py --mode quick
```

涉及 E2E、浏览器流程、多模块改动或提交前验证：

```bash
uv run python scripts/verify.py --mode full
```

## Feature Spec 模板

建议把行为变化写进 OpenSpec，而不是散落在聊天记录里。最小可维护单元是：

- `openspec/changes/<change-name>/proposal.md`
- `openspec/changes/<change-name>/specs/<domain>/spec.md`
- 必要时补 `design.md` 和 `tasks.md`

如果只是临时草稿，也可以先写在 issue、任务描述或 PR 描述里，但最终都要收敛到 OpenSpec。

```markdown
# <功能名> Feature Spec

## 背景

为什么要做这个改动？当前痛点或 Bug 是什么？

## 用户目标

用户完成这个流程后，应该获得什么结果？

## 范围

本次做：

- ...

本次不做：

- ...

## 角色与入口

- 用户入口：
- API 入口：
- 前端入口：
- CLI / Skill 入口：

## 主流程

1. 用户 / Agent 做什么。
2. 系统读取什么数据。
3. 系统写入什么数据。
4. 系统返回什么结果。

## 数据与状态

- 读取：
- 写入：
- 更新：
- 删除：
- 持久化位置：

## 接口约束

### API / 函数

- 路径或函数名：
- 请求参数：
- 响应字段：
- 状态码：
- 兼容性要求：

## 异常与边界

- 空输入：
- 不存在资源：
- 重复资源：
- 路径穿越：
- LLM / 网络失败：
- 并发或重复提交：

## 验收标准

- Given ...
- When ...
- Then ...

## 测试建议

- L1 API：
- L2 Unit：
- L3 E2E：
- Browser：

## 回归风险

- ...
```

## Test Spec 模板

Feature Spec 确认后，再生成 Test Spec。建议把矩阵写进 change 的 tasks 或单独的测试计划文档，并映射到现有测试目录。

````markdown
# <功能名> Test Spec

## 覆盖目标

本测试集保护哪些用户可见行为或系统边界？

## 测试矩阵

| 用例 ID | 场景 | 层级 | 前置条件 | 操作 | 预期 | 文件 |
|---|---|---|---|---|---|---|
| TC-001 | 正常创建资源 | L1 | 空数据 | POST ... | 201/200 + 字段完整 | tests/api/... |

## 正向用例

- TC-001：

## 负向用例

- TC-101：

## 边界用例

- TC-201：

## E2E 场景

需要写入 `tests/e2e/scenarios.yaml` 的自然语言场景：

```yaml
scenarios:
  - id: example_flow
    name: "用户完成某个关键闭环"
    description: |
      ...
    tags: [feature, critical]
```

## Mock 策略

- LLM：
- 网络：
- 文件系统：
- 数据库：

## 验证命令

```bash
uv run pytest tests/api/test_xxx.py -q --tb=short
uv run python scripts/verify.py --mode quick
```
````

## DeepMemo 测试用例生成规则

Agent 生成测试用例时，必须按以下顺序决策。

### Step 1：先判断行为边界

- API 可观察：优先 `tests/api/`
- 用户多步骤闭环：先补 `tests/e2e/scenarios.yaml`，再决定是否需要 `tests/e2e/test_scenarios.py`
- 稳定纯函数：补 `tests/unit/`
- 前端页面关键流程：补 `app/tests/browser/`
- 纯文档变更：检查路径、标题、链接和模板一致性，不要求 pytest

### Step 2：再生成用例矩阵

每个 Feature Spec 至少考虑：

- 一个成功路径。
- 一个失败路径。
- 一个边界路径。
- 一个兼容性检查。
- 如果涉及用户流程，再加一个 E2E 场景。

### Step 3：测试先于实现

Bugfix 必须先固化回归测试。新功能至少先写出 API 合约或 E2E 场景，再实现。

### Step 4：失败解释优先级

如果测试失败，默认判断为实现不满足 Spec。只有当用户明确确认需求变化时，才允许修改 Spec 和断言。

## RD / QA / Agent 协作闭环

DeepMemo 可以用以下工作流组织一次改动。

### 需求进入

输入可以是：

- 用户一句自然语言需求。
- Bug 描述。
- 公众号/文章启发。
- 已有代码中的 TODO。
- 使用中发现的回归。

Agent 的第一步不是写代码，而是把输入整理成 Feature Spec。

### RD 前置：写 Feature Spec

RD 产出：

- 功能范围。
- 主流程。
- 数据流。
- API / 前端 / skill 入口。
- 异常与边界。
- 验收标准。

如果 Spec 写不清，说明需求还不能稳定交给 AI-Coding。

### QA 生成：写 Test Spec

QA 产出：

- 测试矩阵。
- L1 / L2 / L3 / Browser 分层选择。
- Mock 策略。
- 验证命令。
- 需要新增的测试文件。

这一步可以由 Agent 根据 Feature Spec 自动生成，但人要检查是否覆盖了真实验收标准。

### Agent 实现：测试驱动改代码

Agent 执行：

1. 写或更新测试。
2. 运行目标测试，确认失败或覆盖缺口。
3. 实现最小代码改动。
4. 运行目标测试。
5. 运行 quick 或 full 验证。
6. 回写结果。

### 复盘沉淀：更新 skill

当某类测试决策重复出现，或 Agent 犯过同类错误，应更新：

- `.agents/skills/agentic-test/SKILL.md`
- `.agents/skills/agentic-test/references/test-policy.md`
- `.agents/skills/agentic-test/references/examples.md`
- `AGENTS.md`

规则：测试资产留在 `tests/`，决策经验沉淀到 skill，项目级强约束沉淀到 `AGENTS.md`。

## Harness 工程基础设施

DeepMemo 当前已有的 Harness 包括：

| 能力 | 文件 |
|---|---|
| 统一验证入口 | `scripts/verify.py` |
| API 合约测试 | `tests/api/` |
| 稳定单元测试 | `tests/unit/` |
| 自然语言 E2E 场景 | `tests/e2e/scenarios.yaml` |
| 可执行 E2E 测试 | `tests/e2e/test_scenarios.py` |
| 浏览器烟雾测试 | `app/tests/browser/` |
| Agent 测试 skill | `.agents/skills/agentic-test/` |
| 仓库级 Agent 规则 | `AGENTS.md` |

下一步要补齐的是 Spec 资产目录和从 Spec 生成测试的固定流程。

建议新增：

```text
docs/specs/
├── README.md
├── template.feature.md
└── template.test.md
```

## 示例：从需求到测试

需求：

> 用户希望 Wiki ingest 后能看到 graph 更新，并且失败时能知道是哪篇文件造成的。

Feature Spec 应明确：

- 入口是 `/wiki/ingest` 还是 CLI。
- 读取哪些 Markdown。
- graph 写入在哪里。
- 失败时返回什么字段。
- 部分失败是否允许。
- 前端是否展示错误。

Test Spec 可生成：

| 用例 ID | 场景 | 层级 | 预期 |
|---|---|---|---|
| TC-001 | ingest 成功后 graph 包含新节点 | L1 | `/wiki/graph` 返回新页面节点 |
| TC-101 | Markdown frontmatter 错误 | L1 | 返回可定位的错误字段 |
| TC-201 | 空目录 ingest | L1 | 不崩溃，返回空结果或明确状态 |
| TC-301 | 用户从页面触发 ingest 后查看 graph | L3/Browser | 图谱刷新且无旧状态残留 |

然后再落到：

- `tests/api/test_wiki.py`
- `tests/e2e/scenarios.yaml`
- 必要时 `app/tests/browser/`

## 判断标准

这套方案成功的标志不是测试数量变多，而是：

- 每次功能改动都有可追溯 Spec。
- 测试用例能从 Spec 解释，而不是从实现细节倒推。
- Bug 修复会留下回归测试。
- Agent 的最终报告包含验证证据。
- 重复出现的测试经验会沉淀到 skill。
- 新 Agent 进来能按同一套流程稳定交付。
