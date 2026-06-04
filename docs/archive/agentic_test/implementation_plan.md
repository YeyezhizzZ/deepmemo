# DeepMemo Spec Kit + OpenSpec 落地计划

> 目标：用 Spec Kit 建立项目级工程宪法，用 OpenSpec 维护 DeepMemo 的当前行为规格和后续增量变更，并把 spec 场景稳定映射到仓库里的自动化测试。

## 当前判断

DeepMemo 已经是 brownfield 项目，不适合把 Spec Kit 当作唯一长期 spec 系统。

- Spec Kit 更适合初始化项目原则、工作流纪律、spec/plan/tasks 思维方式。
- OpenSpec 更适合维护已有项目的 canonical specs 和每次变更的 delta specs。
- DeepMemo 的测试资产已经存在，下一步应把“测试从哪里来”标准化，而不是重建测试框架。

因此采用：

```text
Spec Kit constitution
  -> OpenSpec baseline specs
  -> OpenSpec change deltas
  -> Test Spec matrix
  -> L1/L2/L3/Browser tests
  -> verify quick/full
  -> archive/sync specs
```

## 开源初始化对照

我已经在临时目录里对照了 Spec Kit 和 OpenSpec 的初始化结果，实际会落出的核心文件是：

Spec Kit 侧：

- `.specify/templates/constitution-template.md`
- `.specify/templates/spec-template.md`
- `.specify/templates/plan-template.md`
- `.specify/templates/tasks-template.md`
- `.specify/templates/checklist-template.md`
- `.specify/workflows/speckit/workflow.yml`
- `.specify/memory/constitution.md`
- `.specify/init-options.json`
- `.specify/integration.json`
- 视 integration 而定的 agent 指令文件，例如 `.github/copilot-instructions.md`

OpenSpec 侧：

- `openspec/config.yaml`
- `openspec/specs/<domain>/spec.md`
- `openspec/changes/<change-name>/proposal.md`
- `openspec/changes/<change-name>/specs/<domain>/spec.md`
- `openspec/changes/<change-name>/design.md`
- `openspec/changes/<change-name>/tasks.md`

对 DeepMemo 的结论是：

- 必须保留的是 `.specify/memory/constitution.md`、`openspec/config.yaml`、`openspec/specs/` 和 `openspec/changes/`
- 可选保留的是 `.specify/templates/` 和 `.specify/workflows/`，如果你想继续做本地 custom workflow
- 不建议把 OpenSpec 的 change 结构搬进 `docx/`，`docx/` 只保留方法论、模板和执行说明

## 目标结构

Spec Kit 只保留治理资产：

```text
.specify/
└── memory/
    └── constitution.md
```

OpenSpec 作为长期行为规格系统：

```text
openspec/
├── config.yaml
├── specs/
│   ├── fs/spec.md
│   ├── chat/spec.md
│   ├── wiki/spec.md
│   └── agentic-testing/spec.md
└── changes/
    └── <change-name>/
        ├── proposal.md
        ├── design.md
        ├── tasks.md
        └── specs/<domain>/spec.md
```

测试资产仍保留当前结构：

```text
tests/api/
tests/unit/
tests/e2e/
app/tests/browser/
scripts/verify.py
```

## 默认工作流

每次涉及应用行为的改动按以下顺序执行：

1. 读 `.specify/memory/constitution.md`。
2. 读相关 `openspec/specs/<domain>/spec.md`。
3. 创建或更新 `openspec/changes/<change-name>/`。
4. 写 `proposal.md` 和 delta spec。
5. 从 delta spec scenarios 生成测试矩阵。
6. 按测试矩阵先补 L1/L2/L3/Browser 测试。
7. 实现代码。
8. 跑目标测试。
9. 跑 `uv run python scripts/verify.py --mode quick`。
10. 对 E2E、浏览器或多模块改动跑 `uv run python scripts/verify.py --mode full`。
11. archive/sync OpenSpec change，并回写 skill 经验。

## 已完成

- [x] 创建 `.specify/memory/constitution.md`，记录 DeepMemo 的 Spec-first、Test-first、本地 Markdown 真值和隔离验证原则。
- [x] 创建 `openspec/config.yaml`，约束 OpenSpec 写作语言、scenario、测试映射和验证命令。
- [x] 创建 `openspec/specs/fs/spec.md`，覆盖文件创建、读取、写入、移动、tree、上传、路径安全。
- [x] 创建 `openspec/specs/chat/spec.md`，覆盖会话、消息、citation、file reference、stream、tool 校验。
- [x] 创建 `openspec/specs/wiki/spec.md`，覆盖 wiki page、tree、graph、health、policy、ingest、rebuild。
- [x] 创建 `openspec/specs/agentic-testing/spec.md`，覆盖 Spec Kit + OpenSpec + 测试分层工作流。
- [x] 创建 `openspec/changes/spec-to-test-pilot/`，作为 Spec-to-Test 试点 change 样例。
- [x] 创建 `docx/agentic_test/spec_to_test_prompt.md`，作为从 OpenSpec scenarios 生成测试矩阵的固定提示词。
- [x] 更新 `tests/e2e/scenarios.yaml`，为关键场景增加 `spec` 追踪字段。
- [x] 更新 `.agents/skills/agentic-test/` 与 `AGENTS.md`，把 OpenSpec 优先流程写入仓库规则。
- [x] 在临时目录里验证 Spec Kit / OpenSpec 的初始化文件结构，并把结果收敛回文档。

## TODO

### Phase 1：完成 baseline 盘点

- [ ] 从 FastAPI app 导出 OpenAPI schema，生成当前后端 API 清单。
- [ ] 盘点 `app/src/api.ts` 和主要组件，列出前端用户入口与 API 调用关系。
- [ ] 盘点 `tests/api/`、`tests/unit/`、`tests/e2e/`、`app/tests/browser/`，把已有测试映射到 OpenSpec requirements。
- [ ] 将盘点结果写入 `openspec/changes/baseline-inventory/`，作为补全后续 domain specs 的原始材料。

### Phase 2：补齐剩余 domain specs

- [ ] `openspec/specs/sessions/spec.md`：session 创建、列表、读取、删除、消息级联。
- [ ] `openspec/specs/diary/spec.md`：auto-draft 输入目录、输出目录、无输入、生成草稿。
- [ ] `openspec/specs/pulse/spec.md`：today 聚合、空数据行为、响应字段。
- [ ] `openspec/specs/frontend/spec.md`：文件树、编辑器、Wiki 模式、Chat/Citation 展示、错误提示。

### Phase 3：建立第一个 OpenSpec change 样例

- [x] 创建 `openspec/changes/spec-to-test-pilot/proposal.md`。
- [x] 创建 `openspec/changes/spec-to-test-pilot/specs/agentic-testing/spec.md`。
- [x] 创建 `openspec/changes/spec-to-test-pilot/design.md`。
- [x] 创建 `openspec/changes/spec-to-test-pilot/tasks.md`。
- [x] 用这个 change 演示 proposal、delta spec、design、tasks 如何映射到测试矩阵。

### Phase 4：从 OpenSpec 生成测试矩阵

- [ ] 为 `openspec/specs/fs/spec.md` 生成测试矩阵，确认已覆盖与缺口。
- [ ] 为 `openspec/specs/chat/spec.md` 生成测试矩阵，确认已覆盖与缺口。
- [ ] 为 `openspec/specs/wiki/spec.md` 生成测试矩阵，确认已覆盖与缺口。
- [x] 将真实用户闭环记录到 `tests/e2e/scenarios.yaml`，并补充 OpenSpec `spec` 追踪字段。
- [ ] 只有前端关键路径才补 `app/tests/browser/`，避免浏览器测试过重。

### Phase 5：同步 Agent 工作流

- [x] 更新 `.agents/skills/agentic-test/SKILL.md`，把“先找或写 OpenSpec”放到默认工作流第一步。
- [x] 更新 `.agents/skills/agentic-test/references/test-policy.md`，加入 OpenSpec-to-Test 分层规则。
- [x] 更新 `.agents/skills/agentic-test/references/examples.md`，加入从 OpenSpec 生成测试的例子。
- [x] 更新 `AGENTS.md`，把 Spec Kit + OpenSpec 作为应用代码变更的默认要求。
- [x] 更新 `tests/e2e/scenarios.yaml`，给场景补充 `spec` 追踪字段。
- [x] 新增 `docx/agentic_test/spec_to_test_prompt.md` 作为固定测试矩阵生成入口。

### Phase 6：跑一个端到端试点

- [ ] 选择一个小需求，例如 `/api/pulse/today` 空数据行为。
- [ ] 创建 `openspec/changes/pulse-empty-state/`。
- [ ] 写 proposal 和 delta spec。
- [ ] 从 scenario 生成 Test Spec。
- [ ] 添加或更新一个 L1 API 测试。
- [ ] 实现必要代码或确认当前行为已满足 spec。
- [ ] 运行目标测试。
- [ ] 运行 `uv run python scripts/verify.py --mode quick`。
- [ ] 把试点中暴露的规则补回 `agentic-test` skill。

## 当前使用方式

现在这份计划不再是“准备开工”的蓝图，而是“继续扩展”的操作记录。

- 先看“已完成”，确认仓库当前已经具备哪些 spec 资产。
- 再看 TODO，按 domain 补齐剩余 specs。
- 新增行为时优先走 `openspec/changes/<change-name>/`。
- 新增测试时从 `openspec/specs/<domain>/spec.md` 的 scenarios 生成测试矩阵。
- 任何试点只要会影响产品行为，就要同步更新 spec、test 和 skill。

## 工具使用原则

- Spec Kit 负责项目治理，不负责长期维护行为真值。
- OpenSpec 负责 canonical specs 和每次 change delta。
- 工具负责抽取事实：API schema、调用关系、测试覆盖、文件结构。
- Agent 负责整理草稿：把工具输出转成 requirements、scenarios 和测试矩阵。
- 人负责确认意图：哪些行为是产品承诺，哪些只是当前实现细节。
- 测试负责锁定承诺：只有确认过的 spec 才应该固化成回归测试。

## 验证命令

文档、spec、skill 修改后：

```bash
find .specify openspec docx/agentic_test .agents/skills/agentic-test -maxdepth 4 -type f | sort
git diff --check -- .specify openspec docx/agentic_test .agents/skills/agentic-test AGENTS.md tests/e2e/scenarios.yaml
```

应用代码或测试修改后：

```bash
uv run python scripts/verify.py --mode quick
```

涉及 E2E、浏览器、多模块或提交前：

```bash
uv run python scripts/verify.py --mode full
```

## 交付标准

本计划完成后，DeepMemo 应满足：

- 有 Spec Kit constitution。
- 有 OpenSpec canonical baseline specs。
- 有 OpenSpec change 示例。
- agentic-test skill 纳入 OpenSpec-to-Test 流程。
- E2E 场景能追溯到 OpenSpec spec。
- 至少一个真实改动跑通过完整闭环。
- 最终交付报告能列出 specs、tests、commands 和残余风险。
